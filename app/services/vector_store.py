"""ChromaDB vector store for freelancer profile storage and retrieval."""

import os
from typing import Any

import chromadb
from chromadb.config import Settings as ChromaSettings
from loguru import logger

from app.exceptions import VectorStoreError

# Set infinite timeout for model download
os.environ["HTTPX_TIMEOUT"] = "0"


class VectorStore:
    """Manage ChromaDB operations for profile storage and semantic search."""

    def __init__(self, persist_directory: str, collection_name: str) -> None:
        """Initialize ChromaDB client and collection.

        Args:
            persist_directory: Directory to persist vector data
            collection_name: Name of the ChromaDB collection
        """
        self.persist_directory = persist_directory
        self.collection_name = collection_name

        try:
            self.client = chromadb.PersistentClient(
                path=persist_directory,
                settings=ChromaSettings(
                    anonymized_telemetry=False,
                    allow_reset=True,
                ),
            )
            self.collection = self.client.get_or_create_collection(
                name=collection_name,
                metadata={"hnsw:space": "cosine"},
            )
            logger.info(
                f"ChromaDB initialized: collection={collection_name}, "
                f"count={self.collection.count()}"
            )
        except Exception as e:
            logger.error(f"Failed to initialize ChromaDB: {e}")
            raise VectorStoreError(f"Failed to initialize vector store: {e}") from e

    def upsert_profile(
        self,
        profile_id: str,
        chunks: list[str],
        metadatas: list[dict[str, Any]],
    ) -> int:
        """Store or update freelancer profile chunks in vector database.

        Args:
            profile_id: Unique identifier for the profile
            chunks: List of text chunks to store
            metadatas: List of metadata dicts for each chunk

        Returns:
            Number of chunks stored

        Raises:
            VectorStoreError: If storage operation fails
        """
        try:
            self._delete_profile(profile_id)

            ids = [f"{profile_id}_{i}" for i in range(len(chunks))]

            for metadata in metadatas:
                metadata["profile_id"] = profile_id

            self.collection.add(
                documents=chunks,
                metadatas=metadatas,
                ids=ids,
            )

            logger.info(
                f"Upserted profile chunks",
                extra={
                    "profile_id": profile_id,
                    "chunks_count": len(chunks),
                },
            )

            return len(chunks)

        except Exception as e:
            logger.error(f"Failed to upsert profile: {e}", extra={"profile_id": profile_id})
            raise VectorStoreError(f"Failed to upsert profile: {e}") from e

    def search_relevant_experience(
        self,
        query: str,
        profile_id: str,
        top_k: int = 5,
        similarity_threshold: float = 0.7,
    ) -> list[dict[str, Any]]:
        """Search for relevant profile chunks based on job requirements.

        Args:
            query: Search query (job description or requirements)
            profile_id: Profile ID to filter results
            top_k: Number of top results to return
            similarity_threshold: Minimum similarity score (0-1)

        Returns:
            List of relevant chunks with metadata and scores

        Raises:
            VectorStoreError: If search operation fails
        """
        try:
            results = self.collection.query(
                query_texts=[query],
                n_results=top_k,
                where={"profile_id": profile_id},
                include=["documents", "metadatas", "distances"],
            )

            if not results["documents"] or not results["documents"][0]:
                logger.warning(
                    f"No results found for profile",
                    extra={"profile_id": profile_id},
                )
                return []

            filtered_results = []
            documents = results["documents"][0]
            metadatas = results["metadatas"][0] if results["metadatas"] else []
            distances = results["distances"][0] if results["distances"] else []

            for i, (doc, metadata, distance) in enumerate(
                zip(documents, metadatas, distances)
            ):
                similarity = 1 - distance

                if similarity >= similarity_threshold:
                    filtered_results.append(
                        {
                            "text": doc,
                            "metadata": metadata,
                            "similarity_score": round(similarity, 3),
                            "rank": i + 1,
                        }
                    )

            logger.info(
                f"Search completed",
                extra={
                    "profile_id": profile_id,
                    "total_results": len(documents),
                    "filtered_results": len(filtered_results),
                    "threshold": similarity_threshold,
                },
            )

            return filtered_results

        except Exception as e:
            logger.error(
                f"Failed to search vector store: {e}",
                extra={"profile_id": profile_id},
            )
            raise VectorStoreError(f"Failed to search vector store: {e}") from e

    def _delete_profile(self, profile_id: str) -> None:
        """Delete all chunks for a profile (used during upsert).

        Args:
            profile_id: Profile ID to delete
        """
        try:
            results = self.collection.get(
                where={"profile_id": profile_id},
                include=["metadatas"],
            )

            if results["ids"]:
                self.collection.delete(ids=results["ids"])
                logger.debug(
                    f"Deleted existing profile chunks",
                    extra={"profile_id": profile_id, "count": len(results["ids"])},
                )

        except Exception as e:
            logger.warning(
                f"Failed to delete profile (may not exist): {e}",
                extra={"profile_id": profile_id},
            )

    def get_profile_exists(self, profile_id: str) -> bool:
        """Check if a profile exists in the vector store.

        Args:
            profile_id: Profile ID to check

        Returns:
            True if profile exists, False otherwise
        """
        try:
            results = self.collection.get(
                where={"profile_id": profile_id},
                limit=1,
            )
            return len(results["ids"]) > 0

        except Exception as e:
            logger.error(
                f"Failed to check profile existence: {e}",
                extra={"profile_id": profile_id},
            )
            return False

    def get_collection_stats(self) -> dict[str, Any]:
        """Get statistics about the vector store collection.

        Returns:
            Dictionary with collection statistics
        """
        try:
            return {
                "total_chunks": self.collection.count(),
                "collection_name": self.collection_name,
                "persist_directory": self.persist_directory,
            }
        except Exception as e:
            logger.error(f"Failed to get collection stats: {e}")
            return {"error": str(e)}
