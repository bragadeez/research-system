"""
main.py — Autonomous Research AI

Drop-in replacement for your original main.py.
All original print statements and variable names preserved.
Now wired to the full pipeline with synthesis + critique.
"""
import asyncio

from loguru import logger

from agents.extraction_agent import extraction_agent
from agents.planner_agent import planner
from agents.search_agent import search_agent
from agents.synthesis_agent import synthesis_agent
from agents.critic_agent import critic_agent
from core.evidence_aggregator import evidence_aggregator
from core.source_ranker import source_ranker


async def main():
    # ── Change this topic to research anything ────────────────────────────────
    topic = "Latest cardiovascular research findings"

    # ── Phase 1: Plan ─────────────────────────────────────────────────────────
    print(f"\n🧠 Creating research plan for: {topic}")
    plan = planner.create_plan(topic)
    print(f"✅ Plan: {len(plan.subtopics)} subtopics | intent={plan.research_intent.value}")

    # ── Phase 2: Search ───────────────────────────────────────────────────────
    print("\n🔍 Searching sources...")
    raw_sources = await search_agent.run(plan)

    # ── Phase 3: Rank ─────────────────────────────────────────────────────────
    ranked_sources = source_ranker.rank_sources(
        raw_sources,
        topic=topic,
        plan=plan,
    )

    # ── Phase 4: Extract ──────────────────────────────────────────────────────
    print("\n🔬 Extracting evidence...")
    evidence = await extraction_agent.run(plan, ranked_sources)

    # ── Phase 5: Aggregate ────────────────────────────────────────────────────
    findings = evidence_aggregator.aggregate(evidence)

    # ── Phase 6: Synthesise ───────────────────────────────────────────────────
    print("\n📝 Writing report...")
    report = await synthesis_agent.run(plan, findings, ranked_sources)

    # ── Phase 7: Critique ─────────────────────────────────────────────────────
    print("\n🔍 Fact-checking...")
    critique = await critic_agent.run(plan, report, findings, ranked_sources)

    # ── Results ───────────────────────────────────────────────────────────────
    print("\nTOTAL RAW SOURCES:", len(raw_sources))
    print("TOTAL RANKED SOURCES:", len(ranked_sources))
    print("TOTAL EXTRACTED EVIDENCE:", len(evidence))
    print("TOTAL FINDINGS:", len(findings))
    print(f"CONFIDENCE SCORE: {critique.confidence_score:.0%}")

    print("\n================ TOP FINDINGS ================")
    for i, finding in enumerate(findings[:15], start=1):
        print("\n--------------------------------")
        print("Finding:", i)
        print("ID:", finding.finding_id)
        print("Title:", finding.title)
        print("Section:", finding.section_title)
        print("Category:", finding.category)
        print("Confidence:", round(finding.confidence, 3))
        print("Support count:", finding.support_count)
        print("Claim:", finding.representative_claim)
        print("Summary:", finding.summary)
        if finding.contradictions:
            print("Contradictions:", " | ".join(finding.contradictions))
        print("Sources:", len(finding.supporting_sources))
        print("--------------------------------")

    print("\n================ REPORT PREVIEW ================")
    print(report[:1500])
    print("...")

    print("\n================ CRITIQUE ================")
    print(f"Confidence: {critique.confidence_score:.0%}")
    print(f"Critique: {critique.critique}")
    for fc in critique.fact_checks:
        icon = "✅" if fc.verdict == "supported" else ("❌" if fc.verdict == "unsupported" else "❓")
        print(f"  {icon} {fc.claim[:80]} → {fc.verdict}")

    # Save report
    with open("report.md", "w", encoding="utf-8") as f:
        f.write(f"# {topic}\n\n{report}")
    print("\n✅ Report saved to report.md")


if __name__ == "__main__":
    asyncio.run(main())
