"""Proposal generation API endpoint with streaming support."""

import json
import time
import uuid
from collections.abc import AsyncGenerator
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.dependencies import get_correlation_id, get_db_session, get_vector_store
from app.exceptions import LLMError, ProfileNotFoundError, ProposalGenerationError, VectorStoreError
from app.models.db_models import ProposalHistory
from app.models.schemas import FreelancerProfile, JobPosting
from app.services.job_analyzer import JobAnalyzer
from app.services.profile_matcher import ProfileMatcher
from app.services.proposal_generator import ProposalGenerator
from app.services.vector_store import VectorStore

router = APIRouter(prefix="/api/v1/proposal", tags=["proposal"])


async def _save_proposal_to_db(
    db: AsyncSession,
    proposal_id: str,
    profile_id: str,
    job_title: str,
    job_description: str,
    proposal_text: str,
    metadata: dict,
    stats: dict,
) -> None:
    """Save generated proposal to database (fire-and-forget).

    Args:
        db: Database session
        proposal_id: Unique proposal ID
        profile_id: Profile ID
        job_title: Job title
        job_description: Job description
        proposal_text: Generated proposal
        metadata: Proposal metadata
        stats: Generation statistics
    """
    try:
        job_summary = job_description[:500] if len(job_description) > 500 else job_description

        proposal_record = ProposalHistory(
            id=proposal_id,
            profile_id=profile_id,
            job_title=job_title,
            job_description=job_description,
            job_summary=job_summary,
            proposal_text=proposal_text,
            confidence_score=metadata["confidence_score"],
            matched_skills=metadata["matched_skills"],
            relevant_projects=metadata["relevant_projects"],
            skill_match_percentage=metadata["skill_match_percentage"],
            budget_alignment=metadata["budget_alignment"],
            timeline_feasibility=metadata["timeline_feasibility"],
            budget_range=None,
            tokens_used=stats["tokens_used"],
            cost_usd=stats["cost_usd"],
            latency_ms=stats["latency_ms"],
            retrieval_chunks=stats["retrieval_chunks"],
            extra_metadata={},
        )

        db.add(proposal_record)
        await db.commit()

        logger.info(
            f"Proposal saved to database",
            extra={"proposal_id": proposal_id, "profile_id": profile_id},
        )

    except Exception as e:
        logger.error(f"Failed to save proposal to database: {e}", extra={"proposal_id": proposal_id})
        await db.rollback()


@router.post("/generate", response_class=EventSourceResponse)
async def generate_proposal(
    job_posting: JobPosting,
    vector_store: Annotated[VectorStore, Depends(get_vector_store)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
) -> EventSourceResponse:
    """Generate proposal with streaming SSE response.

    Args:
        job_posting: Job posting data
        vector_store: ChromaDB vector store
        db: Database session
        correlation_id: Request correlation ID

    Returns:
        Server-Sent Events stream with proposal chunks

    Raises:
        HTTPException: If generation fails
    """

    async def event_generator() -> AsyncGenerator[dict, None]:
        """Generate SSE events for streaming proposal."""
        start_time = time.time()
        proposal_id = f"prop_{uuid.uuid4().hex[:12]}"
        full_proposal = ""

        try:
            logger.bind(correlation_id=correlation_id).info(
                f"Starting proposal generation",
                extra={
                    "proposal_id": proposal_id,
                    "profile_id": job_posting.profile_id,
                    "job_title": job_posting.job_title,
                },
            )

            yield {
                "event": "status",
                "data": json.dumps({"status": "analyzing_job", "message": "Analyzing job requirements..."}),
            }

            analyzer = JobAnalyzer()
            job_requirements = await analyzer.analyze_job(
                job_posting.job_title, job_posting.job_description
            )

            yield {
                "event": "status",
                "data": json.dumps(
                    {
                        "status": "retrieving_profile",
                        "message": "Retrieving relevant experience...",
                    }
                ),
            }

            matcher = ProfileMatcher(vector_store)
            relevant_chunks = matcher.retrieve_relevant_context(
                job_posting.profile_id, job_requirements
            )

            stmt = select(ProposalHistory).where(
                ProposalHistory.profile_id == job_posting.profile_id
            ).limit(1)
            result = await db.execute(stmt)
            sample_profile = result.scalar_one_or_none()

            profile_name = "Freelancer"
            profile_skills = job_requirements.required_skills

            yield {
                "event": "status",
                "data": json.dumps({"status": "generating", "message": "Generating proposal..."}),
            }

            generator = ProposalGenerator()

            async for chunk in generator.generate_proposal_stream(
                job_title=job_posting.job_title,
                job_requirements=job_requirements,
                relevant_chunks=relevant_chunks,
                profile_name=profile_name,
            ):
                full_proposal += chunk
                yield {"event": "proposal_chunk", "data": json.dumps({"text": chunk})}

            latency_ms = int((time.time() - start_time) * 1000)
            tokens_used = generator._estimate_tokens(full_proposal)

            metadata_obj = generator.calculate_metadata(
                job_requirements, relevant_chunks, profile_skills
            )

            stats_obj = generator.create_generation_stats(
                tokens_used, latency_ms, len(relevant_chunks)
            )

            final_data = {
                "proposal_id": proposal_id,
                "metadata": {
                    "confidence_score": metadata_obj.confidence_score,
                    "matched_skills": metadata_obj.matched_skills,
                    "relevant_projects": metadata_obj.relevant_projects,
                    "skill_match_percentage": metadata_obj.skill_match_percentage,
                    "budget_alignment": metadata_obj.budget_alignment,
                    "timeline_feasibility": metadata_obj.timeline_feasibility,
                },
                "generation_stats": {
                    "tokens_used": stats_obj.tokens_used,
                    "cost_usd": stats_obj.cost_usd,
                    "latency_ms": stats_obj.latency_ms,
                    "retrieval_chunks": stats_obj.retrieval_chunks,
                },
            }

            yield {"event": "complete", "data": json.dumps(final_data)}

            await _save_proposal_to_db(
                db=db,
                proposal_id=proposal_id,
                profile_id=job_posting.profile_id,
                job_title=job_posting.job_title,
                job_description=job_posting.job_description,
                proposal_text=full_proposal,
                metadata=final_data["metadata"],
                stats=final_data["generation_stats"],
            )

            logger.bind(correlation_id=correlation_id).info(
                f"Proposal generation completed",
                extra={
                    "proposal_id": proposal_id,
                    "latency_ms": latency_ms,
                    "tokens": tokens_used,
                },
            )

        except ProfileNotFoundError as e:
            logger.bind(correlation_id=correlation_id).error(f"Profile not found: {e.message}")
            yield {
                "event": "error",
                "data": json.dumps(
                    {
                        "code": "PROFILE_NOT_FOUND",
                        "message": e.message,
                        "details": e.details,
                    }
                ),
            }

        except (LLMError, ProposalGenerationError) as e:
            logger.bind(correlation_id=correlation_id).error(f"Generation failed: {e.message}")
            yield {
                "event": "error",
                "data": json.dumps(
                    {
                        "code": "GENERATION_ERROR",
                        "message": e.message,
                        "details": e.details,
                    }
                ),
            }

        except Exception as e:
            logger.bind(correlation_id=correlation_id).error(f"Unexpected error: {e}")
            yield {
                "event": "error",
                "data": json.dumps(
                    {
                        "code": "INTERNAL_ERROR",
                        "message": "An unexpected error occurred",
                        "details": {"error": str(e)},
                    }
                ),
            }

    return EventSourceResponse(event_generator())
