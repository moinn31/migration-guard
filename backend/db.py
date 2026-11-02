from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from .config import settings

def get_async_database_url(url: str) -> str:
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    if "sslmode=require" in url:
        url = url.replace("sslmode=require", "ssl=require")
    url = url.replace("&channel_binding=require", "").replace("channel_binding=require&", "").replace("channel_binding=require", "")
    return url

async_db_url = get_async_database_url(settings.database_url)
engine = create_async_engine(async_db_url, future=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

class Base(DeclarativeBase):
    pass

async def get_db():
    async with SessionLocal() as session:
        yield session
