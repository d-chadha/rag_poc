"""
nexus_agents/critics/groundedness_critic.py
---------------------------------------------
GroundednessCritic — @output_guardrail on AnswerSynthesisAgent.

Verifies every factual claim in the draft answer is traceable to a source
chunk or SQL row. Ungrounded answers trigger a revision cycle (up to 2x),
then escalate to HITL.
"""

from __future__ import annotations

from pydantic import BaseModel

from agents import (
    Agent,
    GuardrailFunctionOutput,
    RunContextWrapper,
    Runner,
    output_guardrail,
)
from agents.extensions.models.litellm_model import LitellmModel
from config.settings import CLAUDE_SONNET_MODEL


class GroundednessCheckOutput(BaseModel):
    is_grounded:       bool
    ungrounded_claims: list[str]   # claims not traceable to provided sources
    revision_notes:    str         # instructions for AnswerSynthesisAgent on retry


class SynthesisOutput(BaseModel):
    answer:       str
    sources_used: list[str]   # chunk IDs, SQL row refs, or source URLs
    claims:       list[str]   # discrete factual claims in the answer


_groundedness_agent = Agent(
    name="GroundednessCheckAgent",
    instructions="""
You are a strict groundedness validator for NEXUS.

You receive a draft answer with its factual claims and the source chunks/rows used.

YOUR JOB: For EACH claim, verify — is it DIRECTLY supported by one of the sources?

RULES:
1. A claim is GROUNDED only if it can be traced word-for-word or by clear
   logical inference to one of the provided sources.
2. A claim is UNGROUNDED if it introduces ANY fact not present in the sources,
   even if that fact seems plausible or likely.
3. Set is_grounded=False if ANY single claim is ungrounded.
4. List all ungrounded claims explicitly in ungrounded_claims.
5. In revision_notes, give AnswerSynthesisAgent precise instructions:
   - Which claims to remove or soften ("say 'not available' instead of...")
   - How to rephrase to stay grounded
   - What sources are missing and what to say when a source is absent
6. Be STRICT — this is a fact-checked system. Err on the side of caution.
7. Templated/formulaic language ("I cannot answer...") is fine — penalize
   only factual claims that exceed the provided evidence.
""",
    model=LitellmModel(model=CLAUDE_SONNET_MODEL),
    output_type=GroundednessCheckOutput,
)


@output_guardrail
async def groundedness_guardrail(
    ctx: RunContextWrapper,
    agent: Agent,
    output: SynthesisOutput,
) -> GuardrailFunctionOutput:
    """
    Output guardrail — runs after AnswerSynthesisAgent produces a draft.
    Verifies all claims in output.claims against output.sources_used.
    Raises OutputGuardrailTripwireTriggered if any claim is ungrounded.
    """
    prompt = (
        f"DRAFT ANSWER:\n{output.answer}\n\n"
        f"CLAIMS TO CHECK:\n" + "\n".join(f"- {c}" for c in output.claims) +
        f"\n\nSOURCES PROVIDED:\n" + "\n".join(f"- {s}" for s in output.sources_used)
    )

    result = await Runner.run(
        _groundedness_agent,
        prompt,
        context=ctx.context,
    )
    check = result.final_output_as(GroundednessCheckOutput)

    return GuardrailFunctionOutput(
        output_info=check,
        tripwire_triggered=not check.is_grounded,
    )
