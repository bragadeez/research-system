"""
main.py — ScholarNode AI (CLI mode)

Uses the same pipeline as the API server.
"""
import asyncio

from loguru import logger

import db.database as db
from config import settings
from orchestrator.pipeline import pipeline


async def main():
    # ── Initialize database ───────────────────────────────────────────────────
    db.init_db()

    # ── Change this topic to research anything ────────────────────────────────
    topic = "Latest cardiovascular research findings"

    print(f"\n🧠 Starting research: {topic}")
    print("─" * 60)

    state = await pipeline.run(topic)

    # ── Results summary ───────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("RESEARCH COMPLETE")
    print("=" * 60)
    print(f"Status:          {state.status}")
    print(f"Iterations:      {state.iteration}")
    print(f"Raw sources:     {len(state.raw_sources)}")
    print(f"Ranked sources:  {len(state.ranked_sources)}")
    print(f"Evidence items:  {len(state.evidence)}")
    print(f"Findings:        {len(state.findings)}")

    if state.critique:
        print(f"Confidence:      {state.critique.confidence_score:.0%}")

    if state.errors:
        print(f"\n⚠️  Errors: {len(state.errors)}")
        for err in state.errors:
            print(f"   • {err}")

    # ── Top findings ──────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("TOP FINDINGS")
    print("=" * 60)
    for i, finding in enumerate(state.findings[:15], start=1):
        print(f"\n[{i}] {finding.title}")
        print(f"    Category:   {finding.category}  |  Confidence: {finding.confidence:.0%}  |  Sources: {finding.support_count}")
        print(f"    Claim:      {finding.representative_claim[:120]}")
        if finding.contradictions:
            print(f"    ⚠️  {finding.contradictions[0][:100]}")

    # ── Report preview ────────────────────────────────────────────────────────
    if state.report:
        print("\n" + "=" * 60)
        print("REPORT PREVIEW (first 1500 chars)")
        print("=" * 60)
        print(state.report[:1500])
        print("…")

    # ── Critique ──────────────────────────────────────────────────────────────
    if state.critique:
        print("\n" + "=" * 60)
        print("CRITIQUE")
        print("=" * 60)
        print(f"Confidence: {state.critique.confidence_score:.0%}")
        print(f"Assessment: {state.critique.critique}")
        for fc in state.critique.fact_checks:
            icon = "✅" if fc.verdict == "supported" else ("❌" if fc.verdict == "unsupported" else "❓")
            print(f"  {icon} {fc.claim[:80]} → {fc.verdict}")

    # ── Save report ───────────────────────────────────────────────────────────
    if state.report:
        import os
        import re

        os.makedirs(settings.EXPORT_PATH, exist_ok=True)
        slug = re.sub(r"[^\w-]", "_", topic[:50])
        out_path = os.path.join(settings.EXPORT_PATH, f"{slug}.md")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(f"# {topic}\n\n{state.report}")
        print(f"\n✅ Report saved to {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
