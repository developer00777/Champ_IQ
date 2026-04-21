from functools import lru_cache

from pydantic_settings import BaseSettings
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/champiq"
    redis_url: str = "redis://localhost:6379/0"
    fernet_key: str = ""

    champmail_base_url: str = "http://localhost:8001"
    champgraph_base_url: str = "http://localhost:8002"
    lakeb2b_base_url: str = "http://localhost:8003"

    champserver_email: str = ""
    champserver_password: str = ""

    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_model: str = "anthropic/claude-sonnet-4"
    openrouter_referrer: str = "https://champiq.local"
    openrouter_app_title: str = "ChampIQ Canvas"

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    return Settings()


def get_engine():
    settings = get_settings()
    return create_async_engine(settings.database_url, echo=False, pool_pre_ping=True)


@lru_cache
def get_session_factory():
    return async_sessionmaker(get_engine(), expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    factory = get_session_factory()
    async with factory() as session:
        yield session
