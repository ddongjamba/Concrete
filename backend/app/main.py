from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: DB connection pool is lazy — no explicit init needed for SQLAlchemy async
    yield
    # Shutdown


app = FastAPI(
    title="Facade Inspect API",
    description="드론 외벽 균열 탐지 B2B SaaS",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.backend_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


from app.routers import auth, projects, inspections, analysis, reports, billing

app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(projects.router, prefix="/api/v1/projects", tags=["projects"])
app.include_router(
    inspections.router,
    prefix="/api/v1/projects/{project_id}/inspections",
    tags=["inspections"],
)
app.include_router(analysis.router, prefix="/api/v1/analysis", tags=["analysis"])
app.include_router(reports.router, prefix="/api/v1", tags=["reports"])
app.include_router(billing.router, prefix="/api/v1/billing", tags=["billing"])


@app.get("/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}
