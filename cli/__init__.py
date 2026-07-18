from __future__ import annotations


def run_tui() -> None:
    """Launch the Textual TUI."""
    from cli.app import AgentTUI

    app = AgentTUI()
    app.run()
