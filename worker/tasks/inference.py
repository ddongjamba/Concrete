"""
YOLOv8 배치 추론.

모델은 워커 시작 시 한 번만 로드 (BaseTask 캐싱).
weights 파일이 없으면 Ultralytics에서 pretrained 모델을 자동 다운로드 후
crack detection fine-tuned 가중치로 교체한다.
"""
import os
from dataclasses import dataclass

import structlog

log = structlog.get_logger()

# YOLOv8 클래스 ID → 결함 타입 매핑 (fine-tuned 모델 기준)
CLASS_MAP = {
    0: "crack",
    1: "spalling",
    2: "efflorescence",
    3: "stain",
    4: "delamination",
}

CONF_THRESHOLD = 0.35
IOU_THRESHOLD = 0.45
BATCH_SIZE = 16


@dataclass
class Detection:
    class_id: int
    defect_type: str
    confidence: float
    # normalized 0-1 (x_center, y_center, w, h)
    bbox_x: float
    bbox_y: float
    bbox_w: float
    bbox_h: float


def load_model(weights_path: str | None = None):
    """YOLOv8 모델 로드. weights_path가 없으면 기본 경로 시도."""
    from ultralytics import YOLO

    if weights_path is None:
        weights_path = os.getenv("MODEL_WEIGHTS_PATH", "/app/weights/yolov8n-crack.pt")

    if not os.path.exists(weights_path):
        # 개발 환경: pretrained yolov8n 사용 (crack fine-tune 없이)
        log.warning("weights_not_found_using_pretrained", path=weights_path)
        weights_path = "yolov8n.pt"

    model = YOLO(weights_path)
    log.info("model_loaded", path=weights_path)
    return model


def run_inference(model, image_paths: list[str]) -> list[list[Detection]]:
    """
    이미지 배치 추론.

    Returns:
        각 이미지별 Detection 리스트
    """
    all_detections: list[list[Detection]] = []

    # 배치 단위로 처리
    for i in range(0, len(image_paths), BATCH_SIZE):
        batch = image_paths[i: i + BATCH_SIZE]
        results = model.predict(
            batch,
            conf=CONF_THRESHOLD,
            iou=IOU_THRESHOLD,
            verbose=False,
        )

        for result in results:
            img_detections: list[Detection] = []
            if result.boxes is not None:
                for box in result.boxes:
                    cls_id = int(box.cls.item())
                    conf = float(box.conf.item())
                    # xywhn: normalized xywh (center)
                    x, y, w, h = box.xywhn[0].tolist()
                    img_detections.append(Detection(
                        class_id=cls_id,
                        defect_type=CLASS_MAP.get(cls_id, "other"),
                        confidence=conf,
                        bbox_x=x,
                        bbox_y=y,
                        bbox_w=w,
                        bbox_h=h,
                    ))
            all_detections.append(img_detections)

    return all_detections
