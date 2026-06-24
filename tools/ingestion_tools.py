"""
tools/ingestion_tools.py
------------------------
@function_tool wrappers for the NEXUS data ingestion pipeline.
Chunks, embeds, and upserts content into Chroma.
"""

from __future__ import annotations

import json
import time
import uuid

from agents import RunContextWrapper, function_tool

from config.settings import (
    CHUNK_SIZE,
    CHUNK_OVERLAP,
    CITIES,
    NEWS_MAX_RESULTS,
    TAVILY_API_KEY,
)
from vectorstore.chroma_client import get_collection


def _chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Fixed-size character chunking with overlap."""
    text = text.strip()
    if not text:
        return []
    chunks = []
    step = max(1, chunk_size - overlap)
    for i in range(0, len(text), step):
        chunk = text[i : i + chunk_size].strip()
        if chunk:
            chunks.append(chunk)
    return chunks


@function_tool
async def ingest_tavily_news(
    ctx: RunContextWrapper,
    max_results: int = 10,
) -> str:
    """
    Fetch recent news from Tavily, chunk the content, and upsert into Chroma
    'tavily_news' collection.

    Args:
        max_results: Number of news articles to fetch (default 10).

    Returns:
        JSON summary: {"articles_processed": N, "chunks_created": M, "source": "..."}
    """
    if not TAVILY_API_KEY:
        # Ingest synthetic news for demo
        return await _ingest_synthetic_news()

    try:
        from tavily import TavilyClient
        client = TavilyClient(api_key=TAVILY_API_KEY)
        results = client.search(
            query="latest news today technology business",
            topic="news",
            max_results=min(max_results, 20),
            search_depth="basic",
        )
        articles = results.get("results", [])
    except Exception as exc:
        return json.dumps({"error": str(exc), "articles_processed": 0})

    col = get_collection("tavily_news")
    now = time.time()
    total_chunks = 0

    for article in articles:
        content = article.get("content") or article.get("snippet", "")
        if not content:
            continue
        chunks = _chunk_text(content)
        url = article.get("url", "unknown")
        title = article.get("title", "")

        col.add(
            documents=chunks,
            metadatas=[
                {
                    "source_url": url,
                    "title": title,
                    "fetched_at": now,
                    "topic": "news",
                    "content_type": "news",
                }
                for _ in chunks
            ],
            ids=[f"news_{uuid.uuid4().hex[:8]}_{i}" for i in range(len(chunks))],
        )
        total_chunks += len(chunks)

    return json.dumps({
        "articles_processed": len(articles),
        "chunks_created": total_chunks,
        "source": "tavily",
    })


@function_tool
async def ingest_weather_for_cities(
    ctx: RunContextWrapper,
    cities: list[str] | None = None,
) -> str:
    """
    Fetch current weather for a list of cities and upsert into Chroma
    'tavily_weather' collection with city_tag metadata.

    Args:
        cities: Optional list of city names. Defaults to all 10 NEXUS cities.
                City names must match employee office_location values exactly.

    Returns:
        JSON summary per city: {"city": ..., "chunks": N, ...}
    """
    target_cities = cities or CITIES
    results_summary = []

    for city in target_cities:
        try:
            from tools.tavily_tools import _upsert_weather, _synthetic_weather
            if TAVILY_API_KEY:
                from tavily import TavilyClient
                client = TavilyClient(api_key=TAVILY_API_KEY)
                resp = client.search(
                    query=f"current weather {city}",
                    topic="general",
                    max_results=3,
                    search_depth="basic",
                )
                snippets = [r.get("content", "") for r in resp.get("results", []) if r.get("content")]
            else:
                snippets = _synthetic_weather(city)

            _upsert_weather(city, snippets)
            results_summary.append({"city": city, "chunks": len(snippets), "status": "ok"})
        except Exception as exc:
            results_summary.append({"city": city, "chunks": 0, "status": str(exc)})

    return json.dumps({
        "cities_processed": len(target_cities),
        "results": results_summary,
    })


async def _ingest_synthetic_news() -> str:
    """Ingest synthetic news articles for demo mode (no Tavily key)."""
    synthetic_articles = [
        {
            "title": "Tech Giants Report Strong Q2 Earnings",
            "content": "Major technology companies reported strong second-quarter earnings, "
                       "beating analyst expectations. Cloud computing and AI services drove "
                       "significant revenue growth across the sector.",
            "url": "https://example.com/tech-earnings",
        },
        {
            "title": "Federal Reserve Signals Rate Decision",
            "content": "The Federal Reserve indicated it may hold interest rates steady at its "
                       "next meeting, citing mixed economic signals. Inflation has moderated but "
                       "remains above the 2% target.",
            "url": "https://example.com/fed-rates",
        },
        {
            "title": "Remote Work Trends Reshape Office Markets",
            "content": "Commercial real estate markets continue to adjust as hybrid and remote "
                       "work arrangements become permanent fixtures. Office vacancy rates in major "
                       "cities remain elevated compared to pre-pandemic levels.",
            "url": "https://example.com/remote-work",
        },
        {
            "title": "AI Adoption Accelerates Across Industries",
            "content": "Companies across healthcare, finance, and manufacturing are rapidly "
                       "deploying AI tools to automate workflows. Productivity gains are measurable "
                       "but workforce displacement concerns persist.",
            "url": "https://example.com/ai-adoption",
        },
        {
            "title": "Supply Chain Resilience Investments Rise",
            "content": "Corporations are investing heavily in supply chain diversification "
                       "following disruptions from the past several years. Nearshoring and "
                       "domestic sourcing are growing trends.",
            "url": "https://example.com/supply-chain",
        },
    ]

    col = get_collection("tavily_news")
    now = time.time()
    total_chunks = 0

    for article in synthetic_articles:
        chunks = _chunk_text(article["content"])
        col.add(
            documents=chunks,
            metadatas=[
                {
                    "source_url": article["url"],
                    "title": article["title"],
                    "fetched_at": now,
                    "topic": "news",
                    "content_type": "news",
                }
                for _ in chunks
            ],
            ids=[f"news_{uuid.uuid4().hex[:8]}_{i}" for i in range(len(chunks))],
        )
        total_chunks += len(chunks)

    return json.dumps({
        "articles_processed": len(synthetic_articles),
        "chunks_created": total_chunks,
        "source": "synthetic (no TAVILY_API_KEY)",
    })
