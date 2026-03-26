"""
DB 타입 호환성 헬퍼.
PostgreSQL: JSONB (인덱싱 지원)
SQLite (테스트): JSON으로 폴백
"""
import os
from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import JSONB as _JSONB

_DB_URL = os.getenv("DATABASE_URL", "")

# SQLite 환경이면 JSON으로 폴백
JsonType = JSON if "sqlite" in _DB_URL else _JSONB
