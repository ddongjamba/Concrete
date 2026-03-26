"""
후처리: 정량화 + 어노테이션 이미지 생성

1. GSD 기반 실세계 치수 환산 (mm/cm²)
2. SegFormer 픽셀 마스크로 정밀 면적 계산 (가능한 경우)
3. 심각도 점수 계산 (0-100)
4. bbox + 마스크 시각화 이미지 생성 → S3 업로드
"""
import os
import uuid
from dataclasses import dataclass

import cv2
import numpy as np
import structlog

from tasks.inference import Detection
from tasks.quantification import (
    CameraParams, compute_gsd, pixels_to_mm, pixels_to_cm2,
    compute_severity_score, score_to_severity,
)
from tasks.preprocessing import upload_file

log = structlog.get_logger()

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
    segmentation_mask_key: str | None = None


def process_image(
    image_path: str,
    file_id: str,
    detections: list[Detection],
    tenant_id: str,
    inspection_id: str,
    camera_params: CameraParams | None,
    use_segformer: bool = True,
) -> list[ProcessedResult]:
    """
    단일 이미지의 모든 detection을 처리하고 어노테이션 이미지를 생성한다.
    use_segformer=True 이면 균열(crack) 결함에 SegFormer 정밀 면적 계산 시도.
    """
    if not detections:
        return []

    img = cv2.imread(image_path)
    if img is None:
        return []

    h, w = img.shape[:2]
    gsd = compute_gsd(camera_params) if camera_params else None

    # SegFormer: 이미지당 한 번만 실행 (균열 결함이 있을 때만)
    seg_result = None
    if use_segformer and any(d.defect_type == "crack" for d in detections):
        try:
            from tasks.segformer import run_segmentation
            seg_result = run_segmentation(image_path, gsd_cm_per_px=gsd)
            log.info("segformer_done", crack_px=seg_result.crack_pixel_count if seg_result else 0)
        except Exception as e:
            log.warning("segformer_skipped", error=str(e))

    results: list[ProcessedResult] = []
    seg_overlay = None  # 마스크를 이미지에 오버레이하기 위한 배열

    if seg_result is not None and seg_result.crack_pixel_count > 0:
        # 빨간 반투명 마스크 오버레이 준비
        mask_rgb = np.zeros_like(img)
        mask_rgb[seg_result.mask == 1] = [0, 0, 220]  # BGR: 빨강
        seg_overlay = cv2.addWeighted(img, 1.0, mask_rgb, 0.35, 0)

    for i, det in enumerate(detections):
        # bbox 픽셀 좌표 계산
        cx, cy = det.bbox_x * w, det.bbox_y * h
        bw, bh = det.bbox_w * w, det.bbox_h * h
        x1 = int(cx - bw / 2)
        y1 = int(cy - bh / 2)
        x2 = int(cx + bw / 2)
        y2 = int(cy + bh / 2)

        # 기본 bbox 기반 치수 (GSD 있을 때)
        short_px = min(bw, bh)
        long_px = max(bw, bh)
        area_px = bw * bh

        crack_width_mm = pixels_to_mm(short_px, gsd) if gsd else None
        crack_length_mm = pixels_to_mm(long_px, gsd) if gsd else None
        crack_area_cm2 = pixels_to_cm2(area_px, gsd) if gsd else None
        affected_area_pct = (area_px / (w * h)) * 100 if w * h > 0 else None

        # SegFormer 정밀 면적으로 교체 (균열 결함만)
        segmentation_mask_key = None
        if det.defect_type == "crack" and seg_result is not None:
            # bbox 내 마스크 픽셀만 카운트
            bx1, by1 = max(0, x1), max(0, y1)
            bx2, by2 = min(w, x2), min(h, y2)
            roi_mask = seg_result.mask[by1:by2, bx1:bx2]
            roi_px = int(roi_mask.sum())
            if roi_px > 0 and gsd:
                crack_area_cm2 = round(roi_px * (gsd ** 2) / 100, 4)
            affected_area_pct = (roi_px / (w * h)) * 100 if w * h > 0 else affected_area_pct

        # 심각도 점수
        score = compute_severity_score(det.confidence, crack_width_mm, affected_area_pct)
        severity = score_to_severity(score)

        # 어노테이션: bbox + 라벨
        draw_img = seg_overlay if seg_overlay is not None else img
        color = SEVERITY_COLORS[severity]
        cv2.rectangle(draw_img, (x1, y1), (x2, y2), color, 2)
        label = f"{det.defect_type} {det.confidence:.2f}"
        if crack_width_mm:
            label += f" {crack_width_mm:.1f}mm"
        cv2.putText(draw_img, label, (x1, max(y1 - 6, 10)),
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
            segmentation_mask_key=None,
        ))

    # 어노테이션 이미지 저장 후 S3 업로드
    annotated_key = f"{tenant_id}/{inspection_id}/annotated/{file_id}_{uuid.uuid4().hex[:8]}.jpg"
    tmp_path = f"/tmp/{uuid.uuid4().hex}.jpg"
    final_img = seg_overlay if seg_overlay is not None else img
    cv2.imwrite(tmp_path, final_img)
    upload_file(tmp_path, annotated_key)
    os.unlink(tmp_path)

    # SegFormer 마스크 S3 업로드 (균열 있는 경우)
    mask_key = None
    if seg_result is not None and seg_result.crack_pixel_count > 0:
        try:
            from tasks.segformer import save_mask_to_s3
            mask_key = save_mask_to_s3(seg_result.mask, annotated_key, tenant_id)
        except Exception as e:
            log.warning("mask_upload_failed", error=str(e))

    for r in results:
        r.annotated_image_key = annotated_key
        if r.detection.defect_type == "crack":
            r.segmentation_mask_key = mask_key

    return results
