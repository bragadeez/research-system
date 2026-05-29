from __future__ import annotations
from typing import List
from pydantic import BaseModel, ConfigDict, Field


class RawSource(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    url: str
    title: str
    content: str
    domain: str
    query: str
    subtopic: str
    content_length: int
    fetch_time: float
    domain_score: float
    query_match_score: int
    final_score: float = 0.0


class RankedSource(RawSource):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    normalized_url: str = ""
    source_kind: str = "unknown"
    topic_alignment: float = 0.0
    credibility_score: float = 0.0
    relevance_score: float = 0.0
    length_score: float = 0.0
    quality_flags: List[str] = Field(default_factory=list)
    rank_reason: str = ""
