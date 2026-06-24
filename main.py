"""
main.py
-------
NEXUS Streamlit frontend — full-featured conversational RAG UI.

Features:
  - Streaming chat with live token output
  - Agent trace expander (handoffs, tool calls, timings)
  - Employee DB browser + stats
  - Data ingestion controls
  - HITL review widget (approve / reject ungrounded answers)
  - Token & latency metrics dashboard
  - Document upload (rag_documents collection)
  - Dark-themed, branded NEXUS identity
"""

from __future__ import annotations

# ── startup MUST be first — ensures correct DLL init order on Windows ─────────
import startup  # noqa: F401

import asyncio
import logging
import time
import uuid
from typing import Any

import streamlit as st
from dotenv import load_dotenv

load_dotenv(dotenv_path=".env", override=True)

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="NEXUS",
    page_icon="🔗",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        "About": "NEXUS — Neural EXchange for Unified Structured/Unstructured Intelligence",
    },
)

# ── Custom CSS: dark branded theme ────────────────────────────────────────────
st.markdown("""
<style>
/* ── Global ── */
[data-testid="stAppViewContainer"] { background: #0d1117; }
[data-testid="stSidebar"] { background: #161b22; border-right: 1px solid #30363d; }
[data-testid="stSidebar"] * { color: #c9d1d9 !important; }

/* ── Chat bubbles ── */
[data-testid="stChatMessage"][data-testid*="user"] { background: #1c2128; border-radius: 12px; }
[data-testid="stChatMessage"] { background: #161b22; border-radius: 12px; border: 1px solid #21262d; }

/* ── Metrics ── */
[data-testid="stMetric"] { background: #161b22; border-radius: 8px; padding: 8px 12px; border: 1px solid #21262d; }

/* ── Expanders ── */
.streamlit-expanderHeader { background: #161b22 !important; border-radius: 8px; color: #58a6ff !important; }
.streamlit-expanderContent { background: #0d1117 !important; }

/* ── Buttons ── */
.stButton > button { border-radius: 8px; font-weight: 600; }
.stButton > button[kind="primary"] { background: #238636; border-color: #238636; }
.stButton > button[kind="secondary"] { background: #21262d; border-color: #30363d; color: #c9d1d9; }

/* ── Input ── */
[data-testid="stChatInput"] textarea { background: #161b22 !important; color: #c9d1d9 !important; border-color: #30363d !important; }

/* ── Nexus brand header ── */
.nexus-header { font-size: 2rem; font-weight: 800; letter-spacing: -1px;
                background: linear-gradient(135deg, #58a6ff, #bc8cff);
                -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
.nexus-sub    { color: #8b949e; font-size: 0.85rem; margin-top: -8px; }

/* ── Trace chip ── */
.trace-chip { display: inline-block; padding: 2px 8px; border-radius: 12px;
              font-size: 0.75rem; font-weight: 600; margin: 2px; }
.chip-agent   { background: #1f4068; color: #79c0ff; }
.chip-tool    { background: #2d1b69; color: #d2a8ff; }
.chip-handoff { background: #0e3b2b; color: #56d364; }

/* ── Status badge ── */
.badge-ok  { color: #56d364; font-weight: 700; }
.badge-err { color: #f85149; font-weight: 700; }
</style>
""", unsafe_allow_html=True)

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("nexus.ui")


# ── Cached heavy singletons ───────────────────────────────────────────────────

@st.cache_resource
def _get_chroma():
    from vectorstore.chroma_client import get_chroma_client
    return get_chroma_client()


@st.cache_resource
def _get_engine():
    from db.session_factory import get_engine
    return get_engine()


@st.cache_resource
def _get_orchestrator():
    from nexus_agents.orchestrator import nexus_orchestrator
    return nexus_orchestrator


# ── Session state bootstrap ───────────────────────────────────────────────────

