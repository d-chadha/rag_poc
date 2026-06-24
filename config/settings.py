"""
config/settings.py
------------------
Central environment-variable loader for NEXUS.
All constants are sourced from .env — never hardcoded.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env", override=True)

# ── LLM providers ────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
OPENAI_API_KEY: str    = os.getenv("OPENAI_API_KEY", "")

# ── Model identifiers ─────────────────────────────────────────────────────────
CLAUDE_SONNET_MODEL = "anthropic/claude-sonnet-4-6"   # matches Sonnet 4.6 env
CLAUDE_HAIKU_MODEL  = "anthropic/claude-haiku-4-5-20251001"
GPT4O_MODEL         = "gpt-4o"
GPT4O_MINI_MODEL    = "gpt-4o-mini"

# ── Tavily ────────────────────────────────────────────────────────────────────
TAVILY_API_KEY: str = os.getenv("TAVILY_API_KEY", "")

# ── Chroma ────────────────────────────────────────────────────────────────────
CHROMA_DB_PATH: str = os.getenv("CHROMA_DB_PATH", "./nexus_chroma_db")

# ── SQLAlchemy ────────────────────────────────────────────────────────────────
EMPLOYEES_DB_URL: str = os.getenv("EMPLOYEES_DB_URL", "sqlite:///nexus_employees.sqlite")

# ── Session persistence ───────────────────────────────────────────────────────
NEXUS_SESSION_DB: str = os.getenv("NEXUS_SESSION_DB", "nexus_conversations.sqlite")
HITL_DB: str          = os.getenv("HITL_DB", "nexus_hitl.sqlite")

# ── Ingestion ─────────────────────────────────────────────────────────────────
WEATHER_STALENESS_SECONDS: int = int(os.getenv("WEATHER_STALENESS_SECONDS", "3600"))
NEWS_MAX_RESULTS: int          = int(os.getenv("NEWS_MAX_RESULTS", "10"))
CHUNK_SIZE: int                = int(os.getenv("CHUNK_SIZE", "500"))
CHUNK_OVERLAP: int             = int(os.getenv("CHUNK_OVERLAP", "75"))

# ── Logging ───────────────────────────────────────────────────────────────────
LOG_LEVEL: str        = os.getenv("LOG_LEVEL", "INFO")
TOOL_AUDIT_LOG: str   = os.getenv("TOOL_AUDIT_LOG", "nexus_tool_audit.log")
DISABLE_TRACING: bool = os.getenv("OPENAI_AGENTS_DISABLE_TRACING", "0") == "1"

# ── Cities (semantic bridge — must match office_location values) ───────────────
CITIES: list[str] = [
    "Austin", "Seattle", "New York", "San Francisco", "Chicago",
    "Boston", "Denver", "Atlanta", "Miami", "Portland",
]

DEPARTMENTS: list[str] = [
    "Engineering", "Product", "Design", "Marketing",
    "Sales", "Finance", "HR", "Legal", "Operations", "Research",
]
