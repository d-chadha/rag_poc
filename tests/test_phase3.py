"""Phase 3 smoke test — schema wiring, no LLM API calls."""
import sys
sys.path.insert(0, ".")

import startup  # noqa: F401 — must be first for correct DLL order


def test_safety_output_schema():
    from nexus_agents.critics.safety_critic import SafetyCheckOutput
    safe = SafetyCheckOutput(is_safe=True, is_in_scope=True, reason="OK")
    blocked = SafetyCheckOutput(is_safe=False, is_in_scope=True, reason="Injection attempt")
    assert safe.is_safe
    assert not blocked.is_safe
    print("[SafetyCheckOutput] schema OK")


def test_synthesis_output_schema():
    from nexus_agents.critics.groundedness_critic import SynthesisOutput, GroundednessCheckOutput
    out = SynthesisOutput(
        answer="Raghav works in Engineering in Austin.",
        sources_used=["emp_row_412", "weather_chunk_austin_001"],
        claims=["Raghav works in Engineering", "Raghav's office is Austin"],
    )
    assert len(out.claims) == 2
    assert "emp_row_412" in out.sources_used
    print("[SynthesisOutput] schema OK")

    gco = GroundednessCheckOutput(
        is_grounded=True,
        ungrounded_claims=[],
        revision_notes="All claims verified.",
    )
    assert gco.is_grounded
    print("[GroundednessCheckOutput] schema OK")


def test_agent_wiring():
    from nexus_agents.synthesis_agent import answer_synthesis_agent
    from nexus_agents.critics.groundedness_critic import groundedness_guardrail, SynthesisOutput
    from nexus_agents.critics.safety_critic import safety_guardrail

    assert answer_synthesis_agent.output_type is SynthesisOutput
    assert len(answer_synthesis_agent.output_guardrails) == 1
    assert answer_synthesis_agent.hooks is not None

    # Verify guardrail decorator metadata
    assert safety_guardrail.name == "nexus_safety_guardrail"
    print("[Agent wiring] synthesis agent correctly wired with guardrails and hooks")


def test_all_agents_coexist():
    """Verify all 6 functional components import together without conflict."""
    from nexus_agents.sql_agent import sql_agent, sql_tool
    from nexus_agents.rag_retriever_agent import rag_retriever_agent, rag_retriever_tool
    from nexus_agents.weather_fusion_agent import weather_fusion_agent, weather_fusion_tool
    from nexus_agents.ingestion_agent import ingestion_agent, ingestion_tool
    from nexus_agents.critics.safety_critic import safety_guardrail
    from nexus_agents.synthesis_agent import answer_synthesis_agent

    agents = [sql_agent, rag_retriever_agent, weather_fusion_agent,
              ingestion_agent, answer_synthesis_agent]
    names = [a.name for a in agents]
    assert len(set(names)) == 5, f"Duplicate agent names: {names}"
    print(f"[All agents] coexist OK: {names}")

    tools = [sql_tool, rag_retriever_tool, weather_fusion_tool, ingestion_tool]
    assert all(t is not None for t in tools)
    print("[All tools] as_tool wrappers OK")


if __name__ == "__main__":
    print("=" * 50)
    print("NEXUS Phase 3 Smoke Test")
    print("=" * 50)
    test_safety_output_schema()
    test_synthesis_output_schema()
    test_agent_wiring()
    test_all_agents_coexist()
    print("=" * 50)
    print("ALL PHASE 3 TESTS PASSED")
    print("=" * 50)
