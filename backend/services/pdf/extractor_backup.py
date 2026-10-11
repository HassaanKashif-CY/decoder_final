import re
from pathlib import Path

import fitz

from backend.core.config import get_settings
from backend.models.document import (
    DocumentMetadata,
    ExtractedDocument,
    PageContent,
    TextBlock,
)


class PDFExtractionError(Exception):
    pass


class PDFExtractor:
    def __init__(self):
        self.settings = get_settings()

    def extract(self, pdf_path: str | Path) -> ExtractedDocument:
        path = Path(pdf_path)

        if not path.exists():
            raise PDFExtractionError(
                f"PDF file not found: {path}"
            )

        if path.suffix.lower() != ".pdf":
            raise PDFExtractionError(
                "Only PDF files are supported."
            )

        try:
            document = fitz.open(path)
        except Exception as exc:
            raise PDFExtractionError(
                f"Unable to open PDF: {exc}"
            ) from exc

        try:
            page_count = len(document)

            if page_count == 0:
                raise PDFExtractionError(
                    "The PDF contains no pages."
                )

            if page_count > self.settings.max_pdf_pages:
                raise PDFExtractionError(
                    f"PDF exceeds the maximum allowed page count "
                    f"of {self.settings.max_pdf_pages}."
                )

            metadata = document.metadata or {}

            document_metadata = DocumentMetadata(
                filename=path.name,
                page_count=page_count,
                title=self._clean_metadata(
                    metadata.get("title")
                ),
                author=self._clean_metadata(
                    metadata.get("author")
                ),
                subject=self._clean_metadata(
                    metadata.get("subject")
                ),
                creator=self._clean_metadata(
                    metadata.get("creator")
                ),
                producer=self._clean_metadata(
                    metadata.get("producer")
                ),
            )

            pages = []

            for page_index in range(page_count):
                page = document.load_page(page_index)

                page_number = page_index + 1

                blocks = self._extract_blocks(
                    page,
                    page_number
                )

                page_text = "\n".join(
                    block.text
                    for block in blocks
                    if block.text.strip()
                )

                has_images = bool(
                    page.get_images(full=True)
                )

                has_tables = self._detect_tables(page)

                pages.append(
                    PageContent(
                        page_number=page_number,
                        width=float(page.rect.width),
                        height=float(page.rect.height),
                        blocks=blocks,
                        text=page_text,
                        has_images=has_images,
                        has_tables=has_tables,
                    )
                )

            return ExtractedDocument(
                metadata=document_metadata,
                pages=pages,
            )

        finally:
            document.close()

    def _extract_blocks(
        self,
        page: fitz.Page,
        page_number: int,
    ) -> list[TextBlock]:
        raw_blocks = page.get_text(
            "dict",
            flags=fitz.TEXTFLAGS_TEXT
        ).get("blocks", [])

        extracted = []

        for block_number, raw_block in enumerate(
            raw_blocks
        ):
            if raw_block.get("type") != 0:
                continue

            lines = raw_block.get(
                "lines",
                []
            )

            spans = []

            for line in lines:
                for span in line.get(
                    "spans",
                    []
                ):
                    text = str(
                        span.get(
                            "text",
                            ""
                        )
                    )

                    if not text.strip():
                        continue

                    spans.append(span)

            if not spans:
                continue

            text_parts = []

            font_sizes = []

            bold = False
            italic = False

            for span in spans:
                value = span.get(
                    "text",
                    ""
                )

                text_parts.append(value)

                font_sizes.append(
                    float(
                        span.get(
                            "size",
                            0.0
                        )
                    )
                )

                flags = int(
                    span.get(
                        "flags",
                        0
                    )
                )

                if flags & 16:
                    bold = True

                if flags & 2:
                    italic = True

            text = " ".join(
                text_parts
            )

            text = self._normalize_text(
                text
            )

            if not text:
                continue

            bbox = raw_block.get(
                "bbox",
                [0, 0, 0, 0]
            )

            block_id = (
                f"page_{page_number}"
                f"_block_{block_number}"
            )

            extracted.append(
                TextBlock(
                    block_id=block_id,
                    page_number=page_number,
                    block_number=block_number,
                    text=text,
                    font_size=max(
                        font_sizes
                    ) if font_sizes else 0.0,
                    is_bold=bold,
                    is_italic=italic,
                    x0=float(bbox[0]),
                    y0=float(bbox[1]),
                    x1=float(bbox[2]),
                    y1=float(bbox[3]),
                    block_type=self._initial_block_type(
                        text
                    ),
                    confidence=1.0,
                )
            )

        extracted.sort(
            key=lambda block: (
                block.y0,
                block.x0,
                block.block_number,
            )
        )

        return extracted

    def _initial_block_type(
        self,
        text: str,
    ) -> str:
        value = text.strip()

        if not value:
            return "unknown"

        if self._is_page_number(
            value
        ):
            return "page_number"

        if self._looks_like_footnote(
            value
        ):
            return "footnote"

        return "text"

    def _detect_tables(
        self,
        page: fitz.Page,
    ) -> bool:
        try:
            result = page.find_tables()

            return bool(
                result.tables
            )

        except Exception:
            return False

    def _is_page_number(
        self,
        text: str,
    ) -> bool:
        value = text.strip()

        patterns = [
            r"\d+",
            r"page\s+\d+",
            r"\d+\s+of\s+\d+",
            r"\d+\s*/\s*\d+",
        ]

        return any(
            re.fullmatch(
                pattern,
                value,
                re.IGNORECASE
            )
            for pattern in patterns
        )

    def _looks_like_footnote(
        self,
        text: str,
    ) -> bool:
        value = text.strip()

        if re.match(
            r"^\d+\s+",
            value
        ):
            if len(value) > 40:
                return True

        if re.match(
            r"^\[\d+\]\s+",
            value
        ):
            return True

        if re.match(
            r"^\*\s+",
            value
        ):
            return True

        return False

    def _normalize_text(
        self,
        text: str,
    ) -> str:
        text = text.replace(
            "\u00ad",
            ""
        )

        text = text.replace(
            "\xa0",
            " "
        )

        text = re.sub(
            r"[ \t]+",
            " ",
            text
        )

        text = re.sub(
            r"\n{3,}",
            "\n\n",
            text
        )

        return text.strip()

    def _clean_metadata(
        self,
        value: str | None,
    ) -> str | None:
        if not value:
            return None

        value = re.sub(
            r"\s+",
            " ",
            str(value)
        ).strip()

        return value or None