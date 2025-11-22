"""Pydantic schemas for API contracts and data validation."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


class FreelancerProfile(BaseModel):
    """Schema for freelancer profile data."""

    profile_id: str = Field(..., description="Unique identifier for the freelancer")
    name: str = Field(..., min_length=1, max_length=200, description="Freelancer name")
    skills: list[str] = Field(..., min_length=1, description="List of skills")
    experience: str = Field(
        ..., min_length=1, max_length=5000, description="Experience description"
    )
    past_projects: list[str] = Field(
        default_factory=list, description="List of past project descriptions"
    )
    hourly_rate: float | None = Field(default=None, ge=0, description="Hourly rate in USD")
    availability: str | None = Field(default=None, description="Availability information")
    bio: str | None = Field(default=None, max_length=2000, description="Professional bio")

    @field_validator("skills", mode="before")
    @classmethod
    def validate_skills(cls, v: Any) -> list[str]:
        """Ensure skills are non-empty strings."""
        if isinstance(v, str):
            v = [s.strip() for s in v.split(",")]
        return [skill for skill in v if skill and isinstance(skill, str)]


class ProfileSetupResponse(BaseModel):
    """Response schema for profile setup endpoint."""

    success: bool = Field(default=True)
    data: dict[str, Any] = Field(...)
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    class Data(BaseModel):
        """Nested data schema."""

        profile_id: str
        chunks_stored: int
        message: str


class JobPosting(BaseModel):
    """Schema for job posting input."""

    job_title: str = Field(..., min_length=1, max_length=300, description="Job title")
    job_description: str = Field(
        ..., min_length=20, max_length=10000, description="Full job description"
    )
    profile_id: str = Field(..., description="Profile ID to match against")
    budget_range: str | None = Field(default=None, description="Budget information")


class JobRequirements(BaseModel):
    """Structured output from job analysis."""

    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    project_scope: str = Field(default="")
    budget_min: float | None = Field(default=None, ge=0)
    budget_max: float | None = Field(default=None, ge=0)
    timeline: str | None = Field(default=None)
    key_priorities: list[str] = Field(default_factory=list)
    red_flags: list[str] = Field(default_factory=list)


class ProposalMetadata(BaseModel):
    """Metadata about the generated proposal."""

    confidence_score: float = Field(..., ge=0.0, le=1.0)
    matched_skills: list[str] = Field(default_factory=list)
    relevant_projects: list[str] = Field(default_factory=list)
    skill_match_percentage: float = Field(..., ge=0.0, le=100.0)
    budget_alignment: str = Field(..., description="Budget alignment status")
    timeline_feasibility: str = Field(..., description="Timeline feasibility assessment")


class GenerationStats(BaseModel):
    """Statistics about the generation process."""

    tokens_used: int = Field(..., ge=0)
    cost_usd: float = Field(..., ge=0.0)
    latency_ms: int = Field(..., ge=0)
    retrieval_chunks: int = Field(..., ge=0)


class ProposalGenerateResponse(BaseModel):
    """Response schema for proposal generation endpoint."""

    success: bool = Field(default=True)
    data: dict[str, Any] = Field(...)
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    class Data(BaseModel):
        """Nested data schema."""

        proposal_text: str
        metadata: ProposalMetadata
        generation_stats: GenerationStats


class ProposalHistorySummary(BaseModel):
    """Summary of a single proposal in history."""

    id: str = Field(..., description="Proposal ID")
    job_summary: str = Field(..., description="Brief job description")
    job_title: str = Field(..., description="Job title")
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    matched_skills: list[str] = Field(default_factory=list)
    created_at: datetime = Field(...)
    budget_range: str | None = Field(default=None)


class ProposalHistoryResponse(BaseModel):
    """Response schema for proposal history endpoint."""

    success: bool = Field(default=True)
    data: dict[str, Any] = Field(...)

    class Data(BaseModel):
        """Nested data schema."""

        proposals: list[ProposalHistorySummary]
        total_count: int = Field(..., ge=0)
        page: int = Field(..., ge=1)


class ErrorResponse(BaseModel):
    """Standard error response schema."""

    success: bool = Field(default=False)
    error: dict[str, Any] = Field(...)
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    class Error(BaseModel):
        """Nested error schema."""

        code: str
        message: str
        details: dict[str, Any] = Field(default_factory=dict)


class HealthResponse(BaseModel):
    """Health check response schema."""

    status: str = Field(..., description="Service status")
    database: str = Field(..., description="Database connection status")
    vector_store: str = Field(..., description="Vector store status")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
