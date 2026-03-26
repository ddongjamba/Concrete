"""
Phase 2: 균열 시계열 추적 매칭 태스크

전략:
  1. GPS 있는 경우: 동일 이미지 좌표(±0.000025도 ≈ 2m) + bbox IoU > 0.3 → 동일 균열
  2. GPS 없는 경우: ORB 특징점 → 호모그래피 → 변환된 bbox 위치 비교
  3. 매칭 신뢰도 < 0.7 → track.status='needs_review' (수동 확인 대상)

완료 후:
  - 악화 판단: score_delta > 15 → track.status = 'worsening'
  - 개선 판단: score_delta < -10 → track.status = 'stable'
"""
import json
import math
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import structlog
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from tasks.celery_app import app

log = structlog.get_logger()

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://facade:facade_secret@postgres:5432/facade_db",
).replace("+asyncpg", "+psycopg2")


def get_engine():
    return create_engine(DATABASE_URL, pool_pre_ping=True)


# ---------------------------------------------------------------------------
# 데이터 구조
# ---------------------------------------------------------------------------

@dataclass
class BBox:
    """정규화된 bounding box (0-1)"""
    x: float
    y: float
    w: float
    h: float


@dataclass
class ResultRow:
    result_id: str
    file_id: str
    defect_type: str
    severity_score: int
    crack_width_mm: Optional[float]
    crack_length_mm: Optional[float]
    crack_area_cm2: Optional[float]
    bbox: BBox
    annotated_image_key: Optional[str]
    gps_lat: Optional[float]
    gps_lon: Optional[float]
    confidence: float


@dataclass
class TrackRow:
    track_id: str
    last_entry_id: str
    last_result_id: str
    last_file_id: str
    last_severity_score: int
    last_width_mm: Optional[float]
    last_length_mm: Optional[float]
    last_bbox: BBox
    last_gps_lat: Optional[float]
    last_gps_lon: Optional[float]
    matched: bool = False


# ---------------------------------------------------------------------------
# 기하 유틸
# ---------------------------------------------------------------------------

def bbox_iou(a: BBox, b: BBox) -> float:
    """두 정규화 bbox의 IoU 계산"""
    ax1, ay1 = a.x, a.y
    ax2, ay2 = a.x + a.w, a.y + a.h
    bx1, by1 = b.x, b.y
    bx2, by2 = b.x + b.w, b.y + b.h

    ix1 = max(ax1, bx1)
    iy1 = max(ay1, by1)
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)

    if ix2 <= ix1 or iy2 <= iy1:
        return 0.0

    inter = (ix2 - ix1) * (iy2 - iy1)
    union = a.w * a.h + b.w * b.h - inter
    return inter / union if union > 0 else 0.0


def gps_distance_deg(lat1, lon1, lat2, lon2) -> float:
    """위도/경도 차이를 미터로 환산 (소규모 거리용 평면 근사)"""
    lat_m = (lat2 - lat1) * 111_320
    lon_m = (lon2 - lon1) * 111_320 * math.cos(math.radians((lat1 + lat2) / 2))
    return math.sqrt(lat_m ** 2 + lon_m ** 2)


GPS_THRESHOLD_M = 3.0    # GPS 동일 촬영 위치 판단 임계값 (미터)
IOU_THRESHOLD = 0.25     # bbox 중첩 임계값
GPS_MATCH_CONFIDENCE = 0.85
IOU_ONLY_CONFIDENCE = 0.60


# ---------------------------------------------------------------------------
# ORB 기반 호모그래피 매칭 (GPS 없는 경우)
# ---------------------------------------------------------------------------

