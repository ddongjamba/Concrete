"""
균열 정량화: 픽셀 → 실세계 단위 환산 + 심각도 점수 계산

GSD(Ground Sampling Distance) 공식:
  GSD (cm/px) = (고도_m × 센서폭_mm) / (초점거리_mm × 이미지폭_px) × 100

심각도 점수 (0-100):
  = confidence × 40  +  min(crack_width_mm / 5.0, 1.0) × 30
    + min(affected_area_pct / 0.1, 1.0) × 30
"""
from dataclasses import dataclass


@dataclass
class CameraParams:
    altitude_m: float
    focal_length_mm: float
    sensor_width_mm: float
    image_width_px: int


def compute_gsd(params: CameraParams) -> float | None:
    """GSD (cm/px) 계산. 파라미터 없으면 None 반환"""
    if not all([params.altitude_m, params.focal_length_mm,
                params.sensor_width_mm, params.image_width_px]):
        return None
    return (params.altitude_m * params.sensor_width_mm) / \
           (params.focal_length_mm * params.image_width_px) * 100


def pixels_to_mm(pixels: float, gsd_cm_per_px: float) -> float:
    """픽셀 수 → mm 환산"""
    return pixels * gsd_cm_per_px * 10


def pixels_to_cm2(pixels: float, gsd_cm_per_px: float) -> float:
    """픽셀 면적 → cm² 환산"""
    return pixels * (gsd_cm_per_px ** 2)


def compute_severity_score(
    confidence: float,
    crack_width_mm: float | None,
    affected_area_pct: float | None,
) -> int:
    """
    복합 심각도 점수 (0-100) 계산

    Returns:
        int: 0-100 점수
        0-29:  관찰 (low)
        30-59: 주의 (medium)
        60-79: 경보 (high)
        80-100: 긴급 (critical)
    """
    score = confidence * 40

    if crack_width_mm is not None:
        score += min(crack_width_mm / 5.0, 1.0) * 30

    if affected_area_pct is not None:
        score += min(affected_area_pct / 0.1, 1.0) * 30

    return min(int(score), 100)


def score_to_severity(score: int) -> str:
    if score >= 80:
        return "critical"
    elif score >= 60:
        return "high"
    elif score >= 30:
        return "medium"
    return "low"
