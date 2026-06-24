"""
nexus_agents/orchestrator.py
-----------------------------
NEXUSOrchestrator — the hub agent.

Routing logic:
  - Employee-only query       → sql_tool
  - News / document query     → rag_retriever_tool
  - Employee + weather        → sql_tool → weather_fusion_tool → handoff synthesis
  - Multi-source / complex    → handoff to AnswerSynthesisAgent
  - Data refresh request      → ingestion_tool
"""

from __future__ import annotations

import logging

from agents import Agent, handoff
from agents.extensions.handoff_filters import remove_all_tools
from agents.extensions.models.litellm_model import LitellmModel

from config.settings import CLAUDE_SONNET_MODEL
from nexus_agents.ingestion_agent import ingestion_tool
from nexus_agents.rag_retriever_agent import rag_retriever_tool
from nexus_agents.sql_agent import sql_tool
from nexus_agents.synthesis_agent import answer_synthesis_agent
from nexus_agents.weather_fusion_agent import weather_fusion_tool
from nexus_agents.critics.safety_critic import safety_guardrail

logger = logging.getLogger("nexus.orchestrator")

ORCHESTRATOR_INSTRUCTIONS = """
You are NEXUS — the Neural EXchange for Unified Structured/Unstructured Intelligence.
You are the conversational interface between users and multiple data sources.

DATA SOURCES:
  1. STRUCTURED:   Employee database (SQL) — name, age, department, office_location
  2. UNSTRUCTURED: Tavily-ingested knowledge (Chroma) — news, weather per city
  3. DOCUMENTS:    User-uploaded files (Chroma rag_documents collection)

ROUTING RULES — follow strictly in order:

  A. Employee-only question (name, age, dept, location, counts, averages)
     → Call query_employee_database tool
     → Return result directly (no handoff needed for simple lookups)

  B. News or document question
     → Call retrieve_from_knowledge_base tool
     → Return result directly

  C. Employee + weather question ("where does X work and what's the weather?")
     → Call query_employee_database FIRST to get office_location
     → Extract office_location from the SQL result
     → Call get_weather_for_employee_location with that office_location
     → Then handoff_to_answer_synthesizer with both results as context

  D. Multi-source or complex reasoning needed
     → Gather data with tools first
     → Then handoff_to_answer_synthesizer

  E. Data refresh / "refresh news / weather"
     → Call refresh_knowledge_base tool

  F. General conversation, greeting, or meta-question about NEXUS
     → Answer directly from your instructions (no tools needed)

NEVER fabricate data. If a tool returns empty results, say so honestly.
NEVER hallucinate employee names, departments, or weather conditions.
Always tell the user what data source answered their question.
"""


def _on_handoff_to_synthesis(ctx) -> None:
    logger.info("[NEXUS] Handoff → AnswerSynthesisAgent")


nexus_orchestrator = Agent(
    name="NEXUSOrchestrator",
    instructions=ORCHESTRATOR_INSTRUCTIONS,
    model=LitellmModel(model=CLAUDE_SONNET_MODEL),
    tools=[
        sql_tool,
        rag_retriever_tool,
        weather_fusion_tool,
        ingestion_tool,
    ],
    handoffs=[
        handoff(
            agent=answer_synthesis_agent,
            tool_name_override="handoff_to_answer_synthesizer",
            input_filter=remove_all_tools,
            on_handoff=_on_handoff_to_synthesis,
        ),
    ],
    input_guardrails=[safety_guardrail],
)
