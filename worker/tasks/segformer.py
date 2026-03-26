"""
SegFormer 픽셀 세그멘테이션 — 균열 면적 정밀 측정

Phase 1 (YOLOv8) bbox 기반 면적은 근사치.
Phase 2에서 SegFormer 픽셀 마스크로 실제 균열 면적을 정밀 계산.

모델 가중치:
  - /app/weights/segformer-crack.pt  (fine-tuned)
  - 없으면 HuggingFace nvidia/segformer-b0-finetuned-ade-512-512 폴백 (균열 세그 전용 X)

반환:
  - per-pixel binary mask (균열=1, 배경=0)
  - crack_area_cm2: GSD 기반 면적 (cm²)
  - mask_key: S3에 업로드된 마스크 이미지 키
"""
import os
from dataclasses import dataclass
from typing import Optional

import numpy as np
import structlog

log = structlog.get_logger()

SEGFORMER_WEIGHTS = os.getenv("SEGFORMER_WEIGHTS_PATH", "/app/weights/segformer-crack.pt")
CRACK_CLASS_ID = 1   # fine-tuned 모델의 균열 클래스 ID

_segformer_model = None
_processor = None


def _load_segformer():
    global _segformer_model, _processor
    if _segformer_model is not None:
        return _segformer_model, _processor

    try:
        import torch
        from transformers import SegformerForSemanticSegmentation, SegformerImageProcessor

        if os.path.exists(SEGFORMER_WEIGHTS):
            log.info("loading_segformer_finetuned", path=SEGFORMER_WEIGHTS)
            processor = SegformerImageProcessor.from_pretrained("nvidia/segformer-b2-finetuned-ade-512-512")
            model = SegformerForSemanticSegmentation.from_pretrained("nvidia/segformer-b2-finetuned-ade-512-512")
            # fine-tuned 가중치만 덮어쓰기
            state = torch.load(SEGFORMER_WEIGHTS, map_location="cpu")
            model.load_state_dict(state, strict=False)
        else:
            log.warning("segformer_weights_not_found_using_pretrained", path=SEGFORMER_WEIGHTS)
            processor = SegformerImageProcessor.from_pretrained("nvidia/segformer-b0-finetuned-ade-512-512")
            model = SegformerForSemanticSegmentation.from_pretrained("nvidia/segformer-b0-finetuned-ade-512-512")

        device = "cuda" if torch.cuda.is_available() else "cpu"
        model = model.to(device).eval()
        _segformer_model = model
        _processor = processor
        log.info("segformer_loaded", device=device)
        return model, processor

    except ImportError:
        log.error("transformers_not_installed")
        return None, None
    except Exception as e:
        log.error("segformer_load_failed", error=str(e))
        return None, None


@dataclass
class SegmentationResult:
    mask: np.ndarray          # H×W binary (uint8): 균열=1
    crack_pixel_count: int
    image_pixel_count: int
    crack_area_cm2: Optional[float]
    affected_area_pct: float
    mask_image_key: Optional[str] = None


def run_segmentation(
    image_path: str,
    *,
    gsd_cm_per_px: Optional[float] = None,
    bbox_hint: Optional[tuple[float, float, float, float]] = None,
) -> Optional[SegmentationResult]:
    """
    단일 이미지에 SegFormer 실행.

    Args:
        image_path: 로컬 이미지 경로
        gsd_cm_per_px: Ground Sampling Distance (cm/pixel)
        bbox_hint: YOLOv8 bbox (x,y,w,h normalized) — ROI 마스킹용

    Returns:
        SegmentationResult 또는 None (실패 시)
    """
    model, processor = _load_segformer()
    if model is None:
        return None

    try:
        import torch
        from PIL import Image

        img = Image.open(image_path).convert("RGB")
        img_w, img_h = img.size

        inputs = processor(images=img, return_tensors="pt")
        device = next(model.parameters()).device
        inputs = {k: v.to(device) for k, v in inputs.items()}

        with torch.no_grad():
            outputs = model(**inputs)

        # logits → 원본 이미지 크기로 업샘플
        logits = outputs.logits  # (1, num_classes, H/4, W/4)
        upsampled = torch.nn.functional.interpolate(
            logits, size=(img_h, img_w), mode="bilinear", align_corners=False
        )
        pred = upsampled.argmax(dim=1).squeeze(0).cpu().numpy()  # H×W

        # 균열 클래스 마스크
        crack_mask = (pred == CRACK_CLASS_ID).astype(np.uint8)

        # bbox_hint 있으면 해당 영역만 남기기 (다른 균열과 겹침 방지)
        if bbox_hint:
            bx, by, bw, bh = bbox_hint
            x1 = max(0, int((bx - bw / 2) * img_w))
            y1 = max(0, int((by - bh / 2) * img_h))
            x2 = min(img_w, int((bx + bw / 2) * img_w))
            y2 = min(img_h, int((by + bh / 2) * img_h))
            roi_mask = np.zeros_like(crack_mask)
            roi_mask[y1:y2, x1:x2] = 1
            crack_mask = crack_mask * roi_mask

        crack_px = int(crack_mask.sum())
        total_px = img_h * img_w

        area_cm2 = None
        if gsd_cm_per_px and crack_px > 0:
            area_cm2 = round(crack_px * (gsd_cm_per_px ** 2) / 100, 4)  # cm² (GSD는 cm/px → cm²/px²)

        return SegmentationResult(
            mask=crack_mask,
            crack_pixel_count=crack_px,
            image_pixel_count=total_px,
            crack_area_cm2=area_cm2,
            affected_area_pct=round(crack_px / total_px, 6) if total_px > 0 else 0.0,
        )

    except Exception as e:
        log.error("segmentation_failed", image=image_path, error=str(e))
        return None


def save_mask_to_s3(
    mask: np.ndarray,
    base_key: str,
    tenant_id: str,
) -> Optional[str]:
    """
    이진 마스크를 PNG로 S3에 저장.
    Returns: S3 key or None
    """
    try:
        import boto3
        import io
        from PIL import Image

        # 시각화: 균열=빨간색, 배경=투명
        rgba = np.zeros((*mask.shape, 4), dtype=np.uint8)
        rgba[mask == 1] = [220, 38, 38, 180]   # 빨간색 반투명

        img = Image.fromarray(rgba, mode="RGBA")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)

        mask_key = base_key.replace("/annotated/", "/masks/").rsplit(".", 1)[0] + "_mask.png"

        s3 = boto3.client(
            "s3",
            endpoint_url=os.getenv("S3_ENDPOINT_URL", "http://minio:9000"),
            aws_access_key_id=os.getenv("S3_ACCESS_KEY", "minioadmin"),
            aws_secret_access_key=os.getenv("S3_SECRET_KEY", "minioadmin"),
        )
        bucket = os.getenv("S3_BUCKET", "facade-inspect")
        s3.put_object(Bucket=bucket, Key=mask_key, Body=buf, ContentType="image/png")
        return mask_key

    except Exception as e:
        log.error("mask_upload_failed", error=str(e))
        return None
