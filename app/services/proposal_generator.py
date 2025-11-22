"""Streaming proposal generator using LangChain LCEL with RAG."""

import time
from collections.abc import AsyncGenerator
from typing import Any

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough
from langchain_openai import ChatOpenAI
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import get_settings
from app.exceptions import ProposalGenerationError
from app.models.schemas import (
    GenerationStats,
    JobRequirements,
    ProposalMetadata,
)


class ProposalGenerator:
    """Generate personalized proposals using LangChain with streaming support."""

    def __init__(self) -> None:
        """Initialize the proposal generator with LangChain components."""
        settings = get_settings()

        self.llm = ChatOpenAI(
            model=settings.OPENAI_MODEL,
            temperature=settings.LLM_TEMPERATURE,
            max_tokens=settings.MAX_TOKENS,
            api_key=settings.OPENAI_API_KEY,
            streaming=settings.STREAMING_ENABLED,
        )

        self.prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    """You are an expert freelance proposal writer. Your goal is to create compelling, personalized proposals that win jobs.

Guidelines:
1. Start with a warm, professional greeting
2. Demonstrate you READ and UNDERSTOOD the job posting
3. Highlight RELEVANT experience from the freelancer's profile (use specific examples)
4. Propose a clear approach/solution aligned with project requirements
5. Include realistic timeline and next steps
6. Keep it concise (300-500 words) and professional
7. End with an engaging call-to-action

Tone: Professional yet approachable, confident but not arrogant.

CRITICAL: Only reference experiences and skills actually present in the freelancer's profile below. Do NOT invent or exaggerate.""",
                ),
                (
                    "human",
                    """Job Title: {job_title}

Job Requirements:
- Required Skills: {required_skills}
- Project Scope: {project_scope}
- Budget: {budget_info}
- Timeline: {timeline}
- Key Priorities: {priorities}

Freelancer Profile Name: {profile_name}

Relevant Experience from Profile:
{relevant_experience}

Generate a winning proposal that connects the freelancer's experience to this specific job.""",
                ),
            ]
        )

        self.chain = (
            RunnablePassthrough.assign(
                relevant_experience=lambda x: self._format_experience(
                    x.get("relevant_chunks", [])
                )
            )
            | self.prompt
            | self.llm
        )

        logger.info("ProposalGenerator initialized with streaming LangChain LCEL")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    async def generate_proposal_stream(
        self,
        job_title: str,
        job_requirements: JobRequirements,
        relevant_chunks: list[dict[str, Any]],
        profile_name: str,
    ) -> AsyncGenerator[str, None]:
        """Generate proposal with streaming output.

        Args:
            job_title: Job posting title
            job_requirements: Structured job requirements
            relevant_chunks: Relevant profile chunks from RAG
            profile_name: Freelancer name

        Yields:
            Chunks of generated proposal text

        Raises:
            ProposalGenerationError: If generation fails
        """
        try:
            logger.info(
                f"Generating proposal (streaming)",
                extra={
                    "job_title": job_title,
                    "chunks_count": len(relevant_chunks),
                },
            )

            input_data = {
                "job_title": job_title,
                "required_skills": ", ".join(job_requirements.required_skills)
                or "Not specified",
                "project_scope": job_requirements.project_scope or "Not specified",
                "budget_info": self._format_budget(job_requirements),
                "timeline": job_requirements.timeline or "Not specified",
                "priorities": ", ".join(job_requirements.key_priorities)
                or "Not specified",
                "profile_name": profile_name,
                "relevant_chunks": relevant_chunks,
            }

            async for chunk in self.chain.astream(input_data):
                if hasattr(chunk, "content"):
                    yield chunk.content
                else:
                    yield str(chunk)

        except Exception as e:
            logger.error(f"Proposal generation failed: {e}", extra={"job_title": job_title})
            raise ProposalGenerationError(f"Failed to generate proposal: {e}") from e

    async def generate_proposal(
        self,
        job_title: str,
        job_requirements: JobRequirements,
        relevant_chunks: list[dict[str, Any]],
        profile_name: str,
    ) -> tuple[str, int]:
        """Generate complete proposal (non-streaming).

        Args:
            job_title: Job posting title
            job_requirements: Structured job requirements
            relevant_chunks: Relevant profile chunks from RAG
            profile_name: Freelancer name

        Returns:
            Tuple of (proposal_text, tokens_used)

        Raises:
            ProposalGenerationError: If generation fails
        """
        full_text = ""
        async for chunk in self.generate_proposal_stream(
            job_title, job_requirements, relevant_chunks, profile_name
        ):
            full_text += chunk

        tokens_used = self._estimate_tokens(full_text)

        logger.info(
            f"Proposal generated",
            extra={
                "job_title": job_title,
                "length": len(full_text),
                "tokens": tokens_used,
            },
        )

        return full_text, tokens_used

    def calculate_metadata(
        self,
        job_requirements: JobRequirements,
        relevant_chunks: list[dict[str, Any]],
        profile_skills: list[str],
    ) -> ProposalMetadata:
        """Calculate proposal metadata and confidence scores.

        Args:
            job_requirements: Structured job requirements
            relevant_chunks: Retrieved profile chunks
            profile_skills: All profile skills

        Returns:
            Proposal metadata with confidence scores
        """
        required_skills = set(s.lower() for s in job_requirements.required_skills)
        profile_skills_lower = set(s.lower() for s in profile_skills)

        matched_skills = []
        for skill in profile_skills:
            if skill.lower() in required_skills:
                matched_skills.append(skill)

        skill_match_pct = (
            (len(matched_skills) / len(required_skills) * 100)
            if required_skills
            else 100.0
        )

        avg_similarity = (
            sum(chunk.get("similarity_score", 0) for chunk in relevant_chunks)
            / len(relevant_chunks)
            if relevant_chunks
            else 0.0
        )

        confidence_score = min(
            (skill_match_pct / 100 * 0.6) + (avg_similarity * 0.4), 1.0
        )

        relevant_projects = [
            chunk["metadata"].get("profile_name", "Unknown Project")
            for chunk in relevant_chunks
            if chunk["metadata"].get("section_type") == "project"
        ]

        budget_alignment = self._assess_budget_alignment(job_requirements)
        timeline_feasibility = self._assess_timeline(job_requirements)

        return ProposalMetadata(
            confidence_score=round(confidence_score, 2),
            matched_skills=matched_skills,
            relevant_projects=relevant_projects[:3],
            skill_match_percentage=round(skill_match_pct, 0),
            budget_alignment=budget_alignment,
            timeline_feasibility=timeline_feasibility,
        )

    def create_generation_stats(
        self, tokens_used: int, latency_ms: int, chunks_count: int
    ) -> GenerationStats:
        """Create generation statistics.

        Args:
            tokens_used: Number of tokens consumed
            latency_ms: Generation latency in milliseconds
            chunks_count: Number of RAG chunks used

        Returns:
            Generation statistics
        """
        settings = get_settings()
        cost_per_1k_input = 2.50 if "gpt-4o" in settings.OPENAI_MODEL else 0.50
        cost_per_1k_output = 10.00 if "gpt-4o" in settings.OPENAI_MODEL else 1.50

        estimated_input_tokens = tokens_used * 0.4
        estimated_output_tokens = tokens_used * 0.6

        cost_usd = (
            (estimated_input_tokens / 1000 * cost_per_1k_input / 1000)
            + (estimated_output_tokens / 1000 * cost_per_1k_output / 1000)
        )

        return GenerationStats(
            tokens_used=tokens_used,
            cost_usd=round(cost_usd, 4),
            latency_ms=latency_ms,
            retrieval_chunks=chunks_count,
        )

    def _format_experience(self, chunks: list[dict[str, Any]]) -> str:
        """Format relevant experience chunks for prompt.

        Args:
            chunks: List of relevant chunks

        Returns:
            Formatted experience string
        """
        if not chunks:
            return "No specific relevant experience found."

        formatted = []
        for i, chunk in enumerate(chunks, 1):
            section_type = chunk["metadata"].get("section_type", "unknown")
            similarity = chunk.get("similarity_score", 0)
            text = chunk["text"]

            formatted.append(
                f"[{i}] {section_type.title()} (relevance: {similarity:.0%}):\n{text}"
            )

        return "\n\n".join(formatted)

    def _format_budget(self, requirements: JobRequirements) -> str:
        """Format budget information for prompt.

        Args:
            requirements: Job requirements

        Returns:
            Formatted budget string
        """
        if requirements.budget_min and requirements.budget_max:
            return f"${requirements.budget_min:,.0f} - ${requirements.budget_max:,.0f}"
        elif requirements.budget_min:
            return f"From ${requirements.budget_min:,.0f}"
        elif requirements.budget_max:
            return f"Up to ${requirements.budget_max:,.0f}"
        return "Not specified"

    def _assess_budget_alignment(self, requirements: JobRequirements) -> str:
        """Assess budget alignment.

        Args:
            requirements: Job requirements

        Returns:
            Budget alignment status
        """
        if not requirements.budget_min and not requirements.budget_max:
            return "not_specified"

        budget = requirements.budget_max or requirements.budget_min or 0

        if budget >= 3000:
            return "excellent"
        elif budget >= 1500:
            return "good"
        elif budget >= 500:
            return "moderate"
        else:
            return "low"

    def _assess_timeline(self, requirements: JobRequirements) -> str:
        """Assess timeline feasibility.

        Args:
            requirements: Job requirements

        Returns:
            Timeline feasibility status
        """
        if not requirements.timeline:
            return "flexible"

        timeline_lower = requirements.timeline.lower()

        if any(word in timeline_lower for word in ["urgent", "asap", "immediate"]):
            return "urgent"
        elif any(word in timeline_lower for word in ["week", "days"]):
            return "short_term"
        elif any(word in timeline_lower for word in ["month", "flexible"]):
            return "confirmed"
        else:
            return "flexible"

    def _estimate_tokens(self, text: str) -> int:
        """Estimate token count for text.

        Args:
            text: Text to estimate

        Returns:
            Estimated token count
        """
        return int(len(text.split()) * 1.3)
