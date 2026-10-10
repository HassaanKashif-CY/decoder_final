from typing import List, Optional, Literal

from pydantic import BaseModel, Field


BlockType = Literal[
    "text",
    "heading",
    "table",
    "table_row",
    "figure",
    "footer",
    "header",
    "page_number",
    "footnote",
    "unknown",
]


class TextBlock(BaseModel):
    block_id: str
    page_number: int
    block_number: int
    text: str

    font_size: float = 0.0
    is_bold: bool = False
    is_italic: bool = False

    x0: float = 0.0
    y0: float = 0.0
    x1: float = 0.0
    y1: float = 0.0

    block_type: BlockType = "text"
    confidence: float = 1.0


class TableCell(BaseModel):
    row_index: int
    column_index: int
    text: str = ""


class ExtractedTable(BaseModel):
    table_id: str
    page_number: int
    bbox: List[float] = Field(
        default_factory=list
    )
    rows: List[List[str]] = Field(
        default_factory=list
    )


class PageContent(BaseModel):
    page_number: int

    width: float = 0.0
    height: float = 0.0

    blocks: List[TextBlock] = Field(
        default_factory=list
    )

    tables: List[ExtractedTable] = Field(
        default_factory=list
    )

    text: str = ""

    has_images: bool = False
    has_tables: bool = False


class DocumentMetadata(BaseModel):
    filename: str
    page_count: int

    title: Optional[str] = None
    author: Optional[str] = None
    subject: Optional[str] = None
    creator: Optional[str] = None
    producer: Optional[str] = None


class ExtractedDocument(BaseModel):
    metadata: DocumentMetadata

    pages: List[PageContent] = Field(
        default_factory=list
    )


class CleanedPage(BaseModel):
    page_number: int

    width: float = 0.0
    height: float = 0.0

    blocks: List[TextBlock] = Field(
        default_factory=list
    )

    tables: List[ExtractedTable] = Field(
        default_factory=list
    )

    text: str = ""


class CleanedDocument(BaseModel):
    metadata: DocumentMetadata

    pages: List[CleanedPage] = Field(
        default_factory=list
    )


class StructureNode(BaseModel):
    node_id: str

    parent_id: Optional[str] = None

    title: str
    level: int
    node_type: str

    numbering: Optional[str] = None

    page_start: int
    page_end: int

    block_start: int
    block_end: int

    source_text: str = ""

    source_block_ids: List[str] = Field(
        default_factory=list
    )

    children: List["StructureNode"] = Field(
        default_factory=list
    )


class DocumentStructure(BaseModel):
    metadata: DocumentMetadata

    nodes: List[StructureNode] = Field(
        default_factory=list
    )

    excluded_blocks: List[str] = Field(
        default_factory=list
    )

    warnings: List[str] = Field(
        default_factory=list
    )


class SourceSegment(BaseModel):
    segment_id: str

    node_id: Optional[str] = None

    page_number: int

    block_start: int
    block_end: int

    title: Optional[str] = None

    text: str

    source_block_ids: List[str] = Field(
        default_factory=list
    )


class DocumentChunk(BaseModel):
    chunk_id: str

    node_id: Optional[str] = None
    title: Optional[str] = None

    page_start: int
    page_end: int

    source_segments: List[SourceSegment] = Field(
        default_factory=list
    )

    text: str

    character_count: int


class RequirementCandidate(BaseModel):
    candidate_id: str

    node_id: Optional[str] = None

    source_title: str

    source_text: str

    page_start: int
    page_end: int

    source_block_ids: List[str] = Field(
        default_factory=list
    )

    source_reference: str = ""

    confidence: float = 0.0


class DocumentRequirementSet(BaseModel):
    document_id: str

    requirements: List[
        RequirementCandidate
    ] = Field(default_factory=list)


TextBlock.model_rebuild()
TableCell.model_rebuild()
ExtractedTable.model_rebuild()
PageContent.model_rebuild()
CleanedPage.model_rebuild()
CleanedDocument.model_rebuild()
StructureNode.model_rebuild()
DocumentStructure.model_rebuild()
SourceSegment.model_rebuild()
DocumentChunk.model_rebuild()
RequirementCandidate.model_rebuild()
DocumentRequirementSet.model_rebuild()