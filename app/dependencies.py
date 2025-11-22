"""FastAPI dependency injection providers."""

import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, Request
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.database.base import get_async_session
from app.services.vector_store import VectorStore


async def get_vector_store(
    settings: Annotated[Settings, Depends(get_settings)]
) -> AsyncGenerator[VectorStore, None]:
    """Dependency to provide ChromaDB vector store instance."""
    store = VectorStore(
        persist_directory=str(settings.CHROMA_PERSIST_DIR),
        collection_name=settings.CHROMA_COLLECTION_NAME,
    )
    try:
        yield store
    finally:
        pass


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency to provide database session."""
    async for session in get_async_session():
        yield session


def get_correlation_id(request: Request) -> str:
    """Extract or generate correlation ID for request tracing."""
    correlation_id = request.headers.get("X-Correlation-ID")
    if not correlation_id:
        correlation_id = str(uuid.uuid4())
    return correlation_id


async def log_request(
    request: Request, correlation_id: Annotated[str, Depends(get_correlation_id)]
) -> None:
    """Log incoming request with correlation ID."""
    logger.bind(
        correlation_id=correlation_id,
        method=request.method,
        path=request.url.path,
        client=request.client.host if request.client else "unknown",
    ).info("Incoming request")
