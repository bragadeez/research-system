from __future__ import annotations

from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from models.research_plan import ResearchPlan
    from models.source import RawSource, RankedSource
    from models.extraction import ExtractedEvidence
    from models.finding import ResearchFinding
    from models.critique import CritiqueResult


class ResearchState:
    """
    Mutable state object passed through the research pipeline.
    Using a class (not TypedDict) so nodes can mutate it in place.
    """

    __slots__ = (
        "topic",
        "session_id",
        "plan",
        "raw_sources",
        "ranked_sources",
        "evidence",
        "findings",
        "report",
        "critique",
        "iteration",
        "status",
        "errors",
        "progress_updates",
    )

    def __init__(self, topic: str, session_id: str):
        self.topic: str = topic
        self.session_id: str = session_id
        self.plan: Optional[Any] = None            # ResearchPlan
        self.raw_sources: List[Any] = []           # List[RawSource]
        self.ranked_sources: List[Any] = []        # List[RankedSource]
        self.evidence: List[Any] = []              # List[ExtractedEvidence]
        self.findings: List[Any] = []              # List[ResearchFinding]
        self.report: str = ""
        self.critique: Optional[Any] = None        # CritiqueResult
        self.iteration: int = 0
        self.status: str = "pending"               # pending|planning|searching|extracting|synthesizing|validating|complete|error
        self.errors: List[str] = []
        self.progress_updates: List[Dict] = []

    def add_progress(self, agent: str, message: str, data: Dict = None):
        self.progress_updates.append({
            "agent": agent,
            "message": message,
            "data": data or {},
        })

    def add_error(self, error: str):
        self.errors.append(error)

    def to_summary(self) -> Dict:
        return {
            "topic": self.topic,
            "session_id": self.session_id,
            "status": self.status,
            "iteration": self.iteration,
            "raw_sources": len(self.raw_sources),
            "ranked_sources": len(self.ranked_sources),
            "evidence": len(self.evidence),
            "findings": len(self.findings),
            "report_words": len(self.report.split()) if self.report else 0,
            "confidence": self.critique.confidence_score if self.critique else 0.0,
            "errors": self.errors,
        }
