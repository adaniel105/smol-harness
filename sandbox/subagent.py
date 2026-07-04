import json
from types import SimpleNamespace

from config import WORKDIR, client, MODEL
from hooks.hook import trigger_hooks
from sandbox.forkd_sandbox import ForkdSandbox, ForkdSandboxPool
from sandbox.tools import SUB_TOOLS, make_handlers


SUB_SYSTEM = (
    f"You are a coding subagent at {WORKDIR}. Your tools run inside an isolated sandbox. "
    "Complete the task, then return a concise final summary. "
    "Do not spawn more agents."
)


def extract_text(content) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return str(content)
    texts = [
        b.get("text", "")
        for b in content
        if isinstance(b, dict) and b.get("type") == "text"
    ]
    return "\n".join(texts).strip()


def has_tool_use(msg) -> bool:
    return bool(getattr(msg, "tool_calls", None))


def spawn_subagent_sandboxed(
    description: str,
    sandbox: ForkdSandbox | None = None,
    pool: ForkdSandboxPool | None = None,
) -> str:
    own_sandbox = sandbox is None
    if sandbox is None:
        pool = pool or ForkdSandboxPool()
        try:
            sandbox = pool.acquire()
        except RuntimeError as e:
            return f"[SandboxError] forkd unavailable: {e}"

    try:
        handlers = make_handlers(sandbox)
        messages = [
            {"role": "system", "content": SUB_SYSTEM},
            {"role": "user", "content": description},
        ]

        for _ in range(30):
            response = client.chat.completions.create(
                model=MODEL,
                messages=messages,
                tools=SUB_TOOLS,
                max_tokens=8000,
            )
            msg = response.choices[0].message
            tool_calls_data = (
                [tc.model_dump() for tc in msg.tool_calls] if msg.tool_calls else None
            )
            messages.append(
                {
                    "role": "assistant",
                    "content": msg.content,
                    "tool_calls": tool_calls_data,
                }
            )

            if not has_tool_use(msg):
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
                    handler = handlers.get(name)
                    if handler:
                        output = handler(**args)
                    else:
                        output = f"Unknown tool: {name}"
                    trigger_hooks("PostToolUse", shim, output)

                messages.append(
                    {
                        "role": "tool",
                        "content": str(output),
                        "tool_call_id": tc_id,
                    }
                )

        for msg in reversed(messages):
            if msg["role"] == "assistant":
                text = extract_text(msg.get("content"))
                if text:
                    return text
        return "Subagent finished without a text summary."

    finally:
        if own_sandbox and sandbox is not None:
            sandbox.close()
