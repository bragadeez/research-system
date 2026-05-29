from enum import Enum
from typing import List

from pydantic import (
    BaseModel,
    ConfigDict,
    field_validator,
    model_validator,
)


class ResearchIntent(str, Enum):
    impact_analysis = "impact_analysis"
    technical_research = "technical_research"
    market_analysis = "market_analysis"
    comparison = "comparison"
    trend_analysis = "trend_analysis"


class Depth(str, Enum):
    quick = "quick"
    standard = "standard"
    deep = "deep"


class SourceType(str, Enum):
    academic = "academic"
    government = "government"
    industry_report = "industry_report"
    news = "news"
    documentation = "documentation"
    dataset = "dataset"
    blog = "blog"


class TaskType(str, Enum):
    research = "research"
    synthesis = "synthesis"
    analysis = "analysis"


class Priority(str, Enum):
    critical = "critical"
    high = "high"
    medium = "medium"
    low = "low"


SOURCE_ALIASES = {
    "paper": "academic",
    "research": "academic",
    "gov": "government",
    "media": "news",
    "report": "industry_report",
}


class ExecutionHints(BaseModel):
    max_parallel_tasks: int
    estimated_total_sources: int
    estimated_total_tokens: int
    execution_strategy: str


class SubTopicPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    title: str
    task_type: TaskType
    objective: str
    search_queries: List[str]
    source_types: List[SourceType]
    expected_evidence: List[str]
    priority: Priority
    execution_priority: int
    depth: Depth
    difficulty: str
    estimated_sources: int
    estimated_tokens: int
    parallel_group: int
    blocking: bool
    max_sources: int
    requires_statistics: bool
    requires_comparison: bool
    requires_extraction: bool
    section_title: str
    depends_on: List[str] = []

    @field_validator("source_types", mode="before")
    @classmethod
    def normalize_sources(cls, v):
        normalized = []
        for item in v:
            if isinstance(item, SourceType):
                normalized.append(item)
            else:
                value = item.lower().strip()
                value = SOURCE_ALIASES.get(value, value)
                try:
                    normalized.append(SourceType(value))
                except ValueError:
                    normalized.append(SourceType.blog)  # safe fallback
        return normalized


class SectionPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    purpose: str
    priority: Priority
    linked_subtopics: List[str]
    required_evidence: List[str]


class ResearchPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    topic: str
    research_intent: ResearchIntent
    depth: Depth
    thesis: str
    audience: str
    complexity: str
    estimated_runtime_minutes: int
    execution: ExecutionHints
    core_tasks: List[str]
    optional_tasks: List[str]
    execution_order: List[str]
    sections: List[SectionPlan]
    subtopics: List[SubTopicPlan]
    contradictions_to_watch: List[str]
    source_strategy: List[SourceType]
    success_criteria: List[str]

    @field_validator("source_strategy", mode="before")
    @classmethod
    def normalize_strategy(cls, v):
        normalized = []
        for item in v:
            if isinstance(item, SourceType):
                normalized.append(item)
            else:
                value = item.lower().strip()
                value = SOURCE_ALIASES.get(value, value)
                try:
                    normalized.append(SourceType(value))
                except ValueError:
                    normalized.append(SourceType.blog)
        return normalized

    @model_validator(mode="after")
    def validate_links(self):
        subtopics = {s.title for s in self.subtopics}
        for section in self.sections:
            section.linked_subtopics = [
                link for link in section.linked_subtopics if link in subtopics
            ]
        return self