def _orb_transform_bbox(src_image_key: str, dst_image_key: str, bbox: BBox) -> Optional[BBox]:
    """
    ORB 특징점으로 두 이미지 간 호모그래피 추정 → bbox 변환.
    MinIO/S3에서 이미지를 직접 다운로드해 OpenCV로 처리.
    실패 시 None 반환.
    """
    try:
        import cv2
        import numpy as np
        import boto3

        s3 = boto3.client(
            "s3",
            endpoint_url=os.getenv("S3_ENDPOINT_URL", "http://minio:9000"),
            aws_access_key_id=os.getenv("S3_ACCESS_KEY", "minioadmin"),
            aws_secret_access_key=os.getenv("S3_SECRET_KEY", "minioadmin"),
        )
        bucket = os.getenv("S3_BUCKET", "facade-inspect")

        def _load(key):
            resp = s3.get_object(Bucket=bucket, Key=key)
            buf = np.frombuffer(resp["Body"].read(), dtype=np.uint8)
            return cv2.imdecode(buf, cv2.IMREAD_GRAYSCALE)

        img_src = _load(src_image_key)
        img_dst = _load(dst_image_key)
        if img_src is None or img_dst is None:
            return None

        orb = cv2.ORB_create(nfeatures=1000)
        kp1, des1 = orb.detectAndCompute(img_src, None)
        kp2, des2 = orb.detectAndCompute(img_dst, None)
        if des1 is None or des2 is None or len(kp1) < 10 or len(kp2) < 10:
            return None

        bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
        matches = bf.match(des1, des2)
        matches = sorted(matches, key=lambda m: m.distance)[:50]
        if len(matches) < 10:
            return None

        pts_src = np.float32([kp1[m.queryIdx].pt for m in matches]).reshape(-1, 1, 2)
        pts_dst = np.float32([kp2[m.trainIdx].pt for m in matches]).reshape(-1, 1, 2)
        H, mask = cv2.findHomography(pts_src, pts_dst, cv2.RANSAC, 5.0)
        if H is None or mask.sum() < 8:
            return None

        h_src, w_src = img_src.shape[:2]
        h_dst, w_dst = img_dst.shape[:2]

        # bbox 중심점 변환
        cx = (bbox.x + bbox.w / 2) * w_src
        cy = (bbox.y + bbox.h / 2) * h_src
        pt = np.float32([[[cx, cy]]])
        pt_dst = cv2.perspectiveTransform(pt, H)[0][0]

        new_cx = pt_dst[0] / w_dst
        new_cy = pt_dst[1] / h_dst
        new_w = bbox.w * (w_src / w_dst)
        new_h = bbox.h * (h_src / h_dst)

        return BBox(
            x=max(0.0, new_cx - new_w / 2),
            y=max(0.0, new_cy - new_h / 2),
            w=new_w,
            h=new_h,
        )
    except Exception as e:
        log.warning("orb_transform_failed", error=str(e))
        return None


# ---------------------------------------------------------------------------
# 매칭 로직
# ---------------------------------------------------------------------------

def _parse_bbox(raw) -> BBox:
    if isinstance(raw, str):
        raw = json.loads(raw)
    return BBox(x=float(raw["x"]), y=float(raw["y"]), w=float(raw["w"]), h=float(raw["h"]))


