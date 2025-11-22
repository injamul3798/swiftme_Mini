"""Custom exception hierarchy for Swiftme Mini."""

from typing import Any


class SwiftmeException(Exception):
    """Base exception for all Swiftme errors."""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class ConfigurationError(SwiftmeException):
    """Raised when configuration is invalid or missing."""

    pass


class VectorStoreError(SwiftmeException):
    """Raised when ChromaDB operations fail."""

    pass


class LLMError(SwiftmeException):
    """Raised when OpenAI/LangChain operations fail."""

    pass


class DatabaseError(SwiftmeException):
    """Raised when database operations fail."""

    pass


class ValidationError(SwiftmeException):
    """Raised when input validation fails."""

    pass


class ProfileNotFoundError(SwiftmeException):
    """Raised when a requested profile doesn't exist."""

    pass


class ProposalGenerationError(SwiftmeException):
    """Raised when proposal generation fails."""

    pass
