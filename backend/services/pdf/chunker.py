from backend.models.document import CleanedDocument, DocumentChunk, DocumentStructure, StructureNode


class DocumentChunker:
    def __init__(self, max_characters: int = 14000, overlap_characters: int = 800):
        self.max_characters = max_characters
        self.overlap_characters = overlap_characters

    def create_chunks(
        self,
        document: CleanedDocument,
        structure: DocumentStructure,
    ) -> list[DocumentChunk]:
        if structure.nodes:
            leaf_nodes = self._get_leaf_nodes(structure.nodes)
            chunks = []

            for node in leaf_nodes:
                text = self._get_node_text(node, document)
                if not text.strip():
                    continue

                chunks.extend(
                    self._split_text(
                        text=text,
                        node=node,
                    )
                )

            if chunks:
                return chunks

        return self._fallback_chunks(document)

    def _get_leaf_nodes(self, nodes: list[StructureNode]) -> list[StructureNode]:
        result = []

        for node in nodes:
            if node.children:
                result.extend(self._get_leaf_nodes(node.children))
            else:
                result.append(node)

        return result

    def _get_node_text(
        self,
        node: StructureNode,
        document: CleanedDocument,
    ) -> str:
        page_map = {
            page.page_number: page.text
            for page in document.pages
        }

        parts = []

        for page_number in range(node.page_start, node.page_end + 1):
            text = page_map.get(page_number, "").strip()

            if text:
                parts.append(
                    f"[Page {page_number}]\n{text}"
                )

        return "\n\n".join(parts)

    def _split_text(
        self,
        text: str,
        node: StructureNode,
    ) -> list[DocumentChunk]:
        if len(text) <= self.max_characters:
            return [
                DocumentChunk(
                    chunk_id=f"{node.node_id}_chunk_1",
                    node_id=node.node_id,
                    title=node.title,
                    page_start=node.page_start,
                    page_end=node.page_end,
                    text=text,
                    character_count=len(text),
                )
            ]

        chunks = []
        start = 0
        counter = 1

        while start < len(text):
            end = min(
                start + self.max_characters,
                len(text),
            )

            if end < len(text):
                split_position = self._find_split_position(
                    text,
                    start,
                    end,
                )

                if split_position > start:
                    end = split_position

            chunk_text = text[start:end].strip()

            if chunk_text:
                page_start, page_end = self._detect_page_range(
                    chunk_text,
                    node.page_start,
                    node.page_end,
                )

                chunks.append(
                    DocumentChunk(
                        chunk_id=f"{node.node_id}_chunk_{counter}",
                        node_id=node.node_id,
                        title=node.title,
                        page_start=page_start,
                        page_end=page_end,
                        text=chunk_text,
                        character_count=len(chunk_text),
                    )
                )

                counter += 1

            if end >= len(text):
                break

            start = max(
                end - self.overlap_characters,
                start + 1,
            )

        return chunks

    def _find_split_position(
        self,
        text: str,
        start: int,
        end: int,
    ) -> int:
        search_start = max(
            start,
            end - 3000,
        )

        candidates = [
            text.rfind("\n\n", search_start, end),
            text.rfind("\n", search_start, end),
            text.rfind(". ", search_start, end),
            text.rfind("; ", search_start, end),
        ]

        valid = [
            position
            for position in candidates
            if position > start
        ]

        if not valid:
            return end

        return max(valid)

    def _detect_page_range(
        self,
        text: str,
        default_start: int,
        default_end: int,
    ) -> tuple[int, int]:
        pages = []

        for line in text.splitlines():
            line = line.strip()

            if line.startswith("[Page ") and line.endswith("]"):
                try:
                    page_number = int(
                        line[6:-1]
                    )
                    pages.append(page_number)
                except ValueError:
                    continue

        if not pages:
            return default_start, default_end

        return min(pages), max(pages)

    def _fallback_chunks(
        self,
        document: CleanedDocument,
    ) -> list[DocumentChunk]:
        chunks = []
        current_text = []
        current_pages = []
        counter = 1

        for page in document.pages:
            if not page.text.strip():
                continue

            page_text = (
                f"[Page {page.page_number}]\n"
                f"{page.text}"
            )

            proposed = "\n\n".join(
                current_text + [page_text]
            )

            if (
                current_text
                and len(proposed) > self.max_characters
            ):
                text = "\n\n".join(current_text)

                chunks.append(
                    DocumentChunk(
                        chunk_id=f"fallback_chunk_{counter}",
                        node_id=None,
                        title=None,
                        page_start=min(current_pages),
                        page_end=max(current_pages),
                        text=text,
                        character_count=len(text),
                    )
                )

                counter += 1
                current_text = [page_text]
                current_pages = [page.page_number]
            else:
                current_text.append(page_text)
                current_pages.append(page.page_number)

        if current_text:
            text = "\n\n".join(current_text)

            chunks.append(
                DocumentChunk(
                    chunk_id=f"fallback_chunk_{counter}",
                    node_id=None,
                    title=None,
                    page_start=min(current_pages),
                    page_end=max(current_pages),
                    text=text,
                    character_count=len(text),
                )
            )

        return chunks