def match_results_to_tracks(
    new_results: list[ResultRow],
    existing_tracks: list[TrackRow],
    db: Session,
    inspection_date,
    tenant_id: str,
    project_id: str,
) -> list[dict]:
    """
    새 분석 결과를 기존 균열 트랙에 매칭하거나 신규 트랙 생성.
    Returns: list of track_entry dicts to insert.
    """
    entries_to_insert = []
    now = datetime.now(timezone.utc)

    for result in new_results:
        best_track: Optional[TrackRow] = None
        best_confidence = 0.0
        best_iou = 0.0

        for track in existing_tracks:
            if track.matched:
                continue  # 이미 매칭된 트랙은 재사용 안 함

            # GPS 기반 매칭
            if (result.gps_lat and result.gps_lon
                    and track.last_gps_lat and track.last_gps_lon):
                dist_m = gps_distance_deg(
                    result.gps_lat, result.gps_lon,
                    track.last_gps_lat, track.last_gps_lon,
                )
                if dist_m <= GPS_THRESHOLD_M:
                    iou = bbox_iou(result.bbox, track.last_bbox)
                    if iou >= IOU_THRESHOLD:
                        confidence = GPS_MATCH_CONFIDENCE * (1 - dist_m / GPS_THRESHOLD_M * 0.3) * iou
                        if confidence > best_confidence:
                            best_confidence = confidence
                            best_track = track
                            best_iou = iou
                    continue  # GPS 있으면 ORB 시도 안 함

            # GPS 없는 경우 IoU만으로 시도 (같은 이미지 내 비교)
            if result.file_id == track.last_file_id:
                iou = bbox_iou(result.bbox, track.last_bbox)
                if iou >= IOU_THRESHOLD:
                    confidence = IOU_ONLY_CONFIDENCE * iou
                    if confidence > best_confidence:
                        best_confidence = confidence
                        best_track = track
                        best_iou = iou

        if best_track:
            # 기존 트랙에 엔트리 추가
            best_track.matched = True

            prev_width = best_track.last_width_mm
            prev_length = best_track.last_length_mm
            prev_score = best_track.last_severity_score

            change = {
                "score_delta": result.severity_score - prev_score,
                "width_delta": round(result.crack_width_mm - prev_width, 3)
                               if (result.crack_width_mm and prev_width) else None,
                "length_delta": round(result.crack_length_mm - prev_length, 3)
                                if (result.crack_length_mm and prev_length) else None,
                "match_confidence": round(best_confidence, 3),
                "iou": round(best_iou, 3),
            }

            entry_id = str(uuid.uuid4())
            entries_to_insert.append({
                "id": entry_id,
                "track_id": best_track.track_id,
                "analysis_result_id": result.result_id,
                "inspection_id": None,  # 아래에서 채움
                "inspection_date": inspection_date,
                "severity_score": result.severity_score,
                "crack_width_mm": result.crack_width_mm,
                "crack_length_mm": result.crack_length_mm,
                "crack_area_cm2": result.crack_area_cm2,
                "change_vs_prev": json.dumps(change),
                "annotated_image_key": result.annotated_image_key,
                "now": now,
                "track_status_update": _compute_track_status(change["score_delta"], best_confidence),
                "track_id_for_status": best_track.track_id,
            })
        else:
            # 신규 트랙 생성
            track_id = str(uuid.uuid4())
            db.execute(text("""
                INSERT INTO defect_tracks (
                    id, project_id, tenant_id, first_seen_at,
                    location_zone, representative_image_key, status,
                    created_at, updated_at
                ) VALUES (
                    :id, :project_id, :tenant_id, :first_seen_at,
                    NULL, :rep_image, 'monitoring',
                    :now, :now
                )
            """), {
                "id": track_id,
                "project_id": project_id,
                "tenant_id": tenant_id,
                "first_seen_at": inspection_date,
                "rep_image": result.annotated_image_key,
                "now": now,
            })

            entry_id = str(uuid.uuid4())
            entries_to_insert.append({
                "id": entry_id,
                "track_id": track_id,
                "analysis_result_id": result.result_id,
                "inspection_id": None,
                "inspection_date": inspection_date,
                "severity_score": result.severity_score,
                "crack_width_mm": result.crack_width_mm,
                "crack_length_mm": result.crack_length_mm,
                "crack_area_cm2": result.crack_area_cm2,
                "change_vs_prev": None,
                "annotated_image_key": result.annotated_image_key,
                "now": now,
                "track_status_update": None,
                "track_id_for_status": track_id,
            })

    return entries_to_insert


def _compute_track_status(score_delta: int, confidence: float) -> Optional[str]:
    if confidence < 0.7:
        return "needs_review"
    if score_delta >= 15:
        return "worsening"
    if score_delta <= -10:
        return "stable"
    return None  # 변경 없음 → 현 상태 유지


# ---------------------------------------------------------------------------
# Celery 태스크
# ---------------------------------------------------------------------------

