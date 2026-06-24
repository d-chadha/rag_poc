"""
tools/tavily_tools.py
---------------------
Tavily API wrappers — news search and weather fetch.
Falls back gracefully if TAVILY_API_KEY is not set.
"""

from __future__ import annotations

import json
import time

from agents import RunContextWrapper, function_tool

from config.settings import TAVILY_API_KEY


def _get_tavily_client():
    if not TAVILY_API_KEY:
        return None
    from tavily import TavilyClient
    return TavilyClient(api_key=TAVILY_API_KEY)


@function_tool
async def fetch_latest_news(
    ctx: RunContextWrapper,
    max_results: int = 10,
) -> str:
    """
    Fetch recent news articles from Tavily.

    Args:
        max_results: Number of articles to retrieve (1-20, default 10).

    Returns:
        JSON string with list of articles including title, url, content, score.
    """
    client = _get_tavily_client()
    if client is None:
        return json.dumps({
            "error": "TAVILY_API_KEY not configured. Set it in .env to enable live news.",
            "articles": [],
        })

    try:
        results = client.search(
            query="latest news today",
            topic="news",
            max_results=min(max_results, 20),
            search_depth="basic",
        )
        articles = results.get("results", [])
        return json.dumps({
            "articles": articles,
            "count": len(articles),
            "fetched_at": time.time(),
        })
    except Exception as exc:
        return json.dumps({"error": str(exc), "articles": []})


@function_tool
async def fetch_weather_for_city(
    ctx: RunContextWrapper,
    city: str,
) -> str:
    """
    Fetch current weather for *city* from Tavily and upsert into Chroma
    'tavily_weather' collection with city_tag metadata.

    Args:
        city: City name — must exactly match an employee office_location value.

    Returns:
        JSON string with weather snippets and ingestion summary.
    """
    client = _get_tavily_client()
    if client is None:
        # Return synthetic weather so demo works without a Tavily key
        synthetic = _synthetic_weather(city)
        _upsert_weather(city, synthetic)
        return json.dumps({
            "city": city,
            "source": "synthetic (no TAVILY_API_KEY)",
            "snippets": synthetic,
            "count": len(synthetic),
        })

    try:
        results = client.search(
            query=f"current weather {city}",
            topic="general",
            max_results=3,
            search_depth="basic",
        )
        snippets = [r.get("content", "") for r in results.get("results", []) if r.get("content")]
        _upsert_weather(city, snippets)
        return json.dumps({
            "city": city,
            "source": "tavily",
            "snippets": snippets,
            "count": len(snippets),
        })
    except Exception as exc:
        return json.dumps({"error": str(exc), "city": city})


def _upsert_weather(city: str, snippets: list[str]) -> None:
    """Upsert weather snippets into Chroma with city_tag metadata."""
    from vectorstore.chroma_client import get_collection
    col = get_collection("tavily_weather")
    now = time.time()

    # Delete stale entries for this city first
    try:
        existing = col.get(where={"city_tag": city}, include=["metadatas"])
        if existing["ids"]:
            col.delete(ids=existing["ids"])
    except Exception:
        pass

    if not snippets:
        return

    col.add(
        documents=snippets,
        metadatas=[
            {
                "city_tag": city,
                "fetched_at": now,
                "content_type": "weather",
            }
            for _ in snippets
        ],
        ids=[f"weather_{city.replace(' ', '_')}_{i}_{int(now)}" for i in range(len(snippets))],
    )


def _synthetic_weather(city: str) -> list[str]:
    """
    Return plausible-looking synthetic weather when Tavily key is absent.
    Keeps the demo runnable end-to-end without an API subscription.
    """
    weather_map = {
        "Austin":        "Austin TX: 92°F, sunny with light wind. Humidity 38%.",
        "Seattle":       "Seattle WA: 58°F, overcast with light drizzle. Humidity 82%.",
        "New York":      "New York NY: 74°F, partly cloudy, mild breeze.",
        "San Francisco": "San Francisco CA: 63°F, foggy morning, clearing afternoon.",
        "Chicago":       "Chicago IL: 68°F, mostly sunny, gusty winds 20mph.",
        "Boston":        "Boston MA: 71°F, clear skies, pleasantly warm.",
        "Denver":        "Denver CO: 85°F, sunny, low humidity 25%.",
        "Atlanta":       "Atlanta GA: 88°F, humid, chance of afternoon thunderstorms.",
        "Miami":         "Miami FL: 91°F, partly cloudy, high humidity 75%.",
        "Portland":      "Portland OR: 61°F, light clouds, mild and comfortable.",
    }
    base = weather_map.get(city, f"{city}: 72°F, clear skies.")
    return [base, f"Extended forecast for {city}: similar conditions for the next 3 days."]
