"""FastAPI main application with middleware and lifecycle management."""

import time
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import history, profile, proposal
from app.config import get_settings
from app.database.base import close_db_connections, create_tables, get_async_session
from app.dependencies import get_vector_store
from app.exceptions import (
    DatabaseError,
    LLMError,
    ProfileNotFoundError,
    ProposalGenerationError,
    SwiftmeException,
    VectorStoreError,
)
from app.logging_config import setup_logging
from app.models.schemas import ErrorResponse, HealthResponse


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager for startup and shutdown events.

    Args:
        app: FastAPI application instance
    """
    setup_logging()
    logger.info("Starting Swiftme Mini API server...")

    settings = get_settings()
    logger.info(
        f"Configuration loaded",
        extra={
            "env": settings.APP_ENV,
            "log_level": settings.LOG_LEVEL,
            "model": settings.OPENAI_MODEL,
        },
    )

    try:
        await create_tables()
        logger.info("Database tables created/verified")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise

    try:
        async for vector_store in get_vector_store(settings):
            stats = vector_store.get_collection_stats()
            logger.info(f"Vector store initialized: {stats}")

            logger.info("NOTE: First API call will download embedding model (~87MB, 2-5 min with slow internet)")
            break
    except Exception as e:
        logger.error(f"Failed to initialize vector store: {e}")
        raise

    logger.info("Swiftme Mini API server started successfully")

    yield

    logger.info("Shutting down Swiftme Mini API server...")
    await close_db_connections()
    logger.info("Database connections closed")
    logger.info("Swiftme Mini API server stopped")


app = FastAPI(
    title="Swiftme Mini",
    description="Smart Job Proposal Generator with LangChain and RAG",
    version="0.1.0",
    lifespan=lifespan,
)

settings = get_settings()

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Correlation-ID"],
)


@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    """Add processing time and correlation ID to response headers.

    Args:
        request: Incoming request
        call_next: Next middleware in chain

    Returns:
        Response with added headers
    """
    start_time = time.time()

    correlation_id = request.headers.get("X-Correlation-ID", "")

    response = await call_next(request)

    process_time = (time.time() - start_time) * 1000
    response.headers["X-Process-Time-Ms"] = str(int(process_time))

    if correlation_id:
        response.headers["X-Correlation-ID"] = correlation_id

    return response


@app.exception_handler(SwiftmeException)
async def swiftme_exception_handler(request: Request, exc: SwiftmeException) -> JSONResponse:
    """Handle custom Swiftme exceptions.

    Args:
        request: Incoming request
        exc: Swiftme exception

    Returns:
        JSON error response
    """
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR

    if isinstance(exc, ProfileNotFoundError):
        status_code = status.HTTP_404_NOT_FOUND
    elif isinstance(exc, (VectorStoreError, DatabaseError)):
        status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    elif isinstance(exc, (LLMError, ProposalGenerationError)):
        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR

    error_response = ErrorResponse(
        success=False,
        error={
            "code": exc.__class__.__name__,
            "message": exc.message,
            "details": exc.details,
        },
    )

    logger.error(
        f"Application error: {exc.message}",
        extra={"error_type": exc.__class__.__name__, "details": exc.details},
    )

    return JSONResponse(
        status_code=status_code,
        content=error_response.model_dump(mode="json"),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Handle request validation errors.

    Args:
        request: Incoming request
        exc: Validation error

    Returns:
        JSON error response
    """
    error_response = ErrorResponse(
        success=False,
        error={
            "code": "VALIDATION_ERROR",
            "message": "Request validation failed",
            "details": {"errors": exc.errors()},
        },
    )

    logger.warning(
        f"Validation error",
        extra={"errors": exc.errors(), "body": exc.body},
    )

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=error_response.model_dump(mode="json"),
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle unexpected exceptions.

    Args:
        request: Incoming request
        exc: Exception

    Returns:
        JSON error response
    """
    error_response = ErrorResponse(
        success=False,
        error={
            "code": "INTERNAL_ERROR",
            "message": "An unexpected error occurred",
            "details": {"error": str(exc)} if settings.is_development else {},
        },
    )

    logger.exception(f"Unhandled exception: {exc}")

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=error_response.model_dump(mode="json"),
    )


app.include_router(profile.router)
app.include_router(proposal.router)
app.include_router(history.router)


@app.get("/", response_model=dict[str, str])
async def root() -> dict[str, str]:
    """Root endpoint with API information.

    Returns:
        API information
    """
    return {
        "name": "Swiftme Mini API",
        "version": "0.1.0",
        "description": "Smart Job Proposal Generator with LangChain and RAG",
        "docs": "/docs",
    }


@app.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Health check endpoint to verify service status.

    Returns:
        Service health status
    """
    db_status = "unknown"
    vector_store_status = "unknown"

    try:
        async for session in get_async_session():
            result = await session.execute(text("SELECT 1"))
            if result.scalar_one() == 1:
                db_status = "healthy"
            break
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        db_status = "unhealthy"

    try:
        async for vector_store in get_vector_store(settings):
            stats = vector_store.get_collection_stats()
            if "total_chunks" in stats:
                vector_store_status = "healthy"
            break
    except Exception as e:
        logger.error(f"Vector store health check failed: {e}")
        vector_store_status = "unhealthy"

    overall_status = (
        "healthy"
        if db_status == "healthy" and vector_store_status == "healthy"
        else "degraded"
    )

    return HealthResponse(
        status=overall_status,
        database=db_status,
        vector_store=vector_store_status,
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.APP_HOST,
        port=settings.APP_PORT,
        reload=settings.is_development,
        log_level=settings.LOG_LEVEL.lower(),
    )
