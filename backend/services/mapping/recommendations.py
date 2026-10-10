class RecommendationMapper:
    def normalize(
        self,
        requirements: list[dict],
    ) -> list[dict]:
        normalized = []

        for requirement in requirements:
            policies = self._unique(
                requirement.get(
                    "policies",
                    []
                )
            )

            documents = self._unique(
                requirement.get(
                    "documents",
                    []
                )
            )

            evidence = self._unique(
                requirement.get(
                    "evidence",
                    []
                )
            )

            normalized.append(
                {
                    "source_title": requirement.get(
                        "source_title",
                        ""
                    ),
                    "source_text": requirement.get(
                        "source_text",
                        ""
                    ),
                    "source_reference": requirement.get(
                        "source_reference",
                        ""
                    ),
                    "todo_name": requirement.get(
                        "todo_name",
                        ""
                    ),
                    "todo_description": requirement.get(
                        "todo_description",
                        ""
                    ),
                    "policies": policies,
                    "documents": documents,
                    "evidence": evidence,
                    "source_status": "SOURCE_DERIVED",
                    "recommendation_status": "AI_GENERATED",
                    "page_start": requirement.get(
                        "page_start"
                    ),
                    "page_end": requirement.get(
                        "page_end"
                    ),
                    "node_id": requirement.get(
                        "node_id"
                    ),
                    "chunk_ids": requirement.get(
                        "chunk_ids",
                        []
                    ),
                }
            )

        return normalized

    def _unique(
        self,
        values,
    ) -> list[str]:
        if not isinstance(values, list):
            return []

        result = []

        for value in values:
            value = str(value).strip()

            if value and value not in result:
                result.append(value)

        return result