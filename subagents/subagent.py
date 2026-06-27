from config import WORKDIR, client, MODEL
from hooks.hook import trigger_hooks
from types import SimpleNamespace
import json


SUB_SYSTEM = (
    f"You are a coding subagent at {WORKDIR}. "
    "Complete the task, then return a concise final summary. "
    "Do not spawn more agents."
)


SUB_TOOLS = [
    {"type": "function", "function": {"name": "bash", "description": "Run a shell command.",
     "parameters": {"type": "object",
                    "properties": {"command": {"type": "string"}},
                    "required": ["command"]}}},
    {"type": "function", "function": {"name": "read_file", "description": "Read file contents.",
     "parameters": {"type": "object",
                    "properties": {"path": {"type": "string"},
                                   "limit": {"type": "integer"},
                                   "offset": {"type": "integer"}},
                    "required": ["path"]}}},
    {"type": "function", "function": {"name": "write_file", "description": "Write content to a file.",
     "parameters": {"type": "object",
                    "properties": {"path": {"type": "string"},
                                   "content": {"type": "string"}},
                    "required": ["path", "content"]}}},
    {"type": "function", "function": {"name": "edit_file", "description": "Replace exact text in a file once.",
     "parameters": {"type": "object",
                    "properties": {"path": {"type": "string"},
                                   "old_text": {"type": "string"},
                                   "new_text": {"type": "string"}},
                    "required": ["path", "old_text", "new_text"]}}},
    {"type": "function", "function": {"name": "glob", "description": "Find files matching a glob pattern.",
     "parameters": {"type": "object",
                    "properties": {"pattern": {"type": "string"}},
                    "required": ["pattern"]}}},
]


def get_sub_handlers() -> dict:
    from tools.tools import run_bash, run_read, run_write, run_edit, run_glob
    return {
        "bash": run_bash, "read_file": run_read,
        "write_file": run_write, "edit_file": run_edit,
        "glob": run_glob,
    }


def extract_text(content) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return str(content)
    texts = [b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"]
    return "\n".join(texts).strip()


def has_tool_use(msg) -> bool:
    return bool(getattr(msg, 'tool_calls', None))


def spawn_subagent(description: str) -> str:
    from tools.tools import call_tool_handler
    sub_handlers = get_sub_handlers()
    messages = [{"role": "system", "content": SUB_SYSTEM}, {"role": "user", "content": description}]
    for _ in range(30):
        response = client.chat.completions.create(
            model=MODEL, messages=messages,
            tools=SUB_TOOLS, max_tokens=8000)
        msg = response.choices[0].message
        tool_calls = [tc.model_dump() for tc in msg.tool_calls] if msg.tool_calls else None
        messages.append({"role": "assistant", "content": msg.content, "tool_calls": tool_calls})
        if not msg.tool_calls:
            break
        for tool_call in msg.tool_calls:
            name = tool_call.function.name
            args = json.loads(tool_call.function.arguments)
            tc_id = tool_call.id
            shim = SimpleNamespace(name=name, input=args, id=tc_id)
            blocked = trigger_hooks("PreToolUse", shim)
            if blocked:
                output = str(blocked)
            else:
                handler = sub_handlers.get(name)
                output = call_tool_handler(handler, args, name)
                trigger_hooks("PostToolUse", shim, output)
            messages.append({"role": "tool", "content": str(output), "tool_call_id": tc_id})
    for msg in reversed(messages):
        if msg["role"] == "assistant":
            text = extract_text(msg.get("content"))
            if text:
                return text
    return "Subagent finished without a text summary."