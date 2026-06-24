"""
nexus_agents/rag_retriever_agent.py
------------------------------------
RAGRetrieverAgent — semantic vector search over Chroma collections.
Exposed as a tool to NEXUSOrchestrator via .as_tool().
"""

from __future__ import annotations

from pydantic import BaseModel

from agents import Agent
from agents.extensions.models.litellm_model import LitellmModel
from tools.chroma_tools import query_chroma
from config.settings import CLAUDE_HAIKU_MODEL, GPT4O_MINI_MODEL


class RAGResult(BaseModel):
    chunks:     list[str]
    chunk_ids:  list[str]
    sources:    list[str]
    collection: str
    count:      int


RAG_AGENT_INSTRUCTIONS = """
You are a precision vector search agent for NEXUS.

Your job: given a semantic query, retrieve the most relevant chunks from Chroma.

COLLECTIONS AVAILABLE:
  - tavily_news    : news articles fetched from Tavily
  - tavily_weather : weather data per city, tagged with city_tag metadata
  - rag_documents  : user-uploaded documents (RAG knowledge base)

RULES:
1. ALWAYS pass city_tag when retrieving weather data — it scopes results to one city.
2. For news queries, use collection_name='tavily_news', no city_tag.
3. For document questions, use collection_name='rag_documents'.
4. Request n_results=5 by default, up to 10 for broad questions.
5. If the collection is empty, report that clearly and suggest running data ingestion.
6. Return chunk text, source metadata (source_url, city_tag, title), and similarity scores.

Use the query_chroma tool to perform searches.
After retrieving, summarize what you found and return the structured result.
"""

rag_retriever_agent = Agent(
    name="RAGRetrieverAgent",
    instructions=RAG_AGENT_INSTRUCTIONS,
    model=LitellmModel(model=CLAUDE_HAIKU_MODEL),
    tools=[query_chroma],
)

# Expose as a tool callable by NEXUSOrchestrator
rag_retriever_tool = rag_retriever_agent.as_tool(
    tool_name="retrieve_from_knowledge_base",
    tool_description=(
        "Retrieve semantically relevant chunks from Chroma vector collections. "
        "Use for news queries (collection: tavily_news), weather lookups by city "
        "(collection: tavily_weather, requires city_tag), or user document questions "
        "(collection: rag_documents)."
    ),
)
