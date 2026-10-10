from backend.models.analysis import RequirementAnalysis


class AnalysisValidator:

    def validate(
        self,
        analysis: dict,
        source_reference: str,
        source_text: str,
    ) -> RequirementAnalysis:

        if not isinstance(analysis, dict):
            raise ValueError(
                "AI analysis must be a JSON object."
            )

        actual_reference = analysis.get(
            "source_reference"
        )

        if actual_reference != source_reference:
            raise ValueError(
                "AI changed source reference: "
                f"expected={source_reference}, "
                f"received={actual_reference}"
            )

        analysis["source_reference"] = source_reference
        analysis["source_text"] = source_text

        if not isinstance(
            analysis.get("policies", []),
            list,
        ):
            analysis["policies"] = []

        if not isinstance(
            analysis.get("documents", []),
            list,
        ):
            analysis["documents"] = []

        if not isinstance(
            analysis.get("evidence", []),
            list,
        ):
            analysis["evidence"] = []

        todo = analysis.get("todo")

        if not isinstance(todo, dict):
            analysis["todo"] = {
                "name": "",
                "description": "",
            }

        return RequirementAnalysis.model_validate(
            analysis
        )