@app.task(
    name="tasks.tracking_tasks.match_defect_tracks",
    max_retries=2,
    default_retry_delay=30,
)
def match_defect_tracks(inspection_id: str):
    log.info("track_matching_started", inspection_id=inspection_id)
    engine = get_engine()

    with Session(engine) as db:
        # 1. 현재 점검 정보
        insp = db.execute(text("""
            SELECT project_id, tenant_id, inspection_date
            FROM inspections WHERE id = :id
        """), {"id": inspection_id}).fetchone()

        if not insp:
            log.error("inspection_not_found", inspection_id=inspection_id)
            return

        project_id = str(insp.project_id)
        tenant_id = str(insp.tenant_id)
        inspection_date = insp.inspection_date

        # 2. 이번 점검의 analysis_results + GPS 조인
        raw_results = db.execute(text("""
            SELECT
                ar.id AS result_id,
                ar.inspection_file_id AS file_id,
                ar.defect_type,
                ar.severity_score,
                ar.crack_width_mm,
                ar.crack_length_mm,
                ar.crack_area_cm2,
                ar.bounding_box,
                ar.annotated_image_key,
                ar.confidence,
                inf.gps_lat,
                inf.gps_lon
            FROM analysis_results ar
            JOIN analysis_jobs aj ON ar.job_id = aj.id
            JOIN inspection_files inf ON ar.inspection_file_id = inf.id
            WHERE aj.inspection_id = :inspection_id
              AND aj.status = 'completed'
        """), {"inspection_id": inspection_id}).fetchall()

        if not raw_results:
            log.info("no_results_to_match", inspection_id=inspection_id)
            return

        new_results = [
            ResultRow(
                result_id=str(r.result_id),
                file_id=str(r.file_id),
                defect_type=r.defect_type,
                severity_score=r.severity_score,
                crack_width_mm=float(r.crack_width_mm) if r.crack_width_mm else None,
                crack_length_mm=float(r.crack_length_mm) if r.crack_length_mm else None,
                crack_area_cm2=float(r.crack_area_cm2) if r.crack_area_cm2 else None,
                bbox=_parse_bbox(r.bounding_box),
                annotated_image_key=r.annotated_image_key,
                gps_lat=float(r.gps_lat) if r.gps_lat else None,
                gps_lon=float(r.gps_lon) if r.gps_lon else None,
                confidence=float(r.confidence),
            )
            for r in raw_results
        ]

        # 3. 같은 project의 기존 defect_track_entries (가장 최신 엔트리만)
        raw_tracks = db.execute(text("""
            SELECT DISTINCT ON (dt.id)
                dt.id AS track_id,
                dte.id AS entry_id,
                dte.analysis_result_id AS last_result_id,
                ar.inspection_file_id AS last_file_id,
                dte.severity_score AS last_score,
                dte.crack_width_mm AS last_width,
                dte.crack_length_mm AS last_length,
                ar.bounding_box AS last_bbox,
                inf.gps_lat AS last_lat,
                inf.gps_lon AS last_lon
            FROM defect_tracks dt
            JOIN defect_track_entries dte ON dte.track_id = dt.id
            JOIN analysis_results ar ON ar.id = dte.analysis_result_id
            JOIN inspection_files inf ON inf.id = ar.inspection_file_id
            WHERE dt.project_id = :project_id
              AND dt.status != 'repaired'
            ORDER BY dt.id, dte.inspection_date DESC
        """), {"project_id": project_id}).fetchall()

        existing_tracks = [
            TrackRow(
                track_id=str(r.track_id),
                last_entry_id=str(r.entry_id),
                last_result_id=str(r.last_result_id),
                last_file_id=str(r.last_file_id),
                last_severity_score=r.last_score,
                last_width_mm=float(r.last_width) if r.last_width else None,
                last_length_mm=float(r.last_length) if r.last_length else None,
                last_bbox=_parse_bbox(r.last_bbox),
                last_gps_lat=float(r.last_lat) if r.last_lat else None,
                last_gps_lon=float(r.last_lon) if r.last_lon else None,
            )
            for r in raw_tracks
        ]

        # 4. 매칭 실행
        entries = match_results_to_tracks(
            new_results, existing_tracks, db,
            inspection_date, tenant_id, project_id,
        )

        # 5. inspection_id 채워서 bulk insert
        for entry in entries:
            db.execute(text("""
                INSERT INTO defect_track_entries (
                    id, track_id, analysis_result_id, inspection_id,
                    inspection_date, severity_score,
                    crack_width_mm, crack_length_mm, crack_area_cm2,
                    change_vs_prev, annotated_image_key,
                    created_at, updated_at
                ) VALUES (
                    :id, :track_id, :result_id, :inspection_id,
                    :inspection_date, :score,
                    :width, :length, :area,
                    :change::jsonb, :img_key,
                    :now, :now
                )
            """), {
                "id": entry["id"],
                "track_id": entry["track_id"],
                "result_id": entry["analysis_result_id"],
                "inspection_id": inspection_id,
                "inspection_date": entry["inspection_date"],
                "score": entry["severity_score"],
                "width": entry["crack_width_mm"],
                "length": entry["crack_length_mm"],
                "area": entry["crack_area_cm2"],
                "change": entry["change_vs_prev"],
                "img_key": entry["annotated_image_key"],
                "now": entry["now"],
            })

            # track status 업데이트
            if entry["track_status_update"]:
                db.execute(text("""
                    UPDATE defect_tracks
                    SET status = :status, updated_at = :now
                    WHERE id = :track_id
                """), {
                    "status": entry["track_status_update"],
                    "track_id": entry["track_id_for_status"],
                    "now": entry["now"],
                })

        db.commit()

        # 6. 악화 알림 발송 (worsening 으로 변경된 트랙만)
        worsening_entries = [
            e for e in entries
            if e.get("track_status_update") == "worsening"
        ]
        if worsening_entries:
            _send_worsening_alerts(
                db, worsening_entries, project_id, tenant_id,
            )

    log.info(
        "track_matching_completed",
        inspection_id=inspection_id,
        entries_created=len(entries),
        new_tracks=sum(1 for e in entries if e["change_vs_prev"] is None),
        worsening_alerts=len(worsening_entries) if worsening_entries else 0,
    )


