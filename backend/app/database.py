from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import event, text
from app.config import settings

engine = create_async_engine(settings.database_url, echo=False, pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    """
    요청마다 새 세션을 생성하고 RLS용 app.tenant_id를 설정한다.
    TenantContextMiddleware가 ContextVar에 tenant_id를 저장해두면 여기서 주입.
    """
    from app.core.logging import _tenant_id_var
    async with AsyncSessionLocal() as session:
        tid = _tenant_id_var.get("")
        if tid and "postgresql" in settings.database_url:
            # PostgreSQL RLS: 현재 커넥션에 tenant_id 설정
            await session.execute(
                text("SELECT set_config('app.tenant_id', :tid, true)"),
                {"tid": tid},
            )
        yield session
