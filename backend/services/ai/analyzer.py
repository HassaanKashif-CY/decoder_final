import json

from backend.models.analysis import RequirementAnalysis
from backend.models.document import RequirementCandidate
from backend.services.ai.client import OpenAIClient
from backend.services.ai.prompts import (
    SYSTEM_PROMPT,
    USER_PROMPT,
)
from backend.services.ai.validator import AnalysisValidator


class DocumentAnalysisError(Exception):
    pass


class RequirementAnalysisError(
    DocumentAnalysisError
):
    pass


class RequirementAnalyzer:

    def __init__(
        self,
        batch_size: int = 10,
    ):
        self.client = OpenAIClient()
        self.validator = AnalysisValidator()
        self.batch_size = batch_size

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
                "No AI analysis returned for "
                f"{requirement.source_reference}"
            )

        return results[0]

    def analyze_many(
        self,
        document_name: str,
        requirements: list[RequirementCandidate],
    ) -> list[RequirementAnalysis]:

        if not requirements:
            return []

        results = []

        total_batches = (
            len(requirements)
            + self.batch_size
            - 1
        ) // self.batch_size

        for start in range(
            0,
            len(requirements),
            self.batch_size,
        ):

            batch = requirements[
                start:start
                + self.batch_size
            ]

            batch_number = (
                start
                // self.batch_size
            ) + 1

            print(
                f"AI analysis batch "
                f"{batch_number}/{total_batches} "
                f"({len(batch)} requirements)"
            )

            batch_results = (
                self._analyze_batch(
                    document_name=document_name,
                    requirements=batch,
                )
            )

            results.extend(
                batch_results
            )

        return results

    def _analyze_batch(
        self,
        document_name: str,
        requirements: list[RequirementCandidate],
    ) -> list[RequirementAnalysis]:

        source_requirements = []

        for index, requirement in enumerate(
            requirements,
            start=1,
        ):

            source_requirements.append(
                {
                    "batch_index": index,
                    "candidate_id": (
                        requirement.candidate_id
                    ),
                    "source_reference": (
                        requirement.source_reference
                    ),
                    "source_title": (
                        requirement.source_title
                    ),
                    "source_text": (
                        requirement.source_text
                    ),
                    "page_start": (
                        requirement.page_start
                    ),
                    "page_end": (
                        requirement.page_end
                    ),
                    "source_block_ids": (
                        requirement.source_block_ids
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

            response = (
                self.client.generate_json(
                    instructions=SYSTEM_PROMPT,
                    input_text=prompt,
                    schema=(
                        self._batch_response_schema()
                    ),
                    schema_name=(
                        "requirement_analysis_batch"
                    ),
                )
            )

        except Exception as exc:

            raise DocumentAnalysisError(
                f"AI batch analysis failed: {exc}"
            ) from exc

        if not isinstance(
            response,
            dict,
        ):
            raise DocumentAnalysisError(
                "OpenAI returned an invalid "
                "batch response."
            )

        raw_analyses = response.get(
            "analyses"
        )

        if not isinstance(
            raw_analyses,
            list,
        ):
            raise DocumentAnalysisError(
                "OpenAI batch response does not "
                "contain an analyses array."
            )

        if len(raw_analyses) != len(
            requirements
        ):

            raise DocumentAnalysisError(
                "OpenAI returned an incorrect "
                "number of analyses. "
                f"Expected {len(requirements)}, "
                f"received {len(raw_analyses)}."
            )

        results = []

        for requirement, analysis in zip(
            requirements,
            raw_analyses,
        ):

            if not isinstance(
                analysis,
                dict,
            ):
                raise DocumentAnalysisError(
                    "Invalid AI analysis for "
                    f"{requirement.source_reference}"
                )

            analysis = (
                self._protect_source_fields(
                    response=analysis,
                    requirement=requirement,
                )
            )

            try:

                validated = (
                    self.validator.validate(
                        analysis=analysis,
                        source_reference=(
                            requirement.source_reference
                        ),
                        source_text=(
                            requirement.source_text
                        ),
                    )
                )

            except Exception as exc:

                raise DocumentAnalysisError(
                    "AI validation failed for "
                    f"{requirement.source_reference}: "
                    f"{exc}"
                ) from exc

            results.append(
                validated
            )

        return results

    def _protect_source_fields(
        self,
        response: dict,
        requirement: RequirementCandidate,
    ) -> dict:

        response["source_reference"] = (
            requirement.source_reference
        )

        response["source_title"] = (
            requirement.source_title
        )

        response["source_text"] = (
            requirement.source_text
        )

        response["page_start"] = (
            requirement.page_start
        )

        response["page_end"] = (
            requirement.page_end
        )

        response["source_block_ids"] = (
            requirement.source_block_ids
        )

        response["ai_generated"] = True

        return response

    def _batch_response_schema(
        self,
    ) -> dict:

        recommendation_item = {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                },
                "description": {
                    "type": "string",
                },
            },
            "required": [
                "name",
                "description",
            ],
            "additionalProperties": False,
        }

        todo_item = {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                },
                "description": {
                    "type": "string",
                },
            },
            "required": [
                "name",
                "description",
            ],
            "additionalProperties": False,
        }

        analysis_item = {
            "type": "object",
            "properties": {
                "source_reference": {
                    "type": "string",
                },
                "source_title": {
                    "type": "string",
                },
                "source_summary": {
                    "type": "string",
                },
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
                },
            },
            "required": [
                "analyses",
            ],
            "additionalProperties": False,
        }


class ComplianceDocumentAnalyzer(
    RequirementAnalyzer
):
    pass
