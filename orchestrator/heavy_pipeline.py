"""
orchestrator/heavy_pipeline.py

Research Heavy pipeline built on LangGraph StateGraph.

Graph layout:
    plan → academic_search → rank → extract → aggregate → heavy_synthesize → critique
                ↑__________________________________________________|  (retry edge)

Exposes the exact same public interface (HeavyResearchPipeline.run) as pipeline.py.
"""
from __future__ import annotations

import asyncio
import uuid
from typing import Callable, Dict, Optional

from loguru import logger
from langgraph.graph import StateGraph, END

from agents.critic_agent import critic_agent
from agents.extraction_agent import extraction_agent
from agents.planner_agent import planner
from agents.academic_search_agent import academic_search_agent
from agents.heavy_synthesis_agent import heavy_synthesis_agent
from config import settings
from core.evidence_aggregator import evidence_aggregator
from core.source_ranker import source_ranker
from models.state import GraphState, ResearchState

# ── Module-level callback registry ────────────────────────────────────────────
_callbacks: Dict[str, Callable] = {}


# ─── Helper ───────────────────────────────────────────────────────────────────

async def _notify(state: GraphState, agent: str, message: str, data: dict = None):
    """Send a progress update via the stored callback and record it in state."""
    update = {"agent": agent, "message": message, "data": data or {}}
    cb = _callbacks.get(state.get("session_id", ""))
    if cb:
        try:
            await cb(update)
        except Exception as exc:
            logger.debug(f"[HeavyPipeline] Progress callback error: {exc}")
    return update


# ─── Node Functions ───────────────────────────────────────────────────────────

async def plan_node(state: GraphState) -> dict:
    """Phase 1: Planner agent — build a structured ResearchPlan."""
    sid = state["session_id"]
    topic = state["topic"]
    update = await _notify(state, "planner", "🧠 Building academic research plan…")
    try:
        plan = await planner.create_plan_async(topic)
        await _notify(
            state, "planner",
            f"✅ Plan ready: {len(plan.subtopics)} subtopics | intent={plan.research_intent.value}",
            {"subtopics": [s.title for s in plan.subtopics]},
        )
        return {
            "plan": plan,
            "status": "planning",
            "progress_updates": [update],
        }
    except Exception as e:
        await _notify(state, "planner", f"❌ Planning failed: {e}")
        logger.error(f"[HeavyPipeline] plan_node failed: {e}")
        return {
            "status": "error",
            "errors": [f"Planning failed: {e}"],
            "progress_updates": [update],
        }


async def academic_search_node(state: GraphState) -> dict:
    """Phase 2: Academic Search agent — query arXiv, PMC, OpenAlex, Semantic Scholar, CORE."""
    update = await _notify(state, "search", f"📚 Querying academic databases (iteration {state.get('iteration', 1)})…")
    try:
        async def cb(u: dict):
            await _notify(state, u.get("agent", "search"), u.get("message", ""), u.get("data", {}))

        raw_sources, academic_papers = await academic_search_agent.run(
            state["plan"],
            paper_threshold=state.get("paper_threshold", settings.HEAVY_PAPER_THRESHOLD),
            progress_callback=cb
        )
        return {
            "raw_sources": raw_sources,
            "academic_papers": academic_papers,
            "status": "searching",
            "iteration": state.get("iteration", 0) + 1,
            "progress_updates": [update],
        }
    except Exception as e:
        await _notify(state, "search", f"❌ Academic search error: {e}")
        logger.error(f"[HeavyPipeline] academic_search_node failed: {e}")
        return {
            "status": "error",
            "errors": [f"Academic search failed: {e}"],
            "progress_updates": [update],
        }


async def rank_node(state: GraphState) -> dict:
    """Phase 3: Source ranker — score and filter raw academic sources."""
    update = await _notify(state, "ranker", "📊 Processing source metadata…")
    try:
        # We run the sources through source_ranker to construct the RankedSource models,
        # but since academic search already selected the best ones, we keep them all.
        ranked = source_ranker.rank_sources(
            state["raw_sources"],
            topic=state["topic"],
            plan=state["plan"],
            min_score=0.0,  # Do not filter out any since they are pre-selected
        )
        # Preserve original citation score order from academic search
        url_to_rank = {s.url: i for i, s in enumerate(state["raw_sources"])}
        ranked.sort(key=lambda r: url_to_rank.get(r.url, 999))

        await _notify(state, "ranker", f"📊 Categorised {len(ranked)} academic sources")
        return {
            "ranked_sources": ranked,
            "progress_updates": [update],
        }
    except Exception as e:
        await _notify(state, "ranker", f"⚠️ Ranking error (using unranked): {e}")
        # Convert raw to ranked manually if it fails
        from models.source import RankedSource
        fallback = []
        for s in state.get("raw_sources", []):
            fallback.append(RankedSource(
                **s.model_dump(),
                normalized_url=s.url,
                source_kind="academic",
                topic_alignment=1.0,
                credibility_score=0.9,
                relevance_score=0.9,
                length_score=0.5,
                final_score=0.8,
            ))
        return {
            "ranked_sources": fallback,
            "errors": [f"Ranking failed: {e}"],
            "progress_updates": [update],
        }


