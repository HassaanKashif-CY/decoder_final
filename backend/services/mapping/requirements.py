import re
from typing import Any

from backend.models.document import (
    CleanedDocument,
    RequirementCandidate,
)
from backend.services.ai.client import OpenAIClient


class RequirementExtractionError(Exception):
    pass


class RequirementExtractor:
    """
    Discovers actionable compliance requirements from the complete
    cleaned PDF text.

    Important:
    - AI does NOT generate source text.
    - AI identifies exact source anchors.
    - Local code reconstructs the source text from the PDF blocks.
    - No framework-specific numbering or hierarchy is hardcoded.
    """

    MAX_FULL_DOCUMENT_CHARS = 180000
    CHUNK_CHARS = 120000
    CHUNK_OVERLAP_BLOCKS = 10

    def __init__(self):
        self.client = OpenAIClient()
        self.last_profile: dict[str, Any] = {}
        self.last_warnings: list[str] = []

    def extract(
        self,
        document: CleanedDocument,
    ) -> list[RequirementCandidate]:

        self.last_profile = {}
        self.last_warnings = []

        records = self._build_source_records(document)

        if not records:
            raise RequirementExtractionError(
                "No usable source text was extracted from the PDF."
            )

        print(
            f"Building AI discovery source: "
            f"{len(records)} source blocks"
        )

        total_chars = sum(
            len(record["text"])
            for record in records
        )

        print(
            f"AI discovery source size: "
            f"{total_chars:,} characters"
        )

        if total_chars <= self.MAX_FULL_DOCUMENT_CHARS:
            print("AI discovery mode: FULL DOCUMENT")
            raw_results = [
                self._discover_full_document(records)
            ]
        else:
            print(
                "AI discovery mode: CHUNKED DOCUMENT "
                "(document exceeds full-context threshold)"
            )
            raw_results = self._discover_chunked(records)

        discovery = self._merge_discovery_results(
            raw_results
        )

        self.last_profile = discovery.get(
            "document_profile",
            {},
        )

        raw_requirements = discovery.get(
            "requirements",
            [],
        )

        if not isinstance(raw_requirements, list):
            raise RequirementExtractionError(
                "AI discovery did not return a valid requirements array."
            )

        candidates = self._materialize_requirements(
            records=records,
            raw_requirements=raw_requirements,
        )

        candidates.sort(
            key=lambda item: (
                item.page_start,
                item.source_block_ids[0]
                if item.source_block_ids
                else "",
            )
        )

        for index, candidate in enumerate(
            candidates,
            start=1,
        ):
            candidate.candidate_id = f"req_{index:05d}"

        print(
            f"Verified source requirements: "
            f"{len(candidates)}"
        )

        return candidates

    def _build_source_records(
        self,
        document: CleanedDocument,
    ) -> list[dict[str, Any]]:

        records: list[dict[str, Any]] = []

        sequence = 1

        excluded_types = {
            "header",
            "footer",
            "page_number",
        }

        for page in document.pages:

            for block in page.blocks:

                if block.block_type in excluded_types:
                    continue

                text = self._clean_block_text(
                    block.text
                )

                if not text:
                    continue

                records.append(
                    {
                        "source_id": f"s{sequence:06d}",
                        "block_id": block.block_id,
                        "page_number": page.page_number,
                        "text": text,
                    }
                )

                sequence += 1

            for table in page.tables:

                for row_index, row in enumerate(
                    table.rows
                ):

                    cells = []

                    for cell in row:
                        cell_text = self._clean_block_text(
                            str(cell)
                        )

                        if cell_text:
                            cells.append(cell_text)

                    if not cells:
                        continue

                    text = " | ".join(cells)

                    records.append(
                        {
                            "source_id": f"s{sequence:06d}",
                            "block_id": (
                                f"{table.table_id}"
                                f":row:{row_index}"
                            ),
                            "page_number": page.page_number,
                            "text": text,
                        }
                    )

                    sequence += 1

        return records

    def _clean_block_text(
        self,
        text: str,
    ) -> str:

        if not text:
            return ""

        text = text.replace(
            "\u00a0",
            " ",
        )

        text = text.replace(
            "\r\n",
            "\n",
        )

        text = text.replace(
            "\r",
            "\n",
        )

        lines = []

        for line in text.split("\n"):

            line = re.sub(
                r"[ \t]+",
                " ",
                line,
            )

            line = line.strip()

            if line:
                lines.append(line)

        return "\n".join(lines).strip()

    def _build_ai_document(
        self,
        records: list[dict[str, Any]],
    ) -> str:

        parts = []

        for record in records:

            parts.append(
                "\n".join(
                    [
                        (
                            f"=== SOURCE BLOCK "
                            f"{record['source_id']} ==="
                        ),
                        (
                            f"BLOCK_ID: "
                            f"{record['block_id']}"
                        ),
                        (
                            f"PAGE: "
                            f"{record['page_number']}"
                        ),
                        "TEXT:",
                        record["text"],
                        "=== END SOURCE BLOCK ===",
                    ]
                )
            )

        return "\n\n".join(parts)

    def _discover_full_document(
        self,
        records: list[dict[str, Any]],
    ) -> dict[str, Any]:

        document_text = self._build_ai_document(
            records
        )

        prompt = self._discovery_prompt(
            document_text=document_text,
            mode="full",
        )

        response = self.client.generate_json(
            instructions=self._discovery_system_prompt(),
            input_text=prompt,
            schema=self._discovery_schema(),
            schema_name="compliance_document_discovery",
        )

        self._validate_discovery_response(
            response
        )

        return response

    def _discover_chunked(
        self,
        records: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:

        chunks = self._make_chunks(records)

        results = []

        total = len(chunks)

        for index, chunk in enumerate(
            chunks,
            start=1,
        ):

            print(
                f"AI discovery chunk "
                f"{index}/{total}"
            )

            document_text = self._build_ai_document(
                chunk
            )

            prompt = self._discovery_prompt(
                document_text=document_text,
                mode="chunk",
            )

            response = self.client.generate_json(
                instructions=self._discovery_system_prompt(),
                input_text=prompt,
                schema=self._discovery_schema(),
                schema_name=(
                    "compliance_document_discovery_chunk"
                ),
            )

            self._validate_discovery_response(
                response
            )

            results.append(response)

        return results

    def _make_chunks(
        self,
        records: list[dict[str, Any]],
    ) -> list[list[dict[str, Any]]]:

        chunks = []

        current = []
        current_chars = 0

        for record in records:

            record_chars = (
                len(record["text"])
                + 120
            )

            if (
                current
                and current_chars + record_chars
                > self.CHUNK_CHARS
            ):

                chunks.append(current)

                overlap = current[
                    -self.CHUNK_OVERLAP_BLOCKS:
                ]

                current = list(overlap)

                current_chars = sum(
                    len(item["text"]) + 120
                    for item in current
                )

            current.append(record)
            current_chars += record_chars

        if current:
            chunks.append(current)

        return chunks

    def _discovery_system_prompt(self) -> str:

        return """
You are the source-discovery engine for Sahl Compliance Decoder.

Your job is to identify actionable compliance requirements AND profile the regulation accurately.
In document_profile, provide a concise plain-language regulation_summary, applicability_conditions, and applicable_industries. Only state applicability supported by the source; if unclear, say it is not clearly specified. Preserve the document's own hierarchy in each requirement hierarchy_path, ordered from highest-level chapter/domain to immediate section/subsection.

Identify the document's REAL actionable compliance requirements.

The PDF can be ANY type of document:
- regulation
- standard
- framework
- guideline
- control catalog
- policy
- regulatory rulebook
- cybersecurity framework
- privacy framework
- safety standard
- financial regulation
- or another compliance document.

DO NOT assume ISO clauses.
DO NOT assume NCA numbering.
DO NOT assume SAMA numbering.
DO NOT assume articles.
DO NOT assume controls.
DO NOT assume chapters.
DO NOT assume any fixed numbering pattern.

First understand how THIS document organizes its actionable requirements.

Examples of possible requirement units include:
controls, clauses, articles, safeguards, requirements, obligations,
measures, provisions, control considerations, implementation
requirements, practices, subcontrols, principles, criteria, etc.

The document's own terminology always wins.

SOURCE FIDELITY IS CRITICAL.

You are NOT allowed to generate or paraphrase source_text.

Instead, every requirement MUST provide:
- start_source_id
- start_anchor
- end_source_id
- end_anchor

The anchors MUST be copied verbatim from the supplied source block text.

The anchors must be short, distinctive pieces of the actual source text.

The local application will use these anchors to reconstruct the exact
source text. Therefore:

1. Never invent an anchor.
2. Never paraphrase an anchor.
3. Never use text that does not exist in the supplied source.
4. Never create a requirement from memory.
5. Never merge unrelated requirements.
6. Never truncate a requirement deliberately.
7. Never return only a heading when the requirement continues below it.
8. Never include a table of contents entry as the actual requirement.
9. Do not treat repeated TOC text as a substantive requirement.
10. If the same requirement appears in a TOC and later in the body,
    use the substantive body occurrence.
11. Keep separate requirements separate, even when several requirements
    appear inside the same PDF text block.
12. A requirement can start and end inside the SAME source block.
13. A requirement can span multiple source blocks.
14. A requirement can span multiple pages.
15. Use the complete requirement span.
16. If the document contains separate subcontrols, obligations,
    measures, bullets, or numbered requirements that are semantically
    independent, return them separately when the document treats them
    as separate actionable units.
17. Do not invent hierarchy levels that the source does not establish.

Definitions, introductions, background, scope, explanatory material,
references, acknowledgements and navigation material are not
requirements unless they themselves contain a substantive obligation
that the document clearly treats as actionable.

The returned source_reference and source_title must be based on the
document itself.

The returned document profile must describe what the document actually
is. Do not guess a framework name, version, jurisdiction or hierarchy
if it is not supported by the source.

Most importantly:

THE SOURCE TEXT WILL BE RECONSTRUCTED LOCALLY.

Your job is to identify exact boundaries, not to write the source.
""".strip()

    def _discovery_prompt(
        self,
        document_text: str,
        mode: str,
    ) -> str:

        if mode == "full":
            scope_instruction = """
You have the complete cleaned document.

Analyze the document globally before deciding what its actionable
requirements are.

Use the complete document to understand:
- title
- version
- document type
- hierarchy
- terminology
- requirement boundaries
- TOC versus substantive body
- repeated headers/footers
- annexes
- tables
- appendices
- exceptions
- notes and implementation guidance
"""
        else:
            scope_instruction = """
This is a document segment from a larger PDF.

Identify requirements only when their boundaries can be established
from the supplied segment. Use the source IDs and anchors exactly.

Do not invent missing text.

If a requirement clearly starts in this segment but its end is not
present, DO NOT fabricate an end anchor. It is acceptable to omit a
requirement whose complete source span cannot be established from this
segment.

Overlapping chunks may contain the same requirement. The application
will deduplicate exact source spans.
"""

        return f"""
{scope_instruction}

Return a document profile and a list of actionable requirements.

For every requirement return:

- requirement_id
- source_reference
- source_title
- unit_type
- hierarchy_path
- start_source_id
- start_anchor
- end_source_id
- end_anchor
- confidence

IMPORTANT ANCHOR RULE:

start_anchor must be copied exactly from the source block identified
by start_source_id.

end_anchor must be copied exactly from the source block identified by
end_source_id.

Choose anchors that are distinctive enough to locate reliably.

Do not return source_text.

SOURCE DOCUMENT:

{document_text}
""".strip()

    def _discovery_schema(self) -> dict[str, Any]:

        requirement_schema = {
            "type": "object",
            "properties": {
                "requirement_id": {
                    "type": "string",
                },
                "source_reference": {
                    "type": "string",
                },
                "source_title": {
                    "type": "string",
                },
                "unit_type": {
                    "type": "string",
                },
                "hierarchy_path": {
                    "type": "array",
                    "items": {
                        "type": "string",
                    },
                },
                "start_source_id": {
                    "type": "string",
                },
                "start_anchor": {
                    "type": "string",
                },
                "end_source_id": {
                    "type": "string",
                },
                "end_anchor": {
                    "type": "string",
                },
                "confidence": {
                    "type": "number",
                },
            },
            "required": [
                "requirement_id",
                "source_reference",
                "source_title",
                "unit_type",
                "hierarchy_path",
                "start_source_id",
                "start_anchor",
                "end_source_id",
                "end_anchor",
                "confidence",
            ],
            "additionalProperties": False,
        }

        profile_schema = {
            "type": "object",
            "properties": {
                "document_title": {
                    "type": "string",
                },
                "document_type": {
                    "type": "string",
                },
                "framework_name": {
                    "type": "string",
                },
                "version": {
                    "type": "string",
                },
                "jurisdiction": {
                    "type": "string",
                },
                "requirement_unit_name": {
                    "type": "string",
                },
                "hierarchy_description": {
                    "type": "string",
                },
                "hierarchy_levels": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "regulation_summary": {"type": "string"},
                "applicability_conditions": {"type": "string"},
                "applicable_industries": {
                    "type": "array", "items": {"type": "string"}
                },
            },
            "required": [
                "document_title",
                "document_type",
                "framework_name",
                "version",
                "jurisdiction",
                "requirement_unit_name",
                "hierarchy_description",
                "hierarchy_levels",
                "regulation_summary",
                "applicability_conditions",
                "applicable_industries",
            ],
            "additionalProperties": False,
        }

        return {
            "type": "object",
            "properties": {
                "document_profile": profile_schema,
                "requirements": {
                    "type": "array",
                    "items": requirement_schema,
                },
            },
            "required": [
                "document_profile",
                "requirements",
            ],
            "additionalProperties": False,
        }

    def _validate_discovery_response(
        self,
        response: Any,
    ) -> None:

        if not isinstance(response, dict):
            raise RequirementExtractionError(
                "AI discovery returned an invalid object."
            )

        if not isinstance(
            response.get("document_profile"),
            dict,
        ):
            raise RequirementExtractionError(
                "AI discovery returned an invalid document profile."
            )

        if not isinstance(
            response.get("requirements"),
            list,
        ):
            raise RequirementExtractionError(
                "AI discovery returned an invalid requirements list."
            )

    def _merge_discovery_results(
        self,
        results: list[dict[str, Any]],
    ) -> dict[str, Any]:

        if not results:
            return {
                "document_profile": {},
                "requirements": [],
            }

        profiles = [
            result.get(
                "document_profile",
                {},
            )
            for result in results
        ]

        profile = self._merge_profiles(
            profiles
        )

        requirements = []

        seen = set()

        for result in results:

            for item in result.get(
                "requirements",
                [],
            ):

                if not isinstance(item, dict):
                    continue

                key = (
                    item.get("start_source_id", ""),
                    item.get("start_anchor", ""),
                    item.get("end_source_id", ""),
                    item.get("end_anchor", ""),
                )

                if key in seen:
                    continue

                seen.add(key)
                requirements.append(item)

        return {
            "document_profile": profile,
            "requirements": requirements,
        }

    def _merge_profiles(
        self,
        profiles: list[dict[str, Any]],
    ) -> dict[str, Any]:

        merged = {}

        fields = [
            "document_title",
            "document_type",
            "framework_name",
            "version",
            "jurisdiction",
            "requirement_unit_name",
            "hierarchy_description",
            "regulation_summary",
            "applicability_conditions",
        ]

        for field in fields:

            value = ""

            for profile in profiles:

                candidate = profile.get(
                    field,
                    "",
                )

                if isinstance(
                    candidate,
                    str,
                ) and candidate.strip():

                    value = candidate.strip()
                    break

            merged[field] = value

        hierarchy_levels = []

        for profile in profiles:

            values = profile.get(
                "hierarchy_levels",
                [],
            )

            if not isinstance(
                values,
                list,
            ):
                continue

            for value in values:

                if (
                    isinstance(value, str)
                    and value.strip()
                    and value.strip()
                    not in hierarchy_levels
                ):

                    hierarchy_levels.append(
                        value.strip()
                    )

        merged["hierarchy_levels"] = hierarchy_levels

        industries = []
        for profile in profiles:
            values = profile.get("applicable_industries", [])
            if isinstance(values, list):
                for value in values:
                    if isinstance(value, str) and value.strip() and value.strip() not in industries:
                        industries.append(value.strip())
        merged["applicable_industries"] = industries
        return merged

    def _materialize_requirements(
        self,
        records: list[dict[str, Any]],
        raw_requirements: list[dict[str, Any]],
    ) -> list[RequirementCandidate]:

        by_source_id = {
            record["source_id"]: (
                index,
                record,
            )
            for index, record in enumerate(records)
        }

        by_block_id = {
            record["block_id"]: (
                index,
                record,
            )
            for index, record in enumerate(records)
        }

        candidates = []

        for raw in raw_requirements:

            try:

                start_ref = self._resolve_record(
                    raw.get("start_source_id"),
                    by_source_id,
                    by_block_id,
                )

                end_ref = self._resolve_record(
                    raw.get("end_source_id"),
                    by_source_id,
                    by_block_id,
                )

                if start_ref is None or end_ref is None:
                    self.last_warnings.append(
                        "Rejected requirement because "
                        "its source block could not be resolved."
                    )
                    continue

                start_index, start_record = start_ref
                end_index, end_record = end_ref

                if end_index < start_index:
                    self.last_warnings.append(
                        "Rejected requirement because "
                        "end source occurs before start source."
                    )
                    continue

                start_match = self._find_anchor(
                    start_record["text"],
                    raw.get(
                        "start_anchor",
                        "",
                    ),
                )

                end_match = self._find_anchor(
                    end_record["text"],
                    raw.get(
                        "end_anchor",
                        "",
                    ),
                )

                if start_match is None:
                    self.last_warnings.append(
                        "Rejected requirement because "
                        "start anchor was not found exactly "
                        "or by whitespace-normalized matching."
                    )
                    continue

                if end_match is None:
                    self.last_warnings.append(
                        "Rejected requirement because "
                        "end anchor was not found exactly "
                        "or by whitespace-normalized matching."
                    )
                    continue

                start_position = (
                    start_match[0]
                )

                end_position = (
                    end_match[1]
                )

                source_text = (
                    self._reconstruct_span(
                        records=records,
                        start_index=start_index,
                        start_position=start_position,
                        end_index=end_index,
                        end_position=end_position,
                    )
                )

                source_text = source_text.strip()

                if len(source_text) < 10:
                    self.last_warnings.append(
                        "Rejected extremely short "
                        "requirement source span."
                    )
                    continue

                source_block_ids = [
                    record["block_id"]
                    for record in records[
                        start_index:end_index + 1
                    ]
                ]

                title = str(
                    raw.get(
                        "source_title",
                        "",
                    )
                    or ""
                ).strip()

                if not title:
                    title = self._derive_title(
                        source_text
                    )

                reference = str(
                    raw.get(
                        "source_reference",
                        "",
                    )
                    or ""
                ).strip()

                candidates.append(
                    RequirementCandidate(
                        candidate_id=(
                            str(
                                raw.get(
                                    "requirement_id",
                                    "",
                                )
                            )
                            or "pending"
                        ),
                        node_id=None,
                        source_title=title,
                        source_text=source_text,
                        page_start=start_record[
                            "page_number"
                        ],
                        page_end=end_record[
                            "page_number"
                        ],
                        source_block_ids=source_block_ids,
                        source_reference=reference,
                        hierarchy_path=[str(v).strip() for v in raw.get("hierarchy_path", []) if isinstance(v, str) and v.strip()],
                        confidence=self._confidence(
                            raw.get(
                                "confidence",
                                0.0,
                            ),
                            start_match[2],
                            end_match[2],
                        ),
                    )
                )

            except Exception as exc:

                self.last_warnings.append(
                    "Rejected malformed AI requirement: "
                    f"{exc}"
                )

        return self._deduplicate_candidates(
            candidates
        )

    def _resolve_record(
        self,
        identifier: Any,
        by_source_id: dict,
        by_block_id: dict,
    ):

        if not isinstance(
            identifier,
            str,
        ):
            return None

        if identifier in by_source_id:
            return by_source_id[
                identifier
            ]

        if identifier in by_block_id:
            return by_block_id[
                identifier
            ]

        return None

    def _find_anchor(
        self,
        text: str,
        anchor: str,
    ):

        if not text or not anchor:
            return None

        exact = text.find(anchor)

        if exact >= 0:
            return (
                exact,
                exact + len(anchor),
                True,
            )

        normalized_text, mapping = (
            self._normalize_with_mapping(text)
        )

        normalized_anchor = (
            self._normalize_for_search(anchor)
        )

        if not normalized_anchor:
            return None

        position = normalized_text.find(
            normalized_anchor
        )

        if position < 0:
            return None

        end_normalized = (
            position
            + len(normalized_anchor)
            - 1
        )

        if (
            position >= len(mapping)
            or end_normalized >= len(mapping)
        ):
            return None

        original_start = mapping[
            position
        ]

        original_end = (
            mapping[end_normalized]
            + 1
        )

        return (
            original_start,
            original_end,
            False,
        )

    def _normalize_for_search(
        self,
        text: str,
    ) -> str:

        text = text.replace(
            "\u00a0",
            " ",
        )

        text = re.sub(
            r"\s+",
            " ",
            text,
        )

        return text.strip()

    def _normalize_with_mapping(
        self,
        text: str,
    ):

        output = []
        mapping = []

        whitespace_open = False

        for index, char in enumerate(text):

            if char.isspace():

                if (
                    output
                    and not whitespace_open
                ):

                    output.append(" ")
                    mapping.append(index)

                whitespace_open = True

            else:

                output.append(char)
                mapping.append(index)
                whitespace_open = False

        normalized = "".join(output).strip()

        if not normalized:
            return "", []

        leading_trim = (
            len("".join(output))
            - len("".join(output).lstrip())
        )

        if leading_trim:
            mapping = mapping[
                leading_trim:
            ]

        return normalized, mapping

    def _reconstruct_span(
        self,
        records: list[dict[str, Any]],
        start_index: int,
        start_position: int,
        end_index: int,
        end_position: int,
    ) -> str:

        if start_index == end_index:

            return records[start_index][
                "text"
            ][start_position:end_position]

        parts = []

        parts.append(
            records[start_index]["text"][
                start_position:
            ]
        )

        for index in range(
            start_index + 1,
            end_index,
        ):

            parts.append(
                records[index]["text"]
            )

        parts.append(
            records[end_index]["text"][
                :end_position
            ]
        )

        return "\n".join(parts)

    def _derive_title(
        self,
        source_text: str,
    ) -> str:

        first_line = (
            source_text
            .splitlines()[0]
            .strip()
        )

        if len(first_line) > 200:
            first_line = first_line[:200]

        return first_line

    def _confidence(
        self,
        raw_confidence: Any,
        start_exact: bool,
        end_exact: bool,
    ) -> float:

        try:
            value = float(
                raw_confidence
            )
        except Exception:
            value = 0.0

        value = max(
            0.0,
            min(
                1.0,
                value,
            ),
        )

        if not start_exact:
            value -= 0.05

        if not end_exact:
            value -= 0.05

        return max(
            0.0,
            min(
                1.0,
                value,
            ),
        )

    def _deduplicate_candidates(
        self,
        candidates: list[RequirementCandidate],
    ) -> list[RequirementCandidate]:

        unique = []
        seen = set()

        for candidate in candidates:

            normalized = re.sub(
                r"\s+",
                " ",
                candidate.source_text,
            ).strip().lower()

            key = (
                candidate.page_start,
                candidate.page_end,
                tuple(
                    candidate.source_block_ids
                ),
                normalized,
            )

            if key in seen:
                continue

            seen.add(key)
            unique.append(candidate)

        unique.sort(
            key=lambda item: (
                item.page_start,
                item.page_end,
                item.source_block_ids,
            )
        )

        return unique
