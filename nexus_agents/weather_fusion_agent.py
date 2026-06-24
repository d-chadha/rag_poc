"""
nexus_agents/weather_fusion_agent.py
-------------------------------------
WeatherFusionAgent — Chroma cache + Tavily live refresh for city weather.
Bridges the structured SQL world (office_location) to unstructured Chroma data.
Exposed as a tool to NEXUSOrchestrator via .as_tool().
"""

from __future__ import annotations

import json
import time

from agents import Agent, RunContextWrapper, function_tool
from agents.extensions.models.litellm_model import LitellmModel

from config.settings import CLAUDE_HAIKU_MODEL, WEATHER_STALENESS_SECONDS
from vectorstore.chroma_client import get_collection


@function_tool
async def get_weather_for_location(
    ctx: RunContextWrapper,
    office_location: str,
) -> str:
    """
    Retrieve current weather for a given office_location city.

    Checks the Chroma 'tavily_weather' cache first. If data is older than
    WEATHER_STALENESS_SECONDS (default 1 hour), triggers a live Tavily refresh.
    If no data exists, fetches immediately.

    Args:
        office_location: City name exactly as stored in the employees table.
                         e.g. "Austin", "Seattle", "New York"

    Returns:
        JSON string with weather summary, source, and fetched_at timestamp.
    """
    col = get_collection("tavily_weather")

    results = col.query(
        query_texts=[f"weather {office_location}"],
        n_results=3,
        where={"city_tag": office_location},
        include=["documents", "metadatas"],
    )

    # Check if we have fresh data
    if results["ids"][0]:
        fetched_at = results["metadatas"][0][0].get("fetched_at", 0)
        age_seconds = time.time() - float(fetched_at)

        if age_seconds <= WEATHER_STALENESS_SECONDS:
            # Cache hit — return existing data
            docs = results["documents"][0]
            return json.dumps({
                "city": office_location,
                "weather": docs,
                "source": "chroma_cache",
                "fetched_at": fetched_at,
                "age_seconds": int(age_seconds),
            })

    # Cache miss or stale — refresh from Tavily
    from tools.tavily_tools import _upsert_weather, _synthetic_weather
    from config.settings import TAVILY_API_KEY

    if TAVILY_API_KEY:
        try:
            from tavily import TavilyClient
            client = TavilyClient(api_key=TAVILY_API_KEY)
            resp = client.search(
                query=f"current weather {office_location}",
                topic="general",
                max_results=3,
                search_depth="basic",
            )
            snippets = [r.get("content", "") for r in resp.get("results", []) if r.get("content")]
            source = "tavily_live"
        except Exception:
            snippets = _synthetic_weather(office_location)
            source = "synthetic_fallback"
    else:
        snippets = _synthetic_weather(office_location)
        source = "synthetic"

    _upsert_weather(office_location, snippets)

    return json.dumps({
        "city": office_location,
        "weather": snippets,
        "source": source,
        "fetched_at": time.time(),
        "age_seconds": 0,
    })


WEATHER_AGENT_INSTRUCTIONS = """
You are the WeatherFusionAgent for NEXUS.

You receive an office_location (city name from the employees SQL table) and
retrieve current weather for that city.

The city_tag in Chroma weather chunks EXACTLY matches employee office_location values.
This is the SEMANTIC BRIDGE between structured SQL data and unstructured Chroma data.

RULES:
1. Use get_weather_for_location with the exact office_location value from SQL results.
2. The tool auto-refreshes stale data — you do not need to worry about cache management.
3. Return the weather summary clearly, including the data source and freshness.
4. If the city is unknown, say so rather than guessing.

OFFICE LOCATIONS (exact match required):
  Austin, Seattle, New York, San Francisco, Chicago,
  Boston, Denver, Atlanta, Miami, Portland
"""

weather_fusion_agent = Agent(
    name="WeatherFusionAgent",
    instructions=WEATHER_AGENT_INSTRUCTIONS,
    model=LitellmModel(model=CLAUDE_HAIKU_MODEL),
    tools=[get_weather_for_location],
)

# Expose as a tool callable by NEXUSOrchestrator
weather_fusion_tool = weather_fusion_agent.as_tool(
    tool_name="get_weather_for_employee_location",
    tool_description=(
        "Given an office_location city name (from employee data), retrieves current weather. "
        "Handles Chroma cache checking + Tavily live refresh automatically. "
        "Use AFTER querying the employee database to get office_location."
    ),
)
