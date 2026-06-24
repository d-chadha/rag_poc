"""
nexus_agents/synthesis_agent.py
---------------------------------
AnswerSynthesisAgent — final answer composer with:
  - Pydantic structured output (SynthesisOutput)
  - @output_guardrail (GroundednessCritic) wired in
  - AgentHooks for per-attempt timing and logging
"""

from __future__ import annotations

import logging
import time

from agents import Agent, AgentHooks, RunContextWrapper
from agents.extensions.models.litellm_model import LitellmModel

from config.settings import CLAUDE_SONNET_MODEL
from nexus_agents.critics.groundedness_critic import (
    SynthesisOutput,
    groundedness_guardrail,
)

logger = logging.getLogger("nexus.synthesis")


class SynthesisHooks(AgentHooks):
    """Scoped hooks — fire only for AnswerSynthesisAgent turns."""

    async def on_start(self, ctx: RunContextWrapper, agent: Agent) -> None:
        attempt = ctx.context.get("synthesis_attempt", 0) + 1
        ctx.context["synthesis_attempt"] = attempt
        ctx.context["synthesis_start_ts"] = time.time()
        logger.info("[Synthesis] attempt #%d started", attempt)

    async def on_end(self, ctx: RunContextWrapper, agent: Agent, output: object) -> None:
        elapsed = time.time() - ctx.context.get("synthesis_start_ts", time.time())
        attempt = ctx.context.get("synthesis_attempt", 1)
        logger.info(
            "[Synthesis] attempt #%d complete in %.2fs",
            attempt,
            elapsed,
        )
        ctx.context["synthesis_elapsed_s"] = round(elapsed, 2)


SYNTHESIS_INSTRUCTIONS = """
You are the AnswerSynthesisAgent for NEXUS — the final answer composer.

You receive a context bundle containing structured data gathered by other agents:
  - SQL employee rows (name, age, department, office_location)
  - RAG knowledge chunks (news articles, weather data, document excerpts)
  - The original user question

YOUR RULES (NON-NEGOTIABLE):
1. GROUND EVERY FACTUAL CLAIM in the provided context.
   - Each claim in your answer must cite its source.
   - Never infer, extrapolate, or introduce facts not in the context.
2. Use "Not available in current data." when a fact is missing — never guess.
3. FORMAT: conversational prose followed by a "Sources:" section listing
   chunk IDs, SQL row refs, or URLs for every fact cited.
4. CLAIMS list: after your answer, enumerate each discrete factual claim
   you made (1 claim per bullet). This list is checked by the groundedness
   validator — be precise.
5. SOURCES list: list every source you drew from (chunk ID, emp_row_N, URL).
6. If you receive revision_notes from a prior groundedness check, address
   EVERY note explicitly before re-attempting your answer.
7. Keep your answer concise and direct — no padding or filler.

RESPONSE FORMAT (SynthesisOutput):
  answer:       full prose answer with inline source references
  sources_used: ["emp_row_412", "weather_chunk_austin_001", "https://..."]
  claims:       ["Raghav works in Engineering", "office is Austin", ...]
"""

answer_synthesis_agent = Agent(
    name="AnswerSynthesisAgent",
    instructions=SYNTHESIS_INSTRUCTIONS,
    model=LitellmModel(model=CLAUDE_SONNET_MODEL),
    output_type=SynthesisOutput,
    output_guardrails=[groundedness_guardrail],
    hooks=SynthesisHooks(),
)
