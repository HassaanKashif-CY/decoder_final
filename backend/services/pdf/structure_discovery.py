import re
from collections import Counter
from dataclasses import dataclass
from typing import Optional

from backend.models.document import CleanedDocument, TextBlock


@dataclass
class PatternCandidate:
    pattern: str
    count: int
    examples: list[str]
    numeric_depth: Optional[int] = None


@dataclass
class HeadingCandidate:
    block_id: str
    page_number: int
    text: str
    font_size: float
    bold: bool
    score: float


class StructureDiscovery:
    """
    Generic document structure discovery.

    This component does not assume ISO, NCA, PDPL, DCC, CCC,
    or any other specific framework structure.
    """

    def discover(self, document: CleanedDocument) -> dict:
        blocks = self._flatten_blocks(document)

        return {
            "document_profile": self._discover_profile(document, blocks),
            "numbering_patterns": self._discover_numbering_patterns(blocks),
            "heading_candidates": self._discover_heading_candidates(blocks),
            "special_regions": self._discover_special_regions(blocks),
        }

    def _flatten_blocks(
        self,
        document: CleanedDocument,
    ) -> list[TextBlock]:
        blocks: list[TextBlock] = []

        for page in document.pages:
            blocks.extend(page.blocks)

        return blocks

    def _discover_profile(
        self,
        document: CleanedDocument,
        blocks: list[TextBlock],
    ) -> dict:
        texts = [block.text for block in blocks]

        return {
            "filename": document.metadata.filename,
            "page_count": document.metadata.page_count,
            "block_count": len(blocks),
            "average_text_length": round(
                sum(len(text) for text in texts) / max(len(texts), 1),
                2,
            ),
            "has_numbering": any(
                self._extract_numbering_tokens(text)
                for text in texts
            ),
        }

    def _discover_numbering_patterns(
        self,
        blocks: list[TextBlock],
    ) -> list[dict]:
        occurrences: Counter[str] = Counter()
        examples: dict[str, list[str]] = {}

        for block in blocks:
            tokens = self._extract_numbering_tokens(block.text)

            for token in tokens:
                normalized = self._normalize_pattern(token)

                occurrences[normalized] += 1

                if normalized not in examples:
                    examples[normalized] = []

                if token not in examples[normalized]:
                    examples[normalized].append(token)

        candidates = []

        for pattern, count in occurrences.most_common():
            if count < 2:
                continue

            candidates.append(
                {
                    "pattern": pattern,
                    "count": count,
                    "examples": examples[pattern][:10],
                    "depth": self._pattern_depth(pattern),
                }
            )

        return candidates[:100]

    def _extract_numbering_tokens(self, text: str) -> list[str]:
        patterns = [
            r"\b\d+(?:\.\d+){1,6}\b",
            r"\b\d+(?:-\d+){1,8}\b",
            r"\b(?:Article|ARTICLE)\s+\d+(?:\.\d+)*\b",
            r"\b(?:Section|SECTION)\s+\d+(?:\.\d+)*\b",
            r"\b(?:Clause|CLAUSE)\s+\d+(?:\.\d+)*\b",
            r"\b(?:Part|PART)\s+[A-Z0-9]+\b",
            r"\b(?:Chapter|CHAPTER)\s+[A-Z0-9]+\b",
            r"\b[A-Z]\.\d+(?:\.\d+)*\b",
            r"(?<!\w)\([a-z]\)(?!\w)",
            r"(?<!\w)\([0-9]+\)(?!\w)",
        ]

        found: list[str] = []

        for pattern in patterns:
            for match in re.finditer(pattern, text):
                value = match.group(0).strip()

                if value not in found:
                    found.append(value)

        return found

    def _normalize_pattern(self, token: str) -> str:
        value = token.strip()

        if re.fullmatch(r"\d+(?:\.\d+){1,6}", value):
            return ".".join(
                ["N"] * len(value.split("."))
            )

        if re.fullmatch(r"\d+(?:-\d+){1,8}", value):
            return "-".join(
                ["N"] * len(value.split("-"))
            )

        if re.fullmatch(
            r"(Article|ARTICLE)\s+\d+(?:\.\d+)*",
            value,
        ):
            number = value.split(maxsplit=1)[1]
            return (
                "ARTICLE "
                + ".".join(["N"] * len(number.split(".")))
            )

        if re.fullmatch(
            r"(Section|SECTION)\s+\d+(?:\.\d+)*",
            value,
        ):
            number = value.split(maxsplit=1)[1]
            return (
                "SECTION "
                + ".".join(["N"] * len(number.split(".")))
            )

        if re.fullmatch(
            r"(Clause|CLAUSE)\s+\d+(?:\.\d+)*",
            value,
        ):
            number = value.split(maxsplit=1)[1]
            return (
                "CLAUSE "
                + ".".join(["N"] * len(number.split(".")))
            )

        if re.fullmatch(
            r"(Part|PART)\s+[A-Z0-9]+",
            value,
        ):
            return "PART X"

        if re.fullmatch(
            r"(Chapter|CHAPTER)\s+[A-Z0-9]+",
            value,
        ):
            return "CHAPTER X"

        if re.fullmatch(r"[A-Z]\.\d+(?:\.\d+)*", value):
            return "LETTER.NUMBER"

        if re.fullmatch(r"\([a-z]\)", value):
            return "(LETTER)"

        if re.fullmatch(r"\([0-9]+\)", value):
            return "(NUMBER)"

        return "OTHER"

    def _pattern_depth(self, pattern: str) -> Optional[int]:
        if pattern in {
            "PART X",
            "CHAPTER X",
            "LETTER.NUMBER",
            "(LETTER)",
            "(NUMBER)",
        }:
            return None

        if pattern.startswith("ARTICLE "):
            return len(pattern.replace("ARTICLE ", "").split("."))

        if pattern.startswith("SECTION "):
            return len(pattern.replace("SECTION ", "").split("."))

        if pattern.startswith("CLAUSE "):
            return len(pattern.replace("CLAUSE ", "").split("."))

        if "N" in pattern:
            return len(pattern.split("." if "." in pattern else "-"))

        return None

    def _discover_heading_candidates(
        self,
        blocks: list[TextBlock],
    ) -> list[dict]:
        candidates: list[HeadingCandidate] = []

        font_sizes = [
            block.font_size
            for block in blocks
            if block.font_size > 0
        ]

        if not font_sizes:
            return []

        median_font = sorted(font_sizes)[len(font_sizes) // 2]

        for block in blocks:
            text = block.text.strip()

            if not text:
                continue

            score = 0.0

            if block.font_size >= median_font * 1.35:
                score += 3.0
            elif block.font_size >= median_font * 1.15:
                score += 1.5

            if block.is_bold:
                score += 2.0

            if len(text) <= 120:
                score += 1.0

            if self._looks_like_sentence(text):
                score -= 2.0

            if self._looks_like_table_header(text):
                score -= 2.0

            if self._looks_like_metadata(text):
                score -= 3.0

            if score >= 2.0:
                candidates.append(
                    HeadingCandidate(
                        block_id=block.block_id,
                        page_number=block.page_number,
                        text=text,
                        font_size=block.font_size,
                        bold=block.is_bold,
                        score=score,
                    )
                )

        candidates.sort(
            key=lambda item: (
                item.page_number,
                item.block_id,
            )
        )

        return [
            {
                "block_id": item.block_id,
                "page_number": item.page_number,
                "text": item.text,
                "font_size": item.font_size,
                "bold": item.bold,
                "score": round(item.score, 2),
            }
            for item in candidates
        ]

    def _discover_special_regions(
        self,
        blocks: list[TextBlock],
    ) -> list[dict]:
        regions = []

        for block in blocks:
            text = block.text.strip()

            region_type = self._classify_region(text)

            if region_type:
                regions.append(
                    {
                        "block_id": block.block_id,
                        "page_number": block.page_number,
                        "type": region_type,
                        "text": text[:300],
                    }
                )

        return regions

    def _classify_region(self, text: str) -> Optional[str]:
        lowered = text.lower()

        if re.search(
            r"\btable of contents\b|\bcontents\b",
            lowered,
        ):
            return "table_of_contents"

        if re.search(
            r"\bappendix\b|\bannex\b",
            lowered,
        ):
            return "appendix_or_annex"

        if re.search(
            r"\bterms and definitions\b|\bterminology\b|\bdefinitions\b",
            lowered,
        ):
            return "definitions"

        if re.search(
            r"\babbreviations\b|\bacronyms\b",
            lowered,
        ):
            return "abbreviations"

        if re.search(
            r"\blist of tables\b",
            lowered,
        ):
            return "list_of_tables"

        if re.search(
            r"\blist of figures\b|\blist of illustrations\b",
            lowered,
        ):
            return "list_of_figures"

        if re.search(
            r"\breferences\b|\bbibliography\b",
            lowered,
        ):
            return "references"

        if re.search(
            r"\btable\s+\d+\b",
            lowered,
        ):
            return "table"

        if re.search(
            r"\bfigure\s+\d+\b|\bfig\.\s*\d+\b",
            lowered,
        ):
            return "figure"

        return None

    def _looks_like_sentence(self, text: str) -> bool:
        lowered = text.lower()

        sentence_markers = (
            " is ",
            " are ",
            " must ",
            " shall ",
            " should ",
            " may ",
            " will ",
            " requires ",
            " required ",
        )

        return (
            len(text.split()) > 18
            and any(marker in f" {lowered} " for marker in sentence_markers)
        )

    def _looks_like_table_header(self, text: str) -> bool:
        lowered = text.lower()

        markers = (
            "control clauses",
            "control reference",
            "data classification",
            "full term",
            "reference number",
            "definition",
            "terminology",
        )

        return any(marker in lowered for marker in markers)

    def _looks_like_metadata(self, text: str) -> bool:
        lowered = text.lower()

        markers = (
            "document classification",
            "sharing indicator",
            "traffic light protocol",
            "tlp:",
        )

        return any(marker in lowered for marker in markers)