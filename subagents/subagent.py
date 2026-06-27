from loop import WORKDIR, client, MODEL
from hooks.hook import trigger_hooks
import json


SUB_SYSTEM = (
    f"You are a coding subagent at {WORKDIR}. "
    "Complete the task, then return a concise final summary. "
    "Do not spawn more agents."
)


SUB_TOOLS = [
    {"name": "bash", "description": "Run a shell command.",
     "input_schema": {"type": "object",
                      "properties": {"command": {"type": "string"}},
                      "required": ["command"]}},
    {"name": "read_file", "description": "Read file contents.",
     "input_schema": {"type": "object",
                      "properties": {"path": {"type": "string"},
                                     "limit": {"type": "integer"},
                                     "offset": {"type": "integer"}},
                      "required": ["path"]}},
    {"name": "write_file", "description": "Write content to a file.",
     "input_schema": {"type": "object",
                      "properties": {"path": {"type": "string"},
                                     "content": {"type": "string"}},
                      "required": ["path", "content"]}},
    {"name": "edit_file", "description": "Replace exact text in a file once.",
     "input_schema": {"type": "object",
                      "properties": {"path": {"type": "string"},
                                     "old_text": {"type": "string"},
                                     "new_text": {"type": "string"}},
                      "required": ["path", "old_text", "new_text"]}},
    {"name": "glob", "description": "Find files matching a glob pattern.",
     "input_schema": {"type": "object",
                      "properties": {"pattern": {"type": "string"}},
                      "required": ["pattern"]}},
]


def get_sub_handlers() -> dict:
    from tools.tools import run_bash, run_read, run_write, run_edit, run_glob
    return {
        "bash": run_bash, "read_file": run_read,
        "write_file": run_write, "edit_file": run_edit,
        "glob": run_glob,
    }


def extract_text(content) -> str:
    if not isinstance(content, list):
        return str(content)
    return "\n".join(
        getattr(block, "text", "")
        for block in content
        if getattr(block, "type", None) == "text").strip()


def has_tool_use(content) -> bool:
    # Do not rely on stop_reason alone; the concrete tool_use block is the
    # continuation signal used by the loop.
    return any(getattr(block, "type", None) == "tool_use"
               for block in content)


def spawn_subagent(description: str) -> str:
    from tools.tools import call_tool_handler
    sub_handlers = get_sub_handlers()
    messages = [{"role": "user", "content": description}]
    for _ in range(30):
        response = client.chat.completions.create(
            model=MODEL, messages=messages,
            tools=SUB_TOOLS, max_tokens=8000)
        msg = response.choices[0].message
        messages.append({"role": "assistant", "content": msg.content})
        if not msg.tool_calls:
            break
        results = []
        for tool_call in msg.tool_calls:
            name = tool_call.function.name
            args = json.loads(tool_call.function.arguments)
            blocked = trigger_hooks("PreToolUse", tool_call)
            if blocked:
                output = str(blocked)
            else:
                handler = sub_handlers.get(name)
                output = call_tool_handler(handler, args, name)
                trigger_hooks("PostToolUse", tool_call, output)
            results.append({"type": "tool_result",
                            "tool_use_id": tool_call.id,
                            "content": str(output)})
        messages.append({"role": "user", "content": results})
    for msg in reversed(messages):
        if msg["role"] == "assistant":
            text = msg.get("content")
            if text:
                return text
    return "Subagent finished without a text summary."