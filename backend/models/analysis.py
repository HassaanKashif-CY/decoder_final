
from typing import List

from pydantic import BaseModel, Field


class RecommendationItem(BaseModel):
    name: str = ""
    description: str = ""


class TodoItem(BaseModel):
    name: str = ""
    description: str = ""


class RequirementAnalysis(BaseModel):
    source_reference: str
    source_title: str = ""
    source_text: str
    source_summary: str = ""
    page_start: int = 0
    page_end: int = 0

    source_block_ids: List[str] = Field(
        default_factory=list
    )

    hierarchy_path: List[str] = Field(
        default_factory=list
    )

    todo: TodoItem = Field(
        default_factory=TodoItem
    )

    policies: List[RecommendationItem] = Field(
        default_factory=list
    )

    documents: List[RecommendationItem] = Field(
        default_factory=list
    )

    evidence: List[RecommendationItem] = Field(
        default_factory=list
    )

    automation_tests: List[RecommendationItem] = Field(
        default_factory=list
    )

    ai_generated: bool = True
