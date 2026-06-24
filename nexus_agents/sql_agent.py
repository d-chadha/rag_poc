"""
nexus_agents/sql_agent.py
-------------------------
SQLAgent — natural-language to SQL translation + execution.
Exposed as a tool to NEXUSOrchestrator via .as_tool().
"""

from __future__ import annotations

from pydantic import BaseModel

from agents import Agent
from agents.extensions.models.litellm_model import LitellmModel
from tools.sql_tools import execute_employee_query
from config.settings import GPT4O_MODEL, OPENAI_API_KEY, CLAUDE_SONNET_MODEL

# Use GPT-4o if key available, else fall back to Claude Sonnet via LiteLLM
_sql_model = GPT4O_MODEL if OPENAI_API_KEY else LitellmModel(model=CLAUDE_SONNET_MODEL)


class EmployeeRow(BaseModel):
    employee_id:     int
    employee_name:   str
    age:             int
    department:      str
    office_location: str


class SQLResult(BaseModel):
    rows:         list[EmployeeRow]
    sql_executed: str
    row_count:    int
    error:        str | None = None


SQL_AGENT_INSTRUCTIONS = """
You are an expert SQL agent for the NEXUS employees database.

DATABASE SCHEMA:
  Table: employees
  Columns:
    - employee_id     (INTEGER, primary key, autoincrement)
    - employee_name   (VARCHAR 100)
    - age             (INTEGER, range 22-65)
    - department      (VARCHAR 100) — one of: Engineering, Product, Design, Marketing,
                       Sales, Finance, HR, Legal, Operations, Research
    - office_location (VARCHAR 100) — one of: Austin, Seattle, New York, San Francisco,
                       Chicago, Boston, Denver, Atlanta, Miami, Portland

RULES (NON-NEGOTIABLE):
1. Generate ONLY SELECT statements. NEVER write UPDATE, DELETE, DROP, INSERT, ALTER.
2. Use LIKE '%name%' for partial name matching (SQLite, case-insensitive by default).
3. ALWAYS include office_location in your SELECT — it is the semantic bridge to weather data.
4. If no rows found, return an empty rows list and explain why.
5. Validate SQL syntax before executing it.
6. For aggregate queries (count, avg age, etc.) return the result directly in sql_executed.
7. LIMIT results to 50 rows maximum unless the user explicitly requests more.

EXAMPLE QUERIES:
  "Who works in Engineering?" → SELECT * FROM employees WHERE department = 'Engineering' LIMIT 50
  "Find Alice" → SELECT * FROM employees WHERE employee_name LIKE '%Alice%' LIMIT 10
  "Average age by department" → SELECT department, AVG(age) as avg_age FROM employees GROUP BY department
  "How many employees in Seattle?" → SELECT COUNT(*) as count, office_location FROM employees WHERE office_location = 'Seattle'

Use the execute_employee_query tool to run your generated SQL.
Return a structured SQLResult with the rows and the SQL you executed.
If the query returns aggregates (not full rows), still use the execute_employee_query tool
and return the raw rows from the result.
"""

sql_agent = Agent(
    name="SQLAgent",
    instructions=SQL_AGENT_INSTRUCTIONS,
    model=_sql_model,
    tools=[execute_employee_query],
)

# Expose as a tool callable by NEXUSOrchestrator
sql_tool = sql_agent.as_tool(
    tool_name="query_employee_database",
    tool_description=(
        "Query the NEXUS employees SQL database using natural language. "
        "Use for any question about employee names, ages, departments, or office locations. "
        "Always returns office_location — the key to weather data lookup."
    ),
)
