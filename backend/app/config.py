from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    # App
    environment: str = "development"
    backend_cors_origins: List[str] = ["http://localhost:3000"]

    # Database
    database_url: str = "postgresql+asyncpg://facade:facade_secret@localhost:5432/facade_db"

    # Redis / Celery
    redis_url: str = "redis://localhost:6379/0"

    # MinIO / S3
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "facade-inspect"
    minio_use_ssl: bool = False

    # JWT
    secret_key: str = "change_me_in_production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 30

    # Stripe
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
