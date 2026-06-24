"""
hooks/logging_hooks.py
-----------------------
RunHooks + AgentHooks implementations for NEXUS observability.

NEXUSRunHooks: global hooks covering the entire Runner.run() invocation.
  - on_agent_start / on_agent_end  → agent timing + token logging
  - on_handoff                     → handoff path tracking
  - on_tool_start / on_tool_end    → tool call audit trail

These populate ctx.context["nexus_trace"] — a list of trace events that
the Streamlit UI uses to render the agent trace expander.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from agents import AgentHooks, RunContextWrapper, RunHooks

logger = logging.getLogger("nexus")


def _append_trace(ctx: RunContextWrapper, event: dict) -> None:
    """Append a structured trace event to the run context."""
    if "nexus_trace" not in ctx.context:
        ctx.context["nexus_trace"] = []
    event.setdefault("ts", round(time.time(), 3))
    ctx.context["nexus_trace"].append(event)


class NEXUSRunHooks(RunHooks):
    """
    Observes the entire Runner.run() invocation including all agent handoffs.
    Populates ctx.context['nexus_trace'] for the UI trace viewer.
    """

    async def on_agent_start(
        self, ctx: RunContextWrapper, agent: Any
    ) -> None:
        ctx.context.setdefault("agent_timings", {})[agent.name] = time.time()
        logger.info("[NEXUS] Agent START: %s", agent.name)
        _append_trace(ctx, {"type": "agent_start", "agent": agent.name})

    async def on_agent_end(
        self, ctx: RunContextWrapper, agent: Any, output: Any
    ) -> None:
        start = ctx.context.get("agent_timings", {}).get(agent.name, time.time())
        elapsed = time.time() - start
        usage = getattr(ctx, "usage", None)
        logger.info(
            "[NEXUS] Agent END: %s | %.2fs | usage=%s",
            agent.name,
            elapsed,
            usage,
        )
        _append_trace(ctx, {
            "type":    "agent_end",
            "agent":   agent.name,
            "elapsed": round(elapsed, 2),
        })

    async def on_handoff(
        self, ctx: RunContextWrapper, from_agent: Any, to_agent: Any
    ) -> None:
        logger.info(
            "[NEXUS] HANDOFF: %s → %s",
            from_agent.name,
            to_agent.name,
        )
        _append_trace(ctx, {
            "type":       "handoff",
            "from_agent": from_agent.name,
            "to_agent":   to_agent.name,
        })

    async def on_tool_start(
        self, ctx: RunContextWrapper, agent: Any, tool: Any
    ) -> None:
        tool_name = getattr(tool, "name", str(tool))
        logger.info("[NEXUS] TOOL START: %s calling %s", agent.name, tool_name)
        _append_trace(ctx, {
            "type":  "tool_start",
            "agent": agent.name,
            "tool":  tool_name,
        })

    async def on_tool_end(
        self, ctx: RunContextWrapper, agent: Any, tool: Any, result: Any
    ) -> None:
        tool_name = getattr(tool, "name", str(tool))
        result_len = len(str(result)) if result is not None else 0
        logger.info("[NEXUS] TOOL END: %s | result_len=%d", tool_name, result_len)
        _append_trace(ctx, {
            "type":       "tool_end",
            "tool":       tool_name,
            "result_len": result_len,
        })
