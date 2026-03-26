import os
from celery import Celery

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

app = Celery(
    "facade_worker",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=[
        "tasks.analysis_tasks",
        "tasks.report_tasks",
    ],
)

app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Seoul",
    enable_utc=True,
    task_routes={
        "tasks.analysis_tasks.*": {"queue": "analysis"},
        "tasks.report_tasks.*": {"queue": "reports"},
    },
    task_acks_late=True,
    worker_prefetch_multiplier=1,  # 한 번에 하나씩 처리 (GPU 태스크)
)
