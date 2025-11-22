"""Profile matching service with RAG retrieval and chunking logic."""

from typing import Any

from loguru import logger

from app.config import get_settings
from app.exceptions import ProfileNotFoundError, VectorStoreError
from app.models.schemas import FreelancerProfile, JobRequirements
from app.services.vector_store import VectorStore


class ProfileMatcher:
    """Match job requirements to freelancer profiles using RAG."""

    def __init__(self, vector_store: VectorStore) -> None:
        """Initialize profile matcher with vector store.

        Args:
            vector_store: ChromaDB vector store instance
        """
        self.vector_store = vector_store
        self.settings = get_settings()

    def chunk_profile(self, profile: FreelancerProfile) -> tuple[list[str], list[dict[str, Any]]]:
        """Chunk freelancer profile into semantic sections for vector storage.

        Args:
            profile: Freelancer profile data

        Returns:
            Tuple of (chunks, metadatas)
        """
        chunks = []
        metadatas = []

        skills_chunk = f"Skills: {', '.join(profile.skills)}"
        chunks.append(skills_chunk)
        metadatas.append(
            {
                "section_type": "skills",
                "profile_name": profile.name,
            }
        )

        experience_chunk = f"Experience:\n{profile.experience}"
        if profile.bio:
            experience_chunk = f"{profile.bio}\n\n{experience_chunk}"
        chunks.append(experience_chunk)
        metadatas.append(
            {
                "section_type": "experience",
                "profile_name": profile.name,
            }
        )

        for i, project in enumerate(profile.past_projects):
            project_chunk = f"Past Project {i+1}:\n{project}"
            chunks.append(project_chunk)
            metadatas.append(
                {
                    "section_type": "project",
                    "profile_name": profile.name,
                    "project_index": i,
                }
            )

        if profile.hourly_rate or profile.availability:
            availability_chunk = ""
            if profile.hourly_rate:
                availability_chunk += f"Hourly Rate: ${profile.hourly_rate}/hour\n"
            if profile.availability:
                availability_chunk += f"Availability: {profile.availability}"
            chunks.append(availability_chunk)
            metadatas.append(
                {
                    "section_type": "availability",
                    "profile_name": profile.name,
                }
            )

        logger.info(
            f"Chunked profile into {len(chunks)} sections",
            extra={"profile_id": profile.profile_id, "chunks": len(chunks)},
        )

        return chunks, metadatas

    def store_profile(self, profile: FreelancerProfile) -> int:
        """Store freelancer profile in vector database.

        Args:
            profile: Freelancer profile to store

        Returns:
            Number of chunks stored

        Raises:
            VectorStoreError: If storage fails
        """
        chunks, metadatas = self.chunk_profile(profile)

        chunks_stored = self.vector_store.upsert_profile(
            profile_id=profile.profile_id,
            chunks=chunks,
            metadatas=metadatas,
        )

        logger.info(
            f"Profile stored successfully",
            extra={
                "profile_id": profile.profile_id,
                "chunks_stored": chunks_stored,
            },
        )

        return chunks_stored

    def retrieve_relevant_context(
        self, profile_id: str, job_requirements: JobRequirements
    ) -> list[dict[str, Any]]:
        """Retrieve relevant profile sections based on job requirements.

        Args:
            profile_id: Profile ID to retrieve from
            job_requirements: Structured job requirements

        Returns:
            List of relevant profile chunks with metadata

        Raises:
            ProfileNotFoundError: If profile doesn't exist
            VectorStoreError: If retrieval fails
        """
        if not self.vector_store.get_profile_exists(profile_id):
            raise ProfileNotFoundError(
                f"Profile not found: {profile_id}",
                details={"profile_id": profile_id},
            )

        search_query = self._build_search_query(job_requirements)

        results = self.vector_store.search_relevant_experience(
            query=search_query,
            profile_id=profile_id,
            top_k=self.settings.MAX_RETRIEVAL_CHUNKS,
            similarity_threshold=self.settings.SIMILARITY_THRESHOLD,
        )

        logger.info(
            f"Retrieved relevant context",
            extra={
                "profile_id": profile_id,
                "results_count": len(results),
                "query_length": len(search_query),
            },
        )

        return results

    def _build_search_query(self, requirements: JobRequirements) -> str:
        """Build semantic search query from job requirements.

        Args:
            requirements: Structured job requirements

        Returns:
            Search query string
        """
        query_parts = []

        if requirements.required_skills:
            query_parts.append(f"Required skills: {', '.join(requirements.required_skills)}")

        if requirements.project_scope:
            query_parts.append(f"Project: {requirements.project_scope}")

        if requirements.key_priorities:
            query_parts.append(
                f"Priorities: {', '.join(requirements.key_priorities)}"
            )

        query = " | ".join(query_parts)

        logger.debug(
            f"Built search query",
            extra={"query_length": len(query), "parts": len(query_parts)},
        )

        return query
