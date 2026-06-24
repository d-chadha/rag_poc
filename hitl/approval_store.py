"""
hitl/approval_store.py
-----------------------
Persists paused RunState to SQLite so HITL reviews survive Streamlit reruns.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from config.settings import HITL_DB

_DB = HITL_DB


def _ensure_table() -> None:
    with sqlite3.connect(_DB) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS pending_approvals (
                run_id     TEXT PRIMARY KEY,
                state_json TEXT NOT NULL,
                answer     TEXT,
                claims     TEXT,
                user_query TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)


def save_pending(
    run_id: str,
    answer: str,
    claims: list[str],
    ungrounded: list[str],
    user_query: str,
) -> None:
    """Save a HITL-pending answer for human review."""
    _ensure_table()
    import json
    with sqlite3.connect(_DB) as conn:
        conn.execute(
            """INSERT OR REPLACE INTO pending_approvals
               (run_id, state_json, answer, claims, user_query)
               VALUES (?, ?, ?, ?, ?)""",
            (
                run_id,
                json.dumps({"ungrounded": ungrounded}),
                answer,
                json.dumps(claims),
                user_query,
            ),
        )


def load_pending(run_id: str) -> dict | None:
    """Load a pending HITL record. Returns None if not found."""
    _ensure_table()
    import json
    with sqlite3.connect(_DB) as conn:
        row = conn.execute(
            "SELECT answer, claims, state_json, user_query FROM pending_approvals WHERE run_id=?",
            (run_id,),
        ).fetchone()
    if row is None:
        return None
    return {
        "answer":      row[0],
        "claims":      json.loads(row[1]),
        "ungrounded":  json.loads(row[2]).get("ungrounded", []),
        "user_query":  row[3],
    }


def delete_pending(run_id: str) -> None:
    """Remove a resolved HITL record."""
    _ensure_table()
    with sqlite3.connect(_DB) as conn:
        conn.execute("DELETE FROM pending_approvals WHERE run_id=?", (run_id,))


def list_pending() -> list[dict]:
    """List all unresolved HITL records (for admin view)."""
    _ensure_table()
    import json
    with sqlite3.connect(_DB) as conn:
        rows = conn.execute(
            "SELECT run_id, user_query, created_at FROM pending_approvals ORDER BY created_at DESC"
        ).fetchall()
    return [{"run_id": r[0], "user_query": r[1], "created_at": r[2]} for r in rows]
