"""
후처리: 정량화 + 어노테이션 이미지 생성

1. GSD 기반 실세계 치수 환산 (mm/cm²)
2. 심각도 점수 계산 (0-100)
3. bbox 시각화 이미지 생성 → S3 업로드
"""
import os
import uuid
from dataclasses import dataclass

import cv2
import numpy as np

from tasks.inference import Detection
from tasks.quantification import (
    CameraParams, compute_gsd, pixels_to_mm, pixels_to_cm2,
    compute_severity_score, score_to_severity,
)
from tasks.preprocessing import upload_file

# 심각도별 색상 (BGR)
SEVERITY_COLORS = {
    "low": (34, 197, 94),       # 초록
    "medium": (251, 191, 36),   # 노랑
    "high": (239, 68, 68),      # 빨강
    "critical": (127, 29, 29),  # 진한 빨강
}


@dataclass
class ProcessedResult:
    file_id: str
    detection: Detection
    # 실세계 치수
    crack_width_mm: float | None
    crack_length_mm: float | None
    crack_area_cm2: float | None
    affected_area_pct: float | None
    # 점수
    severity_score: int
    severity: str
    # S3 키
    annotated_image_key: str


def process_image(
    image_path: str,
    file_id: str,
    detections: list[Detection],
    tenant_id: str,
    inspection_id: str,
    camera_params: CameraParams | None,
) -> list[ProcessedResult]:
    """
    단일 이미지의 모든 detection을 처리하고 어노테이션 이미지를 생성한다.
    """
    if not detections:
        return []

    img = cv2.imread(image_path)
    if img is None:
        return []

    h, w = img.shape[:2]
    gsd = compute_gsd(camera_params) if camera_params else None

    results: list[ProcessedResult] = []

    for det in detections:
        # bbox 픽셀 좌표 계산
        cx, cy = det.bbox_x * w, det.bbox_y * h
        bw, bh = det.bbox_w * w, det.bbox_h * h
        x1 = int(cx - bw / 2)
        y1 = int(cy - bh / 2)
        x2 = int(cx + bw / 2)
        y2 = int(cy + bh / 2)

        # 실세계 치수 환산
        short_px = min(bw, bh)
        long_px = max(bw, bh)
        area_px = bw * bh

        crack_width_mm = pixels_to_mm(short_px, gsd) if gsd else None
        crack_length_mm = pixels_to_mm(long_px, gsd) if gsd else None
        crack_area_cm2 = pixels_to_cm2(area_px, gsd) if gsd else None
        affected_area_pct = (area_px / (w * h)) * 100 if w * h > 0 else None

        # 심각도 점수
        score = compute_severity_score(det.confidence, crack_width_mm, affected_area_pct)
        severity = score_to_severity(score)

        # 어노테이션: bbox + 라벨
        color = SEVERITY_COLORS[severity]
        cv2.rectangle(img, (x1, y1), (x2, y2), color, 2)
        label = f"{det.defect_type} {det.confidence:.2f}"
        if crack_width_mm:
            label += f" {crack_width_mm:.1f}mm"
        cv2.putText(img, label, (x1, max(y1 - 6, 10)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)

        results.append(ProcessedResult(
            file_id=file_id,
            detection=det,
            crack_width_mm=crack_width_mm,
            crack_length_mm=crack_length_mm,
            crack_area_cm2=crack_area_cm2,
            affected_area_pct=affected_area_pct,
            severity_score=score,
            severity=severity,
            annotated_image_key="",  # 아래에서 채움
        ))

    # 어노테이션 이미지 저장 후 S3 업로드
    annotated_key = f"{tenant_id}/{inspection_id}/annotated/{file_id}_{uuid.uuid4().hex[:8]}.jpg"
    tmp_path = f"/tmp/{uuid.uuid4().hex}.jpg"
    cv2.imwrite(tmp_path, img)
    upload_file(tmp_path, annotated_key)
    os.unlink(tmp_path)

    # 모든 결과에 동일한 어노테이션 이미지 키 설정
    for r in results:
        r.annotated_image_key = annotated_key

    return results
