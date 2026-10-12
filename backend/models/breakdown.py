from typing import List, Optional

from pydantic import BaseModel, Field

from backend.models.analysis import RequirementAnalysis
from backend.models.document import StructureNode


class DecoderMetadata(BaseModel):
    document_id: str
    filename: str
    page_count: int
    requirement_count: int
    document_title: str = ""
    document_type: str = ""
    framework_name: str = ""
    version: str = ""
    jurisdiction: str = ""
    requirement_unit_name: str = ""
    hierarchy_description: str = ""
    hierarchy_levels: List[str] = Field(
        default_factory=list
    )
    regulation_summary: str = ""
    applicability_conditions: str = ""
    applicable_industries: List[str] = Field(default_factory=list)
    generated_by: str = (
        "Sahl Compliance Decoder"
    )
    ai_model: Optional[str] = None


class ComplianceBreakdown(BaseModel):
    metadata: DecoderMetadata
    structure: List[StructureNode] = Field(
        default_factory=list
    )
    requirements: List[
        RequirementAnalysis
    ] = Field(
        default_factory=list
    )
    warnings: List[str] = Field(
        default_factory=list
    )
