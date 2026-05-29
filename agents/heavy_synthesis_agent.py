"""
agents/heavy_synthesis_agent.py

Research Heavy mode synthesis agent.
Generates an academic-style Markdown research report from:
  - ResearchPlan
  - List[ResearchFinding]
  - List[dict] (academic_papers from state)
"""
from __future__ import annotations

import asyncio
from textwrap import dedent
from typing import Callable, List, Optional

from loguru import logger

from core.llm_client import llm
from models.finding import ResearchFinding
from models.research_plan import ResearchPlan

HEAVY_SYNTHESIS_SYSTEM = dedent("""\
You are an expert academic research analyst and technical writer.

Write a rigorous, comprehensive academic research report in Markdown.

Report structure:
1. ## Abstract
   A 150-250 word formal academic abstract summarizing the research topic, methodology, key findings, and implications.

2. ## Literature Review
   Synthesize the research by subtopics. For each subtopic, write in-depth paragraphs using citation keys (e.g., [1], [2]) referencing the numerical bibliography below. Do not use generic markdown links here; use numerical citations.

3. ## Key Findings per Paper
   A detailed breakdown of each analyzed paper in a structured list or table format. For each paper, include:
   - **Title**: [Title]
   - **Authors & Year**: [Authors], [Year]
   - **Citations & Score**: [Citation Count] (Citations/Year: [Citation Score])
   - **Source**: [Source, e.g., arXiv, semantic_scholar]
   - **Methodology & Key Findings**: A brief summary of what they did and found.

4. ## Consensus & Contradictions
   Discuss the areas where the literature shows clear consensus and where there are contradictions or debating views.

5. ## Research Gaps
   Identify 3-4 specific areas, questions, or limitations that have not been adequately studied in the current literature.

6. ## Novelty Suggestions
   Provide concrete, actionable suggestions for future studies to fill those research gaps, including possible novel methodologies.

7. ## Bibliography
   List all references in numerical order (e.g., `[1] Authors. (Year). Title. Journal/Source. [Link](URL)`), formatted in APA style.

Writing rules:
- Cite sources as numerical citations like [1], [2] in the text.
- Base claims ONLY on the provided evidence findings and the paper abstracts. Do not hallucinate.
- Maintain a formal, academic, and objective tone.
- Do NOT output any markdown tags outside the report itself. Start directly with the Abstract.
""")


def _format_findings_for_prompt(
    findings: List[ResearchFinding],
    max_findings: int = 35,
) -> str:
    top_findings = sorted(
        findings, key=lambda f: (f.confidence, f.support_count), reverse=True
    )[:max_findings]

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
                lines.append(f"  ⚠️ Contradiction: {f.contradictions[0]}")
            if f.summary and f.summary != f.representative_claim:
                lines.append(f"  Evidence: {f.summary[:200]}")

    return "\n".join(lines)


def _format_academic_papers_for_prompt(papers: List[dict]) -> str:
    lines = []
    for idx, p in enumerate(papers, 1):
        lines.append(
            f"Paper [{idx}]:\n"
            f"Title: {p.get('title')}\n"
            f"URL: {p.get('url')}\n"
            f"Source: {p.get('source')}\n"
            f"Year: {p.get('pub_year')}\n"
            f"Citations: {p.get('citation_count', 0)} (Citations/Year score: {p.get('citation_score', 0):.1f})\n"
            f"Details: {p.get('snippet', '')[:400]}\n"
        )
    return "\n".join(lines)


class HeavySynthesisAgent:

    def build_prompt(
        self,
        plan: ResearchPlan,
        findings: List[ResearchFinding],
        academic_papers: List[dict],
    ) -> str:
        sections_text = "\n".join(
            f"- **{s.title}**: {s.purpose}" for s in plan.sections
        )
        findings_text = _format_findings_for_prompt(findings)
        papers_text = _format_academic_papers_for_prompt(academic_papers)

        return dedent(f"""\
{HEAVY_SYNTHESIS_SYSTEM}

---

RESEARCH TOPIC: {plan.topic}

RESEARCH INTENT: {plan.research_intent.value}

THESIS: {plan.thesis}

AUDIENCE: {plan.audience}

SECTIONS TO COVER:
{sections_text}

EVIDENCE FINDINGS:
{findings_text}

ACADEMIC PAPERS METADATA:
{papers_text}

CONTRADICTIONS TO ACKNOWLEDGE:
{chr(10).join(f'- {c}' for c in plan.contradictions_to_watch[:5])}

Now write the complete research report. Start directly with "## Abstract".
""")

    async def run(
        self,
        plan: ResearchPlan,
        findings: List[ResearchFinding],
        academic_papers: List[dict],
        progress_callback: Optional[Callable] = None,
    ) -> str:
        """Generate the academic Markdown report. Returns the report string."""
        async def _notify(msg: str):
            if progress_callback:
                await progress_callback({"agent": "synthesis", "message": msg, "data": {}})

        await _notify(
            f"📝 Writing academic research report from {len(findings)} findings and "
            f"{len(academic_papers)} papers…"
        )

        prompt = self.build_prompt(plan, findings, academic_papers)

        for attempt in range(3):
            try:
                report = await llm.generate_text_async(prompt)
                word_count = len(report.split())
                await _notify(f"✅ Report written — {word_count} words")
                logger.info(f"[HeavySynthesis] Report: {word_count} words")
                return report
            except Exception as e:
                if attempt == 2:
                    logger.error(f"[HeavySynthesis] Failed after 3 attempts: {e}")
                    return f"# Academic Research Report\n\n**Error generating report:** {e}\n\n"
                await asyncio.sleep(2 ** attempt * 2)

        return ""


heavy_synthesis_agent = HeavySynthesisAgent()
