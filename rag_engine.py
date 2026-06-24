"""
rag_engine.py
-------------
Retrieval-Augmented Generation engine that:
  1. Retrieves the top-k chunks from ChromaDB
  2. Builds a prompt with those chunks as context
  3. Streams the answer from Claude claude-opus-4-8 with prompt caching

Uses adaptive thinking for complex questions and prompt caching to keep
repeated context cheap.
"""

from __future__ import annotations

from typing import Generator, List

import anthropic

from vector_store import VectorStore


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CLAUDE_MODEL   = "claude-opus-4-8"
MAX_TOKENS     = 2048
TOP_K_CHUNKS   = 5
MAX_HISTORY    = 10          # max conversation turns kept in context


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are a knowledgeable assistant that answers questions \
based on the provided document context.

Guidelines:
- Base your answers primarily on the provided context chunks.
- If the context does not contain enough information to answer confidently, \
say so clearly instead of fabricating details.
- When quoting or closely paraphrasing the source material, mention the \
source filename.
- Be concise and precise. Use bullet points or numbered lists when helpful.
- For follow-up questions, consider the full conversation history."""


# ---------------------------------------------------------------------------
# RAGEngine
# ---------------------------------------------------------------------------

class RAGEngine:
    """Orchestrates retrieval + Claude generation."""

    def __init__(self, vector_store: VectorStore) -> None:
        self._store  = vector_store
        self._client = anthropic.Anthropic()

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def stream_answer(
        self,
        question: str,
        history: List[dict],          # list of {"role": ..., "content": ...}
        n_results: int = TOP_K_CHUNKS,
    ) -> Generator[str, None, None]:
        """
        Retrieve context and stream Claude's answer token-by-token.

        Yields str tokens that the caller can write directly to the UI.
        """
        # 1. Retrieve relevant chunks
        chunks = self._store.query(question, n_results=n_results)

        # 2. Build context block
        context_block = self._format_context(chunks)

        # 3. Build messages list (history + current question)
        messages = self._build_messages(history, question, context_block)

        # 4. Stream from Claude
        with self._client.messages.stream(
            model      = CLAUDE_MODEL,
            max_tokens = MAX_TOKENS,
            system     = [
                {
                    "type":          "text",
                    "text":          SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},   # cache stable system prompt
                }
            ],
            thinking   = {"type": "adaptive"},               # let Claude decide when to think
            messages   = messages,
        ) as stream:
            for text in stream.text_stream:
                yield text

    def get_sources(self, question: str, n_results: int = TOP_K_CHUNKS) -> List[dict]:
        """Return the retrieved chunks (without generating an answer)."""
        return self._store.query(question, n_results=n_results)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _format_context(chunks: List[dict]) -> str:
        if not chunks:
            return "No relevant document context was found for this query."
        parts = []
        for i, chunk in enumerate(chunks, 1):
            src   = chunk["metadata"].get("source", "unknown")
            cidx  = chunk["metadata"].get("chunk_index", "?")
            dist  = chunk["distance"]
            parts.append(
                f"[Context {i} | Source: {src} | Chunk: {cidx} | Similarity: {1 - dist:.2f}]\n"
                f"{chunk['text']}"
            )
        return "\n\n---\n\n".join(parts)

    @staticmethod
    def _build_messages(
        history: List[dict],
        question: str,
        context_block: str,
    ) -> List[dict]:
        """
        Construct the messages array:
          - Trimmed conversation history (up to MAX_HISTORY turns)
          - Current user turn with injected context
        """
        # Trim history to the last MAX_HISTORY turns
        trimmed = history[-(MAX_HISTORY * 2):]

        user_content = (
            f"<document_context>\n{context_block}\n</document_context>\n\n"
            f"Question: {question}"
        )

        return [*trimmed, {"role": "user", "content": user_content}]
