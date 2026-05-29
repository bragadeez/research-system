"""
agents/planner_agent.py

Creates a structured ResearchPlan from a topic string.
Uses Gemini for structured JSON output with retry logic.
"""
from __future__ import annotations

import asyncio
from textwrap import dedent

from loguru import logger

from core.llm_client import llm
from models.research_plan import (
    Depth, Priority, ResearchIntent, ResearchPlan, SourceType, TaskType
)


PLANNER_PROMPT = dedent("""\
You are a senior research strategist in an autonomous research system.

Convert the topic below into a detailed, execution-ready research plan.

TOPIC: {topic}

Design the plan to maximize:
- Information coverage across different angles
- Search efficiency (specific, keyword-rich queries)
- Fact extraction quality
- Contradiction detection

Return ONLY valid JSON matching this exact structure:

{{
  "topic": "{topic}",
  "research_intent": "<one of: impact_analysis|technical_research|market_analysis|comparison|trend_analysis>",
  "depth": "<quick|standard|deep>",
  "thesis": "<one sentence stating the main research angle>",
  "audience": "<target audience e.g. researchers, professionals, general public>",
  "complexity": "<low|moderate|high>",
  "estimated_runtime_minutes": <int 5-30>,
  "execution": {{
    "max_parallel_tasks": <int>,
    "estimated_total_sources": <int>,
    "estimated_total_tokens": <int>,
    "execution_strategy": "<brief strategy description>"
  }},
  "core_tasks": ["<task 1>", "<task 2>"],
  "optional_tasks": ["<optional task>"],
  "execution_order": ["<subtopic title in order>"],
  "sections": [
    {{
      "title": "<section heading>",
      "purpose": "<what this section covers>",
      "priority": "<critical|high|medium|low>",
      "linked_subtopics": ["<subtopic title that feeds this section>"],
      "required_evidence": ["<type of evidence needed>"]
    }}
  ],
  "subtopics": [
    {{
      "title": "<specific subtopic title>",
      "task_type": "research",
      "objective": "<what this subtopic investigates>",
      "search_queries": [
        "<specific search query 1>",
        "<specific search query 2>",
        "<specific search query 3>"
      ],
      "source_types": ["<academic|government|industry_report|news|documentation|dataset|blog>"],
      "expected_evidence": ["<type of evidence expected>"],
      "priority": "<critical|high|medium|low>",
      "execution_priority": <1-10 int, 1=first>,
      "depth": "<quick|standard|deep>",
      "difficulty": "<easy|medium|hard>",
      "estimated_sources": <int 3-15>,
      "estimated_tokens": <int 1000-10000>,
      "parallel_group": <int 1-3>,
      "blocking": <true|false>,
      "max_sources": <int 5-20>,
      "requires_statistics": <true|false>,
      "requires_comparison": <true|false>,
      "requires_extraction": true,
      "section_title": "<section this subtopic feeds>",
      "depends_on": []
    }}
  ],
  "contradictions_to_watch": ["<potential contradictory claim to monitor>"],
  "source_strategy": ["<academic|government|industry_report|news|documentation|blog>"],
  "success_criteria": ["<measurable criterion for complete research>"]
}}

Rules:
- Create {min_sub} to {max_sub} subtopics covering different angles
- Each subtopic must have 2-4 specific, varied search queries (not generic)
- Academic source_type is for scientific papers; use for medical/technical topics
- Sections must reference valid subtopic titles in linked_subtopics
- Return ONLY the JSON — no explanation, no markdown code blocks
""")

REPAIR_PROMPT = dedent("""\
Fix the research plan JSON for this topic.

Topic: {topic}

The plan MUST include ALL these fields:
- topic, research_intent, depth, thesis, audience, complexity
- estimated_runtime_minutes, execution (object with 4 fields)
- core_tasks, optional_tasks, execution_order
- sections (list), subtopics (list), contradictions_to_watch
- source_strategy, success_criteria

Enum constraints:
- research_intent: impact_analysis|technical_research|market_analysis|comparison|trend_analysis
- depth: quick|standard|deep
- priority: critical|high|medium|low
- source_types items: academic|government|industry_report|news|documentation|dataset|blog
- task_type: research|synthesis|analysis

Validation error from previous attempt:
{error}

Return ONLY valid JSON.
""")


class PlannerAgent:

    def build_prompt(self, topic: str) -> str:
        from config import settings
        return PLANNER_PROMPT.format(
            topic=topic,
            min_sub=settings.MIN_SUBTOPICS,
            max_sub=settings.MAX_SUBTOPICS,
        )

    async def create_plan_async(self, topic: str) -> ResearchPlan:
        """Async plan creation for pipeline use."""
        prompt = self.build_prompt(topic)
        last_error = ""

        for attempt in range(2):
            try:
                if attempt == 0:
                    plan = await llm.generate_structured_async(prompt, ResearchPlan)
                else:
                    repair = REPAIR_PROMPT.format(topic=topic, error=last_error[:500])
                    plan = await llm.generate_structured_async(repair, ResearchPlan)

                logger.info(
                    f"[Planner] Plan created: {len(plan.subtopics)} subtopics, "
                    f"intent={plan.research_intent.value}"
                )
                return plan

            except Exception as e:
                last_error = str(e)
                if attempt == 0:
                    logger.warning(f"[Planner] First attempt failed: {e}. Retrying with repair prompt…")
                else:
                    logger.error(f"[Planner] Both attempts failed: {e}")
                    raise


planner = PlannerAgent()
