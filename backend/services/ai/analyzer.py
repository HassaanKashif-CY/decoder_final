
import json
from typing import Any

from backend.models.analysis import RequirementAnalysis
from backend.models.document import RequirementCandidate
from backend.services.ai.client import OpenAIClient
from backend.services.ai.prompts import SYSTEM_PROMPT, USER_PROMPT
from backend.services.ai.validator import AnalysisValidator


class DocumentAnalysisError(Exception):
    """Raised when requirement analysis cannot be completed safely."""


class RequirementAnalysisError(DocumentAnalysisError):
    """Backward-compatible analysis exception."""


class RequirementAnalyzer:
    def __init__(self, batch_size: int = 5):
        self.client = OpenAIClient()
        self.validator = AnalysisValidator()
        self.batch_size = max(1, batch_size)

    def analyze(
        self,
        document_name: str,
        requirement: RequirementCandidate,
    ) -> RequirementAnalysis:
        results = self.analyze_many(
            document_name=document_name,
            requirements=[requirement],
        )

        if not results:
            raise DocumentAnalysisError(
                "The requirement could not be analyzed. "
                "Please retry with an official, text-searchable PDF."
            )

        return results[0]

    def analyze_many(
        self,
        document_name: str,
        requirements: list[RequirementCandidate],
    ) -> list[RequirementAnalysis]:
        if not requirements:
            return []

        results: list[RequirementAnalysis] = []
        total_batches = (
            len(requirements) + self.batch_size - 1
        ) // self.batch_size

        for start in range(0, len(requirements), self.batch_size):
            batch = requirements[start:start + self.batch_size]
            batch_number = start // self.batch_size + 1

            print(
                f"AI analysis batch {batch_number}/{total_batches} "
                f"({len(batch)} requirements)"
            )

            batch_results = self._analyze_batch(
                document_name=document_name,
                requirements=batch,
            )
            results.extend(batch_results)

        return results

    def _analyze_batch(
        self,
        document_name: str,
        requirements: list[RequirementCandidate],
    ) -> list[RequirementAnalysis]:
        source_requirements: list[dict[str, Any]] = []

        for index, requirement in enumerate(requirements, start=1):
            source_requirements.append(
                {
                    "batch_index": index,
                    "candidate_id": requirement.candidate_id,
                    "source_reference": requirement.source_reference,
                    "source_title": requirement.source_title,
                    "source_text": requirement.source_text,
                    "page_start": requirement.page_start,
                    "page_end": requirement.page_end,
                    "source_block_ids": requirement.source_block_ids,
                    "hierarchy_path": getattr(
                        requirement, "hierarchy_path", []
                    ),
                }
            )

        prompt = USER_PROMPT.format(
            document_name=document_name,
            requirements=json.dumps(
                source_requirements,
                ensure_ascii=False,
                indent=2,
            ),
        )

        try:
            response = self.client.generate_json(
                instructions=SYSTEM_PROMPT,
                input_text=prompt,
                schema=self._batch_response_schema(),
                schema_name="requirement_analysis_batch",
            )
        except Exception as exc:
            raise DocumentAnalysisError(
                "AI analysis could not be completed. "
                "Check the OpenAI API key, available credits, "
                "model configuration and server logs, then retry."
            ) from exc

        if not isinstance(response, dict):
            raise DocumentAnalysisError(
                "The AI service returned an invalid response. Please retry."
            )

        raw_analyses = response.get("analyses")
        if not isinstance(raw_analyses, list):
            raise DocumentAnalysisError(
                "The AI response did not contain a valid analyses list."
            )

        if len(raw_analyses) != len(requirements):
            raise DocumentAnalysisError(
                "The AI service returned an incomplete analysis batch. "
                f"Expected {len(requirements)} results, "
                f"received {len(raw_analyses)}. Please retry."
            )

        results: list[RequirementAnalysis] = []

        for requirement, raw_analysis in zip(
            requirements, raw_analyses
        ):
            if not isinstance(raw_analysis, dict):
                raise DocumentAnalysisError(
                    "An AI result was malformed. Please retry this document."
                )

            analysis = self._protect_source_fields(
                response=raw_analysis,
                requirement=requirement,
            )

            try:
                validated = self.validator.validate(
                    analysis=analysis,
                    source_reference=requirement.source_reference,
                    source_text=requirement.source_text,
                )
            except Exception as exc:
                raise DocumentAnalysisError(
                    "The analysis could not pass source-validation checks "
                    f"for {requirement.source_reference or requirement.candidate_id}. "
                    "Please retry or check the source PDF."
                ) from exc

            results.append(validated)

        return results

    def _protect_source_fields(
        self,
        response: dict[str, Any],
        requirement: RequirementCandidate,
    ) -> dict[str, Any]:
        # Source text and references always come from the extracted PDF,
        # never from generated AI text.
        response["source_reference"] = requirement.source_reference
        response["source_title"] = requirement.source_title
        response["source_text"] = requirement.source_text
        response["page_start"] = requirement.page_start
        response["page_end"] = requirement.page_end
        response["source_block_ids"] = requirement.source_block_ids
        response["hierarchy_path"] = getattr(
            requirement, "hierarchy_path", []
        )
        response["ai_generated"] = True

        for field in (
            "policies",
            "documents",
            "evidence",
            "automation_tests",
        ):
            value = response.get(field, [])
            if not isinstance(value, list):
                response[field] = []

        todo = response.get("todo")
        if not isinstance(todo, dict):
            response["todo"] = {
                "name": "Review and implement the requirement",
                "description": (
                    "Review the source requirement and determine "
                    "the appropriate implementation steps."
                ),
            }

        return response

    def _batch_response_schema(self) -> dict[str, Any]:
        recommendation_item = {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "description": {"type": "string"},
            },
            "required": ["name", "description"],
            "additionalProperties": False,
        }

        todo_item = {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "description": {"type": "string"},
            },
            "required": ["name", "description"],
            "additionalProperties": False,
        }

        analysis_item = {
            "type": "object",
            "properties": {
                "source_reference": {"type": "string"},
                "source_title": {"type": "string"},
                "source_summary": {"type": "string"},
                "todo": todo_item,
                "policies": {
                    "type": "array",
                    "items": recommendation_item,
                },
                "documents": {
                    "type": "array",
                    "items": recommendation_item,
                },
                "evidence": {
                    "type": "array",
                    "items": recommendation_item,
                },
                "automation_tests": {
                    "type": "array",
                    "items": recommendation_item,
                },
            },
            "required": [
                "source_reference",
                "source_title",
                "source_summary",
                "todo",
                "policies",
                "documents",
                "evidence",
                "automation_tests",
            ],
            "additionalProperties": False,
        }

        return {
            "type": "object",
            "properties": {
                "analyses": {
                    "type": "array",
                    "items": analysis_item,
                }
            },
            "required": ["analyses"],
            "additionalProperties": False,
        }


class ComplianceDocumentAnalyzer(RequirementAnalyzer):
    """Compatibility alias used by the API routes."""
    pass
