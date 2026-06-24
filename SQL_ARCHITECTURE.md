# SQL Architecture in NEXUS: sql_tools vs sql_agent

## Quick Answer

| Layer | Component | Responsibility | Reasoning |
|-------|-----------|-----------------|-----------|
| **Execution** | `sql_tools.py` | Raw SQL execution + safety gating | Isolated, reusable, security-focused |
| **Intelligence** | `sql_agent.py` | NL→SQL translation + orchestration | Uses LLM to understand user intent |
| **Integration** | `sql_tool` (exposed) | Callable by NEXUSOrchestrator | Agents talking to agents via SDK |

---

## Architecture Diagram

```
NEXUSOrchestrator Agent
  "Find employees in Engineering"
         |
         | calls (as Tool)
         v
    sql_tool (exposed)
    .as_tool() wrapper
         |
         | invokes
         v
    SQLAgent (Agent class)
    - Instructions: Translate NL→SQL
    - Model: GPT-4o OR Claude
    - Tools: [execute_employee_query]
         |
         | calls
         v
    execute_employee_query() @function_tool
    - Safety check: SELECT only
    - Execute via SQLAlchemy
    - Return JSON {rows, error}
         |
         | executes
         v
    SQLite "nexus_employees.db"
    SELECT * FROM employees WHERE...
         |
         | returns
         v
    Rows: [{employee_id:1, name:..., ...}]
         |
         | parsed into
         v
    SQLResult (Pydantic)
    - rows: list[EmployeeRow]
    - sql_executed: str
    - row_count: int
```

---

## Detailed Responsibility Breakdown

### 1. sql_tools.py — The Execution Layer

**Responsibility:** Raw SQL execution + security gating

**What it does:**
- ✅ Validates if SQL is safe (SELECT only)
- ✅ Executes via SQLAlchemy
- ✅ Catches exceptions
- ✅ Returns JSON with results/errors

**What it does NOT do:**
- ❌ Understand user intent
- ❌ Translate natural language to SQL
- ❌ Choose which columns to return
- ❌ Format intelligently for other agents

**Why separate?**
```python
# Same tool can be reused by:
# 1. SQLAgent (understands NL, generates SQL)
# 2. RAGRetrieverAgent (pre-generated SQL)
# 3. Any future agent needing employee data
```

---

### 2. sql_agent.py — The Intelligence Layer

**Responsibility:** NL→SQL translation + structured output

**What it does:**
- ✅ Reads user intent from natural language
- ✅ Applies domain knowledge (schema, rules, examples)
- ✅ Generates syntactically correct SQL
- ✅ **Calls** `execute_employee_query` tool
- ✅ Structures results into Pydantic `SQLResult`
- ✅ Explains why rows were/weren't found

**Example internal flow:**

```python
# User: "Find all employees in Austin"

# SQLAgent LLM:
# 1. Parse: "Need Austin employees"
# 2. Generate: "SELECT * FROM employees 
#                WHERE office_location = 'Austin' LIMIT 50"
# 3. Call tool: execute_employee_query(sql=...)
# 4. Tool returns: {"rows": [...], "row_count": 23}
# 5. Wrap in Pydantic SQLResult
```

---

### 3. sql_tool (exposed) — The Integration Point

**Responsibility:** Expose SQLAgent as a tool to NEXUSOrchestrator

```python
sql_tool = sql_agent.as_tool(
    tool_name="query_employee_database",
    tool_description="Query using natural language..."
)
```

**Enables:**
- ✅ NEXUSOrchestrator calls SQLAgent
- ✅ SDK handles tool invocation & streaming
- ✅ Structured output auto-validates
- ✅ Can combine with other tools

---

## Real Query Flow Example

### User: "Where does Alice Johnson work and what's the weather there?"

