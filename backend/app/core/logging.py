"""
구조화 로깅 설정 (structlog + JSON 출력)

각 요청에 request_id를 부여해 전체 처리 흐름을 추적.
프로덕션: JSON 형식 → CloudWatch / ELK로 수집
개발: 컬러 콘솔 출력
"""
import logging
import os
import sys
import uuid
from contextvars import ContextVar

import structlog

# 요청별 컨텍스트 변수
_request_id_var: ContextVar[str] = ContextVar("request_id", default="")
_tenant_id_var: ContextVar[str] = ContextVar("tenant_id", default="")


def get_request_id() -> str:
    return _request_id_var.get()


def set_request_id(rid: str) -> None:
    _request_id_var.set(rid)


def set_tenant_id(tid: str) -> None:
    _tenant_id_var.set(tid)


def _add_request_context(logger, method, event_dict):
    """structlog 프로세서: request_id, tenant_id 자동 주입"""
    rid = _request_id_var.get()
    tid = _tenant_id_var.get()
    if rid:
        event_dict["request_id"] = rid
    if tid:
        event_dict["tenant_id"] = tid
    return event_dict


def configure_logging() -> None:
    """앱 시작 시 한 번 호출."""
    is_production = os.getenv("ENVIRONMENT", "development") == "production"

    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        _add_request_context,
        structlog.processors.StackInfoRenderer(),
    ]

    if is_production:
        # JSON 출력 — CloudWatch / ELK 수집용
        renderer = structlog.processors.JSONRenderer()
    else:
        # 컬러 콘솔
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processor=renderer,
        foreign_pre_chain=shared_processors,
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.INFO)

    # 노이즈 억제
    for noisy in ("uvicorn.access", "sqlalchemy.engine"):
        logging.getLogger(noisy).setLevel(
            logging.WARNING if is_production else logging.INFO
        )
