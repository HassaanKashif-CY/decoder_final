import re
from collections import defaultdict

from backend.models.document import (
    RequirementCandidate,
    DocumentRequirementSet,
)


class RequirementMapper:
    def map(
        self,
        document_id: str,
        requirements: list[RequirementCandidate],
    ) -> DocumentRequirementSet:

        requirements = sorted(
            requirements,
            key=lambda item: (
                item.page_start,
                self._reference_sort_key(item.source_reference),
            ),
        )

        requirements = self._remove_non_requirements(requirements)

        return DocumentRequirementSet(
            document_id=document_id,
            requirements=requirements,
        )

    def _remove_non_requirements(self, requirements):
        result = []

        for item in requirements:
            reference = item.source_reference

            if not reference:
                continue

            depth = self._reference_depth(reference)

            if depth == 1:
                continue

            if self._looks_like_heading(item.source_text):
                continue

            result.append(item)

        return result

    def _reference_depth(self, reference):
        if not reference:
            return 0

        return len(reference.split("-"))

    def _looks_like_heading(self, text):
        value = text.strip()

        if len(value) < 10:
            return True

        lowered = value.lower()

        if "objective" in lowered and len(value.split()) < 80:
            return True

        if (
            "controlsdata classification level" in lowered
            or "controls data classification level" in lowered
        ):
            return True

        return False

    def _reference_sort_key(self, reference):
        if not reference:
            return (999,)

        parts = []

        for part in reference.split("-"):
            try:
                parts.append(int(part))
            except ValueError:
                parts.append(999)

        return tuple(parts)