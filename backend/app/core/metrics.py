"""
Prometheus 메트릭

수집 항목:
  - http_requests_total (method, path, status)
  - http_request_duration_seconds (histogram)
  - active_analysis_jobs (gauge)
  - dlq_size (gauge) — Redis DLQ 적체량
  - crack_detections_total (counter)

/metrics 엔드포인트: Prometheus scrape용
"""
import os
import time

import structlog

log = structlog.get_logger()

try:
    from prometheus_client import (
        Counter, Histogram, Gauge,
        generate_latest, CONTENT_TYPE_LATEST,
        CollectorRegistry, REGISTRY,
    )
    _PROMETHEUS_AVAILABLE = True
except ImportError:
    _PROMETHEUS_AVAILABLE = False
    log.warning("prometheus_client_not_installed_metrics_disabled")


if _PROMETHEUS_AVAILABLE:
    HTTP_REQUESTS = Counter(
        "http_requests_total",
        "Total HTTP requests",
        ["method", "path", "status"],
    )

    HTTP_DURATION = Histogram(
        "http_request_duration_seconds",
        "HTTP request latency",
        ["method", "path"],
        buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
    )

    ACTIVE_JOBS = Gauge(
        "active_analysis_jobs",
        "Number of analysis jobs currently running or queued",
    )

    DLQ_SIZE = Gauge(
        "dlq_size",
        "Number of failed tasks in Dead Letter Queue",
    )

    CRACK_DETECTIONS = Counter(
        "crack_detections_total",
        "Total crack detections by severity",
        ["severity"],
    )


def record_request(method: str, path: str, status: int, duration_s: float) -> None:
    if not _PROMETHEUS_AVAILABLE:
        return
    # 경로 파라미터 정규화 (UUID 제거)
    normalized = _normalize_path(path)
    HTTP_REQUESTS.labels(method=method, path=normalized, status=str(status)).inc()
    HTTP_DURATION.labels(method=method, path=normalized).observe(duration_s)


def record_crack_detection(severity: str) -> None:
    if not _PROMETHEUS_AVAILABLE:
        return
    CRACK_DETECTIONS.labels(severity=severity).inc()


def update_active_jobs(count: int) -> None:
    if not _PROMETHEUS_AVAILABLE:
        return
    ACTIVE_JOBS.set(count)


def update_dlq_size() -> None:
    """Redis DLQ 길이 조회 후 gauge 업데이트"""
    if not _PROMETHEUS_AVAILABLE:
        return
    try:
        import redis
        REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        r = redis.from_url(REDIS_URL, socket_connect_timeout=1)
        size = r.llen("facade.dlq")
        DLQ_SIZE.set(size)
    except Exception:
        pass


def get_metrics_response():
    """
    /metrics 엔드포인트용 Prometheus text 출력.
    Returns: (content: bytes, content_type: str)
    """
    if not _PROMETHEUS_AVAILABLE:
        return b"# prometheus_client not installed\n", "text/plain"

    update_dlq_size()
    return generate_latest(), CONTENT_TYPE_LATEST


def _normalize_path(path: str) -> str:
    """UUID/숫자 경로 세그먼트를 {id}로 치환해 카디널리티 억제"""
    import re
    path = re.sub(
        r"/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
        "/{id}",
        path,
    )
    path = re.sub(r"/\d+", "/{n}", path)
    return path
