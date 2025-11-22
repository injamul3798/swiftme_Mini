"""Proposal history API endpoint."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from loguru import logger
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_correlation_id, get_db_session
from app.models.db_models import ProposalHistory
from app.models.schemas import ProposalHistoryResponse, ProposalHistorySummary

router = APIRouter(prefix="/api/v1/proposal", tags=["proposal"])


@router.get("/history", response_model=ProposalHistoryResponse)
async def get_proposal_history(
    profile_id: str = Query(..., description="Profile ID to retrieve history for"),
    limit: int = Query(5, ge=1, le=50, description="Number of proposals to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    db: AsyncSession = Depends(get_db_session),
    correlation_id: str = Depends(get_correlation_id),
) -> ProposalHistoryResponse:
    """Retrieve proposal generation history for a profile.

    Args:
        profile_id: Profile ID to filter by
        limit: Maximum number of results to return
        offset: Number of results to skip (pagination)
        db: Database session
        correlation_id: Request correlation ID

    Returns:
        List of proposal summaries

    Raises:
        HTTPException: If database query fails
    """
    try:
        logger.bind(correlation_id=correlation_id).info(
            f"Fetching proposal history",
            extra={
                "profile_id": profile_id,
                "limit": limit,
                "offset": offset,
            },
        )

        count_stmt = select(func.count()).select_from(ProposalHistory).where(
            ProposalHistory.profile_id == profile_id
        )
        total_count_result = await db.execute(count_stmt)
        total_count = total_count_result.scalar_one()

        stmt = (
            select(ProposalHistory)
            .where(ProposalHistory.profile_id == profile_id)
            .order_by(desc(ProposalHistory.created_at))
            .limit(limit)
            .offset(offset)
        )

        result = await db.execute(stmt)
        proposals = result.scalars().all()

        proposal_summaries = [
            ProposalHistorySummary(
                id=p.id,
                job_summary=p.job_summary,
                job_title=p.job_title,
                confidence_score=p.confidence_score,
                matched_skills=p.matched_skills,
                created_at=p.created_at,
                budget_range=p.budget_range,
            )
            for p in proposals
        ]

        page = (offset // limit) + 1 if limit > 0 else 1

        logger.bind(correlation_id=correlation_id).info(
            f"Retrieved proposal history",
            extra={
                "profile_id": profile_id,
                "count": len(proposal_summaries),
                "total": total_count,
            },
        )

        return ProposalHistoryResponse(
            success=True,
            data={
                "proposals": proposal_summaries,
                "total_count": total_count,
                "page": page,
            },
        )

    except Exception as e:
        logger.bind(correlation_id=correlation_id).error(
            f"Failed to retrieve proposal history: {e}",
            extra={"profile_id": profile_id},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "DATABASE_ERROR",
                "message": "Failed to retrieve proposal history",
                "details": {"error": str(e)},
            },
        ) from e
