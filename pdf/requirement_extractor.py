import re

from backend.models.document import (
    CleanedDocument,
    RequirementCandidate,
)


class RequirementExtractor:
    def __init__(self):
        self.id_pattern = re.compile(
            r"(?<!\d)(\d+(?:-\d+){1,8})(?!\d)"
        )

        self.requirement_markers = (
            "shall",
            "must",
            "should",
            "required",
            "requires",
            "need to",
            "is required",
            "are required",
            "organization must",
            "organization shall",
            "requirements",
            "implement",
            "establish",
            "maintain",
            "ensure",
            "protect",
            "review",
            "monitor",
            "document",
            "assess",
            "verify",
            "define",
            "manage",
            "identify",
            "prohibit",
            "restrict",
            "notify",
            "agreement",
            "signed",
            "approval",
            "record",
            "conduct",
            "perform",
        )

        self.reference_markers = (
            "ecc control",
            "ecc subcontrol",
            "ecc subdomain",
            "figure",
            "table",
            "appendix",
            "annex",
        )

        self.noise_phrases = (
            "document classification",
            "sharing indicator",
            "white : sharing",
            "green–sharing",
            "amber -restricted",
            "disclaimer:",
            "terminologydefinition",
            "data lifecycle",
            "control clauses table",
        )

    def extract(
        self,
        document: CleanedDocument,
    ):
        candidates = []

        all_blocks = []

        for page in document.pages:
            for block in page.blocks:
                all_blocks.append(block)

        for block_index, block in enumerate(all_blocks):
            text = self._normalize(block.text)

            if not text:
                continue

            if self._is_noise(text):
                continue

            matches = list(
                self.id_pattern.finditer(text)
            )

            if not matches:
                continue

            valid_matches = []

            for match in matches:
                if self._is_reference_id(
                    text,
                    match.start(),
                ):
                    continue

                if self._looks_like_table_or_appendix(
                    text
                ):
                    continue

                valid_matches.append(match)

            if not valid_matches:
                continue

            for match_index, match in enumerate(
                valid_matches
            ):
                reference = match.group(1)

                start = match.end()

                if (
                    match_index
                    < len(valid_matches) - 1
                ):
                    end = valid_matches[
                        match_index + 1
                    ].start()
                else:
                    end = len(text)

                first_part = text[
                    start:end
                ].strip()

                source_parts = []

                if first_part:
                    source_parts.append(
                        first_part
                    )

                source_parts = (
                    self._collect_continuation(
                        all_blocks=all_blocks,
                        current_block_index=block_index,
                        current_match_index=match_index,
                        valid_matches=valid_matches,
                        initial_text=source_parts,
                    )
                )

                content = self._clean_content(
                    " ".join(source_parts)
                )

                if not self._is_requirement(
                    reference,
                    content,
                ):
                    continue

                source_block_ids = (
                    self._get_source_block_ids(
                        all_blocks=all_blocks,
                        current_block_index=block_index,
                        current_match_index=match_index,
                        valid_matches=valid_matches,
                    )
                )

                end_page = (
                    self._get_requirement_end_page(
                        all_blocks=all_blocks,
                        source_block_ids=source_block_ids,
                    )
                )

                candidates.append(
                    RequirementCandidate(
                        candidate_id=(
                            f"req_p{block.page_number}_"
                            f"{block.block_id}_"
                            f"{match_index}"
                        ),
                        node_id=None,
                        source_title=self._make_title(
                            content
                        ),
                        source_text=content,
                        page_start=block.page_number,
                        page_end=end_page,
                        source_block_ids=source_block_ids,
                        source_reference=reference,
                        confidence=self._confidence(
                            reference,
                            content,
                        ),
                    )
                )

        return self._deduplicate(
            candidates
        )

    def _collect_continuation(
        self,
        all_blocks,
        current_block_index,
        current_match_index,
        valid_matches,
        initial_text,
    ):
        parts = list(initial_text)

        if (
            current_match_index
            < len(valid_matches) - 1
        ):
            return parts

        max_following_blocks = 5

        for offset in range(
            1,
            max_following_blocks + 1,
        ):
            next_index = (
                current_block_index
                + offset
            )

            if next_index >= len(all_blocks):
                break

            next_block = all_blocks[
                next_index
            ]

            next_text = self._normalize(
                next_block.text
            )

            if not next_text:
                continue

            if self._is_noise(next_text):
                continue

            next_matches = list(
                self.id_pattern.finditer(
                    next_text
                )
            )

            valid_next_matches = []

            for next_match in next_matches:
                if self._is_reference_id(
                    next_text,
                    next_match.start(),
                ):
                    continue

                if self._looks_like_table_or_appendix(
                    next_text
                ):
                    continue

                valid_next_matches.append(
                    next_match
                )

            if valid_next_matches:
                first_match = (
                    valid_next_matches[0]
                )

                continuation_text = (
                    next_text[
                        :first_match.start()
                    ].strip()
                )

                if continuation_text:
                    parts.append(
                        continuation_text
                    )

                break

            if self._looks_like_new_section(
                next_text
            ):
                break

            if self._looks_like_metadata_or_layout(
                next_text
            ):
                continue

            parts.append(next_text)

        return parts

    def _get_source_block_ids(
        self,
        all_blocks,
        current_block_index,
        current_match_index,
        valid_matches,
    ):
        block_ids = [
            all_blocks[
                current_block_index
            ].block_id
        ]

        if (
            current_match_index
            < len(valid_matches) - 1
        ):
            return block_ids

        max_following_blocks = 5

        for offset in range(
            1,
            max_following_blocks + 1,
        ):
            next_index = (
                current_block_index
                + offset
            )

            if next_index >= len(all_blocks):
                break

            next_block = all_blocks[
                next_index
            ]

            next_text = self._normalize(
                next_block.text
            )

            if not next_text:
                continue

            next_matches = list(
                self.id_pattern.finditer(
                    next_text
                )
            )

            valid_next_matches = []

            for next_match in next_matches:
                if self._is_reference_id(
                    next_text,
                    next_match.start(),
                ):
                    continue

                if self._looks_like_table_or_appendix(
                    next_text
                ):
                    continue

                valid_next_matches.append(
                    next_match
                )

            if valid_next_matches:
                break

            if self._looks_like_new_section(
                next_text
            ):
                break

            if self._looks_like_metadata_or_layout(
                next_text
            ):
                continue

            block_ids.append(
                next_block.block_id
            )

        return block_ids

    def _get_requirement_end_page(
        self,
        all_blocks,
        source_block_ids,
    ):
        pages = []

        source_block_ids = set(
            source_block_ids
        )

        for block in all_blocks:
            if block.block_id in source_block_ids:
                pages.append(
                    block.page_number
                )

        if not pages:
            return 0

        return max(pages)

    def _is_reference_id(
        self,
        text,
        position,
    ):
        before = text[
            max(0, position - 80):position
        ].lower()

        for marker in self.reference_markers:
            if marker in before:
                return True

        return False

    def _is_requirement(
        self,
        reference,
        content,
    ):
        if not content:
            return False

        if len(content) < 15:
            return False

        value = content.strip()
        lowered = value.lower()

        if self._looks_like_heading(
            value
        ):
            return False

        if self._looks_like_objective_or_control_header(
            lowered
        ):
            return False

        if self._looks_like_classification_table(
            value
        ):
            return False

        if self._is_parent_control(
            reference,
            value,
        ):
            return False

        if any(
            marker in lowered
            for marker in self.requirement_markers
        ):
            return True

        if len(value.split()) >= 20:
            return True

        return False

    def _looks_like_objective_or_control_header(
        self,
        text,
    ):
        value = text.lower().strip()

        if value.startswith("objective"):
            return True

        if value.startswith("controls"):
            return True

        if (
            "objective" in value
            and "controls" in value
        ):
            return True

        return False

    def _looks_like_classification_table(
        self,
        text,
    ):
        value = text.lower().strip()

        classification_terms = (
            "public",
            "confidential",
            "secret",
            "top secret",
            "data classification level",
        )

        matches = sum(
            1
            for term in classification_terms
            if term in value
        )

        return matches >= 2

    def _is_parent_control(
        self,
        reference,
        content,
    ):
        parts = reference.split("-")

        if len(parts) < 2:
            return False

        lowered = content.lower()

        if (
            "objective" in lowered
            or "controls" in lowered
            or "data classification" in lowered
        ):
            return True

        if len(parts) == 2:
            requirement_markers = (
                "shall",
                "must",
                "required",
                "requires",
                "organization",
                "implement",
                "establish",
                "maintain",
                "ensure",
                "protect",
                "review",
                "monitor",
                "assess",
                "verify",
            )

            if not any(
                marker in lowered
                for marker in requirement_markers
            ):
                return True

        return False

    def _looks_like_heading(
        self,
        text,
    ):
        value = text.strip()

        if not value:
            return True

        if len(value) < 5:
            return True

        if (
            len(value.split()) <= 8
            and not re.search(
                r"[.;:!?]",
                value,
            )
        ):
            return True

        return False

    def _looks_like_new_section(
        self,
        text,
    ):
        value = text.strip()

        if not value:
            return False

        if re.match(
            r"^(objective|controls|appendix|annex|table|figure)\b",
            value,
            re.IGNORECASE,
        ):
            return True

        if re.match(
            r"^\d+(?:\.\d+){0,5}\s+\S+",
            value,
        ):
            return True

        return False

    def _looks_like_metadata_or_layout(
        self,
        text,
    ):
        value = text.lower().strip()

        metadata_markers = (
            "document classification",
            "sharing indicator",
            "tlp:",
            "disclaimer:",
            "white : sharing",
            "green : sharing",
            "amber",
            "red",
        )

        return any(
            marker in value
            for marker in metadata_markers
        )

    def _clean_content(
        self,
        text,
    ):
        value = self._normalize(text)

        value = re.sub(
            r"^(public|confidential|secret|top secret)+",
            "",
            value,
            flags=re.IGNORECASE,
        )

        value = re.sub(
            r"(public|confidential|secret|top secret)+$",
            "",
            value,
            flags=re.IGNORECASE,
        )

        value = re.sub(
            r"\b(public|confidential|secret|top secret){2,}\b",
            " ",
            value,
            flags=re.IGNORECASE,
        )

        return re.sub(
            r"\s+",
            " ",
            value,
        ).strip()

    def _is_noise(
        self,
        text,
    ):
        lowered = text.lower()

        if any(
            phrase in lowered
            for phrase in self.noise_phrases
        ):
            return True

        if re.fullmatch(
            r"\d+\s+document classification:.*",
            text,
            re.IGNORECASE,
        ):
            return True

        return False

    def _looks_like_table_or_appendix(
        self,
        text,
    ):
        lowered = text.lower()

        if "data lifecycle" in lowered:
            return True

        if (
            "control reference number control clauses"
            in lowered
        ):
            return True

        if (
            "table 4" in lowered
            and "terminology" in lowered
        ):
            return True

        return False

    def _confidence(
        self,
        reference,
        content,
    ):
        score = 0.60

        lowered = content.lower()

        if any(
            marker in lowered
            for marker in (
                "shall",
                "must",
                "required",
                "requires",
            )
        ):
            score += 0.25

        if len(content.split()) >= 25:
            score += 0.10

        if len(reference.split("-")) >= 3:
            score += 0.05

        return min(
            score,
            1.0,
        )

    def _make_title(
        self,
        text,
    ):
        value = self._normalize(text)

        if not value:
            return ""

        sentence = re.split(
            r"(?<=[.!?])\s+",
            value,
            maxsplit=1,
        )[0]

        words = sentence.split()

        if len(words) > 18:
            sentence = (
                " ".join(words[:18])
                + "..."
            )

        if len(sentence) > 140:
            sentence = (
                sentence[:140].rstrip()
                + "..."
            )

        return sentence

    def _normalize(
        self,
        text,
    ):
        text = text.replace(
            "\u00ad",
            "",
        )

        text = text.replace(
            "\xa0",
            " ",
        )

        text = re.sub(
            r"\s+",
            " ",
            text,
        )

        return text.strip()

    def _deduplicate(
        self,
        candidates,
    ):
        seen = set()
        result = []

        for candidate in candidates:
            key = (
                candidate.source_reference,
                candidate.source_text,
                candidate.page_start,
            )

            if key in seen:
                continue

            seen.add(key)
            result.append(candidate)

        return result