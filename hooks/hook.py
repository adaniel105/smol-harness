from config.config import WORKDIR
from typing import Callable

HOOKS = {"UserPromptSubmit": [], "PreToolUse": [],
         "PostToolUse": [], "Stop": []}

_permission_prompt_fn: Callable[[str], str] | None = None


def set_permission_prompt_fn(fn: Callable[[str], str] | None) -> None:
    """Set a custom prompt function for permission checks.

    The function receives a message string and should return "y" or "n".
    Set to None to restore default stdin input() behavior.
    """
    global _permission_prompt_fn
    _permission_prompt_fn = fn


def _default_permission_prompt(message: str) -> str:
    print(f"\n\033[33m[permission] {message}\033[0m")
    return input("  Allow? [y/N] ").strip().lower()


def register_hook(event: str, callback):
    HOOKS[event].append(callback)


def trigger_hooks(event: str, *args):
    for callback in HOOKS[event]:
        result = callback(*args)
        if result is not None:
            return result
    return None


DENY_LIST = ["rm -rf /", "sudo", "shutdown", "reboot", "mkfs", "dd if="]
DESTRUCTIVE = ["rm ", "> /etc/", "chmod 777"]


def permission_hook(block):
    from tools.tools import safe_path
    prompt_fn = _permission_prompt_fn or _default_permission_prompt
    if block.name == "bash":
        command = block.input.get("command", "")
        for pattern in DENY_LIST:
            if pattern in command:
                return f"Permission denied: '{pattern}' is on the deny list"
        if any(token in command for token in DESTRUCTIVE):
            choice = prompt_fn(f"destructive command: {command}")
            if choice not in ("y", "yes"):
                return "Permission denied by user"
    if block.name in ("write_file", "edit_file"):
        path = block.input.get("path", "")
        try:
            safe_path(path)
        except Exception:
            return f"Permission denied: path escapes workspace: {path}"
    if block.name.startswith("mcp__") and "deploy" in block.name:
        choice = prompt_fn(f"MCP destructive-looking tool: {block.name}")
        if choice not in ("y", "yes"):
            return "Permission denied by user"
    return None


def log_hook(block):
    print(f"\033[90m[HOOK] {block.name}\033[0m")
    return None


def large_output_hook(block, output):
    if len(str(output)) > 100000:
        print(f"\033[33m[HOOK] large output from {block.name}: "
              f"{len(str(output))} chars\033[0m")
    return None


def user_prompt_hook(query: str):
    print(f"\033[90m[HOOK] UserPromptSubmit: {WORKDIR}\033[0m")
    return None


def stop_hook(messages: list):
    tool_count = 0
    for msg in messages:
        content = msg.get("content")
        if isinstance(content, list):
            tool_count += sum(1 for item in content
                              if isinstance(item, dict)
                              and item.get("type") == "tool_result")
    print(f"\033[90m[HOOK] Stop: {tool_count} tool result(s)\033[0m")
    return None


register_hook("UserPromptSubmit", user_prompt_hook)
register_hook("PreToolUse", permission_hook)
register_hook("PreToolUse", log_hook)
register_hook("PostToolUse", large_output_hook)
register_hook("Stop", stop_hook)