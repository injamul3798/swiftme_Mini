"""Profile setup API endpoint."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from loguru import logger

from app.dependencies import get_correlation_id, get_vector_store
from app.exceptions import VectorStoreError
from app.models.schemas import FreelancerProfile, ProfileSetupResponse
from app.services.profile_matcher import ProfileMatcher
from app.services.vector_store import VectorStore

router = APIRouter(prefix="/api/v1/profile", tags=["profile"])


@router.post("/setup", response_model=ProfileSetupResponse, status_code=status.HTTP_201_CREATED)
async def setup_profile(
    profile: FreelancerProfile,
    vector_store: Annotated[VectorStore, Depends(get_vector_store)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
) -> ProfileSetupResponse:
    """Store freelancer profile in vector database.

    Args:
        profile: Freelancer profile data
        vector_store: ChromaDB vector store instance
        correlation_id: Request correlation ID

    Returns:
        Profile setup confirmation with chunk count

    Raises:
        HTTPException: If profile storage fails
    """
    try:
        logger.bind(correlation_id=correlation_id).info(
            f"Setting up profile",
            extra={
                "profile_id": profile.profile_id,
                "name": profile.name,
                "skills_count": len(profile.skills),
            },
        )

        matcher = ProfileMatcher(vector_store)
        chunks_stored = matcher.store_profile(profile)

        logger.bind(correlation_id=correlation_id).info(
            f"Profile setup completed",
            extra={
                "profile_id": profile.profile_id,
                "chunks_stored": chunks_stored,
            },
        )

        return ProfileSetupResponse(
            success=True,
            data={
                "profile_id": profile.profile_id,
                "chunks_stored": chunks_stored,
                "message": f"Profile for {profile.name} stored successfully with {chunks_stored} chunks",
            },
            timestamp=datetime.utcnow(),
        )

    except VectorStoreError as e:
        logger.bind(correlation_id=correlation_id).error(
            f"Profile setup failed: {e.message}",
            extra={"profile_id": profile.profile_id, "details": e.details},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "VECTOR_STORE_ERROR",
                "message": e.message,
                "details": e.details,
            },
        ) from e

    except Exception as e:
        logger.bind(correlation_id=correlation_id).error(
            f"Unexpected error during profile setup: {e}",
            extra={"profile_id": profile.profile_id},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "INTERNAL_ERROR",
                "message": "An unexpected error occurred during profile setup",
                "details": {"error": str(e)},
            },
        ) from e
