"""
agents/critic_agent.py

Validates the synthesised report:
  - Checks key claims against the evidence findings
  - Assigns a confidence score
  - Decides if another search iteration is needed
  - Returns CritiqueResult
"""
from __future__ import annotations

import asyncio
from textwrap import dedent
from typing import Callable, List, Optional

from loguru import logger

from core.llm_client import llm
from models.critique import CritiqueResult
from models.finding import ResearchFinding
from models.research_plan import ResearchPlan
from models.source import RankedSource


CRITIC_SYSTEM = dedent("""
You are a rigorous research quality controller and fact-checker.

Evaluate the research report against the provided evidence findings.

Your job:
1. Extract 4-6 key factual claims from the report
2. Check each claim against the evidence — verdict: supported|unsupported|uncertain
3. Assign confidence_score (0.0–1.0):
   - 0.85-1.0: All claims well-supported, comprehensive coverage
   - 0.70-0.85: Most claims supported, minor gaps
   - 0.55-0.70: Some important gaps or unsupported claims
   - Below 0.55: Significant quality problems
4. Write a 2-3 sentence critique (what's strong, what's weak)
5. List knowledge gaps not covered by the evidence
6. Decide if more research is needed (only if major gaps exist)
7. If more research needed, provide 1-2 specific follow-up search queries

Be strict but fair. Focus on factual accuracy, not writing style.
""")


def _format_evidence_summary(
    findings: List[ResearchFinding],
    max_findings: int = 25,
) -> str:
    top = sorted(findings, key=lambda f: f.confidence, reverse=True)[:max_findings]
    lines = []
    for f in top:
        lines.append(
            f"[{f.category}] conf={f.confidence:.0%} | "
            f"{f.representative_claim[:120]}"
        )
    return "\n".join(lines)


class CriticAgent:

    def build_prompt(
        self,
        plan: ResearchPlan,
        report: str,
        findings: List[ResearchFinding],
        ranked_sources: List[RankedSource],
    ) -> str:
        evidence_summary = _format_evidence_summary(findings)
        report_excerpt = report[:4000]
        source_count = len(ranked_sources)
        source_kinds = {s.source_kind for s in ranked_sources}

        return dedent(f"""
{CRITIC_SYSTEM}

---

RESEARCH TOPIC: {plan.topic}

SOURCE COVERAGE: {source_count} sources ({', '.join(source_kinds)})

EVIDENCE FINDINGS (top {min(25, len(findings))} by confidence):
{evidence_summary}

REPORT TO EVALUATE:
{report_excerpt}

---

Return a JSON object with exactly these fields:
{{
  "confidence_score": <float 0.0-1.0>,
  "critique": "<2-3 sentence critique>",
  "fact_checks": [
    {{
      "claim": "<key claim from report>",
      "verdict": "<supported|unsupported|uncertain>",
      "evidence": "<brief justification>"
    }}
  ],
  "needs_more_research": <true|false>,
  "improvement_queries": ["<specific search query>"],
  "gaps": ["<knowledge gap>"]
}}
""")

    async def run(
        self,
        plan: ResearchPlan,
        report: str,
        findings: List[ResearchFinding],
        ranked_sources: List[RankedSource],
        progress_callback: Optional[Callable] = None,
    ) -> CritiqueResult:
        """Validate the report and return a CritiqueResult."""
        async def _notify(msg: str, data: dict = None):
            if progress_callback:
                await progress_callback({"agent": "critic", "message": msg, "data": data or {}})

        await _notify("🔬 Fact-checking report...")

        prompt = self.build_prompt(plan, report, findings, ranked_sources)

        for attempt in range(3):
            try:
                result = await llm.generate_structured_async(prompt, CritiqueResult)
                score = result.confidence_score
                icon = "🟢" if score >= 0.75 else ("🟡" if score >= 0.55 else "🔴")
                await _notify(
                    f"{icon} Confidence: {score:.0%} — {result.critique[:80]}",
                    {"confidence": score, "fact_checks": len(result.fact_checks)},
                )
                logger.info(
                    f"[Critic] confidence={score:.0%} | "
                    f"needs_more={result.needs_more_research} | "
                    f"fact_checks={len(result.fact_checks)}"
                )
                return result

            except Exception as e:
                if attempt == 2:
                    logger.error(f"[Critic] Failed after 3 attempts: {e}")
                    # Return safe default so pipeline doesn't crash
                    return CritiqueResult(
                        confidence_score=0.5,
                        critique=f"Automatic validation failed: {e}",
                        fact_checks=[],
                        needs_more_research=False,
                        improvement_queries=[],
                        gaps=[],
                    )
                await asyncio.sleep(2 ** attempt * 2)

        return CritiqueResult(confidence_score=0.5, critique="Validation unavailable.")


critic_agent = CriticAgent()
