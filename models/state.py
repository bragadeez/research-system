"""
models/state.py

Defines:
  - GraphState  : TypedDict used by LangGraph StateGraph nodes (serialisable).
  - ResearchState: Convenience class built from GraphState for backward-compat
                   with api/server.py which accesses state.critique, state.findings etc.
"""
from __future__ import annotations

import operator
from typing import Any, Annotated, Dict, List, Optional, TYPE_CHECKING
from typing_extensions import TypedDict

if TYPE_CHECKING:
    from models.research_plan import ResearchPlan
    from models.source import RawSource, RankedSource
    from models.extraction import ExtractedEvidence
    from models.finding import ResearchFinding
    from models.critique import CritiqueResult


# ─── LangGraph TypedDict State ────────────────────────────────────────────────

class GraphState(TypedDict, total=False):
    """
    Typed state dict passed through every LangGraph node.

    List fields annotated with `operator.add` are *reducers*: each node returns
    only the NEW items to append; LangGraph merges them automatically.
    """
    # Core identifiers
    topic: str
    session_id: str
    research_mode: str          # "standard" | "heavy"
    paper_threshold: int        # Heavy mode: max papers to keep after scoring

    # Pipeline phases
    plan: Optional[Any]                                   # ResearchPlan
    raw_sources: Annotated[List[Any], operator.add]       # List[RawSource]
    ranked_sources: List[Any]                             # List[RankedSource]
    evidence: Annotated[List[Any], operator.add]          # List[ExtractedEvidence]
    findings: List[Any]                                   # List[ResearchFinding]
    report: str
    critique: Optional[Any]                               # CritiqueResult

    # Heavy mode extras
    academic_papers: List[Any]  # enriched paper dicts with citation metadata

    # Orchestration
    iteration: int
    status: str
    needs_retry: bool
    errors: Annotated[List[str], operator.add]
    progress_updates: Annotated[List[Dict], operator.add]


# ─── Backward-compat wrapper ──────────────────────────────────────────────────

class ResearchState:
    """
    Thin wrapper around GraphState dict that exposes attribute-style access.
    Used by api/server.py which was written before the LangGraph migration.
    """

    __slots__ = ("_d",)

    def __init__(self, topic: str, session_id: str, research_mode: str = "standard",
                 paper_threshold: int = 10):
        self._d: GraphState = {
            "topic": topic,
            "session_id": session_id,
            "research_mode": research_mode,
            "paper_threshold": paper_threshold,
            "plan": None,
            "raw_sources": [],
            "ranked_sources": [],
            "evidence": [],
            "findings": [],
            "report": "",
            "critique": None,
            "academic_papers": [],
            "iteration": 0,
            "status": "pending",
            "needs_retry": False,
            "errors": [],
            "progress_updates": [],
        }

    # ── Attribute proxies ──────────────────────────────────────────────────────

    @classmethod
    def from_graph_state(cls, state: GraphState) -> "ResearchState":
        rs = cls.__new__(cls)
        rs._d = dict(state)  # type: ignore[arg-type]
        return rs

    def to_graph_state(self) -> GraphState:
        return dict(self._d)  # type: ignore[return-value]

    # Generic getattr / setattr so all existing code works unchanged
    def __getattr__(self, name: str):
        try:
            return self._d[name]
        except KeyError:
            raise AttributeError(name)

    def __setattr__(self, name: str, value):
        if name == "_d":
            object.__setattr__(self, name, value)
        else:
            self._d[name] = value

    # ── Helpers ────────────────────────────────────────────────────────────────

    def add_progress(self, agent: str, message: str, data: Dict = None):
        self._d["progress_updates"].append({
            "agent": agent,
            "message": message,
            "data": data or {},
        })

    def add_error(self, error: str):
        self._d["errors"].append(error)

    def to_summary(self) -> Dict:
        d = self._d
        return {
            "topic":          d.get("topic", ""),
            "session_id":     d.get("session_id", ""),
            "status":         d.get("status", ""),
            "research_mode":  d.get("research_mode", "standard"),
            "iteration":      d.get("iteration", 0),
            "raw_sources":    len(d.get("raw_sources", [])),
            "ranked_sources": len(d.get("ranked_sources", [])),
            "evidence":       len(d.get("evidence", [])),
            "findings":       len(d.get("findings", [])),
            "report_words":   len(d.get("report", "").split()) if d.get("report") else 0,
            "confidence":     d["critique"].confidence_score if d.get("critique") else 0.0,
            "errors":         d.get("errors", []),
        }
