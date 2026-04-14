"""
agents/synthesis_agent.py

Generates a comprehensive Markdown research report from:
  - ResearchPlan (sections, thesis, intent)
  - List[ResearchFinding] (structured evidence clusters)
  - List[RankedSource]  (for citation URLs and titles)
"""
from __future__ import annotations

import asyncio
from textwrap import dedent
from typing import Callable, List, Optional

from loguru import logger

from core.llm_client import llm
from models.finding import ResearchFinding
from models.research_plan import ResearchPlan
from models.source import RankedSource


# ── Prompt ──────────────────────────────────────────────────────────────────

SYNTHESIS_SYSTEM = dedent("""
You are an expert research analyst and technical writer.

Write a comprehensive, well-structured research report in Markdown.

Report structure:
1. ## Executive Summary  — 2-3 sentence TL;DR
2. One section per provided section plan
3. ## Key Findings       — bullet list of top discoveries
4. ## Limitations & Gaps — honest gaps in the evidence
5. ## Conclusion         — final synthesis
6. ## References         — numbered list of cited sources

Writing rules:
- Cite sources inline as [Author/Title](URL) whenever referencing a specific finding
- Base claims ONLY on the provided evidence findings — do not hallucinate
- Include specific numbers, metrics, and data when available
- Note contradictions as trade-offs, not as errors
- Professional, objective tone
- Aim for 900–1500 words
- Return ONLY the Markdown report — no preamble
""")


def _format_findings_for_prompt(
    findings: List[ResearchFinding],
    sections: list,
    max_findings: int = 35,
) -> str:
    """Format top findings grouped by section for the synthesis prompt."""
    # Cap to avoid token overflow
    top_findings = sorted(
        findings, key=lambda f: (f.confidence, f.support_count), reverse=True
    )[:max_findings]

    # Group by section_title
    section_map: dict = {}
    for f in top_findings:
        section_map.setdefault(f.section_title or "General", []).append(f)

    lines = []
    for section_title, section_findings in section_map.items():
        lines.append(f"\n### Section: {section_title}")
        for f in section_findings:
            lines.append(
                f"[{f.category.upper()}] (confidence={f.confidence:.0%}, "
                f"sources={f.support_count}) {f.representative_claim}"
            )
            if f.contradictions:
                lines.append(f"  ⚠️ {f.contradictions[0]}")
            if f.summary and f.summary != f.representative_claim:
                lines.append(f"  Evidence: {f.summary[:200]}")

    return "\n".join(lines)


def _format_sources_for_prompt(sources: List[RankedSource], max_sources: int = 20) -> str:
    """Build a compact citation reference block."""
    seen: set = set()
    lines = []
    for s in sorted(sources, key=lambda x: x.final_score, reverse=True):
        if s.url in seen or not s.title:
            continue
        seen.add(s.url)
        lines.append(f"- [{s.title[:80]}]({s.url}) [{s.source_kind}]")
        if len(lines) >= max_sources:
            break
    return "\n".join(lines)


class SynthesisAgent:

    def build_prompt(
        self,
        plan: ResearchPlan,
        findings: List[ResearchFinding],
        ranked_sources: List[RankedSource],
    ) -> str:
        sections_text = "\n".join(
            f"- **{s.title}**: {s.purpose}" for s in plan.sections
        )
        findings_text = _format_findings_for_prompt(findings, plan.sections)
        sources_text = _format_sources_for_prompt(ranked_sources)

        return dedent(f"""
{SYNTHESIS_SYSTEM}

---

RESEARCH TOPIC: {plan.topic}

RESEARCH INTENT: {plan.research_intent.value}

THESIS: {plan.thesis}

AUDIENCE: {plan.audience}

SECTIONS TO COVER:
{sections_text}

EVIDENCE FINDINGS:
{findings_text}

AVAILABLE CITATION SOURCES:
{sources_text}

CONTRADICTIONS TO ACKNOWLEDGE:
{chr(10).join(f'- {c}' for c in plan.contradictions_to_watch[:5])}

Now write the complete research report.
""")

    async def run(
        self,
        plan: ResearchPlan,
        findings: List[ResearchFinding],
        ranked_sources: List[RankedSource],
        progress_callback: Optional[Callable] = None,
    ) -> str:
        """Generate the Markdown report. Returns the report string."""
        async def _notify(msg: str):
            if progress_callback:
                await progress_callback({"agent": "synthesis", "message": msg, "data": {}})

        await _notify(
            f"📝 Writing report from {len(findings)} findings and "
            f"{len(ranked_sources)} sources..."
        )

        prompt = self.build_prompt(plan, findings, ranked_sources)

        for attempt in range(3):
            try:
                report = await llm.generate_text_async(prompt)
                word_count = len(report.split())
                await _notify(f"✅ Report written — {word_count} words")
                logger.info(f"[Synthesis] Report: {word_count} words")
                return report
            except Exception as e:
                if attempt == 2:
                    logger.error(f"[Synthesis] Failed after 3 attempts: {e}")
                    return f"# Research Report\n\n**Error generating report:** {e}\n\n"
                await asyncio.sleep(2 ** attempt * 2)

        return ""


synthesis_agent = SynthesisAgent()
