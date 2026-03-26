from contextlib import asynccontextmanager
from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.core.logging import configure_logging
from app.core.middleware import RequestLoggingMiddleware, TenantContextMiddleware

configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(
    title="Facade Inspect API",
    description="드론 외벽 균열 탐지 B2B SaaS",
    version="0.1.0",
    lifespan=lifespan,
)

# 미들웨어 등록 순서: 바깥쪽 → 안쪽
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(TenantContextMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.backend_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


from app.routers import auth, projects, inspections, analysis, defect_tracks, alerts, reports, billing

app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(projects.router, prefix="/api/v1/projects", tags=["projects"])
app.include_router(
    inspections.router,
    prefix="/api/v1/projects/{project_id}/inspections",
    tags=["inspections"],
)
app.include_router(analysis.router, prefix="/api/v1/analysis", tags=["analysis"])
app.include_router(defect_tracks.router, prefix="/api/v1", tags=["defect-tracks"])
app.include_router(alerts.router, prefix="/api/v1", tags=["alerts"])
app.include_router(reports.router, prefix="/api/v1", tags=["reports"])
app.include_router(billing.router, prefix="/api/v1/billing", tags=["billing"])


@app.get("/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}


@app.get("/metrics")
async def metrics():
    """Prometheus scrape 엔드포인트."""
    from app.core.metrics import get_metrics_response
    content, content_type = get_metrics_response()
    return Response(content=content, media_type=content_type)


@app.get("/admin/dlq", include_in_schema=False)
async def dlq_inspect(limit: int = 20):
    """DLQ 내용 조회 (내부 관리용). 프로덕션에서는 IP 화이트리스트 필요."""
    import os, redis, json
    r = redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"),
                       socket_connect_timeout=1)
    items = r.lrange("facade.dlq", 0, limit - 1)
    return {"count": r.llen("facade.dlq"), "items": [json.loads(i) for i in items]}
