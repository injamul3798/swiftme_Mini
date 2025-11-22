"""Quick start script for Swiftme Mini."""

import sys
from pathlib import Path

try:
    import uvicorn
    from app.config import get_settings
except ImportError:
    print("ERROR: Dependencies not installed!")
    print("\nPlease run: pip install -r requirements.txt")
    sys.exit(1)


def check_env_file():
    """Check if .env file exists."""
    env_file = Path(".env")
    if not env_file.exists():
        print("WARNING: .env file not found!")
        print("\nPlease create .env file from .env.example:")
        print("  cp .env.example .env")
        print("\nThen configure your OpenAI API key and database URL.")
        sys.exit(1)


def main():
    """Start the FastAPI server."""
    check_env_file()

    try:
        settings = get_settings()
        print(f"\n{'='*60}")
        print(f"  Swiftme Mini - Smart Job Proposal Generator")
        print(f"{'='*60}")
        print(f"\n  Environment: {settings.APP_ENV}")
        print(f"  Model: {settings.OPENAI_MODEL}")
        print(f"  Database: {settings.DATABASE_URL.split('@')[-1]}")
        print(f"  ChromaDB: {settings.CHROMA_PERSIST_DIR}")
        print(f"\n  Server: http://{settings.APP_HOST}:{settings.APP_PORT}")
        print(f"  Docs: http://{settings.APP_HOST}:{settings.APP_PORT}/docs")
        print(f"  Health: http://{settings.APP_HOST}:{settings.APP_PORT}/health")
        print(f"\n{'='*60}\n")

        uvicorn.run(
            "app.main:app",
            host=settings.APP_HOST,
            port=settings.APP_PORT,
            reload=settings.is_development,
            log_level=settings.LOG_LEVEL.lower(),
        )

    except Exception as e:
        print(f"\nERROR: Failed to start server: {e}")
        print("\nPlease check your configuration in .env file")
        sys.exit(1)


if __name__ == "__main__":
    main()
