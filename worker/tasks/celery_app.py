import os
import structlog
from celery import Celery
from celery.signals import task_failure, task_retry, task_success

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

app = Celery(
    "facade_worker",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=[
        "tasks.analysis_tasks",
        "tasks.report_tasks",
        "tasks.tracking_tasks",
    ],
)

_DLQ = "facade.dlq"  # Redis list key for dead-letter queue

app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Seoul",
    enable_utc=True,
    task_routes={
        "tasks.analysis_tasks.*": {"queue": "analysis"},
        "tasks.report_tasks.*": {"queue": "reports"},
        "tasks.tracking_tasks.*": {"queue": "tracking"},
    },
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_reject_on_worker_lost=True,
    result_expires=604_800,
)

try:
    from kombu import Queue, Exchange
    dead_exchange = Exchange("dlx", type="direct")
    app.conf.task_queues = [
        Queue("analysis",  routing_key="analysis"),
        Queue("reports",   routing_key="reports"),
        Queue("tracking",  routing_key="tracking"),
        Queue(_DLQ,        exchange=dead_exchange, routing_key="dlq"),
    ]
    app.conf.task_default_queue = "analysis"
except ImportError:
    pass

log = structlog.get_logger()

@task_failure.connect
def on_task_failure(sender, task_id, exception, args, kwargs, traceback, einfo, **kw):
    log.error("celery_task_failed", task_name=sender.name, task_id=task_id, error=str(exception))
    try:
        import redis, json
        from datetime import datetime, timezone
        r = redis.from_url(REDIS_URL)
        r.lpush(_DLQ, json.dumps({
            "task_name": sender.name,
            "task_id": task_id,
            "error": str(exception),
            "args": list(args),
            "kwargs": kwargs,
            "failed_at": datetime.now(timezone.utc).isoformat(),
        }))
        r.ltrim(_DLQ, 0, 999)
    except Exception as e:
        log.warning("dlq_write_failed", error=str(e))

@task_retry.connect
def on_task_retry(sender, request, reason, einfo, **kw):
    log.warning("celery_task_retry", task_name=sender.name, task_id=request.id,
                reason=str(reason), retries=request.retries)

@task_success.connect
def on_task_success(sender, result, **kw):
    log.info("celery_task_success", task_name=sender.name)
