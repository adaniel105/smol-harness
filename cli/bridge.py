from __future__ import annotations

import threading
from typing import Any


def init_context() -> dict[str, Any]:
    """Create a fresh agent context."""
    from context.memory import update_context
    return update_context({}, [])


def update_agent_context(ctx: dict[str, Any], history: list[dict]) -> dict[str, Any]:
    """Update the agent context after a turn."""
    from context.memory import update_context
    return update_context(ctx, history)


def submit_prompt(query: str, history: list[dict], ctx: dict[str, Any], lock: threading.Lock) -> list[dict]:
    """Run the agent loop for one user query. Returns new assistant messages."""
    from hooks.hook import trigger_hooks
    from runner import agent_loop

    history.append({"role": "user", "content": query})
    trigger_hooks("UserPromptSubmit", query)

    turn_start = len(history)
    with lock:
        agent_loop(history, ctx)

    return [
        msg for msg in history[turn_start:]
        if msg.get("role") == "assistant"
    ]
