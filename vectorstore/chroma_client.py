"""
vectorstore/chroma_client.py
----------------------------
Chroma persistent client singleton + collection bootstrap.

Collections:
  - tavily_news    : news articles from Tavily, chunked + indexed
  - tavily_weather : weather data per city, tagged with city_tag metadata
"""

from __future__ import annotations

import chromadb
from chromadb import Collection

from config.settings import CHROMA_DB_PATH
from vectorstore.embedder import get_embedder

_client: chromadb.PersistentClient | None = None


def get_chroma_client() -> chromadb.PersistentClient:
    global _client
    if _client is None:
        _client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
        _ensure_collections(_client)
    return _client


def _ensure_collections(client: chromadb.PersistentClient) -> None:
    """Create NEXUS collections if they don't already exist."""
    ef = get_embedder()

    client.get_or_create_collection(
        name="tavily_news",
        embedding_function=ef,
        metadata={"hnsw:space": "cosine"},
    )
    client.get_or_create_collection(
        name="tavily_weather",
        embedding_function=ef,
        metadata={"hnsw:space": "cosine"},
    )
    client.get_or_create_collection(
        name="rag_documents",
        embedding_function=ef,
        metadata={"hnsw:space": "cosine"},
    )


def get_collection(name: str) -> Collection:
    client = get_chroma_client()
    ef = get_embedder()
    return client.get_or_create_collection(
        name=name,
        embedding_function=ef,
        metadata={"hnsw:space": "cosine"},
    )
