from __future__ import annotations

import asyncio
import queue
import threading

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Header, Input, RichLog

from cli.bridge import init_context, submit_prompt, update_agent_context
from cli.output import OutputCategory, OutputEvent, set_tui_queue
from cli.theme import ERROR, PRIMARY, SECONDARY, TEXT_MUTED, WARNING


class AgentTUI(App):
    CSS_PATH = "css/app.tcss"
    TITLE = "smol-harness"

    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit"),
        Binding("ctrl+l", "clear_panes", "Clear"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._sync_queue: queue.Queue[OutputEvent] | None = None
        self._history: list[dict] = []
        self._agent_ctx: dict = {}
        self._agent_lock = threading.Lock()
        self._agent_busy = False

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="main"):
            with Vertical(id="chat-area"):
                yield RichLog(id="chat-pane", markup=True, wrap=True)
                yield Input(placeholder="Ask me anything...", id="input-box")
            yield RichLog(id="tool-pane", markup=True, wrap=True)
        yield Footer()

    async def on_mount(self) -> None:
        try:
            self._agent_ctx = init_context()
        except Exception:
            self._agent_ctx = {}

        q: queue.Queue[OutputEvent] = queue.Queue()
        self._sync_queue = q
        set_tui_queue(q)  # type: ignore[arg-type]

        self.set_interval(0.1, self._poll_output)

        chat = self.query_one("#chat-pane", RichLog)
        chat.write(f"[bold {PRIMARY}]smol-harness TUI[/] — type your query below")
        chat.write(f"[{TEXT_MUTED}]Press Ctrl+C to quit, Ctrl+L to clear[/]")



    def _poll_output(self) -> None:
        if self._sync_queue is None:
            return

        tool_pane = self.query_one("#tool-pane", RichLog)
        chat = self.query_one("#chat-pane", RichLog)

        for _ in range(200):
            try:
                event = self._sync_queue.get_nowait()
            except queue.Empty:
                return
            self._route_event(event, chat, tool_pane)

    def _route_event(self, event: OutputEvent, chat: RichLog, tool_pane: RichLog) -> None:
        text = event.text
        cat = event.category
        pane = tool_pane if cat in (
            OutputCategory.TOOL_CALL, OutputCategory.TOOL_RESULT,
            OutputCategory.HOOK, OutputCategory.CRON,
        ) else chat

        match cat:
            case OutputCategory.TOOL_CALL:
                pane.write(f"[bold {PRIMARY}]{text}[/]")
            case OutputCategory.ASSISTANT:
                pane.write(f"[bold {PRIMARY}]Agent:[/] {text}")
            case OutputCategory.USER:
                pane.write(f"[bold {SECONDARY}]You:[/] {text}")
            case OutputCategory.ERROR:
                pane.write(f"[bold {ERROR}]{text}[/]")
            case OutputCategory.WARNING:
                pane.write(f"[bold {WARNING}]{text}[/]")
            case _:
                pane.write(text)

    # ── User input ───────────────────────────────────────────────────

    def on_input_submitted(self, event: Input.Submitted) -> None:
        query = event.value.strip()
        if not query:
            return

        self.query_one("#input-box", Input).value = ""
        self.query_one("#chat-pane", RichLog).write(
            f"[bold {SECONDARY}]You:[/] {query}"
        )

        self._pending_query = query
        self.run_worker(self._run_agent, exclusive=True)

    async def _run_agent(self) -> None:
        if self._agent_busy:
            return
        self._agent_busy = True
        try:
            query = self._pending_query
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, self._run_agent_sync, query)
        finally:
            self._agent_busy = False

    def _run_agent_sync(self, query: str) -> None:
        new_assistant_msgs = submit_prompt(
            query, self._history, self._agent_ctx, self._agent_lock,
        )
        self._agent_ctx = update_agent_context(self._agent_ctx, self._history)

        from cli.output import tui_print
        for msg in new_assistant_msgs:
            content = msg.get("content")
            if isinstance(content, str) and content.strip():
                tui_print(content, OutputCategory.ASSISTANT)

    # ── Actions ──────────────────────────────────────────────────────

    def action_clear_panes(self) -> None:
        self.query_one("#chat-pane", RichLog).clear()
        self.query_one("#tool-pane", RichLog).clear()

    def action_quit(self) -> None:
        self.exit()
