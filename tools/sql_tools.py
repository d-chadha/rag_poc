"""
tools/sql_tools.py
------------------
@function_tool wrappers for the NEXUS employee SQL database.
SELECT-only. Never generates destructive SQL.
"""

from __future__ import annotations

import json
import re

from agents import RunContextWrapper, function_tool
from sqlalchemy import text

from db.session_factory import get_db_session


def _is_safe_sql(sql: str) -> bool:
    """Reject any SQL that is not a SELECT statement."""
    clean = sql.strip().upper()
    if not clean.startswith("SELECT"):
        return False
    dangerous = re.compile(
        r"\b(INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|TRUNCATE|EXEC|EXECUTE|GRANT|REVOKE)\b"
    )
    return not dangerous.search(clean)


@function_tool
async def execute_employee_query(
    ctx: RunContextWrapper,
    sql: str,
) -> str:
    """
    Execute a read-only SQL SELECT against the NEXUS employees table and return
    matching rows as a JSON string.

    Schema:
      Table: employees
      Columns: employee_id (INT PK), employee_name (VARCHAR),
               age (INT), department (VARCHAR), office_location (VARCHAR)

    Args:
        sql: A valid SELECT statement. Must NOT contain INSERT/UPDATE/DELETE/DROP.

    Returns:
        JSON string: {"rows": [...], "row_count": N, "sql_executed": "..."}
        or {"error": "...", "sql_executed": "..."} on failure.
    """
    if not _is_safe_sql(sql):
        return json.dumps({
            "error": "Only SELECT statements are permitted.",
            "sql_executed": sql,
        })

    try:
        with get_db_session() as session:
            result = session.execute(text(sql))
            cols = list(result.keys())
            rows = [dict(zip(cols, row)) for row in result.fetchall()]

        return json.dumps({
            "rows": rows,
            "row_count": len(rows),
            "sql_executed": sql,
        })
    except Exception as exc:
        return json.dumps({
            "error": str(exc),
            "sql_executed": sql,
        })
