"""Output abstraction for the TUI.

Modules call tui_print() to emit messages. When a TUI queue is set,
events land there for the app to poll. Otherwise they fall back to stdout.
"""

from __future__ import annotations

import queue
import time
from dataclasses import dataclass
from enum import Enum


class OutputCategory(Enum):
    USER = "user"
    ASSISTANT = "assistant"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"
    HOOK = "hook"
    CRON = "cron"


@dataclass(frozen=True)
class OutputEvent:
    text: str
    category: OutputCategory
    timestamp: float


_tui_queue: queue.Queue[OutputEvent] | None = None


def set_tui_queue(q: queue.Queue[OutputEvent] | None) -> None:
    global _tui_queue
    _tui_queue = q


def get_tui_queue() -> queue.Queue[OutputEvent] | None:
    return _tui_queue


def tui_print(text: str, category: OutputCategory = OutputCategory.INFO) -> None:
    if _tui_queue is not None:
        _tui_queue.put(OutputEvent(text, category, time.time()))
    else:
        print(text)
