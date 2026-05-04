"""
Database setup — includes both events and company_profiles tables.
"""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from config import get_settings
from models.event import Base as EventBase
from models.company_profile import CompanyProfileORM  # ensures table is registered
from loguru import logger

settings = get_settings()

is_sqlite = settings.database_url.startswith("sqlite")
engine_kwargs = {
    "echo": settings.debug,
    "pool_pre_ping": True,
}
if is_sqlite:
    engine_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_async_engine(settings.database_url, **engine_kwargs)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(EventBase.metadata.create_all)
    logger.info("Database initialised (events + company_profiles).")


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
