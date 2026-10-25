import re
import unicodedata
from bisect import bisect_left, bisect_right
from collections import Counter
from typing import Any

from backend.models.document import (
    CleanedDocument,
    RequirementCandidate,
)
from backend.services.ai.client import OpenAIClient


class RequirementExtractionError(Exception):
    pass


ROLE_CHAPTER = "chapter"
ROLE_SUBCHAPTER = "subchapter"
ROLE_REQUIREMENT = "requirement"
ROLE_INFO = "info"
ROLES = (ROLE_CHAPTER, ROLE_SUBCHAPTER, ROLE_REQUIREMENT, ROLE_INFO)


class RequirementExtractor:
    """
    Structure-first compliance extractor.

    What the AI does
    ----------------
    The AI only reads the document and says WHERE each structural node
    STARTS (chapter, subchapter, requirement, info) and how the document
    numbers/names its levels. It never decides where a node ENDS and it
    never writes source text.

    What local code does
    --------------------
    * Normalises the PDF text (Arabic presentation forms, tatweel, glued
      words/references) and removes repeated headers/footers.
    * Merges blocks and tables in reading order without duplicates.
    * Locates every start anchor with a spacing/punctuation/Unicode tolerant
      matcher (the AI "cleaning" a jammed anchor can no longer break it).
    * Ends every node at the start of the next node -> source text is
      complete and never cut mid-sentence.
    * Learns the numbering from the nodes the AI returned and uses it to
      find siblings the AI skipped (gap recovery) and to ask for
      continuation when the AI stopped early.
    * Builds the chapter -> subchapter -> requirement tree and keeps parent
      lead-in text / objective as CONTEXT (never mixed into source_text).

    Nothing here is tied to one framework's numbering.
    """

    # ------------------------------------------------------------------
    # SETTINGS
    # ------------------------------------------------------------------

    MAX_SINGLE_PASS_TOKENS = 70_000
    CHUNK_TOKENS = 45_000
    CHUNK_OVERLAP_RECORDS = 12
    MAX_CONTINUATIONS = 2
    CONTINUATION_REMAINING_RATIO = 0.15
    CONTINUATION_MIN_CHARS = 4_000
    MIN_UNIT_CHARS = 15
    MAX_UNIT_CHARS_WARNING = 15_000
    MAX_TAIL_RECOVERY = 40
    REPAIR_GLUED_TEXT = True
    AI_ATTEMPTS = 2

    # ------------------------------------------------------------------
    # REGEXES
    # ------------------------------------------------------------------

    _INVISIBLE = re.compile(
        "[\u200b-\u200f\u202a-\u202e\u2066-\u2069\ufeff\u00ad\u0640]"
    )

    _REF_TOKEN = r"(?:\d{1,3}|[A-Z])"

    # "1-1-1With" -> "1-1-1 With"
    _GLUE_AFTER_REF = re.compile(
        rf"(?<![\d\-])(\d{{1,3}}(?:-{_REF_TOKEN})+)(?=[A-Z][a-z])"
    )
    # "annually1-1-2" -> "annually" + newline + "1-1-2" (ref starts a line)
    _GLUE_BEFORE_REF = re.compile(
        rf"(?<=[a-z.:;)])(?="
        rf"\d{{1,3}}(?:-{_REF_TOKEN}){{2,}}(?![\d\-])"
        rf"|\d{{1,3}}(?:-{_REF_TOKEN})+(?=[A-Z][a-z]))"
    )
    # "level.At least" -> "level. At least"
    _GLUE_SENTENCE = re.compile(r"(?<=[a-z]{2}[.;])(?=[A-Z][a-z])")
    # visual-order brackets  ")5 (" -> "(5)"
    _REVERSED_PAREN_NUMBER = re.compile(r"\)\s?(\d{1,3})\s?\(")

    _JAMMED_TOC = re.compile(r"[A-Za-z]\d{1,3}-\d{1,3}(?:-\d{1,3})?[A-Z]")

    _VARIANTS = str.maketrans(
        {
            "ی": "ي", "ې": "ي", "ى": "ي", "ئ": "ي",
            "ک": "ك", "ڪ": "ك",
            "أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا",
            "ة": "ه", "ۀ": "ه", "ہ": "ه", "ھ": "ه",
            "ؤ": "و",
        }
    )

    # ------------------------------------------------------------------
    # INIT
    # ------------------------------------------------------------------

    def __init__(self):
        self.client = OpenAIClient()
        self._reset()

    def _reset(self) -> None:
        self.last_profile: dict[str, Any] = {}
        self.last_warnings: list[str] = []
        self.last_structure: list[dict[str, Any]] = []
        self.last_tree: list[dict[str, Any]] = []
        self.last_meta: dict[str, dict[str, Any]] = {}
        self.last_coverage: dict[str, Any] = {}

    def get_candidate_context(self, candidate_id: str) -> dict[str, Any]:
        """Hierarchy + context for one candidate (for the analysis step)."""
        return self.last_meta.get(candidate_id, {})

    # ------------------------------------------------------------------
    # PUBLIC
    # ------------------------------------------------------------------

    def extract(
        self,
        document: CleanedDocument,
    ) -> list[RequirementCandidate]:

        self._reset()

        records = self._build_records(document)

        if not records:
            raise RequirementExtractionError(
                "No usable source text was extracted from the PDF."
            )

        full = self._index_records(records)
        total_pages = len(document.pages)

        print(
            f"Source records: {len(records)} | "
            f"{len(full):,} characters | pages: {total_pages}"
        )

        discovery = self._discover(records, full)

        nodes = discovery["nodes"]
        self.last_profile = discovery["profile"]

        nodes, recovered, gaps = self._recover_gaps(nodes, full)

        if recovered:
            self.last_warnings.append(
                f"{len(recovered)} node(s) the AI skipped were recovered "
                f"locally from the numbering sequence."
            )

        if gaps:
            self.last_warnings.append(
                "Numbering gaps that could not be recovered: "
                + ", ".join(gaps[:30])
            )

        candidates = self._assemble(records, full, nodes)

        self._finalize_coverage(
            records=records,
            nodes=nodes,
            candidates=candidates,
            recovered=recovered,
            gaps=gaps,
            discovery=discovery,
            total_pages=total_pages,
        )

        self._print_summary()

        return candidates

    # ------------------------------------------------------------------
    # TEXT NORMALISATION
    # ------------------------------------------------------------------

    def _normalize_source_text(self, text: Any) -> str:

        value = unicodedata.normalize("NFKC", str(text or ""))
        value = self._INVISIBLE.sub("", value)
        value = value.replace("\u00a0", " ")
        value = value.replace("\r\n", "\n").replace("\r", "\n")

        lines = []

        for line in value.split("\n"):
            line = re.sub(r"[ \t]+", " ", line).strip()

            if line:
                lines.append(line)

        value = "\n".join(lines)

        value = self._REVERSED_PAREN_NUMBER.sub(r"(\1)", value)

        if self.REPAIR_GLUED_TEXT:
            value = self._GLUE_SENTENCE.sub(" ", value)
            value = self._GLUE_BEFORE_REF.sub("\n", value)
            value = self._GLUE_AFTER_REF.sub(r"\1 ", value)

        return value.strip()

    def _squash(self, text: str) -> tuple[str, list[int]]:
        """Letters+digits only, Arabic/Persian variants unified.

        Returns the squashed string and, for every squashed char, its index
        in the original text. Used only for MATCHING.
        """

        chars: list[str] = []
        index: list[int] = []

        for position, char in enumerate(text):

            if char.isdigit():
                try:
                    char = str(unicodedata.digit(char))
                except (TypeError, ValueError):
                    pass

                chars.append(char)
                index.append(position)

            elif char.isalpha():
                chars.append(char.lower().translate(self._VARIANTS))
                index.append(position)

        return "".join(chars), index

    # ------------------------------------------------------------------
    # RECORDS (blocks + tables, reading order, no duplicates)
    # ------------------------------------------------------------------

    def _build_records(self, document: CleanedDocument) -> list[dict[str, Any]]:

        pages = []

        for page in document.pages:
            pages.append([page.page_number, self._page_items(page)])

        self._normalize_arabic_letters(pages)
        self._strip_boilerplate(pages)

        records: list[dict[str, Any]] = []
        sequence = 1

        for page_number, items in pages:

            for item in items:
                text = item["text"].strip()

                if not text or self._is_noise_record(text):
                    continue

                records.append(
                    {
                        "source_id": f"s{sequence:06d}",
                        "block_id": item["block_id"],
                        "page_number": page_number,
                        "text": text,
                        "toc": False,
                    }
                )

                sequence += 1

        self._flag_toc_records(records)

        return records

    _PERSIAN_LETTER_MAP = str.maketrans(
        {"ک": "ك", "ی": "ي", "ې": "ي", "ڪ": "ك"}
    )

    def _normalize_arabic_letters(self, pages) -> None:
        """PDF fonts often encode Arabic with Persian-shaped kaf/yeh.

        Convert them to standard Arabic letters, but only when the whole
        document is clearly Arabic (no Persian/Urdu-only letters), so
        searching, summaries and the AI's copied anchors agree.
        """

        sample = " ".join(
            item["text"] for _, items in pages for item in items
        )

        arabic_letters = len(re.findall(r"[\u0621-\u064A]", sample))

        if arabic_letters < 200:
            return

        if re.search(r"[پچژگٹڈڑںےھ]", sample):
            return

        for _, items in pages:
            for item in items:
                item["text"] = item["text"].translate(
                    self._PERSIAN_LETTER_MAP
                )

    def _page_items(self, page) -> list[dict[str, Any]]:

        excluded = {"header", "footer", "page_number"}

        tables = []

        for table in getattr(page, "tables", None) or []:
            rows = []

            for row_index, row in enumerate(table.rows):
                cells = []

                for cell in row:
                    if cell is None:
                        continue

                    value = self._normalize_source_text(cell).replace("\n", " ")

                    if value:
                        cells.append(value)

                if cells:
                    rows.append((row_index, " | ".join(cells)))

            if rows:
                tables.append(
                    {
                        "table_id": table.table_id,
                        "rows": rows,
                        "bbox": self._bbox(table),
                    }
                )

        pending = sorted(
            [t for t in tables if t["bbox"]],
            key=lambda t: t["bbox"][1],
        )
        unplaced = [t for t in tables if not t["bbox"]]

        items: list[dict[str, Any]] = []

        def emit_table(info):
            for row_index, text in info["rows"]:
                items.append(
                    {
                        "text": text,
                        "block_id": f"{info['table_id']}:row:{row_index}",
                    }
                )

        for block in page.blocks:

            if block.block_type in excluded:
                continue

            text = self._normalize_source_text(block.text)

            if not text:
                continue

            y0 = getattr(block, "y0", 0.0) or 0.0

            while pending and pending[0]["bbox"][1] <= y0:
                emit_table(pending.pop(0))

            if self._inside_table(block, tables):
                continue

            items.append({"text": text, "block_id": block.block_id})

        for info in pending + unplaced:
            emit_table(info)

        return items

    def _bbox(self, table):
        for attr in ("bbox", "rect", "bounding_box"):
            value = getattr(table, attr, None)

            if value is None:
                continue

            try:
                if len(value) == 4:
                    return tuple(float(v) for v in value)
            except (TypeError, ValueError):
                continue

        return None

    def _inside_table(self, block, tables) -> bool:

        x0 = getattr(block, "x0", 0.0) or 0.0
        x1 = getattr(block, "x1", 0.0) or 0.0
        y0 = getattr(block, "y0", 0.0) or 0.0
        y1 = getattr(block, "y1", 0.0) or 0.0

        if not (x1 or y1):
            return False

        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2

        for table in tables:
            box = table["bbox"]

            if box and box[0] <= cx <= box[2] and box[1] <= cy <= box[3]:
                return True

        return False

    def _is_noise_record(self, text: str) -> bool:
        value = text.strip().lower()

        return bool(
            re.fullmatch(r"\d{1,4}", value)
            or re.fullmatch(r"page\s+\d+(?:\s+of\s+\d+)?", value)
            or re.fullmatch(r"\d+\s+of\s+\d+", value)
        )

    def _line_key(self, line: str) -> str:
        squashed, _ = self._squash(re.sub(r"\d+", "#", line))
        return squashed

    def _strip_boilerplate(self, pages) -> None:
        """Remove page furniture, also when glued inside a block.

        * a whole line repeated (digits ignored) on >= 40% of pages;
        * any 6-word run repeated on >= 40% of pages (+ adjacent numbers).
        """

        total = len(pages)

        if total < 4:
            return

        threshold = max(3, int(total * 0.4))
        shingle = 6

        line_counter: Counter = Counter()
        shingle_counter: Counter = Counter()

        for _, items in pages:
            lines_seen = set()
            shingles_seen = set()

            for item in items:
                for line in item["text"].split("\n"):
                    if 3 <= len(line) <= 160 and not re.match(
                        r"^[\(\[]?\d{1,3}[\.\)\-]", line
                    ):
                        lines_seen.add(self._line_key(line))

                    tokens = [
                        re.sub(r"\d+", "#", t.lower()) for t in line.split()
                    ]

                    for i in range(len(tokens) - shingle + 1):
                        shingles_seen.add(tuple(tokens[i:i + shingle]))

            line_counter.update(lines_seen)
            shingle_counter.update(shingles_seen)

        repeated_lines = {
            key for key, count in line_counter.items()
            if count >= threshold and key
        }
        repeated_shingles = {
            key for key, count in shingle_counter.items()
            if count >= threshold
        }

        if not repeated_lines and not repeated_shingles:
            return

        for entry in pages:
            for item in entry[1]:
                kept_lines = []

                for line in item["text"].split("\n"):

                    if self._line_key(line) in repeated_lines:
                        continue

                    tokens = line.split()
                    norm = [re.sub(r"\d+", "#", t.lower()) for t in tokens]
                    covered = [False] * len(tokens)

                    for i in range(len(norm) - shingle + 1):
                        if tuple(norm[i:i + shingle]) in repeated_shingles:
                            for k in range(i, i + shingle):
                                covered[k] = True

                    if any(covered):
                        snapshot = covered[:]

                        for k, token in enumerate(tokens):
                            if snapshot[k] or not re.fullmatch(
                                r"\d{1,4}", token
                            ):
                                continue

                            if (k > 0 and snapshot[k - 1]) or (
                                k + 1 < len(tokens) and snapshot[k + 1]
                            ):
                                covered[k] = True

                        line = " ".join(
                            t for t, c in zip(tokens, covered) if not c
                        )

                    if line.strip():
                        kept_lines.append(line.strip())

                item["text"] = "\n".join(kept_lines)

    def _flag_toc_records(self, records) -> None:
        """Mark records on table-of-contents-like pages (structure hint)."""

        by_page: dict[int, list[dict[str, Any]]] = {}

        for record in records:
            by_page.setdefault(record["page_number"], []).append(record)

        for page_records in by_page.values():

            joined = " ".join(r["text"] for r in page_records)
            count = len(page_records)

            # 1) most rows end with a page number / dot leader
            ends_with_number = sum(
                1 for r in page_records
                if re.search(r"(?:\s|\|)\d{1,3}\s*$", r["text"])
                or re.search(r"\.{3,}\s*\d{1,3}\s*$", r["text"])
            )
            short = sum(1 for r in page_records if len(r["text"]) < 140)

            is_toc = (
                count >= 6
                and ends_with_number / count >= 0.6
                and short / count >= 0.7
            )

            # 2) dense list of references with titles and no sentences
            references = len(
                re.findall(
                    r"(?<![\d\-])\d{1,3}(?:-\d{1,3}){1,3}(?![\d\-])", joined
                )
            )
            words = len(joined.split()) or 1
            sentences = len(re.findall(r"[.;:!?؟](?:\s|$)", joined))

            if references >= 2 and references / words >= 0.08 and sentences <= 1:
                is_toc = True

            if is_toc:
                for record in page_records:
                    record["toc"] = True

    def _index_records(self, records) -> str:

        position = 0
        parts = []

        for record in records:
            record["offset"] = position
            parts.append(record["text"])
            position += len(record["text"]) + 1

        self._offsets = [record["offset"] for record in records]
        self._records = records
        self._full_text = "\n".join(parts)

        return self._full_text

    def _record_at(self, offset: int) -> int:
        return max(0, bisect_right(self._offsets, offset) - 1)

    # ------------------------------------------------------------------
    # DISCOVERY (AI: where nodes START)
    # ------------------------------------------------------------------

    def _estimate_tokens(self, text: str) -> int:
        non_latin = sum(1 for char in text if ord(char) > 0x2FF)
        return (len(text) - non_latin) // 4 + int(non_latin / 1.6)

    def _plan_ranges(self, records) -> list[tuple[int, int]]:

        sizes = [self._estimate_tokens(r["text"]) + 40 for r in records]

        if sum(sizes) <= self.MAX_SINGLE_PASS_TOKENS:
            print("AI discovery mode: FULL DOCUMENT")
            return [(0, len(records))]

        print("AI discovery mode: CHUNKED DOCUMENT")

        ranges = []
        start = 0

        while start < len(records):
            total = 0
            end = start

            while end < len(records) and (
                total + sizes[end] <= self.CHUNK_TOKENS or end == start
            ):
                total += sizes[end]
                end += 1

            ranges.append((start, end))

            if end >= len(records):
                break

            start = max(start + 1, end - self.CHUNK_OVERLAP_RECORDS)

        return ranges

    def _discover(self, records, full) -> dict[str, Any]:

        profiles: list[dict[str, Any]] = []
        all_nodes: list[dict[str, Any]] = []
        rejected: list[str] = []
        ai_node_count = 0
        continuation_runs = 0

        ranges = self._plan_ranges(records)

        for range_number, (range_start, range_end) in enumerate(ranges, 1):

            current_start = range_start

            for attempt in range(self.MAX_CONTINUATIONS + 1):

                subset = records[current_start:range_end]

                label = (
                    f"{range_number}/{len(ranges)}"
                    + (f" continuation {attempt}" if attempt else "")
                )
                print(f"AI discovery pass {label}")

                response = self._ai_pass(
                    subset,
                    grammar_hint=self._grammar_hint(profiles, all_nodes),
                    mode="chunk" if len(ranges) > 1 or attempt else "full",
                    fallback=False,
                )

                profiles.append(response.get("document_profile", {}))

                raw_nodes = response.get("nodes", [])
                ai_node_count += len(raw_nodes)

                resolved, bad = self._resolve_nodes(
                    records=records,
                    raw_nodes=raw_nodes,
                    floor=records[current_start]["offset"],
                )

                all_nodes.extend(resolved)
                rejected.extend(bad)

                if not resolved:
                    break

                last_record = max(n["record_index"] for n in resolved)

                remaining_chars = sum(
                    len(r["text"])
                    for r in records[last_record + 1:range_end]
                )
                span_chars = sum(
                    len(r["text"]) for r in records[current_start:range_end]
                ) or 1

                if (
                    attempt < self.MAX_CONTINUATIONS
                    and remaining_chars >= self.CONTINUATION_MIN_CHARS
                    and remaining_chars / span_chars
                    >= self.CONTINUATION_REMAINING_RATIO
                ):
                    continuation_runs += 1
                    current_start = max(
                        range_start,
                        last_record - self.CHUNK_OVERLAP_RECORDS,
                    )
                    continue

                break

        nodes = self._dedupe_nodes(all_nodes)

        if not any(n["role"] == ROLE_REQUIREMENT for n in nodes):
            self.last_warnings.append(
                "No requirement nodes found on the first attempt; "
                "retrying with relaxed rules."
            )
            print("No requirements found - retrying with relaxed rules")

            response = self._ai_pass(
                records,
                grammar_hint=self._grammar_hint(profiles, nodes),
                mode="full",
                fallback=True,
            )

            profiles.append(response.get("document_profile", {}))

            resolved, bad = self._resolve_nodes(
                records=records,
                raw_nodes=response.get("nodes", []),
                floor=0,
            )

            ai_node_count += len(response.get("nodes", []))
            rejected.extend(bad)
            nodes = self._dedupe_nodes(nodes + resolved)

        return {
            "profile": self._merge_profiles(profiles),
            "nodes": nodes,
            "rejected": rejected,
            "ai_nodes": ai_node_count,
            "continuations": continuation_runs,
        }

    def _grammar_hint(self, profiles, nodes) -> str:

        if not profiles:
            return ""

        merged = self._merge_profiles(profiles)
        lines = []

        if merged.get("hierarchy_levels"):
            lines.append(
                "Levels learned so far: "
                + " > ".join(merged["hierarchy_levels"])
            )

        if merged.get("numbering_examples"):
            lines.append(
                "Reference examples seen: "
                + ", ".join(merged["numbering_examples"][:10])
            )

        if merged.get("requirement_unit_name"):
            lines.append(
                "Requirement unit: " + merged["requirement_unit_name"]
            )

        structural = [
            n for n in sorted(nodes, key=lambda n: n["start"])
            if n["role"] in (ROLE_CHAPTER, ROLE_SUBCHAPTER)
        ][-4:]

        if structural:
            lines.append(
                "Last structural nodes already found (continue from them): "
                + "; ".join(
                    f"L{n['level']} {n['role']} "
                    f"{n.get('reference') or ''} {n.get('title') or ''}".strip()
                    for n in structural
                )
            )

        return "\n".join(lines)

    def _ai_pass(self, subset, grammar_hint, mode, fallback) -> dict[str, Any]:

        document_text = self._build_ai_document(subset)

        prompt = self._discovery_prompt(
            document_text=document_text,
            mode=mode,
            grammar_hint=grammar_hint,
            fallback=fallback,
        )

        last_error: Exception | None = None

        for attempt in range(1, self.AI_ATTEMPTS + 1):
            try:
                response = self.client.generate_json(
                    instructions=self._discovery_system_prompt(),
                    input_text=prompt,
                    schema=self._discovery_schema(),
                    schema_name="compliance_document_structure",
                )

                self._validate_discovery_response(response)

                return response

            except Exception as exc:  # noqa: BLE001
                last_error = exc
                self.last_warnings.append(
                    f"AI discovery attempt {attempt} failed: {exc}"
                )

        raise RequirementExtractionError(
            f"AI discovery failed after {self.AI_ATTEMPTS} attempts: "
            f"{last_error}"
        )

    def _build_ai_document(self, records) -> str:

        parts = []

        for record in records:
            page_line = f"PAGE: {record['page_number']}"

            if record.get("toc"):
                page_line += (
                    " (TABLE-OF-CONTENTS-LIKE PAGE: use it to learn the "
                    "structure, never start a node here)"
                )

            parts.append(
                "\n".join(
                    [
                        f"=== SOURCE BLOCK {record['source_id']} ===",
                        page_line,
                        "TEXT:",
                        record["text"],
                        "=== END SOURCE BLOCK ===",
                    ]
                )
            )

        return "\n\n".join(parts)

    def _validate_discovery_response(self, response: Any) -> None:

        if not isinstance(response, dict):
            raise RequirementExtractionError(
                "AI discovery returned an invalid object."
            )

        if not isinstance(response.get("document_profile"), dict):
            raise RequirementExtractionError(
                "AI discovery returned an invalid document profile."
            )

        if not isinstance(response.get("nodes"), list):
            raise RequirementExtractionError(
                "AI discovery returned an invalid nodes list."
            )

    # ------------------------------------------------------------------
    # PROMPTS / SCHEMA
    # ------------------------------------------------------------------

    def _discovery_system_prompt(self) -> str:

        return """
You are the document-structure discovery engine for Sahl Compliance
Decoder.

You receive a compliance document (standard, regulation, law, control
framework, policy, guideline, ...) split into numbered SOURCE BLOCKS.
Your job is to describe how THIS document is organised and to say WHERE
each structural node STARTS. You do not write or end anything: the
application computes every end (a node ends where the next node starts)
and reconstructs all text itself.

Never assume a numbering scheme, a hierarchy depth or a terminology.
Learn them from the document (its table of contents is the best
evidence) and use the document's own words.

NODE ROLES
- chapter: top-level division that groups related content (a "domain",
  "chapter", "part", ...).
- subchapter: a division inside a chapter that groups requirements and
  usually carries an objective/purpose statement. Use it only if the
  document really has this intermediate level.
- requirement: the smallest numbered or headed unit that an organisation
  would turn into ONE implementation task (a control, clause, article,
  safeguard, obligation, provision, ...). Its sub-items - (a), (b),
  1-2-1-1 under a control that says "must include the following", numbered
  clauses inside an article - are NOT separate nodes; they stay inside the
  requirement. If sub-items are independent controls of their own,
  each one is a requirement.
- info: anything that is NOT a requirement and must stop the previous node:
  table of contents, cover, preface, document-level introduction / scope /
  applicability statements, definitions, glossary, abbreviations,
  appendices, annexes, revision history, figures. Return ONE info node at
  the start of each such section so that the previous node ends there.

LEVEL
- Integer depth, 1 = top. A node's parent is the nearest earlier node with
  a smaller level. Use consistent levels for the same kind of node.

WHAT TO RETURN FOR EVERY NODE
- start_source_id: the SOURCE BLOCK in which the node starts. Never a block
  from a table-of-contents-like page.
- start_anchor: the first 6-15 words of the node copied VERBATIM from that
  block, beginning at its number/reference if it has one. Copy exactly what
  is printed, including odd spacing or glued words. Do NOT correct, re-space,
  translate or reorder. The anchor must lie inside ONE block.
- reference: the number/label exactly as printed ("1-1-1", "Article 5",
  "A.5.1", ...). Never add the document or framework name. null when the
  node has no number.
- title: the heading text exactly as printed when the node has one, else
  null. Never use the document title as a node title.
- confidence: 0-1.

COMPLETENESS (very important)
- List EVERY node in reading order. Do not summarise, sample or stop early.
- Check the numbering yourself: if you list 1-1-1 and 1-1-3, look for 1-1-2.
  Add every numbered unit that exists.
- Do not return a node for text that only repeats a table-of-contents
  entry; use the body occurrence.
- Do not invent nodes, references or text.

DOCUMENT PROFILE
Describe what the document actually is. Leave a field empty (or an empty
list) when the source does not support it. Do not guess names, versions,
jurisdictions or industries. numbering_examples: up to 8 references copied
exactly from the document that show each level of its numbering.
""".strip()

    def _discovery_prompt(
        self,
        document_text: str,
        mode: str,
        grammar_hint: str,
        fallback: bool,
    ) -> str:

        if mode == "full":
            scope = (
                "You have the complete document. Understand its table of "
                "contents, numbering and terminology first, then list every "
                "node."
            )
        else:
            scope = (
                "This is a segment of a larger document. List every node "
                "that STARTS inside this segment. Blocks at the beginning "
                "may overlap with the previous segment - listing a node "
                "twice is harmless."
            )

        hint = (
            f"\nKNOWN DOCUMENT GRAMMAR (from earlier parts, keep levels "
            f"consistent with it):\n{grammar_hint}\n"
            if grammar_hint
            else ""
        )

        relaxed = (
            "\nRELAXED MODE: an earlier attempt found no requirement nodes. "
            "Treat every headed section or numbered clause that states an "
            "obligation, permission, prohibition, criterion or procedure as "
            "a requirement.\n"
            if fallback
            else ""
        )

        return f"""
{scope}
{hint}{relaxed}
Return the document profile and the list of nodes
(node_id, role, level, reference, title, start_source_id, start_anchor,
confidence). Do not return source text and do not return end positions.

SOURCE DOCUMENT:

{document_text}
""".strip()

    def _discovery_schema(self) -> dict[str, Any]:

        nullable_string = {"type": ["string", "null"]}

        node_schema = {
            "type": "object",
            "properties": {
                "node_id": {"type": "string"},
                "role": {"type": "string", "enum": list(ROLES)},
                "level": {"type": "integer"},
                "reference": nullable_string,
                "title": nullable_string,
                "start_source_id": {"type": "string"},
                "start_anchor": {"type": "string"},
                "confidence": {"type": "number"},
            },
            "required": [
                "node_id", "role", "level", "reference", "title",
                "start_source_id", "start_anchor", "confidence",
            ],
            "additionalProperties": False,
        }

        string_list = {"type": "array", "items": {"type": "string"}}

        profile_schema = {
            "type": "object",
            "properties": {
                "document_title": {"type": "string"},
                "document_type": {"type": "string"},
                "framework_name": {"type": "string"},
                "version": {"type": "string"},
                "jurisdiction": {"type": "string"},
                "requirement_unit_name": {"type": "string"},
                "hierarchy_description": {"type": "string"},
                "hierarchy_levels": string_list,
                "numbering_examples": string_list,
                "regulation_summary": {"type": "string"},
                "applicability_conditions": {"type": "string"},
                "applicable_industries": string_list,
            },
            "required": [
                "document_title", "document_type", "framework_name",
                "version", "jurisdiction", "requirement_unit_name",
                "hierarchy_description", "hierarchy_levels",
                "numbering_examples", "regulation_summary",
                "applicability_conditions", "applicable_industries",
            ],
            "additionalProperties": False,
        }

        return {
            "type": "object",
            "properties": {
                "document_profile": profile_schema,
                "nodes": {"type": "array", "items": node_schema},
            },
            "required": ["document_profile", "nodes"],
            "additionalProperties": False,
        }

    def _merge_profiles(self, profiles) -> dict[str, Any]:

        merged: dict[str, Any] = {}

        text_fields = [
            "document_title", "document_type", "framework_name", "version",
            "jurisdiction", "requirement_unit_name", "hierarchy_description",
            "regulation_summary", "applicability_conditions",
        ]

        for field in text_fields:
            merged[field] = ""

            for profile in profiles:
                value = (profile or {}).get(field, "")

                if isinstance(value, str) and value.strip():
                    merged[field] = value.strip()
                    break

        for field in (
            "hierarchy_levels", "numbering_examples", "applicable_industries",
        ):
            values: list[str] = []

            for profile in profiles:
                items = (profile or {}).get(field, [])

                if not isinstance(items, list):
                    continue

                for item in items:
                    if (
                        isinstance(item, str)
                        and item.strip()
                        and item.strip() not in values
                    ):
                        values.append(item.strip())

            merged[field] = values

        return merged

    # ------------------------------------------------------------------
    # ANCHOR RESOLUTION
    # ------------------------------------------------------------------

    def _rec_squash(self, record) -> tuple[str, list[int]]:

        if "_sq" not in record:
            record["_sq"] = self._squash(record["text"])

        return record["_sq"]

    def _locate(self, record, anchor: str, hint: int):
        """Spacing/punctuation/Unicode tolerant search inside one record."""

        squashed, index = self._rec_squash(record)

        needle_full, _ = self._squash(
            unicodedata.normalize("NFKC", anchor or "")
        )

        if len(needle_full) < 3:
            return None

        needles = [(needle_full, "full")]

        for size in (40, 24, 14, 8):
            if len(needle_full) > size:
                needles.append((needle_full[:size], "prefix"))

        begin = bisect_left(index, hint) if hint > 0 else 0

        for needle, mode in needles:

            for origin in ([begin, 0] if begin else [0]):
                position = squashed.find(needle, origin)

                if position >= 0:
                    start = index[position]
                    end = index[position + len(needle) - 1] + 1
                    return start, end, mode

        return None

    def _ref_regex(self, reference: str):

        tokens = re.findall(r"\d+|[^\W\d_]+", reference or "")

        if not tokens:
            return None

        parts = []

        for position, token in enumerate(tokens):
            if position:
                previous = tokens[position - 1]
                parts.append(
                    r"[\W_]{1,3}"
                    if previous.isdigit() and token.isdigit()
                    else r"[\W_]{0,3}"
                )

            parts.append(re.escape(token))

        return re.compile(
            r"(?<![\d\-])" + "".join(parts) + r"(?!\d|-\d)",
            re.IGNORECASE,
        )

    def _anchor_like(self, text: str, position: int) -> bool:
        """At a line start or glued to a word; not 'see control 1-8-1,'."""

        return (
            position == 0
            or text[position - 1] == "\n"
            or not text[position - 1].isspace()
        )

    def _locate_by_reference(self, text: str, reference: str, begin: int):

        pattern = self._ref_regex(reference)

        if pattern is None:
            return None

        for match in pattern.finditer(text, max(0, begin)):
            if self._anchor_like(text, match.start()):
                return match.start(), match.end()

        return None

    def _resolve_nodes(self, records, raw_nodes, floor: int):

        by_source = {r["source_id"]: i for i, r in enumerate(records)}
        by_block = {r["block_id"]: i for i, r in enumerate(records)}

        resolved: list[dict[str, Any]] = []
        rejected: list[str] = []

        cursor = floor

        for raw in raw_nodes:

            if not isinstance(raw, dict):
                continue

            role = raw.get("role")

            if role not in ROLES:
                rejected.append(f"{raw.get('node_id')}: unknown role {role!r}")
                continue

            reference = (raw.get("reference") or "").strip()
            title = (raw.get("title") or "").strip()
            anchor = raw.get("start_anchor") or ""

            index = by_source.get(raw.get("start_source_id"))

            if index is None:
                index = by_block.get(raw.get("start_source_id"))

            start = None
            method = None

            if index is not None:
                record = records[index]

                hint = (
                    cursor - record["offset"]
                    if record["offset"] <= cursor
                    else 0
                )

                located = self._locate(record, anchor, max(0, hint))

                if located:
                    start = record["offset"] + located[0]
                    method = located[2]

                elif reference:
                    byref = self._locate_by_reference(
                        record["text"], reference, max(0, hint)
                    ) or self._locate_by_reference(record["text"], reference, 0)

                    if byref:
                        start = record["offset"] + byref[0]
                        method = "reference"

            if start is None and reference:
                found = self._locate_by_reference(
                    self._all_text, reference, cursor
                )

                if found:
                    start = found[0]
                    method = "reference-global"

            if start is None:
                rejected.append(
                    f"{raw.get('node_id')} {reference or title or anchor[:30]!r}: "
                    f"anchor not found"
                )
                continue

            start = self._extend_to_reference(start, reference, cursor)

            record_index = self._record_at(start)

            if (
                role == ROLE_REQUIREMENT
                and records[record_index].get("toc")
            ):
                rejected.append(
                    f"{raw.get('node_id')} {reference!r}: starts on a "
                    f"table-of-contents page"
                )
                continue

            try:
                level = int(raw.get("level", 1))
            except (TypeError, ValueError):
                level = 1

            resolved.append(
                {
                    "node_id": str(raw.get("node_id") or ""),
                    "role": role,
                    "level": max(1, min(level, 8)),
                    "reference": reference,
                    "title": title,
                    "start": start,
                    "record_index": record_index,
                    "method": method,
                    "confidence": self._float(raw.get("confidence")),
                    "recovered": False,
                }
            )

            cursor = max(cursor, start)

        return resolved, rejected

    @property
    def _all_text(self) -> str:
        return self._full_text

    def _extend_to_reference(self, start: int, reference: str, floor: int) -> int:
        """If the reference sits just before the anchor, include it."""

        if not reference:
            return start

        pattern = self._ref_regex(reference)

        if pattern is None:
            return start

        window_start = max(floor + 1, start - len(reference) - 12, 0)
        window = self._full_text[window_start:start + len(reference) + 12]

        for match in pattern.finditer(window):
            absolute = window_start + match.start()

            if absolute < start and start - absolute <= 40 and (
                self._anchor_like(self._full_text, absolute)
            ):
                return absolute

        return start

    def _dedupe_nodes(self, nodes) -> list[dict[str, Any]]:

        ordered = sorted(
            nodes,
            key=lambda n: (n["start"], n["level"], n["role"] != ROLE_CHAPTER),
        )

        result: list[dict[str, Any]] = []
        seen = set()

        for node in ordered:
            key = (node["start"], node["role"], node["reference"].lower())

            if key in seen:
                continue

            seen.add(key)
            result.append(node)

        return result

    def _float(self, value: Any) -> float:
        try:
            return max(0.0, min(1.0, float(value)))
        except (TypeError, ValueError):
            return 0.0

    # ------------------------------------------------------------------
    # GAP RECOVERY (numbering learned from the AI's own nodes)
    # ------------------------------------------------------------------

    def _recover_gaps(self, nodes, full):

        nodes = sorted(nodes, key=lambda n: n["start"])

        groups: dict[tuple, list[tuple[int, int, dict]]] = {}

        for node in nodes:
            if node["role"] == ROLE_INFO or not node["reference"]:
                continue

            match = re.match(
                r"^(?P<pre>.*?)(?P<num>\d+)(?P<suf>\D*)$", node["reference"]
            )

            if not match:
                continue

            key = (
                re.sub(r"\s+", "", match["pre"]),
                re.sub(r"\s+", "", match["suf"]),
                node["role"],
            )

            groups.setdefault(key, []).append(
                (int(match["num"]), len(match["num"]), node)
            )

        recovered: list[dict[str, Any]] = []
        gaps: list[str] = []
        taken_starts = {n["start"] for n in nodes}

        for key, members in groups.items():

            if len(members) < 2:
                continue

            members.sort(key=lambda m: m[0])
            numbers = {m[0]: m for m in members}
            low, high = members[0][0], members[-1][0]

            sample_ref = members[0][2]["reference"]
            sample = re.match(
                r"^(?P<pre>.*?)(?P<num>\d+)(?P<suf>\D*)$", sample_ref
            )

            def build_reference(number: int) -> str:
                width = len(sample["num"]) if sample["num"].startswith("0") else 0
                return f"{sample['pre']}{str(number).zfill(width)}{sample['suf']}"

            # interior gaps
            for number in range(low, high + 1):

                if number in numbers:
                    continue

                previous = max(n for n in numbers if n < number)
                following = min(n for n in numbers if n > number)

                window_start = numbers[previous][2]["start"] + 1
                window_end = numbers[following][2]["start"]

                node = self._find_missing(
                    full,
                    build_reference(number),
                    window_start,
                    window_end,
                    template=numbers[previous][2],
                    taken=taken_starts,
                )

                if node:
                    recovered.append(node)
                    taken_starts.add(node["start"])
                else:
                    gaps.append(build_reference(number))

            # tail siblings after the last one the AI listed
            last_node = members[-1][2]
            limit = len(full)
            member_ids = {id(m[2]) for m in members}

            for other in nodes:
                if other["start"] > last_node["start"] and (
                    other["level"] < last_node["level"]
                    or (
                        other["level"] == last_node["level"]
                        and id(other) not in member_ids
                    )
                ):
                    limit = other["start"]
                    break

            number = high + 1
            window_start = last_node["start"] + 1

            for _ in range(self.MAX_TAIL_RECOVERY):
                node = self._find_missing(
                    full,
                    build_reference(number),
                    window_start,
                    limit,
                    template=last_node,
                    taken=taken_starts,
                )

                if not node:
                    break

                recovered.append(node)
                taken_starts.add(node["start"])
                window_start = node["start"] + 1
                number += 1

        merged = self._dedupe_nodes(nodes + recovered)

        return merged, recovered, gaps

    def _find_missing(self, full, reference, begin, end, template, taken):

        pattern = self._ref_regex(reference)

        if pattern is None or begin >= end:
            return None

        for match in pattern.finditer(full, begin, end):

            if match.start() in taken:
                continue

            if not self._anchor_like(full, match.start()):
                continue

            record_index = self._record_at(match.start())

            if self._records[record_index].get("toc"):
                continue

            return {
                "node_id": f"recovered:{reference}",
                "role": template["role"],
                "level": template["level"],
                "reference": reference,
                "title": "",
                "start": match.start(),
                "record_index": record_index,
                "method": "recovered",
                "confidence": 0.75,
                "recovered": True,
            }

        return None

    # ------------------------------------------------------------------
    # TREE + CANDIDATES
    # ------------------------------------------------------------------

    def _assemble(self, records, full, nodes) -> list[RequirementCandidate]:

        nodes = sorted(nodes, key=lambda n: (n["start"], n["level"]))

        for position, node in enumerate(nodes):
            node["end"] = (
                nodes[position + 1]["start"]
                if position + 1 < len(nodes)
                else len(full)
            )
            node["text"] = self._join_text(full[node["start"]:node["end"]])
            node["page_start"] = records[
                self._record_at(node["start"])
            ]["page_number"]
            node["page_end"] = records[
                self._record_at(max(node["start"], node["end"] - 1))
            ]["page_number"]

        # parents (stack by level; info nodes only close levels)
        stack: list[dict[str, Any]] = []

        for index, node in enumerate(nodes):
            node["index"] = index

            while stack and stack[-1]["level"] >= node["level"]:
                stack.pop()

            node["parent_index"] = stack[-1]["index"] if stack else None
            node["ancestors"] = list(stack)

            if node["role"] != ROLE_INFO:
                stack.append(node)

        children: dict[int, list[int]] = {}

        for node in nodes:
            if node["parent_index"] is not None:
                children.setdefault(node["parent_index"], []).append(
                    node["index"]
                )

        candidates: list[RequirementCandidate] = []

        for node in nodes:

            if node["role"] != ROLE_REQUIREMENT:
                continue

            has_requirement_children = any(
                nodes[c]["role"] == ROLE_REQUIREMENT
                for c in children.get(node["index"], [])
            )

            if has_requirement_children and self._is_lead_in(node["text"]):
                node["context_only"] = True
                continue

            text = node["text"]

            if len(text) < self.MIN_UNIT_CHARS:
                self.last_warnings.append(
                    f"Skipped {node['reference'] or 'unnumbered unit'}: "
                    f"text too short."
                )
                continue

            if len(text) > self.MAX_UNIT_CHARS_WARNING:
                self.last_warnings.append(
                    f"{node['reference'] or 'Unnumbered unit'} is very "
                    f"long ({len(text):,} chars): check that no unlisted "
                    f"section follows it."
                )

            candidates.append(self._make_candidate(records, nodes, node))

        for number, candidate in enumerate(candidates, start=1):
            old_id = candidate.candidate_id
            candidate.candidate_id = f"req_{number:05d}"

            self.last_meta[candidate.candidate_id] = self.last_meta.pop(old_id)

        self._build_structure_outputs(nodes, candidates)

        return candidates

    def _is_lead_in(self, text: str) -> bool:
        value = text.strip()

        return value.endswith(":") or len(value.split()) < 25

    def _join_text(self, raw: str) -> str:

        result = ""

        for part in raw.split("\n"):
            part = part.strip()

            if not part:
                continue

            if not result:
                result = part
            elif re.match(
                r"^(?:[•●▪◦\-–—*]\s|\([A-Za-z0-9\u0600-\u06FF]{1,3}\)\s"
                r"|[A-Za-z0-9\u0600-\u06FF]{1,2}[.)]\s"
                r"|\d{1,3}(?:-[A-Za-z0-9]{1,3}){1,6}\s)",
                part,
            ):
                result += "\n" + part
            else:
                result += " " + part

        return result.strip()

    def _make_candidate(self, records, nodes, node) -> RequirementCandidate:

        text = node["text"]

        first = self._record_at(node["start"])
        last = self._record_at(max(node["start"], node["end"] - 1))

        block_ids: list[str] = []

        for position in range(first, last + 1):
            block_id = records[position]["block_id"]

            if block_id not in block_ids:
                block_ids.append(block_id)

        reference, reference_ok = self._validated_reference(node, text)
        title, title_derived = self._validated_title(node, text)

        chapter = None
        subchapter = None
        parent_requirement = None

        for ancestor in node["ancestors"]:
            if ancestor["role"] == ROLE_CHAPTER:
                chapter = ancestor
            elif ancestor["role"] == ROLE_SUBCHAPTER:
                subchapter = ancestor
            elif ancestor["role"] == ROLE_REQUIREMENT:
                parent_requirement = ancestor

        path = [
            self._label(a)
            for a in node["ancestors"]
            if a["role"] in (ROLE_CHAPTER, ROLE_SUBCHAPTER)
        ]

        confidence = node["confidence"] or 0.7

        confidence *= {
            "full": 1.0, "prefix": 0.95, "reference": 0.85,
            "reference-global": 0.8, "recovered": 1.0,
        }.get(node["method"], 0.9)

        if not reference_ok:
            confidence -= 0.1

        if self._has_open_lead_in(text):
            confidence -= 0.05

        candidate_id = f"pending-{node['index']}"

        self.last_meta[candidate_id] = {
            "node_index": node["index"],
            "unit_level": node["level"],
            "hierarchy_path": path,
            "chapter": self._describe(chapter),
            "subchapter": self._describe(subchapter),
            "objective": self._objective(subchapter),
            "parent_context": (
                self._clip(parent_requirement["text"], 1500)
                if parent_requirement
                else ""
            ),
            "reference_verified": reference_ok,
            "title_is_derived": title_derived,
            "recovered_locally": node["recovered"],
            "anchor_method": node["method"],
        }

        return RequirementCandidate(
            candidate_id=candidate_id,
            node_id=None,
            source_title=title,
            source_text=text,
            page_start=node["page_start"],
            page_end=node["page_end"],
            source_block_ids=block_ids,
            source_reference=reference,
            confidence=max(0.0, min(1.0, confidence)),
        )

    def _has_open_lead_in(self, text: str) -> bool:
        return text.rstrip().endswith(":")

    def _label(self, node) -> str:
        parts = [node.get("reference") or "", self._title_of(node)]
        return " ".join(p for p in parts if p).strip()

    def _title_of(self, node) -> str:

        if node.get("title"):
            return node["title"]

        first_line = (node.get("text") or "").split("\n", 1)[0]
        reference = node.get("reference") or ""

        squashed_reference, _ = self._squash(reference)
        squashed_line, _ = self._squash(first_line)

        if len(first_line) <= 120 and not first_line.endswith("."):
            if squashed_reference and squashed_line.startswith(
                squashed_reference
            ):
                match = self._ref_regex(reference)
                found = match.search(first_line) if match else None

                if found:
                    return self._strip_title_punct(first_line[found.end():])

            return self._strip_title_punct(first_line)

        return ""

    def _describe(self, node) -> dict[str, Any] | None:

        if node is None:
            return None

        return {
            "reference": node.get("reference") or "",
            "title": self._title_of(node),
            "level": node["level"],
        }

    def _objective(self, subchapter) -> str:

        if subchapter is None:
            return ""

        text = subchapter.get("text") or ""
        parts = text.split("\n", 1)

        body = parts[1] if len(parts) > 1 and len(parts[0]) <= 200 else text

        return self._clip(body.strip(), 1500)

    def _strip_title_punct(self, value: str) -> str:
        return value.strip(" \t:-–—|)]\u00a0")

    def _clip(self, text: str, limit: int) -> str:
        return text if len(text) <= limit else text[:limit].rstrip() + " ..."

    def _validated_reference(self, node, text: str) -> tuple[str, bool]:
        """A reference must actually be printed at the start of the unit."""

        reference = node.get("reference") or ""

        if not reference:
            return "", True

        pattern = self._ref_regex(reference)

        if pattern and pattern.search(text[: len(reference) + 40]):
            return reference, True

        self.last_warnings.append(
            f"Reference {reference!r} was not found at the start of its "
            f"source text and was cleared."
        )

        return "", False

    def _validated_title(self, node, text: str) -> tuple[str, bool]:
        """A title is accepted only if it appears in the unit's own text."""

        title = (node.get("title") or "").strip()

        if title:
            squashed_title, _ = self._squash(title)
            squashed_head, _ = self._squash(text[:400])

            if squashed_title and squashed_title in squashed_head:
                return title, False

        first_line = text.strip().split("\n", 1)[0].strip()

        if len(first_line) <= 140:
            derived = first_line
        else:
            derived = re.split(r"(?<=[.;])\s", first_line, maxsplit=1)[0]

        reference = node.get("reference") or ""

        if reference:
            pattern = self._ref_regex(reference)
            found = pattern.match(derived) if pattern else None

            if found:
                derived = derived[found.end():]

        derived = self._strip_title_punct(derived)

        if len(derived) > 140:
            derived = derived[:137].rstrip() + "..."

        return derived, True

    # ------------------------------------------------------------------
    # STRUCTURE OUTPUTS + COVERAGE
    # ------------------------------------------------------------------

    def _build_structure_outputs(self, nodes, candidates) -> None:

        candidate_by_index = {
            meta["node_index"]: cid for cid, meta in self.last_meta.items()
        }

        flat = []

        for node in nodes:
            flat.append(
                {
                    "index": node["index"],
                    "role": node["role"],
                    "level": node["level"],
                    "reference": node.get("reference") or "",
                    "title": self._title_of(node),
                    "parent_index": node["parent_index"],
                    "page_start": node["page_start"],
                    "page_end": node["page_end"],
                    "text": (
                        node["text"]
                        if node["role"] in (ROLE_CHAPTER, ROLE_SUBCHAPTER)
                        else ""
                    ),
                    "candidate_id": candidate_by_index.get(node["index"]),
                    "recovered": node["recovered"],
                }
            )

        self.last_structure = flat

        by_index = {item["index"]: dict(item, children=[]) for item in flat}
        roots = []

        for item in by_index.values():
            parent = item["parent_index"]

            if parent is not None and parent in by_index:
                by_index[parent]["children"].append(item)
            else:
                roots.append(item)

        self.last_tree = roots

    def _finalize_coverage(
        self, records, nodes, candidates, recovered, gaps, discovery, total_pages
    ) -> None:

        requirement_nodes = [n for n in nodes if n["role"] == ROLE_REQUIREMENT]

        last_page = max(
            (n["page_end"] for n in requirement_nodes), default=0
        )

        self.last_coverage = {
            "pages": total_pages,
            "ai_nodes_returned": discovery["ai_nodes"],
            "nodes_resolved": len(nodes) - len(recovered),
            "nodes_rejected": len(discovery["rejected"]),
            "rejected_details": discovery["rejected"][:50],
            "nodes_recovered_locally": len(recovered),
            "unrecovered_gaps": gaps,
            "continuation_passes": discovery["continuations"],
            "chapters": sum(1 for n in nodes if n["role"] == ROLE_CHAPTER),
            "subchapters": sum(
                1 for n in nodes if n["role"] == ROLE_SUBCHAPTER
            ),
            "requirement_nodes": len(requirement_nodes),
            "requirements_emitted": len(candidates),
            "last_requirement_page": last_page,
        }

        if discovery["rejected"]:
            self.last_warnings.append(
                f"{len(discovery['rejected'])} AI node(s) were rejected "
                f"(see last_coverage['rejected_details'])."
            )

        if total_pages and last_page and last_page < total_pages * 0.6:
            self.last_warnings.append(
                f"Last requirement is on page {last_page} of "
                f"{total_pages}: the document may be only partly covered."
            )

        if not candidates:
            self.last_warnings.append(
                "No requirements could be extracted from this document."
            )

    def _print_summary(self) -> None:

        coverage = self.last_coverage

        print(
            "Structure: "
            f"{coverage.get('chapters', 0)} chapters, "
            f"{coverage.get('subchapters', 0)} subchapters, "
            f"{coverage.get('requirement_nodes', 0)} requirement nodes "
            f"({coverage.get('nodes_recovered_locally', 0)} recovered "
            f"locally, {coverage.get('nodes_rejected', 0)} rejected)"
        )
        print(
            f"Verified source requirements: "
            f"{coverage.get('requirements_emitted', 0)}"
        )

        for warning in self.last_warnings[:15]:
            print(f"   warning: {warning}")
