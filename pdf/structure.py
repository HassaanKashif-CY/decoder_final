import re
from collections import Counter
from dataclasses import dataclass

from backend.models.document import (
    CleanedDocument,
    DocumentStructure,
    StructureNode,
    TextBlock,
)


@dataclass
class HeadingCandidate:
    block: TextBlock
    title: str
    level: int
    node_type: str
    numbering: str | None
    score: float


@dataclass
class ControlMatch:
    reference: str
    start: int
    end: int


class StructureDetector:
    def detect(self, document: CleanedDocument) -> DocumentStructure:
        excluded_blocks = []
        warnings = []

        all_blocks = [
            block
            for page in document.pages
            for block in page.blocks
        ]

        body_font_size = self._estimate_body_font_size(all_blocks)

        document_section_candidates = []
        domain_candidates = []
        subdomain_candidates = []

        for block in all_blocks:
            if self._is_document_artifact(block, document):
                excluded_blocks.append(block.block_id)
                continue

            if self._is_figure_or_reference_page(block, document):
                excluded_blocks.append(block.block_id)
                continue

            candidate = self._classify_heading(
                block=block,
                body_font_size=body_font_size,
                document=document,
            )

            if not candidate:
                continue

            if candidate.node_type == "section":
                document_section_candidates.append(candidate)
            elif candidate.node_type == "domain":
                domain_candidates.append(candidate)
            elif candidate.node_type == "subdomain":
                subdomain_candidates.append(candidate)

        document_section_candidates = self._deduplicate_candidates(
            document_section_candidates
        )
        domain_candidates = self._deduplicate_candidates(domain_candidates)
        subdomain_candidates = self._deduplicate_candidates(
            subdomain_candidates
        )

        all_candidates = (
            document_section_candidates
            + domain_candidates
            + subdomain_candidates
        )

        all_candidates.sort(
            key=lambda candidate: (
                candidate.block.page_number,
                candidate.block.y0,
                candidate.block.x0,
                candidate.block.block_number,
            )
        )

        nodes = self._build_tree(
            candidates=all_candidates,
            document=document,
        )

        if not nodes:
            warnings.append(
                "No reliable document hierarchy was detected."
            )

        return DocumentStructure(
            metadata=document.metadata,
            nodes=nodes,
            excluded_blocks=excluded_blocks,
            warnings=warnings,
        )

    def _estimate_body_font_size(self, blocks):
        sizes = []

        for block in blocks:
            text = block.text.strip()

            if not text:
                continue

            if block.font_size <= 0:
                continue

            if len(text.split()) < 8:
                continue

            if self._looks_like_control_content(text):
                continue

            sizes.append(round(block.font_size, 1))

        if not sizes:
            return 10.0

        counts = Counter(sizes)

        return float(
            counts.most_common(1)[0][0]
        )

    def _classify_heading(
        self,
        block,
        body_font_size,
        document,
    ):
        text = block.text.strip()

        if not text:
            return None

        if len(text) > 180:
            return None

        if self._looks_like_table_row(text):
            return None

        if self._looks_like_control_content(text):
            return None

        if self._looks_like_figure_caption(text):
            return None

        numbering = self._extract_numbering(text)

        if self._is_subcontrol_reference(numbering):
            return None

        if self._is_main_control_reference(numbering):
            return None

        if self._is_subdomain_reference(numbering):
            title = self._clean_heading_title(text)

            if not title:
                return None

            return HeadingCandidate(
                block=block,
                title=title,
                level=3,
                node_type="subdomain",
                numbering=numbering,
                score=10.0,
            )

        if self._is_domain_reference(numbering):
            title = self._clean_heading_title(text)

            if not title:
                return None

            return HeadingCandidate(
                block=block,
                title=title,
                level=2,
                node_type="domain",
                numbering=numbering,
                score=10.0,
            )

        if self._looks_like_document_section(
            block,
            body_font_size,
            document,
        ):
            return HeadingCandidate(
                block=block,
                title=text,
                level=1,
                node_type="section",
                numbering=None,
                score=self._section_score(
                    block,
                    body_font_size,
                ),
            )

        return None

    def _looks_like_document_section(
        self,
        block,
        body_font_size,
        document,
    ):
        text = block.text.strip()

        if len(text.split()) > 12:
            return False

        if self._looks_like_sentence(text):
            return False

        if self._is_metadata_line(text):
            return False

        if self._looks_like_figure_caption(text):
            return False

        if block.font_size >= body_font_size * 1.45:
            return True

        if block.font_size >= body_font_size * 1.25 and block.is_bold:
            return True

        if block.is_bold and len(text.split()) <= 8:
            return True

        return False

    def _section_score(
        self,
        block,
        body_font_size,
    ):
        score = 3.0

        if block.is_bold:
            score += 2.0

        if block.font_size >= body_font_size * 1.25:
            score += 2.0

        if block.font_size >= body_font_size * 1.45:
            score += 2.0

        return score

    def _extract_numbering(self, text):
        value = text.strip()

        patterns = [
            r"^(\d+(?:\.\d+)*)\s+",
            r"^(\d+(?:-\d+){1,8})\s*[-–—]?\s*",
            r"^([A-Z](?:\.\d+)*)\s+",
            r"^([A-Z](?:-\d+){1,8})\s*[-–—]?\s*",
            r"^([IVXLC]+)\s+",
        ]

        for pattern in patterns:
            match = re.match(
                pattern,
                value,
                re.IGNORECASE,
            )

            if match:
                return match.group(1)

        return None

    def _is_domain_reference(self, numbering):
        if not numbering:
            return False

        return bool(
            re.fullmatch(
                r"\d+",
                numbering,
            )
        )

    def _is_subdomain_reference(self, numbering):
        if not numbering:
            return False

        return bool(
            re.fullmatch(
                r"\d+-\d+",
                numbering,
            )
        )

    def _is_main_control_reference(self, numbering):
        if not numbering:
            return False

        return bool(
            re.fullmatch(
                r"\d+-\d+-[A-Z]-\d+",
                numbering,
                re.IGNORECASE,
            )
        )

    def _is_subcontrol_reference(self, numbering):
        if not numbering:
            return False

        return bool(
            re.fullmatch(
                r"\d+-\d+-[A-Z]-\d+(?:-\d+)+",
                numbering,
                re.IGNORECASE,
            )
        )

    def _clean_heading_title(self, text):
        value = text.strip()

        value = re.sub(
            r"^\d+(?:-\d+)*\s*[-–—]?\s*",
            "",
            value,
        )

        value = re.sub(
            r"^\d+(?:\.\d+)*\s+",
            "",
            value,
        )

        value = re.sub(
            r"\s+",
            " ",
            value,
        )

        return value.strip()

    def _looks_like_control_content(self, text):
        value = text.strip()

        if self._contains_control_reference(value):
            return True

        markers = [
            "objective ",
            " controls ",
            "the csp shall",
            "the cst shall",
            "shall also",
            "should include",
            "must ",
            "required ",
        ]

        lowered = f" {value.lower()} "

        return any(
            marker in lowered
            for marker in markers
        )

    def _contains_control_reference(self, text):
        pattern = (
            r"\b\d+-\d+-[A-Z]-\d+"
            r"(?:-\d+)*\b"
        )

        return bool(
            re.search(
                pattern,
                text,
                re.IGNORECASE,
            )
        )

    def _looks_like_table_row(self, text):
        if text.count("|") >= 2:
            return True

        if text.count("\t") >= 2:
            return True

        lowered = text.lower()

        markers = [
            "level 4",
            "level 3",
            "level 2",
            "level 1",
            "subdomains and",
            "reference number",
            "name of subdomain",
            "control clauses",
        ]

        matches = sum(
            marker in lowered
            for marker in markers
        )

        return matches >= 2

    def _looks_like_figure_caption(self, text):
        normalized = re.sub(
            r"\s+",
            " ",
            text.lower(),
        ).strip()

        patterns = [
            r"^figure\s+\d+",
            r"^figure\s+\([a-z0-9]+\)",
            r"^table\s+\d+",
            r"^table\s+\([a-z0-9]+\)",
            r"^f\s+i\s+g\s+u\s+r\s+e",
        ]

        return any(
            re.match(pattern, normalized)
            for pattern in patterns
        )

    def _is_figure_or_reference_page(
        self,
        block,
        document,
    ):
        page = next(
            (
                page
                for page in document.pages
                if page.page_number == block.page_number
            ),
            None,
        )

        if not page:
            return False

        page_text = page.text.lower()

        figure_markers = [
            "figure 2",
            "figure 3",
            "figure 4",
            "controls unique identifier structure",
            "ccc main domains and subdomains",
            "ccc identification notation",
            "ccc structure",
        ]

        marker_count = sum(
            marker in page_text
            for marker in figure_markers
        )

        if marker_count >= 1:
            return True

        return False

    def _looks_like_sentence(self, text):
        value = text.strip()

        if value.endswith(
            (
                ".",
                "?",
                "!",
                ";",
                ":",
            )
        ):
            return True

        words = value.split()

        if len(words) <= 4:
            return False

        markers = {
            "shall",
            "must",
            "should",
            "may",
            "requires",
            "require",
            "required",
            "includes",
            "include",
            "provides",
            "provide",
            "applies",
            "apply",
            "ensures",
            "ensure",
            "organization",
            "organizations",
            "system",
            "systems",
            "controls",
        }

        matches = sum(
            word.lower().strip(
                ",;:()"
            ) in markers
            for word in words
        )

        return matches >= 1 and len(words) >= 7

    def _is_metadata_line(self, text):
        lowered = text.lower()

        phrases = [
            "document classification",
            "classification:",
            "tlp:",
            "tlp :",
            "copyright",
            "all rights reserved",
            "version:",
            "date of issue:",
            "effective date:",
            "disclaimer:",
        ]

        return any(
            phrase in lowered
            for phrase in phrases
        )

    def _is_document_artifact(
        self,
        block,
        document,
    ):
        text = block.text.strip()

        if not text:
            return True

        if block.block_type in {
            "page_number",
            "header",
            "footer",
        }:
            return True

        if self._is_metadata_line(text):
            return True

        if text in {
            "مقيد - محدود",
            "مقيد-محدود",
        }:
            return True

        page = next(
            (
                page
                for page in document.pages
                if page.page_number == block.page_number
            ),
            None,
        )

        if page:
            if page.height > 0:
                if block.y0 <= page.height * 0.08:
                    if not self._looks_like_numbered_structure(text):
                        return True

                if block.y1 >= page.height * 0.92:
                    return True

        return False

    def _looks_like_numbered_structure(self, text):
        numbering = self._extract_numbering(text)

        if not numbering:
            return False

        return (
            self._is_domain_reference(numbering)
            or self._is_subdomain_reference(numbering)
            or self._is_main_control_reference(numbering)
            or self._is_subcontrol_reference(numbering)
        )

    def _deduplicate_candidates(self, candidates):
        result = []
        seen = set()

        for candidate in candidates:
            key = (
                candidate.block.page_number,
                candidate.node_type,
                candidate.numbering,
                self._normalize(candidate.title),
            )

            if key in seen:
                continue

            seen.add(key)
            result.append(candidate)

        return result

    def _build_tree(
        self,
        candidates,
        document,
    ):
        ordered = sorted(
            candidates,
            key=lambda candidate: (
                candidate.block.page_number,
                candidate.block.y0,
                candidate.block.x0,
                candidate.block.block_number,
            ),
        )

        nodes = []
        stack = []

        for index, candidate in enumerate(
            ordered,
            start=1,
        ):
            node = StructureNode(
                node_id=f"node_{index}",
                parent_id=None,
                title=candidate.title,
                level=candidate.level,
                node_type=candidate.node_type,
                numbering=candidate.numbering,
                page_start=candidate.block.page_number,
                page_end=candidate.block.page_number,
                block_start=candidate.block.block_number,
                block_end=candidate.block.block_number,
                source_text=candidate.block.text,
                source_block_ids=[
                    candidate.block.block_id
                ],
                children=[],
            )

            while stack and stack[-1].level >= node.level:
                stack.pop()

            if stack:
                node.parent_id = stack[-1].node_id
                stack[-1].children.append(node)
            else:
                nodes.append(node)

            stack.append(node)

        self._assign_ranges(
            nodes,
            document,
        )

        return nodes

    def _assign_ranges(
        self,
        nodes,
        document,
    ):
        all_blocks = [
            block
            for page in document.pages
            for block in page.blocks
        ]

        positions = {
            block.block_id: index
            for index, block in enumerate(all_blocks)
        }

        flat_nodes = self._flatten(nodes)

        for index, node in enumerate(flat_nodes):
            start_position = self._node_position(
                node,
                positions,
                all_blocks,
            )

            if start_position is None:
                continue

            end_position = len(all_blocks)

            for next_node in flat_nodes[index + 1:]:
                next_position = self._node_position(
                    next_node,
                    positions,
                    all_blocks,
                )

                if (
                    next_position is not None
                    and next_position > start_position
                ):
                    end_position = next_position
                    break

            relevant_blocks = all_blocks[
                start_position:end_position
            ]

            if not relevant_blocks:
                continue

            node.block_start = (
                relevant_blocks[0].block_number
            )

            node.block_end = (
                relevant_blocks[-1].block_number
            )

            node.page_start = (
                relevant_blocks[0].page_number
            )

            node.page_end = (
                relevant_blocks[-1].page_number
            )

            node.source_block_ids = [
                block.block_id
                for block in relevant_blocks
            ]

    def _flatten(self, nodes):
        result = []

        for node in nodes:
            result.append(node)

            if node.children:
                result.extend(
                    self._flatten(node.children)
                )

        return result

    def _node_position(
        self,
        node,
        positions,
        all_blocks,
    ):
        for block_id in node.source_block_ids:
            if block_id in positions:
                return positions[block_id]

        for block in all_blocks:
            if (
                block.page_number == node.page_start
                and block.block_number == node.block_start
            ):
                return positions.get(
                    block.block_id
                )

        return None

    def _normalize(self, text):
        value = text.lower().strip()
        value = re.sub(
            r"\s+",
            " ",
            value,
        )
        value = re.sub(
            r"[|•·]+",
            " ",
            value,
        )

        return value.strip()