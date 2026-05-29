from __future__ import annotations

from typing import List

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ResearchFinding(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    finding_id: str
    topic: str
    section_title: str
    subtopic: str = ""
    category: str = "unknown"

    title: str
    summary: str

    confidence: float = 0.0
    support_count: int = 1

    representative_claim: str = ""
    evidence_ids: List[str] = Field(default_factory=list)
    supporting_sources: List[str] = Field(default_factory=list)
    source_kinds: List[str] = Field(default_factory=list)
    claim_variants: List[str] = Field(default_factory=list)
    keywords: List[str] = Field(default_factory=list)
    contradictions: List[str] = Field(default_factory=list)

    @field_validator("confidence")
    @classmethod
    def clamp_confidence(cls, v):
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
