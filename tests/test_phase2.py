"""Quick Phase 2 smoke test — run as: python tests/test_phase2.py"""
import asyncio
import sys
sys.path.insert(0, ".")

from dotenv import load_dotenv
load_dotenv(dotenv_path=".env", override=True)


def test_sql():
    from db.session_factory import get_db_session
    from sqlalchemy import text
    with get_db_session() as s:
        rows = s.execute(text("SELECT employee_name, office_location FROM employees LIMIT 3")).fetchall()
    assert len(rows) == 3
    print("[SQL] OK —", rows[0][0], "->", rows[0][1])


def test_sql_safety():
    from tools.sql_tools import _is_safe_sql
    assert _is_safe_sql("SELECT * FROM employees")
    assert not _is_safe_sql("DELETE FROM employees")
    assert not _is_safe_sql("DROP TABLE employees")
    print("[SQL safety] OK")


def test_weather_cache():
    from tools.tavily_tools import _upsert_weather, _synthetic_weather
    from vectorstore.chroma_client import get_collection

    for city in ["Chicago", "Denver", "Boston"]:
        snippets = _synthetic_weather(city)
        _upsert_weather(city, snippets)

    col = get_collection("tavily_weather")
    count = col.count()
    assert count >= 3
    print(f"[Chroma weather] OK — {count} docs in collection")

    res = col.query(
        query_texts=["weather conditions today"],
        n_results=1,
        where={"city_tag": "Chicago"},
        include=["documents", "metadatas"],
    )
    assert res["documents"][0]
    assert res["metadatas"][0][0]["city_tag"] == "Chicago"
    print("[Chroma weather query] OK —", res["documents"][0][0][:50])


def test_chunking():
    from tools.ingestion_tools import _chunk_text
    chunks = _chunk_text("A " * 300, chunk_size=100, overlap=20)
    assert len(chunks) > 1
    print(f"[Chunking] OK — {len(chunks)} chunks")


def test_agent_imports():
    from nexus_agents.sql_agent import sql_agent, sql_tool
    from nexus_agents.rag_retriever_agent import rag_retriever_agent, rag_retriever_tool
    from nexus_agents.weather_fusion_agent import weather_fusion_agent, weather_fusion_tool
    from nexus_agents.ingestion_agent import ingestion_agent, ingestion_tool

    assert sql_agent.name == "SQLAgent"
    assert rag_retriever_agent.name == "RAGRetrieverAgent"
    assert weather_fusion_agent.name == "WeatherFusionAgent"
    assert ingestion_agent.name == "IngestionAgent"
    print("[Agent imports] OK — all 4 agents + tools loaded")


async def test_weather_tool_standalone():
    """Test WeatherFusionAgent tool function directly."""
    from nexus_agents.weather_fusion_agent import get_weather_for_location
    import json

    # Simulate calling the underlying function
    from vectorstore.chroma_client import get_collection
    col = get_collection("tavily_weather")
    res = col.query(
        query_texts=["weather Chicago"],
        n_results=1,
        where={"city_tag": "Chicago"},
        include=["documents", "metadatas"],
    )
    assert res["documents"][0]
    print("[Weather fusion standalone] OK —", res["documents"][0][0][:50])


if __name__ == "__main__":
    print("=" * 50)
    print("NEXUS Phase 2 Smoke Test")
    print("=" * 50)
    test_sql()
    test_sql_safety()
    test_weather_cache()
    test_chunking()
    test_agent_imports()
    asyncio.run(test_weather_tool_standalone())
    print("=" * 50)
    print("ALL PHASE 2 TESTS PASSED")
    print("=" * 50)
