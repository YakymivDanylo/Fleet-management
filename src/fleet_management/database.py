from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from .config import settings
from sqlalchemy.orm import declarative_base

engine = create_async_engine(settings.database_url)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

Base = declarative_base()

async def get_db():
    async with SessionLocal() as session:
        yield session