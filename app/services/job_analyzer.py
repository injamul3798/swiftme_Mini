"""LangChain-based job posting analyzer with structured output."""

import re
from typing import Any

from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import get_settings
from app.exceptions import LLMError
from app.models.schemas import JobRequirements


class JobAnalyzer:
    """Analyze job postings and extract structured requirements using LangChain."""

    def __init__(self) -> None:
        """Initialize the job analyzer with LangChain components."""
        settings = get_settings()

        self.llm = ChatOpenAI(
            model=settings.OPENAI_MODEL,
            temperature=0.2,
            api_key=settings.OPENAI_API_KEY,
        )

        self.parser = JsonOutputParser(pydantic_object=JobRequirements)

        self.prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    """You are an expert job posting analyzer. Extract structured information from job descriptions.

Your task:
1. Identify required vs preferred skills (be specific, e.g., "React" not just "frontend")
2. Extract budget information (parse ranges like "$1000-2000" or "up to $5k")
3. Identify timeline/deadline requirements
4. Detect key project priorities
5. Flag potential red flags (unrealistic requirements, low budget vs scope, etc.)

Format your response as JSON matching this schema:
{format_instructions}

Be thorough but concise. Focus on technical requirements and project specifics.""",
                ),
                ("human", "Job Title: {job_title}\n\nJob Description:\n{job_description}"),
            ]
        )

        self.chain = self.prompt | self.llm | self.parser

        logger.info("JobAnalyzer initialized with LangChain LCEL")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    async def analyze_job(self, job_title: str, job_description: str) -> JobRequirements:
        """Analyze a job posting and extract structured requirements.

        Args:
            job_title: Title of the job posting
            job_description: Full job description text

        Returns:
            Structured job requirements

        Raises:
            LLMError: If analysis fails after retries
        """
        try:
            logger.info(
                f"Analyzing job posting",
                extra={"job_title": job_title, "desc_length": len(job_description)},
            )

            result = await self.chain.ainvoke(
                {
                    "job_title": job_title,
                    "job_description": job_description,
                    "format_instructions": self.parser.get_format_instructions(),
                }
            )

            self._extract_budget_from_text(job_description, result)

            requirements = JobRequirements(**result)

            logger.info(
                f"Job analysis completed",
                extra={
                    "required_skills": len(requirements.required_skills),
                    "preferred_skills": len(requirements.preferred_skills),
                    "has_budget": requirements.budget_min is not None,
                },
            )

            return requirements

        except Exception as e:
            logger.error(f"Job analysis failed: {e}", extra={"job_title": job_title})
            raise LLMError(f"Failed to analyze job posting: {e}") from e

    def _extract_budget_from_text(
        self, description: str, result: dict[str, Any]
    ) -> None:
        """Extract budget information from text if LLM didn't capture it.

        Args:
            description: Job description text
            result: Parsed result dictionary to update
        """
        if result.get("budget_min") is None or result.get("budget_max") is None:
            budget_patterns = [
                r"\$(\d+(?:,\d{3})*(?:\.\d{2})?)\s*-\s*\$(\d+(?:,\d{3})*(?:\.\d{2})?)",
                r"budget:?\s*\$?(\d+(?:,\d{3})*(?:\.\d{2})?)\s*-\s*\$?(\d+(?:,\d{3})*(?:\.\d{2})?)",
                r"(\d+(?:,\d{3})*(?:\.\d{2})?)\s*-\s*(\d+(?:,\d{3})*(?:\.\d{2})?)\s*(?:USD|dollars|\$)",
            ]

            for pattern in budget_patterns:
                match = re.search(pattern, description, re.IGNORECASE)
                if match:
                    try:
                        min_val = float(match.group(1).replace(",", ""))
                        max_val = float(match.group(2).replace(",", ""))
                        result["budget_min"] = min_val
                        result["budget_max"] = max_val
                        logger.debug(f"Extracted budget: ${min_val} - ${max_val}")
                        break
                    except (ValueError, IndexError):
                        continue
