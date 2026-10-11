import re
from collections import Counter

from backend.models.document import (
    CleanedDocument,
    CleanedPage,
    ExtractedDocument,
)


class PDFCleaner:
    def clean(
        self,
        document: ExtractedDocument,
    ) -> CleanedDocument:

        repeated_lines = (
            self._find_repeated_lines(
                document
            )
        )

        cleaned_pages = []

        for page in document.pages:

            page_blocks = []

            for block in page.blocks:

                text = self._clean_text(
                    block.text
                )

                if not text:
                    continue

                normalized = self._normalize(
                    text
                )

                if self._is_page_number(
                    text
                ):
                    block.block_type = (
                        "page_number"
                    )
                    continue

                if (
                    normalized
                    in repeated_lines
                ):
                    block.block_type = (
                        self._classify_repeated_block(
                            block,
                            page.height,
                        )
                    )
                    continue

                block.text = text

                page_blocks.append(
                    block
                )

            page_text = "\n".join(
                block.text
                for block in page_blocks
                if block.text.strip()
            )

            cleaned_pages.append(
                CleanedPage(
                    page_number=page.page_number,
                    width=page.width,
                    height=page.height,
                    blocks=page_blocks,
                    tables=page.tables,
                    text=page_text,
                )
            )

        return CleanedDocument(
            metadata=document.metadata,
            pages=cleaned_pages,
        )

    def _find_repeated_lines(
        self,
        document,
    ):

        page_count = len(
            document.pages
        )

        if page_count < 4:
            return set()

        occurrences = Counter()

        for page in document.pages:

            page_seen = set()

            for block in page.blocks:

                text = block.text.strip()

                if not text:
                    continue

                normalized = self._normalize(
                    text
                )

                if not normalized:
                    continue

                if len(normalized) > 180:
                    continue

                if self._looks_like_real_content(
                    text,
                    block,
                ):
                    continue

                page_seen.add(
                    normalized
                )

            for value in page_seen:
                occurrences[value] += 1

        threshold = max(
            3,
            int(page_count * 0.30),
        )

        return {
            value
            for value, count
            in occurrences.items()
            if count >= threshold
        }

    def _looks_like_real_content(
        self,
        text,
        block,
    ):

        value = text.strip()

        if self._looks_like_numbered_heading(
            value
        ):
            return True

        if self._looks_like_requirement(
            value
        ):
            return True

        if block.is_bold:
            return True

        if len(value.split()) <= 12:
            return True

        return False

    def _looks_like_numbered_heading(
        self,
        text,
    ):

        patterns = [
            r"^\d+(?:\.\d+){0,6}\s+\S+",
            r"^[A-Z](?:\.\d+){0,6}\s+\S+",
            r"^[IVXLC]+\s+\S+",
            r"^\([A-Za-z0-9]+\)\s+\S+",
            r"^[A-Za-z]\)\s+\S+",
        ]

        return any(
            re.match(
                pattern,
                text,
                re.IGNORECASE,
            )
            for pattern in patterns
        )

    def _looks_like_requirement(
        self,
        text,
    ):

        lowered = text.lower()

        markers = (
            "shall ",
            "must ",
            "should ",
            "required ",
            "requirement ",
            "the organization ",
            "the entity ",
            "the system ",
            "control objective",
            "control requirement",
        )

        return any(
            marker in lowered
            for marker in markers
        )

    def _is_page_number(
        self,
        text,
    ):

        value = text.strip()

        patterns = [
            r"\d+",
            r"page\s+\d+",
            r"page\s+\d+\s+of\s+\d+",
            r"\d+\s+of\s+\d+",
            r"\d+\s*/\s*\d+",
        ]

        return any(
            re.fullmatch(
                pattern,
                value,
                re.IGNORECASE,
            )
            for pattern in patterns
        )

    def _classify_repeated_block(
        self,
        block,
        page_height,
    ):

        if block.y0 <= 80:
            return "header"

        if block.y1 >= page_height - 80:
            return "footer"

        return "unknown"

    def _clean_text(
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
            r"[ \t]+",
            " ",
            text,
        )

        text = re.sub(
            r"\n{3,}",
            "\n\n",
            text,
        )

        return text.strip()

    def _normalize(
        self,
        text,
    ):

        text = text.lower().strip()

        text = re.sub(
            r"\s+",
            " ",
            text,
        )

        text = re.sub(
            r"[|•·]+",
            " ",
            text,
        )

        return text.strip()