from __future__ import annotations

from typing import List

from pydantic import BaseModel, ConfigDict, Field, field_validator


class FactCheckResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim: str
    verdict: str        # "supported" | "unsupported" | "uncertain"
    evidence: str       # brief justification


class CritiqueResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confidence_score: float = 0.0
    critique: str = ""
    fact_checks: List[FactCheckResult] = Field(default_factory=list)
    needs_more_research: bool = False
    improvement_queries: List[str] = Field(default_factory=list)
    gaps: List[str] = Field(default_factory=list)

    @field_validator("confidence_score")
    @classmethod
    def clamp_score(cls, v):
        try:
            return max(0.0, min(1.0, float(v)))
        except Exception:
            return 0.0
