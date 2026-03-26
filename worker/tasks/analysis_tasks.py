"""
메인 Celery 태스크: 드론 이미지 분석 파이프라인

파이프라인 순서:
1. 전처리 (프레임 추출, 리사이즈)
2. YOLOv8 배치 추론
3. 후처리 (정량화, 어노테이션)
4. DB 저장
5. 균열 추적 매칭 태스크 실행
"""
import os
import structlog
from celery import Task
from tasks.celery_app import app

log = structlog.get_logger()


class BaseAnalysisTask(Task):
    """모델 가중치를 워커 시작 시 한 번만 로드"""
    _model = None

    @property
    def model(self):
        if self._model is None:
            from ultralytics import YOLO
            weights_path = os.getenv("MODEL_WEIGHTS_PATH", "/app/weights/yolov8n-crack.pt")
            self._model = YOLO(weights_path)
            log.info("model_loaded", path=weights_path)
        return self._model


@app.task(
    bind=True,
    base=BaseAnalysisTask,
    name="tasks.analysis_tasks.run_inspection_analysis",
    max_retries=3,
    default_retry_delay=60,
)
def run_inspection_analysis(self, inspection_id: str, job_id: str):
    """
    점검 분석 메인 태스크

    Args:
        inspection_id: Inspection UUID
        job_id: AnalysisJob UUID
    """
    log.info("analysis_started", inspection_id=inspection_id, job_id=job_id)

    try:
        # TODO Phase 1: 실제 구현
        # 1. DB에서 inspection_files 조회
        # 2. S3에서 파일 다운로드
        # 3. 전처리 (preprocessing.py)
        # 4. 배치 추론 (inference.py)
        # 5. 정량화 (quantification.py)
        # 6. 결과 저장 + 어노테이션 이미지 업로드
        # 7. DB 업데이트 (job.status = completed)
        # 8. 균열 추적 태스크 실행
        #    match_defect_tracks.delay(inspection_id)

        log.info("analysis_completed", inspection_id=inspection_id, job_id=job_id)
        return {"status": "completed", "job_id": job_id}

    except Exception as exc:
        log.error("analysis_failed", inspection_id=inspection_id, error=str(exc))
        raise self.retry(exc=exc)


@app.task(name="tasks.analysis_tasks.match_defect_tracks")
def match_defect_tracks(inspection_id: str):
    """
    이전 점검과 균열 매칭 → defect_tracks / defect_track_entries 업데이트

    매칭 전략:
    1. GPS 기반: 동일 촬영 위치(±2m) + bbox IoU > 0.3 → 동일 균열
    2. GPS 없는 경우: ORB 특징점 매칭 + 호모그래피
    3. 신뢰도 < 0.7 → status = 'needs_review'
    """
    log.info("track_matching_started", inspection_id=inspection_id)
    # TODO Phase 2: 구현
    log.info("track_matching_completed", inspection_id=inspection_id)


@app.task(name="tasks.analysis_tasks.ping")
def ping():
    """워커 연결 확인용"""
    return "pong"