def _send_worsening_alerts(db: Session, worsening_entries: list[dict],
                           project_id: str, tenant_id: str) -> None:
    """악화 균열에 대해 이메일 + 앱 내 알림 발송"""
    import sys
    sys.path.insert(0, "/app/backend")
    try:
        from app.services.alert_service import send_worsening_alert, insert_in_app_alert
    except ImportError:
        # 워커 환경에서 백엔드 임포트 불가능한 경우 — 이메일만 직접 처리
        send_worsening_alert = None
        insert_in_app_alert = None

    # 프로젝트명 조회
    proj = db.execute(text("""
        SELECT name FROM projects WHERE id = :id
    """), {"id": project_id}).fetchone()
    project_name = proj.name if proj else "알 수 없는 프로젝트"

    # 테넌트 admin/manager 이메일 조회
    recipients_rows = db.execute(text("""
        SELECT email FROM users
        WHERE tenant_id = :tid AND role IN ('admin', 'manager')
        AND deleted_at IS NULL
    """), {"tid": tenant_id}).fetchall()
    recipients = [r.email for r in recipients_rows]

    for entry in worsening_entries:
        track_id = entry["track_id_for_status"]
        change = json.loads(entry["change_vs_prev"]) if entry.get("change_vs_prev") else {}

        # 트랙 location_zone 조회
        track_row = db.execute(text("""
            SELECT location_zone FROM defect_tracks WHERE id = :id
        """), {"id": track_id}).fetchone()
        location_zone = track_row.location_zone if track_row else None

        score_before = entry["severity_score"] - change.get("score_delta", 0)
        score_after = entry["severity_score"]

        # 이메일
        if send_worsening_alert and recipients:
            send_worsening_alert(
                recipients=recipients,
                project_name=project_name,
                location_zone=location_zone,
                track_id=track_id,
                score_before=score_before,
                score_after=score_after,
                crack_width_mm=entry.get("crack_width_mm"),
                width_delta=change.get("width_delta"),
            )

        # 앱 내 알림 (defect_alerts 테이블)
        if insert_in_app_alert:
            try:
                insert_in_app_alert(
                    db,
                    tenant_id=tenant_id,
                    track_id=track_id,
                    project_name=project_name,
                    location_zone=location_zone,
                    score_before=score_before,
                    score_after=score_after,
                )
                db.commit()
            except Exception as e:
                log.warning("in_app_alert_failed", error=str(e))
        else:
            # 직접 INSERT (백엔드 임포트 실패 시)
            _insert_alert_direct(db, tenant_id=tenant_id, track_id=track_id,
                                 project_name=project_name, location_zone=location_zone,
                                 score_before=score_before, score_after=score_after)


def _insert_alert_direct(db: Session, *, tenant_id: str, track_id: str,
                         project_name: str, location_zone: str | None,
                         score_before: int, score_after: int) -> None:
    """백엔드 서비스 임포트 없이 직접 alert 삽입"""
    now = datetime.now(timezone.utc)
    alert_id = str(uuid.uuid4())
    try:
        db.execute(text("""
            INSERT INTO defect_alerts (
                id, tenant_id, track_id, alert_type, title, body, is_read, created_at, updated_at
            ) VALUES (
                :id, :tid, :track_id, 'worsening', :title, :body, false, :now, :now
            )
        """), {
            "id": alert_id,
            "tid": tenant_id,
            "track_id": track_id,
            "title": f"균열 악화 — {project_name} {location_zone or ''}".strip(),
            "body": f"심각도 점수 {score_before} → {score_after} (△{score_after - score_before:+d})",
            "now": now,
        })
        db.commit()
    except Exception as e:
        log.warning("direct_alert_insert_failed", error=str(e))