async def extract_node(state: GraphState) -> dict:
    """Phase 4: Extraction agent — pull facts from academic papers."""
    update = await _notify(state, "extraction", "🔬 Extracting academic evidence…")
    try:
        async def cb(u: dict):
            await _notify(state, u.get("agent", "extraction"), u.get("message", ""), u.get("data", {}))

        new_evidence = await extraction_agent.run(
            state["plan"], state["ranked_sources"], progress_callback=cb
        )
        existing_ids = {e.evidence_id for e in state.get("evidence", [])}
        fresh = [ev for ev in new_evidence if ev.evidence_id not in existing_ids]
        total = len(state.get("evidence", [])) + len(fresh)
        await _notify(state, "extraction", f"✅ Total evidence: {total} items extracted")
        return {
            "evidence": fresh,
            "status": "extracting",
            "progress_updates": [update],
        }
    except Exception as e:
        await _notify(state, "extraction", f"❌ Extraction error: {e}")
        logger.error(f"[HeavyPipeline] extract_node failed: {e}")
        return {
            "status": "error",
            "errors": [f"Extraction failed: {e}"],
            "progress_updates": [update],
        }


async def aggregate_node(state: GraphState) -> dict:
    """Phase 5: Evidence aggregator — cluster findings."""
    update = await _notify(state, "aggregator", "🔗 Clustering evidence…")
    try:
        findings = evidence_aggregator.aggregate(state.get("evidence", []))
        await _notify(state, "aggregator", f"🔗 Synthesised {len(findings)} research findings")
        return {
            "findings": findings,
            "progress_updates": [update],
        }
    except Exception as e:
        await _notify(state, "aggregator", f"❌ Aggregation error: {e}")
        logger.error(f"[HeavyPipeline] aggregate_node failed: {e}")
        return {
            "status": "error",
            "errors": [f"Aggregation failed: {e}"],
            "progress_updates": [update],
        }


async def heavy_synthesize_node(state: GraphState) -> dict:
    """Phase 6: Heavy Synthesis agent — write the academic report."""
    update = await _notify(state, "synthesis", "📝 Compiling academic report…")
    try:
        async def cb(u: dict):
            await _notify(state, u.get("agent", "synthesis"), u.get("message", ""), u.get("data", {}))

        report = await heavy_synthesis_agent.run(
            state["plan"], state["findings"], state["academic_papers"], progress_callback=cb
        )
        return {
            "report": report,
            "status": "synthesizing",
            "progress_updates": [update],
        }
    except Exception as e:
        await _notify(state, "synthesis", f"❌ Academic synthesis error: {e}")
        logger.error(f"[HeavyPipeline] heavy_synthesize_node failed: {e}")
        return {
            "status": "error",
            "errors": [f"Synthesis failed: {e}"],
            "progress_updates": [update],
        }


async def critique_node(state: GraphState) -> dict:
    """Phase 7: Critic agent — fact-check report and decide on loopback retry."""
    update = await _notify(state, "critic", "🔬 Fact-checking academic report…")
    try:
        async def cb(u: dict):
            await _notify(state, u.get("agent", "critic"), u.get("message", ""), u.get("data", {}))

        critique = await critic_agent.run(
            state["plan"], state["report"],
            state["findings"], state["ranked_sources"],
            progress_callback=cb,
        )

        score = critique.confidence_score
        needs_retry = (
            critique.needs_more_research
            and score < settings.CONFIDENCE_THRESHOLD
            and state.get("iteration", 1) < settings.MAX_ITERATIONS
        )

        if needs_retry and critique.improvement_queries:
            from models.research_plan import (
                SubTopicPlan, TaskType, Priority, Depth, SourceType
            )
            plan = state["plan"]
            for i, q in enumerate(critique.improvement_queries[:2], 1):
                try:
                    follow_up = SubTopicPlan(
                        title=f"Academic Follow-up {state.get('iteration',1)}.{i}: {q[:40]}",
                        task_type=TaskType.research,
                        objective=f"Resolve academic critique gap: {q}",
                        search_queries=[q, f"{q} {state['topic']}"],
                        source_types=[SourceType.academic],
                        expected_evidence=["factual claims", "peer reviewed research"],
                        priority=Priority.high,
                        execution_priority=1,
                        depth=Depth.detailed,
                        difficulty="hard",
                        estimated_sources=5,
                        estimated_tokens=4000,
                        parallel_group=1,
                        blocking=False,
                        max_sources=8,
                        requires_statistics=True,
                        requires_comparison=True,
                        requires_extraction=True,
                        section_title="Additional Academic Review",
                        depends_on=[],
                    )
                    plan.subtopics.append(follow_up)
                except Exception as exc:
                    logger.warning(f"[HeavyPipeline] Could not add follow-up: {exc}")

        return {
            "critique": critique,
            "needs_retry": needs_retry,
            "status": "validating",
            "progress_updates": [update],
        }
    except Exception as e:
        await _notify(state, "critic", f"❌ Critique error: {e}")
        logger.error(f"[HeavyPipeline] critique_node failed: {e}")
        return {
            "critique": None,
            "needs_retry": False,
            "status": "complete",
            "errors": [f"Critique failed: {e}"],
            "progress_updates": [update],
        }


