from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Static


class PermissionModal(ModalScreen[bool]):
    """Modal dialog for destructive command confirmation.

    Displays the command being run and asks the user to Allow or Deny.
    Returns True if allowed, False otherwise.
    """

    CSS = """
    PermissionModal {
        align: center middle;
    }
    #dialog {
        width: 60;
        max-width: 90%;
        height: auto;
        max-height: 20;
        background: #141414;
        border: thick #fab283;
        padding: 1 2;
    }
    #dialog-title {
        text-style: bold;
        color: #f5a742;
        margin-bottom: 1;
        width: 100%;
    }
    #dialog-tool-label {
        color: #808080;
        margin-bottom: 0;
    }
    #dialog-message {
        color: #eeeeee;
        margin-bottom: 1;
        width: 100%;
    }
    #dialog-buttons {
        height: 3;
        align: center middle;
        margin-top: 1;
    }
    #dialog-buttons Button {
        margin: 0 1;
    }
    """

    def __init__(self, command: str, tool_name: str = "bash") -> None:
        super().__init__()
        self.command = command
        self.tool_name = tool_name

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Static("Warning: Destructive Command", id="dialog-title")
            yield Static(f"Tool: {self.tool_name}", id="dialog-tool-label")
            yield Static(f"Command: {self.command}", id="dialog-message")
            with Horizontal(id="dialog-buttons"):
                yield Button("Allow", variant="success", id="allow")
                yield Button("Deny", variant="error", id="deny")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "allow":
            self.dismiss(True)
        else:
            self.dismiss(False)

    def on_key(self, event: object) -> None:
        from textual import events

        if isinstance(event, events.Key):
            if event.key == "y":
                self.dismiss(True)
            elif event.key in ("n", "escape"):
                self.dismiss(False)
