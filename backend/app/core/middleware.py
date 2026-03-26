"""
FastAPI 미들웨어

1. RequestLoggingMiddleware: 요청/응답 구조화 로그 + request_id 헤더
2. TenantMiddleware: JWT에서 tenant_id 추출 → ContextVar 저장 (RLS용)
"""
import time
import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.logging import set_request_id, set_tenant_id

log = structlog.get_logger()


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    모든 HTTP 요청에 request_id 부여 및 응답 시간 기록.
    헬스체크(/health)는 로그 스킵.
    """
    _SKIP_PATHS = {"/health", "/metrics"}

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        set_request_id(request_id)

        if request.url.path in self._SKIP_PATHS:
            return await call_next(request)

        start = time.perf_counter()
        response: Response = await call_next(request)
        elapsed_ms = round((time.perf_counter() - start) * 1000, 2)

        log.info(
            "http_request",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            elapsed_ms=elapsed_ms,
        )

        response.headers["X-Request-ID"] = request_id

        try:
            from app.core.metrics import record_request
            record_request(request.method, request.url.path,
                           response.status_code, elapsed_ms / 1000)
        except Exception:
            pass

        return response


class TenantContextMiddleware(BaseHTTPMiddleware):
    """
    Authorization 헤더의 JWT를 디코딩해 tenant_id를 ContextVar에 저장.
    인증 실패 시 조용히 통과 (인증은 get_current_user에서 처리).
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            try:
                from app.core.security import decode_token
                payload = decode_token(auth[7:])
                tid = payload.get("tenant_id", "")
                if tid:
                    set_tenant_id(tid)
            except Exception:
                pass
        return await call_next(request)