# ─── Routing ──────────────────────────────────────────────────────────────────

def _route_after_plan(state: GraphState) -> str:
    return "search" if state.get("status") != "error" else END


def _route_after_extract(state: GraphState) -> str:
    return "aggregate" if state.get("status") != "error" else END


def _route_after_aggregate(state: GraphState) -> str:
    findings = state.get("findings", [])
    if not findings:
        logger.warning("[HeavyPipeline] No findings — ending early")
        return END
    return "synthesize" if state.get("status") != "error" else END


def _route_after_critique(state: GraphState) -> str:
    if state.get("needs_retry"):
        logger.info("[HeavyPipeline] Retry triggered — looping back to search")
        return "search"
    return END


# ─── Build Graph ──────────────────────────────────────────────────────────────

def _build_graph() -> StateGraph:
    wf = StateGraph(GraphState)

    wf.add_node("plan",      plan_node)
    wf.add_node("search",    academic_search_node)
    wf.add_node("rank",      rank_node)
    wf.add_node("extract",   extract_node)
    wf.add_node("aggregate", aggregate_node)
    wf.add_node("synthesize",heavy_synthesize_node)
    wf.add_node("critique",  critique_node)

    wf.set_entry_point("plan")

    wf.add_conditional_edges("plan", _route_after_plan, {"search": "search", END: END})
    wf.add_edge("search",    "rank")
    wf.add_edge("rank",      "extract")
    wf.add_conditional_edges("extract",   _route_after_extract,   {"aggregate": "aggregate",  END: END})
    wf.add_conditional_edges("aggregate", _route_after_aggregate, {"synthesize": "synthesize", END: END})
    wf.add_edge("synthesize", "critique")
    wf.add_conditional_edges("critique", _route_after_critique, {"search": "search", END: END})

    return wf.compile()


_graph = _build_graph()


# ─── Public Interface ─────────────────────────────────────────────────────────

class HeavyResearchPipeline:
    """
    Research Heavy pipeline exposing the identical run() signature
    so that api/server.py routes easily.
    """

    async def run(
        self,
        topic: str,
        session_id: Optional[str] = None,
        progress_callback: Optional[Callable] = None,
        research_mode: str = "heavy",
        paper_threshold: int = None,
    ) -> ResearchState:
        sid = session_id or str(uuid.uuid4())

        # Register callback
        if progress_callback:
            _callbacks[sid] = progress_callback

        init_state: GraphState = {
            "topic": topic,
            "session_id": sid,
            "research_mode": "heavy",
            "paper_threshold": paper_threshold or settings.HEAVY_PAPER_THRESHOLD,
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

        await _notify(init_state, "system", f"🚀 Starting Research Heavy pipeline: {topic}")

        try:
            final_state = await _graph.ainvoke(init_state)
        except Exception as e:
            logger.error(f"[HeavyPipeline] Graph invocation failed: {e}")
            final_state = dict(init_state)
            final_state["status"] = "error"
            final_state["errors"] = [f"Heavy pipeline crashed: {e}"]
        finally:
            _callbacks.pop(sid, None)

        rs = ResearchState.from_graph_state(final_state)
        final_score = rs.critique.confidence_score if rs.critique else 0.0
        report_words = len(rs.report.split()) if rs.report else 0

        if progress_callback:
            try:
                await progress_callback({
                    "agent": "system",
                    "message": (
                        f"🎉 Academic research complete! Confidence: {final_score:.0%} | "
                        f"Papers: {len(rs.academic_papers)} | Words: {report_words}"
                    ),
                    "data": rs.to_summary(),
                })
            except Exception:
                pass

        rs.status = "complete" if rs.status not in ("error",) else "error"
        return rs


heavy_pipeline = HeavyResearchPipeline()
