"""Database connection and session management."""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import get_settings
from app.models.db_models import Base

_engine: AsyncEngine | None = None
_async_session_maker: async_sessionmaker[AsyncSession] | None = None


def get_async_engine() -> AsyncEngine:
    """Get or create the async SQLAlchemy engine."""
    global _engine

    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(
            settings.DATABASE_URL,
            echo=settings.DATABASE_ECHO,
            pool_size=settings.DATABASE_POOL_SIZE,
            max_overflow=settings.DATABASE_MAX_OVERFLOW,
            pool_recycle=settings.DATABASE_POOL_RECYCLE,
            pool_pre_ping=True,
            poolclass=NullPool if settings.APP_ENV == "test" else None,
        )

    return _engine


def get_session_maker() -> async_sessionmaker[AsyncSession]:
    """Get or create the async session maker."""
    global _async_session_maker

    if _async_session_maker is None:
        engine = get_async_engine()
        _async_session_maker = async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )

    return _async_session_maker


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency to provide database session."""
    session_maker = get_session_maker()
    async with session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def create_tables() -> None:
    """Create all database tables."""
    engine = get_async_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def drop_tables() -> None:
    """Drop all database tables."""
    engine = get_async_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


async def close_db_connections() -> None:
    """Close all database connections."""
    global _engine, _async_session_maker

    if _engine is not None:
        await _engine.dispose()
        _engine = None

    _async_session_maker = None
