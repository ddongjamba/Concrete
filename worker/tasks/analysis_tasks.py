"""
메인 Celery 태스크: 드론 이미지 분석 파이프라인

순서:
1. DB에서 inspection_files 조회
2. S3에서 파일 다운로드 + 전처리 (프레임 추출)
3. YOLOv8 배치 추론
4. 정량화 + 어노테이션 이미지 생성
5. analysis_results DB 저장
6. inspection/job 상태 완료 처리
7. 균열 추적 매칭 태스크 enqueue
"""
import os
import tempfile
import uuid
from datetime import datetime, timezone

import structlog
from celery import Task
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from tasks.celery_app import app
from tasks.preprocessing import prepare_images, CameraParams as _CP
from tasks.inference import load_model, run_inference
from tasks.postprocessing import process_image
from tasks.quantification import CameraParams

log = structlog.get_logger()

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://facade:facade_secret@postgres:5432/facade_db",
).replace("+asyncpg", "+psycopg2")  # Celery 워커는 동기 드라이버 사용


def get_sync_engine():
    return create_engine(DATABASE_URL, pool_pre_ping=True)


class BaseAnalysisTask(Task):
    """모델 가중치를 워커 프로세스당 한 번만 로드"""
    _model = None

    @property
    def model(self):
        if self._model is None:
            self._model = load_model()
        return self._model


@app.task(
    bind=True,
    base=BaseAnalysisTask,
    name="tasks.analysis_tasks.run_inspection_analysis",
    max_retries=3,
    default_retry_delay=60,
)
def run_inspection_analysis(self, inspection_id: str, job_id: str):
    log.info("analysis_started", inspection_id=inspection_id, job_id=job_id)
    engine = get_sync_engine()

    try:
        with Session(engine) as db:
            # 1. job 상태 → running
            db.execute(text("""
                UPDATE analysis_jobs
                SET status='running', started_at=:now, updated_at=:now
                WHERE id=:job_id
            """), {"job_id": job_id, "now": datetime.now(timezone.utc)})
            db.execute(text("""
                UPDATE inspections SET status='processing', updated_at=:now WHERE id=:id
            """), {"id": inspection_id, "now": datetime.now(timezone.utc)})
            db.commit()

            # 2. inspection_files 조회
            rows = db.execute(text("""
                SELECT id, storage_key, file_type, altitude_m,
                       focal_length_mm, sensor_width_mm, image_width_px,
                       tenant_id
                FROM inspection_files
                WHERE inspection_id = :id
            """), {"id": inspection_id}).fetchall()

            if not rows:
                raise ValueError("분석할 파일이 없습니다")

            tenant_id = str(rows[0].tenant_id)
            files = [dict(r._mapping) for r in rows]

        # 3. 로컬 다운로드 + 전처리
        with tempfile.TemporaryDirectory() as work_dir:
            items = prepare_images(files, work_dir)
            total = len(items)
            log.info("preprocessing_done", count=total)

            # 4. 배치 추론
            image_paths = [it.local_path for it in items]
            all_detections = run_inference(self.model, image_paths)

            all_results = []
            for idx, (item, detections) in enumerate(zip(items, all_detections)):
                # 5. 정량화 + 어노테이션
                cam = CameraParams(
                    altitude_m=item.altitude_m or 0,
                    focal_length_mm=item.focal_length_mm or 0,
                    sensor_width_mm=item.sensor_width_mm or 0,
                    image_width_px=item.image_width_px or 0,
                ) if any([item.altitude_m, item.focal_length_mm]) else None

                processed = process_image(
                    item.local_path, item.file_id,
                    detections, tenant_id, inspection_id, cam,
                )
                all_results.extend(processed)

                # 진행률 업데이트
                pct = int((idx + 1) / total * 90)
                with Session(engine) as db:
                    db.execute(text("""
                        UPDATE analysis_jobs SET progress_pct=:pct, updated_at=:now WHERE id=:id
                    """), {"pct": pct, "id": job_id, "now": datetime.now(timezone.utc)})
                    db.commit()

        # 6. analysis_results bulk insert
        with Session(engine) as db:
            # 파일 ID → inspection_file_id 매핑
            file_id_map = {f["id"]: f["id"] for f in files}

            for r in all_results:
                raw_file_id = r.file_id.split("_")[0]  # 비디오 프레임 "_숫자" 제거
                db.execute(text("""
                    INSERT INTO analysis_results (
                        id, job_id, inspection_file_id, tenant_id,
                        defect_type, severity_score, severity, confidence,
                        bounding_box, crack_width_mm, crack_length_mm,
                        crack_area_cm2, affected_area_pct, annotated_image_key,
                        created_at, updated_at
                    ) VALUES (
                        :id, :job_id, :file_id, :tenant_id,
                        :defect_type, :score, :severity, :conf,
                        :bbox, :width, :length, :area, :area_pct, :img_key,
                        :now, :now
                    )
                """), {
                    "id": str(uuid.uuid4()),
                    "job_id": job_id,
                    "file_id": raw_file_id,
                    "tenant_id": tenant_id,
                    "defect_type": r.detection.defect_type,
                    "score": r.severity_score,
                    "severity": r.severity,
                    "conf": round(r.detection.confidence, 4),
                    "bbox": f'{{"x":{r.detection.bbox_x:.4f},"y":{r.detection.bbox_y:.4f},"w":{r.detection.bbox_w:.4f},"h":{r.detection.bbox_h:.4f}}}',
                    "width": r.crack_width_mm,
                    "length": r.crack_length_mm,
                    "area": r.crack_area_cm2,
                    "area_pct": r.affected_area_pct,
                    "img_key": r.annotated_image_key,
                    "now": datetime.now(timezone.utc),
                })

            # 7. 완료 처리
            db.execute(text("""
                UPDATE analysis_jobs
                SET status='completed', progress_pct=100, completed_at=:now, updated_at=:now
                WHERE id=:id
            """), {"id": job_id, "now": datetime.now(timezone.utc)})
            db.execute(text("""
                UPDATE inspections SET status='completed', updated_at=:now WHERE id=:id
            """), {"id": inspection_id, "now": datetime.now(timezone.utc)})
            db.commit()

        log.info("analysis_completed", job_id=job_id, result_count=len(all_results))

        # 8. 균열 추적 매칭 (비동기)
        match_defect_tracks.delay(inspection_id)

        return {"status": "completed", "job_id": job_id, "result_count": len(all_results)}

    except Exception as exc:
        log.error("analysis_failed", job_id=job_id, error=str(exc))
        with Session(engine) as db:
            db.execute(text("""
                UPDATE analysis_jobs
                SET status='failed', error_message=:err, updated_at=:now
                WHERE id=:id
            """), {"id": job_id, "err": str(exc)[:500], "now": datetime.now(timezone.utc)})
            db.execute(text("""
                UPDATE inspections SET status='failed', updated_at=:now WHERE id=:id
            """), {"id": inspection_id, "now": datetime.now(timezone.utc)})
            db.commit()
        raise self.retry(exc=exc)


@app.task(name="tasks.analysis_tasks.match_defect_tracks")
def match_defect_tracks(inspection_id: str):
    """균열 추적 매칭 → tracking_tasks로 위임"""
    from tasks.tracking_tasks import match_defect_tracks as _match
    _match.delay(inspection_id)


@app.task(name="tasks.analysis_tasks.ping")
def ping():
    return "pong"
