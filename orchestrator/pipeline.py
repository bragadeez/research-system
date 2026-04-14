"""
orchestrator/pipeline.py

Coordinates the full research pipeline:
  Planner → Search → Rank → Extract → Aggregate → Synthesise → Critique
  Optional retry loop if confidence < threshold
"""
from __future__ import annotations

import asyncio
import uuid
from typing import Callable, Optional

from loguru import logger

from agents.critic_agent import critic_agent
from agents.extraction_agent import extraction_agent
from agents.planner_agent import planner
from agents.search_agent import search_agent
from agents.synthesis_agent import synthesis_agent
from config import settings
from core.evidence_aggregator import evidence_aggregator
from core.source_ranker import source_ranker
from models.state import ResearchState


class ResearchPipeline:
    """
    Runs the full research pipeline.

    Usage:
        pipeline = ResearchPipeline()
        state = await pipeline.run("Latest advances in CRISPR therapy")
    """

    async def run(
        self,
        topic: str,
        session_id: Optional[str] = None,
        progress_callback: Optional[Callable] = None,
    ) -> ResearchState:
        """
        Execute the research pipeline end-to-end.

        Args:
            topic:             Research query string
            session_id:        UUID string for this session (auto-generated if None)
            progress_callback: async callable receiving {agent, message, data} dicts

        Returns:
            ResearchState with all results populated
        """
        sid = session_id or str(uuid.uuid4())
        state = ResearchState(topic=topic, session_id=sid)

        async def notify(agent: str, message: str, data: dict = None):
            update = {"agent": agent, "message": message, "data": data or {}}
            state.add_progress(agent, message, data)
            if progress_callback:
                try:
                    await progress_callback(update)
                except Exception as e:
                    logger.debug(f"Progress callback error: {e}")

        # Shared callback wrapper for agents
        async def cb(update: dict):
            agent = update.get("agent", "system")
            message = update.get("message", "")
            data = update.get("data", {})
            await notify(agent, message, data)

        await notify("system", f"🚀 Starting research: {topic}")

        # ── Phase 1: Plan ─────────────────────────────────────────────────
        state.status = "planning"
        await notify("planner", "🧠 Building research plan...")
        try:
            state.plan = await planner.create_plan_async(topic)
            await notify(
                "planner",
                f"✅ Plan ready: {len(state.plan.subtopics)} subtopics | "
                f"intent={state.plan.research_intent.value}",
                {"subtopics": [s.title for s in state.plan.subtopics]},
            )
        except Exception as e:
            state.add_error(f"Planning failed: {e}")
            state.status = "error"
            await notify("planner", f"❌ Planning failed: {e}")
            return state

        # ── Retry loop ────────────────────────────────────────────────────
        while state.iteration < settings.MAX_ITERATIONS:
            state.iteration += 1
            is_retry = state.iteration > 1

            if is_retry:
                await notify(
                    "system",
                    f"🔄 Retry #{state.iteration}: running targeted follow-up search",
                )

            # ── Phase 2: Search ───────────────────────────────────────────
            state.status = "searching"
            await notify("search", f"🔍 Searching sources (iteration {state.iteration})...")
            try:
                raw = await search_agent.run(state.plan, progress_callback=cb)
                # On retry: append new sources to existing ones
                state.raw_sources.extend(raw)
                await notify("search", f"✅ {len(state.raw_sources)} total raw sources")
            except Exception as e:
                state.add_error(f"Search failed: {e}")
                await notify("search", f"❌ Search error: {e}")
                break

            # ── Phase 3: Rank ──────────────────────────────────────────────
            try:
                ranked = source_ranker.rank_sources(
                    state.raw_sources,
                    topic=topic,
                    plan=state.plan,
                )
                state.ranked_sources = ranked
                await notify(
                    "ranker",
                    f"📊 Ranked {len(ranked)} sources (min_score={source_ranker.min_score})",
                )
            except Exception as e:
                state.add_error(f"Ranking failed: {e}")
                state.ranked_sources = list(state.raw_sources)
                await notify("ranker", f"⚠️ Ranking error (using unranked): {e}")

            # ── Phase 4: Extract ───────────────────────────────────────────
            state.status = "extracting"
            try:
                new_evidence = await extraction_agent.run(
                    state.plan, state.ranked_sources, progress_callback=cb
                )
                # Merge with existing evidence on retry (dedup by evidence_id)
                existing_ids = {e.evidence_id for e in state.evidence}
                for ev in new_evidence:
                    if ev.evidence_id not in existing_ids:
                        state.evidence.append(ev)
                        existing_ids.add(ev.evidence_id)
                await notify("extraction", f"✅ Total evidence: {len(state.evidence)} items")
            except Exception as e:
                state.add_error(f"Extraction failed: {e}")
                await notify("extraction", f"❌ Extraction error: {e}")
                break

            # ── Phase 5: Aggregate ─────────────────────────────────────────
            try:
                state.findings = evidence_aggregator.aggregate(state.evidence)
                await notify(
                    "aggregator",
                    f"🔗 Aggregated {len(state.findings)} findings",
                )
            except Exception as e:
                state.add_error(f"Aggregation failed: {e}")
                await notify("aggregator", f"❌ Aggregation error: {e}")
                break

            if not state.findings:
                await notify("system", "⚠️ No findings extracted — check search quality")
                break

            # ── Phase 6: Synthesise ────────────────────────────────────────
            state.status = "synthesizing"
            try:
                state.report = await synthesis_agent.run(
                    state.plan, state.findings, state.ranked_sources, progress_callback=cb
                )
            except Exception as e:
                state.add_error(f"Synthesis failed: {e}")
                await notify("synthesis", f"❌ Synthesis error: {e}")
                break

            # ── Phase 7: Critique ──────────────────────────────────────────
            state.status = "validating"
            try:
                state.critique = await critic_agent.run(
                    state.plan, state.report,
                    state.findings, state.ranked_sources,
                    progress_callback=cb,
                )
            except Exception as e:
                state.add_error(f"Critique failed: {e}")
                state.status = "complete"   # still return what we have
                break

            score = state.critique.confidence_score
            needs_retry = (
                state.critique.needs_more_research
                and score < settings.CONFIDENCE_THRESHOLD
                and state.iteration < settings.MAX_ITERATIONS
            )

            if needs_retry and state.critique.improvement_queries:
                # Inject follow-up queries as new sub-tasks for the next iteration
                from models.research_plan import (
                    SubTopicPlan, TaskType, Priority, Depth, SourceType
                )
                for i, q in enumerate(state.critique.improvement_queries[:2], 1):
                    try:
                        follow_up = SubTopicPlan(
                            title=f"Follow-up {state.iteration}.{i}: {q[:40]}",
                            task_type=TaskType.research,
                            objective=f"Fill research gap: {q}",
                            search_queries=[q, f"{q} {topic}"],
                            source_types=[SourceType.academic, SourceType.news],
                            expected_evidence=["factual claims", "data"],
                            priority=Priority.high,
                            execution_priority=1,
                            depth=Depth.standard,
                            difficulty="medium",
                            estimated_sources=5,
                            estimated_tokens=3000,
                            parallel_group=1,
                            blocking=False,
                            max_sources=8,
                            requires_statistics=False,
                            requires_comparison=False,
                            requires_extraction=True,
                            section_title="Additional Research",
                            depends_on=[],
                        )
                        state.plan.subtopics.append(follow_up)
                    except Exception as e:
                        logger.debug(f"Could not add follow-up subtopic: {e}")
            else:
                break   # confidence OK or no improvement queries

        # ── Final ─────────────────────────────────────────────────────────
        state.status = "complete"
        final_score = state.critique.confidence_score if state.critique else 0.0
        await notify(
            "system",
            f"🎉 Research complete! Confidence: {final_score:.0%} | "
            f"Findings: {len(state.findings)} | Words: {len(state.report.split())}",
            state.to_summary(),
        )
        return state


pipeline = ResearchPipeline()
