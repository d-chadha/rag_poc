"""
memory/nexus_session.py
-----------------------
SQLiteSession factory for NEXUS conversation history.
One session per Streamlit browser session — keyed by session UUID.
"""

from __future__ import annotations

from agents import SQLiteSession

from config.settings import NEXUS_SESSION_DB


def get_or_create_session(user_session_id: str) -> SQLiteSession:
    """
    Return a persistent SQLiteSession for *user_session_id*.
    History survives app restarts because it's file-backed.
    The same session is shared across all agents in a single turn.
    """
    return SQLiteSession(
        session_id=user_session_id,
        db_path=NEXUS_SESSION_DB,
    )
