import json
from pathlib import Path

from backend.models.breakdown import ComplianceBreakdown


class JSONExportError(Exception):
    pass


class JSONExporter:

    def export(
        self,
        breakdown: ComplianceBreakdown,
        output_path: str | Path,
    ) -> Path:

        path = Path(output_path)

        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        try:
            print(
                f"   Preparing JSON payload: "
                f"{path.name}"
            )

            payload = breakdown.model_dump(
                mode="json",
                exclude_none=True,
            )

            if not isinstance(payload, dict):
                raise TypeError(
                    "ComplianceBreakdown did not produce "
                    "a dictionary payload."
                )

            print(
                "   JSON payload created successfully."
            )

            json_text = json.dumps(
                payload,
                ensure_ascii=False,
                indent=2,
            )

            print(
                f"   JSON text size: "
                f"{len(json_text):,} characters"
            )

            temporary_path = path.with_suffix(
                path.suffix + ".tmp"
            )

            temporary_path.write_text(
                json_text,
                encoding="utf-8",
            )

            temporary_path.replace(path)

            print(
                f"   Master JSON saved: "
                f"{path}"
            )

            return path

        except Exception as exc:

            print("")
            print("=" * 60)
            print("JSON EXPORT ERROR")
            print("=" * 60)
            print(
                f"Type: {type(exc).__name__}"
            )
            print(
                f"Error: {exc}"
            )
            print("=" * 60)
            print("")

            raise JSONExportError(
                "Unable to export master JSON: "
                f"{type(exc).__name__}: {exc}"
            ) from exc