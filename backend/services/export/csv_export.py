import csv
import json
from pathlib import Path
from typing import Any

from backend.models.breakdown import ComplianceBreakdown


class CSVExportError(Exception):
    pass


class CSVExporter:
    FIELDNAMES = [
        "document",
        "framework",
        "version",
        "document_type",
        "jurisdiction",
        "hierarchy",
        "source_reference",
        "source_title",
        "source_text",
        "source_summary",
        "page_start",
        "page_end",
        "todo_name",
        "todo_description",
        "policies",
        "documents",
        "evidence",
        "ai_generated",
    ]

    def export(
        self,
        breakdown: ComplianceBreakdown,
        output_path: str | Path,
    ) -> Path:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        metadata = breakdown.metadata

        try:
            with path.open(
                "w",
                encoding="utf-8-sig",
                newline="",
            ) as file:
                writer = csv.DictWriter(
                    file,
                    fieldnames=self.FIELDNAMES,
                )
                writer.writeheader()

                for requirement in breakdown.requirements:
                    todo = getattr(requirement, "todo", None)

                    writer.writerow(
                        {
                            "document": self._get(metadata, "filename"),
                            "framework": self._get(metadata, "framework_name"),
                            "version": self._get(metadata, "version"),
                            "document_type": self._get(
                                metadata, "document_type"
                            ),
                            "jurisdiction": self._get(
                                metadata, "jurisdiction"
                            ),
                            "hierarchy": " > ".join(
                                str(part)
                                for part in (
                                    getattr(
                                        requirement,
                                        "hierarchy_path",
                                        None,
                                    )
                                    or []
                                )
                            ),
                            "source_reference": self._get(
                                requirement, "source_reference"
                            ),
                            "source_title": self._get(
                                requirement, "source_title"
                            ),
                            "source_text": self._get(
                                requirement, "source_text"
                            ),
                            "source_summary": self._get(
                                requirement, "source_summary"
                            ),
                            "page_start": self._get(
                                requirement, "page_start"
                            ),
                            "page_end": self._get(requirement, "page_end"),
                            "todo_name": self._get(todo, "name"),
                            "todo_description": self._get(
                                todo, "description"
                            ),
                            "policies": self._serialize_items(
                                getattr(requirement, "policies", None)
                            ),
                            "documents": self._serialize_items(
                                getattr(requirement, "documents", None)
                            ),
                            "evidence": self._serialize_items(
                                getattr(requirement, "evidence", None)
                            ),
                            "ai_generated": getattr(
                                requirement, "ai_generated", True
                            ),
                        }
                    )

        except Exception as exc:
            raise CSVExportError(
                f"Unable to export CSV: {type(exc).__name__}: {exc}"
            ) from exc

        return path

    @staticmethod
    def _get(obj: Any, name: str, default: Any = "") -> Any:
        if obj is None:
            return default

        value = getattr(obj, name, default)

        return default if value is None else value

    @staticmethod
    def _serialize_items(items) -> str:
        values = []

        for item in items or []:
            values.append(
                {
                    "name": getattr(item, "name", ""),
                    "description": getattr(item, "description", ""),
                }
            )

        return json.dumps(values, ensure_ascii=False)