"""
nexus_agents/ingestion_agent.py
--------------------------------
IngestionAgent — Tavily fetch + chunk + embed + Chroma upsert pipeline.
Can be triggered on-demand from the orchestrator for data refresh.
Exposed as a tool to NEXUSOrchestrator via .as_tool().
"""

from __future__ import annotations

from agents import Agent
from agents.extensions.models.litellm_model import LitellmModel

from tools.ingestion_tools import ingest_tavily_news, ingest_weather_for_cities
from config.settings import CLAUDE_HAIKU_MODEL


INGESTION_AGENT_INSTRUCTIONS = """
You are the IngestionAgent for NEXUS — the data pipeline manager.

You populate the Chroma vector store with fresh data from Tavily.

CRITICAL METADATA RULES:
- Weather chunks MUST be tagged with:
    city_tag: exact city name matching employees.office_location
    fetched_at: Unix timestamp of fetch
    content_type: "weather"
- News chunks MUST be tagged with:
    source_url: article URL
    fetched_at: Unix timestamp
    content_type: "news"
    topic: "news"

This metadata is the semantic bridge between SQL (employee.office_location)
and Chroma (city_tag). Without it, weather lookups will fail.

TOOLS AVAILABLE:
- ingest_tavily_news(max_results): Fetch and index latest news articles.
- ingest_weather_for_cities(cities): Fetch and index weather for a city list.
  If cities is None, all 10 NEXUS cities are refreshed.

Report a clear summary of what was ingested including article/chunk counts.
"""

ingestion_agent = Agent(
    name="IngestionAgent",
    instructions=INGESTION_AGENT_INSTRUCTIONS,
    model=LitellmModel(model=CLAUDE_HAIKU_MODEL),
    tools=[ingest_tavily_news, ingest_weather_for_cities],
)

# Expose as a tool callable by NEXUSOrchestrator
ingestion_tool = ingestion_agent.as_tool(
    tool_name="refresh_knowledge_base",
    tool_description=(
        "Triggers Tavily data fetch and Chroma ingestion for news or weather. "
        "Use when the user requests fresh data, or when weather/news collections are empty."
    ),
)
