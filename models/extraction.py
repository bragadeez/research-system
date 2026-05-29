from __future__ import annotations

from enum import Enum
from typing import List

from pydantic import BaseModel, ConfigDict, Field, field_validator


class EvidenceCategory(str, Enum):
    definition = "definition"
    method = "method"
    algorithm = "algorithm"
    result = "result"
    metric = "metric"
    dataset = "dataset"
    limitation = "limitation"
    comparison = "comparison"
    trend = "trend"
    conclusion = "conclusion"
    context = "context"
    unknown = "unknown"


class ExtractedEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    evidence_id: str = ""
    topic: str
    subtopic: str = ""
    source_url: str
    source_title: str = ""
    domain: str = ""
    source_kind: str = "unknown"

    category: EvidenceCategory = EvidenceCategory.unknown
    claim: str
    evidence_text: str

    confidence: float = 0.0
    source_score: float = 0.0

    sentence_index: int = 0
    paragraph_index: int = 0

    support_count: int = 1
    supporting_sources: List[str] = Field(default_factory=list)
    keywords: List[str] = Field(default_factory=list)

    @field_validator("confidence", "source_score")
    @classmethod
    def clamp_score(cls, v):
        try:
            v = float(v)
        except Exception:
            v = 0.0
        return max(0.0, min(1.0, v))

    @field_validator("support_count")
    @classmethod
    def clamp_support_count(cls, v):
        try:
            v = int(v)
        except Exception:
            v = 1
        return max(1, v)
