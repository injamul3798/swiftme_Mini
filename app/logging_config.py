"""Structured logging configuration using Loguru."""

import sys
from pathlib import Path

from loguru import logger

from app.config import get_settings


def setup_logging() -> None:
    """Configure Loguru with JSON formatting and correlation IDs."""
    settings = get_settings()

    logger.remove()

    log_format = (
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
        "<level>{message}</level>"
    )

    if settings.is_production:
        log_format = (
            "{{"
            '"timestamp": "{time:YYYY-MM-DD HH:mm:ss.SSS}", '
            '"level": "{level}", '
            '"logger": "{name}", '
            '"function": "{function}", '
            '"line": {line}, '
            '"message": "{message}", '
            '"extra": {extra}'
            "}}"
        )

    logger.add(
        sys.stdout,
        format=log_format,
        level=settings.LOG_LEVEL,
        colorize=not settings.is_production,
        serialize=settings.is_production,
        backtrace=True,
        diagnose=settings.is_development,
    )

    logs_dir = Path("logs")
    logs_dir.mkdir(exist_ok=True)

    logger.add(
        logs_dir / "swiftme_{time:YYYY-MM-DD}.log",
        format=log_format,
        level=settings.LOG_LEVEL,
        rotation="00:00",
        retention="30 days",
        compression="zip",
        serialize=True,
        enqueue=True,
    )

    logger.add(
        logs_dir / "errors_{time:YYYY-MM-DD}.log",
        format=log_format,
        level="ERROR",
        rotation="00:00",
        retention="90 days",
        compression="zip",
        serialize=True,
        backtrace=True,
        diagnose=True,
        enqueue=True,
    )

    logger.info(
        f"Logging configured: level={settings.LOG_LEVEL}, env={settings.APP_ENV}"
    )
