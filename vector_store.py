"""
vector_store.py
---------------
Thin wrapper around ChromaDB for storing and retrieving document chunks.

Uses ChromaDB's default embedding function for compatibility and performance.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import List, Optional

import chromadb

from document_processor import DocumentChunk


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

COLLECTION_NAME = "rag_documents"
PERSIST_DIR      = "./chroma_db"


# ---------------------------------------------------------------------------
# VectorStore
# ---------------------------------------------------------------------------

class VectorStore:
    """Manages a persistent ChromaDB collection."""

    def __init__(
        self,
        persist_directory: str = PERSIST_DIR,
        collection_name: str = COLLECTION_NAME,
    ) -> None:
        self._client = chromadb.PersistentClient(path=persist_directory)
        # Use ChromaDB's default embedding function (no external dependencies)
        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def add_chunks(self, chunks: List[DocumentChunk]) -> int:
        """
        Embed and store *chunks*.  Returns the number of new chunks added
        (duplicates, identified by a content hash, are silently skipped).
        """
        if not chunks:
            return 0

        ids       = [self._chunk_id(c) for c in chunks]
        documents = [c.text for c in chunks]
        metadatas = [c.metadata for c in chunks]

        # Deduplicate against what is already stored
        existing = set(self._collection.get(ids=ids)["ids"])
        new_mask = [i for i, cid in enumerate(ids) if cid not in existing]
        if not new_mask:
            return 0

        self._collection.add(
            ids       =[ids[i]       for i in new_mask],
            documents =[documents[i] for i in new_mask],
            metadatas =[metadatas[i] for i in new_mask],
        )
        return len(new_mask)

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def query(
        self,
        query_text: str,
        n_results: int = 5,
        where: Optional[dict] = None,
    ) -> List[dict]:
        """
        Return the *n_results* most similar chunks to *query_text*.

        Each result dict contains:
          - ``text``      : chunk text
          - ``metadata``  : source filename, chunk_index, etc.
          - ``distance``  : cosine distance (lower = more similar)
        """
        if self._collection.count() == 0:
            return []

        kwargs: dict = {
            "query_texts": [query_text],
            "n_results":   min(n_results, self._collection.count()),
            "include":     ["documents", "metadatas", "distances"],
        }
        if where:
            kwargs["where"] = where

        results = self._collection.query(**kwargs)

        output = []
        for doc, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            output.append({"text": doc, "metadata": meta, "distance": dist})
        return output

    # ------------------------------------------------------------------
    # Management
    # ------------------------------------------------------------------

    def list_sources(self) -> List[str]:
        """Return a sorted list of unique source filenames in the store."""
        if self._collection.count() == 0:
            return []
        all_meta = self._collection.get(include=["metadatas"])["metadatas"]
        return sorted({m.get("source", "unknown") for m in all_meta})

    def delete_source(self, filename: str) -> int:
        """Delete all chunks whose ``source`` metadata matches *filename*."""
        results = self._collection.get(
            where={"source": filename},
            include=["metadatas"],
        )
        ids_to_delete = results["ids"]
        if ids_to_delete:
            self._collection.delete(ids=ids_to_delete)
        return len(ids_to_delete)

    def clear(self) -> None:
        """Delete the entire collection and re-create it."""
        self._client.delete_collection(COLLECTION_NAME)
        self._collection = self._client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )

    @property
    def count(self) -> int:
        return self._collection.count()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _chunk_id(chunk: DocumentChunk) -> str:
        """Deterministic ID based on content hash so dedup works reliably."""
        digest = hashlib.md5(chunk.text.encode()).hexdigest()
        source = chunk.metadata.get("source", "unknown")
        idx    = chunk.metadata.get("chunk_index", 0)
        return f"{source}_{idx}_{digest[:8]}"
