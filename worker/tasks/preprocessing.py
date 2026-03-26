"""
전처리: 동영상 프레임 추출 + 이미지 리사이즈/정규화

GSD 계산을 위한 카메라 파라미터도 여기서 파싱한다.
"""
import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import boto3
from botocore.config import Config


@dataclass
class ImageItem:
    local_path: str
    storage_key: str           # 원본 S3 키
    file_id: str
    # 카메라 파라미터 (GSD 계산용)
    altitude_m: float | None = None
    focal_length_mm: float | None = None
    sensor_width_mm: float | None = None
    image_width_px: int | None = None


def get_s3_client():
    endpoint = os.getenv("MINIO_ENDPOINT", "minio:9000")
    use_ssl = os.getenv("MINIO_USE_SSL", "false").lower() == "true"
    return boto3.client(
        "s3",
        endpoint_url=f"{'https' if use_ssl else 'http'}://{endpoint}",
        aws_access_key_id=os.getenv("MINIO_ACCESS_KEY", "minioadmin"),
        aws_secret_access_key=os.getenv("MINIO_SECRET_KEY", "minioadmin"),
        config=Config(signature_version="s3v4"),
        region_name="us-east-1",
    )


def download_file(storage_key: str, local_path: str) -> None:
    """S3/MinIO에서 파일 다운로드"""
    s3 = get_s3_client()
    bucket = os.getenv("MINIO_BUCKET", "facade-inspect")
    s3.download_file(bucket, storage_key, local_path)


def upload_file(local_path: str, storage_key: str, content_type: str = "image/jpeg") -> None:
    """로컬 파일을 S3/MinIO에 업로드"""
    s3 = get_s3_client()
    bucket = os.getenv("MINIO_BUCKET", "facade-inspect")
    s3.upload_file(local_path, bucket, storage_key, ExtraArgs={"ContentType": content_type})


def extract_frames(video_path: str, output_dir: str, fps: float = 1.0) -> list[str]:
    """
    ffmpeg으로 동영상에서 프레임 추출.
    기본 1fps (초당 1프레임) — 드론 영상은 대개 4K/30fps이므로 충분.
    """
    os.makedirs(output_dir, exist_ok=True)
    pattern = os.path.join(output_dir, "frame_%05d.jpg")
    cmd = [
        "ffmpeg", "-i", video_path,
        "-vf", f"fps={fps}",
        "-q:v", "2",     # JPEG 품질 (낮을수록 고품질)
        pattern,
        "-y", "-loglevel", "error",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg 실패: {result.stderr}")

    frames = sorted(Path(output_dir).glob("frame_*.jpg"))
    return [str(f) for f in frames]


def prepare_images(files: list[dict], work_dir: str) -> list[ImageItem]:
    """
    inspection_files 목록을 받아 로컬에 다운로드하고 ImageItem 리스트 반환.
    동영상이면 프레임 추출.
    """
    items: list[ImageItem] = []

    for f in files:
        file_id = f["id"]
        storage_key = f["storage_key"]
        file_type = f["file_type"]  # "image" | "video"

        local_path = os.path.join(work_dir, f"{file_id}_{Path(storage_key).name}")
        download_file(storage_key, local_path)

        camera_params = {
            "altitude_m": f.get("altitude_m"),
            "focal_length_mm": f.get("focal_length_mm"),
            "sensor_width_mm": f.get("sensor_width_mm"),
            "image_width_px": f.get("image_width_px"),
        }

        if file_type == "video":
            frames_dir = os.path.join(work_dir, f"frames_{file_id}")
            frame_paths = extract_frames(local_path, frames_dir, fps=1.0)
            for idx, fp in enumerate(frame_paths):
                items.append(ImageItem(
                    local_path=fp,
                    storage_key=f"{storage_key}#frame{idx}",
                    file_id=f"{file_id}_{idx}",
                    **camera_params,
                ))
        else:
            items.append(ImageItem(
                local_path=local_path,
                storage_key=storage_key,
                file_id=file_id,
                **camera_params,
            ))

    return items
