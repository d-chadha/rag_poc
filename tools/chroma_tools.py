"""
tools/chroma_tools.py
---------------------
@function_tool wrappers for Chroma vector search.
Supports metadata filtering (city_tag for weather, content_type for news).
"""

from __future__ import annotations

import json

from agents import RunContextWrapper, function_tool

from vectorstore.chroma_client import get_collection


@function_tool
async def query_chroma(
    ctx: RunContextWrapper,
    query: str,
    collection_name: str,
    n_results: int = 5,
    city_tag: str | None = None,
) -> str:
    """
    Query a Chroma vector collection for semantically relevant chunks.

    Args:
        query:           Semantic search query string.
        collection_name: One of 'tavily_news', 'tavily_weather', 'rag_documents'.
        n_results:       How many top chunks to return (default 5).
        city_tag:        Optional — filter weather chunks to this exact city name.
                         Must match an employee office_location value exactly.

    Returns:
        JSON string with matching chunks, their source metadata, and similarity
        scores. Format: {"chunks": [...], "collection": "...", "count": N}
    """
    try:
        col = get_collection(collection_name)
        total = col.count()
        if total == 0:
            return json.dumps({
                "chunks": [],
                "collection": collection_name,
                "count": 0,
                "note": "Collection is empty — run data ingestion first.",
            })

        kwargs: dict = {
            "query_texts": [query],
            "n_results": min(n_results, total),
            "include": ["documents", "metadatas", "distances"],
        }
        # Chroma 1.5 equality filter — direct field:value (no $eq wrapper)
        if city_tag:
            kwargs["where"] = {"city_tag": city_tag}

        results = col.query(**kwargs)

        chunks = []
        for doc, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            chunks.append({
                "text": doc,
                "metadata": meta,
                "similarity": round(1 - dist, 4),
            })

        return json.dumps({
            "chunks": chunks,
            "collection": collection_name,
            "count": len(chunks),
        })

    except Exception as exc:
        return json.dumps({"error": str(exc), "collection": collection_name})