def _init_state() -> None:
    defaults = {
        "nexus_session_id":  str(uuid.uuid4()),
        "messages":          [],          # [{"role": "user"|"assistant", "content": "..."}]
        "processed_files":   set(),
        "total_tokens":      0,
        "total_latency_s":   0.0,
        "query_count":       0,
        "hitl_pending":      None,        # {run_id, answer, claims, ungrounded, user_query}
        "last_trace":        [],          # from ctx.context["nexus_trace"]
        "show_trace":        False,
        "ingestion_status":  "",
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


_init_state()

# ── Helpers ───────────────────────────────────────────────────────────────────

def _run_async(coro):
    """Run an async coroutine synchronously inside Streamlit."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, coro)
                return future.result()
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


def _get_db_stats() -> dict:
    """Return employee DB stats for the sidebar."""
    try:
        from db.models import Employee
        from db.session_factory import get_db_session
        from sqlalchemy import func
        with get_db_session() as s:
            total = s.query(func.count(Employee.employee_id)).scalar()
            depts = s.query(Employee.department, func.count()).group_by(Employee.department).all()
            cities = s.query(Employee.office_location, func.count()).group_by(Employee.office_location).all()
        return {
            "total": total,
            "depts": dict(depts),
            "cities": dict(cities),
        }
    except Exception:
        return {"total": 0, "depts": {}, "cities": {}}


def _chroma_stats() -> dict:
    """Return Chroma collection stats."""
    try:
        client = _get_chroma()
        return {
            "news":     client.get_or_create_collection("tavily_news").count(),
            "weather":  client.get_or_create_collection("tavily_weather").count(),
            "docs":     client.get_or_create_collection("rag_documents").count(),
        }
    except Exception:
        return {"news": 0, "weather": 0, "docs": 0}


def _render_trace(trace: list[dict]) -> None:
    """Render agent trace events as styled chips."""
    if not trace:
        st.caption("No trace events recorded.")
        return

    icons = {"agent_start": "🤖", "agent_end": "✅", "handoff": "🔀",
             "tool_start": "🔧", "tool_end": "✔️"}
    chip_css = {"agent_start": "chip-agent", "agent_end": "chip-agent",
                "handoff": "chip-handoff", "tool_start": "chip-tool", "tool_end": "chip-tool"}

    html_parts = []
    for event in trace:
        etype = event.get("type", "?")
        icon  = icons.get(etype, "•")
        css   = chip_css.get(etype, "chip-agent")

        if etype == "agent_start":
            label = f"{icon} {event.get('agent')} started"
        elif etype == "agent_end":
            elapsed = event.get("elapsed", "?")
            label = f"{icon} {event.get('agent')} done ({elapsed}s)"
        elif etype == "handoff":
            label = f"{icon} {event.get('from_agent')} → {event.get('to_agent')}"
        elif etype in ("tool_start", "tool_end"):
            label = f"{icon} {event.get('tool')}"
        else:
            label = f"• {etype}"

        html_parts.append(f'<span class="trace-chip {css}">{label}</span>')

    st.markdown(" ".join(html_parts), unsafe_allow_html=True)


async def _run_nexus(user_input: str) -> dict:
    """
    Run one NEXUS turn. Returns:
      {"answer": str, "trace": list, "tokens": int, "elapsed": float,
       "hitl": dict|None, "error": str|None}
    """
    from agents import Runner, RunConfig, InputGuardrailTripwireTriggered, OutputGuardrailTripwireTriggered
    from agents.extensions.models.litellm_provider import LitellmProvider
    from hooks.logging_hooks import NEXUSRunHooks
    from memory.nexus_session import get_or_create_session

    orchestrator = _get_orchestrator()
    session = get_or_create_session(st.session_state["nexus_session_id"])
    run_config = RunConfig(
        model_provider=LitellmProvider(),
        tracing_disabled=False,
    )
    hooks = NEXUSRunHooks()
    ctx_data: dict = {}

    t0 = time.time()

    try:
        result = await Runner.run(
            orchestrator,
            user_input,
            session=session,
            run_config=run_config,
            hooks=hooks,
            context=ctx_data,
        )

        elapsed = time.time() - t0
        trace = ctx_data.get("nexus_trace", [])
        output = result.final_output

        # SynthesisOutput or plain string
        if hasattr(output, "answer"):
            answer = output.answer
        else:
            answer = str(output)

        return {
            "answer":  answer,
            "trace":   trace,
            "elapsed": round(elapsed, 2),
            "tokens":  0,
            "hitl":    None,
            "error":   None,
        }

    except InputGuardrailTripwireTriggered as e:
        check = e.guardrail_result.output_info
        return {
            "answer":  f"🚫 Query blocked: {check.reason}",
            "trace":   ctx_data.get("nexus_trace", []),
            "elapsed": round(time.time() - t0, 2),
            "tokens":  0,
            "hitl":    None,
            "error":   "blocked",
        }

    except OutputGuardrailTripwireTriggered as e:
        # Attempt auto-revision (attempt #1 already counted in SynthesisHooks)
        attempt = ctx_data.get("synthesis_attempt", 1)
        check   = e.guardrail_result.output_info
        draft   = getattr(e, "agent_output", None)

        if attempt < 2:
            revision = check.revision_notes
            revised_input = f"{user_input}\n\n[REVISION REQUIRED — address these issues]:\n{revision}"
            return await _run_nexus(revised_input)  # one auto-retry

        # Second failure → HITL
        run_id = str(uuid.uuid4())
        draft_answer = getattr(draft, "answer", str(draft)) if draft else "Draft not available."
        draft_claims = getattr(draft, "claims", []) if draft else []

        from hitl.approval_store import save_pending
        save_pending(
            run_id=run_id,
            answer=draft_answer,
            claims=draft_claims,
            ungrounded=check.ungrounded_claims,
            user_query=user_input,
        )

        return {
            "answer":  None,
            "trace":   ctx_data.get("nexus_trace", []),
            "elapsed": round(time.time() - t0, 2),
            "tokens":  0,
            "hitl": {
                "run_id":      run_id,
                "answer":      draft_answer,
                "claims":      draft_claims,
                "ungrounded":  check.ungrounded_claims,
                "user_query":  user_input,
                "revision":    check.revision_notes,
            },
            "error": None,
        }

    except Exception as exc:
        logger.exception("NEXUS run error")
        return {
            "answer":  f"⚠️ Error: {exc}",
            "trace":   ctx_data.get("nexus_trace", []),
            "elapsed": round(time.time() - t0, 2),
            "tokens":  0,
            "hitl":    None,
            "error":   str(exc),
        }


# ═══════════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ═══════════════════════════════════════════════════════════════════════════════

with st.sidebar:
    # ── Brand ──────────────────────────────────────────────────────────────
    st.markdown('<div class="nexus-header">NEXUS</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="nexus-sub">Neural EXchange for Unified Structured/Unstructured Intelligence</div>',
        unsafe_allow_html=True,
    )
    st.divider()

    # ── Session metrics ────────────────────────────────────────────────────
    col1, col2, col3 = st.columns(3)
    col1.metric("Queries", st.session_state["query_count"])
    col2.metric("Latency", f"{st.session_state['total_latency_s']:.1f}s")
    col3.metric("HITL", "⚠️" if st.session_state["hitl_pending"] else "✅")
    st.divider()

    # ── Tab switcher ───────────────────────────────────────────────────────
    sidebar_tab = st.radio(
        "Panel",
        ["📊 Data", "📁 Documents", "⚙️ Settings"],
        horizontal=True,
        label_visibility="collapsed",
    )

    st.markdown("")

    # ══════════════════════════════════════════════════════════════════════
    if sidebar_tab == "📊 Data":
        st.subheader("Employee Database")
        db_stats = _get_db_stats()

        if db_stats["total"]:
            st.metric("Total Employees", f"{db_stats['total']:,}")

            with st.expander("By Department", expanded=False):
                if db_stats["depts"]:
                    import pandas as pd
                    df_dept = pd.DataFrame(
                        list(db_stats["depts"].items()),
                        columns=["Department", "Count"]
                    ).sort_values("Count", ascending=False)
                    st.dataframe(df_dept, width="stretch", hide_index=True)

            with st.expander("By City", expanded=False):
                if db_stats["cities"]:
                    import pandas as pd
                    df_city = pd.DataFrame(
                        list(db_stats["cities"].items()),
                        columns=["City", "Count"]
                    ).sort_values("Count", ascending=False)
                    st.dataframe(df_city, width="stretch", hide_index=True)
        else:
            st.info("No employee data. Run `python db/seed.py` to seed.")

        st.divider()
        st.subheader("Vector Collections")
        ch_stats = _chroma_stats()
        c1, c2, c3 = st.columns(3)
        c1.metric("📰 News", ch_stats["news"])
        c2.metric("🌤 Weather", ch_stats["weather"])
        c3.metric("📄 Docs", ch_stats["docs"])

        st.divider()
        st.subheader("Data Refresh")
        st.caption("Fetch fresh content from Tavily (requires API key) or use synthetic data.")

        col_a, col_b = st.columns(2)
        if col_a.button("🌤 Refresh Weather", width="stretch"):
            with st.spinner("Refreshing weather for all cities..."):
                from tools.tavily_tools import _upsert_weather, _synthetic_weather
                from config.settings import CITIES
                for city in CITIES:
                    _upsert_weather(city, _synthetic_weather(city))
            st.session_state["ingestion_status"] = f"✅ Weather refreshed for {len(CITIES)} cities"
            st.rerun()

        if col_b.button("📰 Refresh News", width="stretch"):
            with st.spinner("Ingesting news articles..."):
                async def _ingest():
                    from tools.ingestion_tools import _ingest_synthetic_news
                    return await _ingest_synthetic_news()
                result = _run_async(_ingest())
            import json
            r = json.loads(result)
            st.session_state["ingestion_status"] = (
                f"✅ News: {r.get('articles_processed',0)} articles, "
                f"{r.get('chunks_created',0)} chunks"
            )
            st.rerun()

        if st.session_state["ingestion_status"]:
            st.success(st.session_state["ingestion_status"])

    # ══════════════════════════════════════════════════════════════════════
    elif sidebar_tab == "📁 Documents":
        st.subheader("Upload Documents")
        from document_processor import SUPPORTED_EXTENSIONS
        ext_list = ", ".join(f"*{e}" for e in SUPPORTED_EXTENSIONS)
        uploaded = st.file_uploader(
            "Choose files",
            accept_multiple_files=True,
            type=[e.lstrip(".") for e in SUPPORTED_EXTENSIONS],
            help=f"Supported: {ext_list}",
        )
        if uploaded:
            new_files = [f for f in uploaded if f.name not in st.session_state["processed_files"]]
            if new_files:
                with st.spinner(f"Processing {len(new_files)} file(s)…"):
                    for uf in new_files:
                        try:
                            from document_processor import process_document
                            from vectorstore.chroma_client import get_collection
                            chunks_data = process_document(uf.name, uf.read())
                            col = get_collection("rag_documents")
                            import uuid as _uuid
                            col.add(
                                documents=[c.text for c in chunks_data],
                                metadatas=[c.metadata for c in chunks_data],
                                ids=[f"doc_{_uuid.uuid4().hex[:8]}_{i}" for i in range(len(chunks_data))],
                            )
                            st.session_state["processed_files"].add(uf.name)
                            st.success(f"✅ **{uf.name}** — {len(chunks_data)} chunks")
                        except Exception as exc:
                            st.error(f"❌ {uf.name}: {exc}")

        st.divider()
        st.subheader("Indexed Documents")
        ch = _chroma_stats()
        if ch["docs"] > 0:
            st.metric("Doc Chunks", ch["docs"])
        if st.session_state["processed_files"]:
            for name in sorted(st.session_state["processed_files"]):
                st.markdown(f"📄 `{name}`")
        else:
            st.info("No documents uploaded yet.")

        if st.session_state["processed_files"]:
            if st.button("🗑️ Clear All Documents", width="stretch", type="secondary"):
                from vectorstore.chroma_client import get_chroma_client
                client = get_chroma_client()
                client.delete_collection("rag_documents")
                st.session_state["processed_files"].clear()
                st.rerun()

    # ══════════════════════════════════════════════════════════════════════
    elif sidebar_tab == "⚙️ Settings":
        st.subheader("Chat Settings")
        st.toggle("Show agent trace", key="show_trace")

        st.divider()
        st.subheader("Session")
        st.caption(f"Session ID: `{st.session_state['nexus_session_id'][:16]}…`")
        if st.button("🔄 New Session", width="stretch"):
            st.session_state["nexus_session_id"]  = str(uuid.uuid4())
            st.session_state["messages"]          = []
            st.session_state["query_count"]       = 0
            st.session_state["total_latency_s"]   = 0.0
            st.session_state["hitl_pending"]      = None
            st.session_state["last_trace"]        = []
            st.rerun()

        st.divider()
        st.subheader("API Keys")
        from config.settings import ANTHROPIC_API_KEY, TAVILY_API_KEY, OPENAI_API_KEY
        st.markdown(
            f"Anthropic: {'<span class=\"badge-ok\">✓ set</span>' if ANTHROPIC_API_KEY else '<span class=\"badge-err\">✗ missing</span>'}",
            unsafe_allow_html=True,
        )
        st.markdown(
            f"OpenAI: {'<span class=\"badge-ok\">✓ set</span>' if OPENAI_API_KEY else '<span class=\"badge-err\">✗ missing (SQL agent uses gpt-4o)</span>'}",
            unsafe_allow_html=True,
        )
        st.markdown(
            f"Tavily: {'<span class=\"badge-ok\">✓ set</span>' if TAVILY_API_KEY else '<span class=\"badge-err\">✗ not set (synthetic fallback active)</span>'}",
            unsafe_allow_html=True,
        )

        st.divider()
        st.caption("NEXUS v1.0 · openai-agents 0.17 · Chroma 1.5")


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN — Header + Metrics bar
# ═══════════════════════════════════════════════════════════════════════════════

# Header
st.markdown(
    '<h1 class="nexus-header" style="font-size:1.8rem">🔗 NEXUS</h1>',
    unsafe_allow_html=True,
)
st.caption(
    "Conversational AI fusing **Employee SQL**, **Weather**, **News**, and **Documents** · "
    "Powered by Claude Sonnet 4 + GPT-4o · ChromaDB vector search"
)

# ── HITL banner (shown at top if a review is pending) ─────────────────────────
if st.session_state["hitl_pending"]:
    hitl = st.session_state["hitl_pending"]
    st.error("⚠️ **Human Review Required** — NEXUS could not produce a fully-grounded answer.")

    with st.expander("🔍 Review Draft Answer", expanded=True):
        st.markdown("**Draft answer:**")
        st.info(hitl["answer"])

        if hitl.get("ungrounded"):
            st.markdown("**Ungrounded claims detected:**")
            for claim in hitl["ungrounded"]:
                st.markdown(f"- ❌ {claim}")

        if hitl.get("revision"):
            st.markdown("**Revision notes:**")
            st.caption(hitl["revision"])

        col_approve, col_reject = st.columns(2)
        if col_approve.button("✅ Approve — send to user", type="primary", width="stretch"):
            answer = hitl["answer"]
            st.session_state["messages"].append({"role": "assistant", "content": answer})
            st.session_state["hitl_pending"] = None
            from hitl.approval_store import delete_pending
            delete_pending(hitl["run_id"])
            st.rerun()

        if col_reject.button("❌ Reject — discard", type="secondary", width="stretch"):
            st.session_state["hitl_pending"] = None
            from hitl.approval_store import delete_pending
            delete_pending(hitl["run_id"])
            st.session_state["messages"].append({
                "role": "assistant",
                "content": "⚠️ Answer was rejected during human review. Please rephrase your question.",
            })
            st.rerun()

# ── Conversation history ───────────────────────────────────────────────────────
for msg in st.session_state["messages"]:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# ── Last trace (shown after most recent answer) ────────────────────────────────
if st.session_state["show_trace"] and st.session_state["last_trace"]:
    with st.expander("🔍 Agent trace (last turn)", expanded=False):
        _render_trace(st.session_state["last_trace"])

# ── Empty state ────────────────────────────────────────────────────────────────
if not st.session_state["messages"] and not st.session_state["hitl_pending"]:
    st.markdown("")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.info("**👤 Employee queries**\n\nTry: *\"Who works in Engineering in Seattle?\"*")
    with c2:
        st.info("**🌤 Weather fusion**\n\nTry: *\"Where does Kevin work and what's the weather?\"*")
    with c3:
        st.info("**📰 News & Docs**\n\nTry: *\"What's the latest news about AI?\"*")
    st.markdown("")

# ═══════════════════════════════════════════════════════════════════════════════
# CHAT INPUT → NEXUS RUN
# ═══════════════════════════════════════════════════════════════════════════════

placeholder_text = (
    "Ask about employees, weather, news, or uploaded documents…"
    if not st.session_state["hitl_pending"]
    else "Resolve the HITL review above before continuing…"
)

if user_input := st.chat_input(
    placeholder_text,
    disabled=bool(st.session_state["hitl_pending"]),
):
    # Show user bubble
    with st.chat_message("user"):
        st.markdown(user_input)
    st.session_state["messages"].append({"role": "user", "content": user_input})

    # Run NEXUS
    with st.chat_message("assistant"):
        with st.status("NEXUS thinking…", expanded=True) as status_widget:
            st.write("🔒 Safety check…")
            result = _run_async(_run_nexus(user_input))
            st.write("✅ Done")
        status_widget.update(label="NEXUS", state="complete", expanded=False)

        answer = result.get("answer")
        hitl   = result.get("hitl")
        trace  = result.get("trace", [])
        elapsed = result.get("elapsed", 0)

        if answer:
            st.markdown(answer)
            st.session_state["messages"].append({"role": "assistant", "content": answer})
        elif hitl:
            st.warning("⚠️ Requires human review — see banner above.")
            st.session_state["hitl_pending"] = hitl
            st.rerun()

        # ── Trace expander ─────────────────────────────────────────────
        if trace:
            st.session_state["last_trace"] = trace
            if st.session_state["show_trace"]:
                with st.expander(f"🔍 Agent trace ({len(trace)} events, {elapsed}s)", expanded=False):
                    _render_trace(trace)

        # ── Per-turn metrics ───────────────────────────────────────────
        col_m1, col_m2, col_m3 = st.columns(3)
        col_m1.metric("Latency", f"{elapsed}s")
        col_m2.metric("Trace events", len(trace))
        col_m3.metric("Status", "🚫 blocked" if result.get("error") == "blocked" else "✅ ok")

    # ── Update session-level stats ─────────────────────────────────────────
    st.session_state["query_count"]     += 1
    st.session_state["total_latency_s"] += elapsed