```
Step 1: NEXUSOrchestrator receives query
         ↓
Step 2: Orchestrator decides: "I need SQL + weather"
         ↓
Step 3: Orchestrator calls sql_tool
         │
         ├─→ sql_agent LLM: "Find Alice Johnson"
         │
         ├─→ sql_agent generates:
         │   "SELECT * FROM employees 
         │    WHERE employee_name LIKE '%Alice Johnson%' LIMIT 10"
         │
         ├─→ sql_agent calls execute_employee_query(sql=...)
         │   ├─→ Check: _is_safe_sql(...) ✓
         │   ├─→ Execute: session.execute(text(sql))
         │   ├─→ Return: JSON with rows
         │
         ├─→ sql_agent wraps result in SQLResult
         │
Step 4: Orchestrator gets office_location="Austin"
         ↓
Step 5: Orchestrator calls weather_tool with "Austin"
         ↓
Step 6: HANDOFF to AnswerSynthesisAgent with both results
         ↓
Step 7: Final answer:
        "Alice Johnson works in Engineering in Austin, TX.
         Current weather: 94°F, partly cloudy."
```

---

## Separation of Concerns

### Why separate instead of merge?

```python
# ❌ BAD: Merged into one
class SQLAgent:
    def query(self, nl_query: str):
        # - Understand NL
        # - Generate SQL
        # - Validate SQL
        # - Execute via DB
        # - Format output
        # (5 concerns in one place)

# ✅ GOOD: Separated
# sql_tools.py: Execute only
@function_tool
async def execute_employee_query(sql: str) -> str:
    # - Validate (safety)
    # - Execute (DB)
    # - Return JSON

# sql_agent.py: Intelligence only
class SQLAgent(Agent):
    # - Understand NL
    # - Generate SQL
    # - Call tool
    # - Wrap result
```

**Benefits:**
1. **Reusability:** Tool usable by any agent
2. **Testability:** Test execution separately from reasoning
3. **Security:** sql_tools owns safety policy
4. **Agility:** Change LLM without touching execution
5. **Composability:** Mix agents freely

---

## Tool Composition Pattern

```python
# LAYER 1: Low-level @function_tool
@function_tool
async def execute_employee_query(sql: str) -> str:
    # Direct DB execution, safety checks

# LAYER 2: Agent with intelligence
sql_agent = Agent(
    name="SQLAgent",
    model="gpt-4o",
    tools=[execute_employee_query],  # ← uses tool
)

# LAYER 3: Agent's exposed interface
sql_tool = sql_agent.as_tool(
    tool_name="query_employee_database"
)

# LAYER 4: Higher agent uses it
nexus_orchestrator = Agent(
    name="NEXUSOrchestrator",
    model="claude-sonnet-4",
    tools=[sql_tool],  # ← sql_agent AS a tool
)
```

**Key insight:** An Agent can BE a Tool. Recursively composable.

---

## Comparison Table

| Aspect | sql_tools.py | sql_agent.py |
|--------|-------------|-------------|
| Purpose | Execute SQL safely | Translate NL→SQL |
| Input | Raw SQL string | User intent |
| Output | JSON string | Pydantic SQLResult |
| Model | ❌ No LLM | ✅ GPT-4o or Claude |
| Reasoning | ❌ None | ✅ Full semantic |
| Safety | ✅ Active gating | ❌ Relies on tool |
| Reusable by | Any agent | Via orchestrator |
| SDK type | @function_tool | Agent.as_tool() |

---

## Summary

```
NEXUS Pattern for External Data Sources:

HIGH-LEVEL GOAL: "Query employee database"

↓ Breaks down to:

1. EXECUTION (sql_tools.py)
   • What: Run SQL, return rows
   • Decorator: @function_tool
   • Reused by: Any agent

2. INTELLIGENCE (sql_agent.py)
   • What: Understand intent, generate SQL
   • Type: Agent with tools
   • Used by: Orchestrator as tool

3. INTEGRATION (sql_tool)
   • What: Agent callable by higher agents
   • Pattern: agent.as_tool()
   • Consumer: NEXUSOrchestrator
```

Same pattern applies to:
- `chroma_tools.py` + `rag_retriever_agent.py`
- `tavily_tools.py` + `ingestion_agent.py`
- `tavily_tools.py` + `weather_fusion_agent.py`

*Generated: 2026-06-16 | Pattern: Multi-layer Agent Composition in OpenAI Agents SDK*
