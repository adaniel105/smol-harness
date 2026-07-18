import time
import json
import random
import threading
from types import SimpleNamespace
from context.prompt_assembly import assemble_system_prompt, prepare_context, inject_background_notifications, build_user_content
from context.memory import update_context, compact_history, reactive_compact
from tools.mcp_connector import assemble_tool_pool
from tools.tools import call_tool_handler
from subagents.subagent import has_tool_use
from hooks.hook import trigger_hooks
from tasks.workers import should_run_background, start_background_task
from tasks.scheduler import consume_cron_queue
from protocol.protocols import consume_lead_inbox
from cli.output import OutputCategory

try:
    import readline
    readline.parse_and_bind('set bind-tty-special-chars off')
    READLINE_AVAILABLE = True
except ImportError:
    READLINE_AVAILABLE = False

from config.config import PRIMARY_MODEL, FALLBACK_MODEL, DEFAULT_MAX_TOKENS, ESCALATED_MAX_TOKENS, MAX_RETRIES, MAX_CONSECUTIVE_529, MAX_RECOVERY_RETRIES, BASE_DELAY_MS, client
CONTINUATION_PROMPT = "Continue from the previous response. Do not repeat completed work."
PROMPT = "\033[36mQuery: >> \033[0m"
CLI_ACTIVE = False


def terminal_print(text: str, category=None):
    from cli.output import get_tui_queue, tui_print, OutputCategory
    if get_tui_queue() is not None:
        tui_print(text, category or OutputCategory.INFO)
        return
    if threading.current_thread() is not threading.main_thread() or not CLI_ACTIVE:
        print(text)
        return
    line = ""
    if READLINE_AVAILABLE:
        try:
            line = readline.get_line_buffer()
        except Exception:
            line = ""
    print(f"\r\033[K{text}")
    print(PROMPT + line, end="", flush=True)


class RecoveryState:
    def __init__(self):
        self.has_escalated = False
        self.recovery_count = 0
        self.consecutive_529 = 0
        self.has_attempted_reactive_compact = False
        self.current_model = PRIMARY_MODEL


def retry_delay(attempt: int) -> float:
    base = min(BASE_DELAY_MS * (2 ** attempt), 32000) / 1000
    return base + random.uniform(0, base * 0.25)


def with_retry(fn, state: RecoveryState):
    for attempt in range(MAX_RETRIES):
        try:
            result = fn()
            state.consecutive_529 = 0
            return result
        except Exception as e:
            name = type(e).__name__.lower()
            msg = str(e).lower()
            if "ratelimit" in name or "429" in msg:
                delay = retry_delay(attempt)
                terminal_print(f"  \033[33m[429] retry {attempt + 1}/{MAX_RETRIES} after {delay:.1f}s\033[0m")
                time.sleep(delay)
            elif "overloaded" in name or "529" in msg or "overloaded" in msg:
                state.consecutive_529 += 1
                if state.consecutive_529 >= MAX_CONSECUTIVE_529 and FALLBACK_MODEL:
                    state.current_model = FALLBACK_MODEL
                    state.consecutive_529 = 0
                    terminal_print(f"  \033[31m[529] switching to {FALLBACK_MODEL}\033[0m")
                delay = retry_delay(attempt)
                terminal_print(f"  \033[33m[529] retry {attempt + 1}/{MAX_RETRIES} after {delay:.1f}s\033[0m")
                time.sleep(delay)
            else:
                raise
    raise RuntimeError(f"Max retries ({MAX_RETRIES}) exceeded")


def is_prompt_too_long_error(e: Exception) -> bool:
    msg = str(e).lower()
    return ("prompt" in msg and "long" in msg) or "context_length_exceeded" in msg or "max_context_window" in msg


rounds_since_todo = 0
agent_lock = threading.Lock()


def call_llm(messages: list, context: dict, tools: list, state: RecoveryState, max_tokens: int):
    system = assemble_system_prompt(context)
    messages.append({"role": "system", "content": system})
    return with_retry(lambda: client.chat.completions.create(
        model=state.current_model,
        messages=messages,
        tools=tools,
        max_tokens=max_tokens,
    ), state)


def agent_loop(messages: list, context: dict):
    tools, handlers = assemble_tool_pool()
    state = RecoveryState()
    max_tokens = DEFAULT_MAX_TOKENS

    while True:
        global rounds_since_todo
        fired = consume_cron_queue()
        for job in fired:
            messages.append({"role": "user", "content": f"[Scheduled] {job.prompt}"})
            terminal_print(f"  \033[35m[cron inject] {str(job.prompt)[:60]}\033[0m")

        inject_background_notifications(messages)

        if rounds_since_todo >= 3:
            messages.append({"role": "user", "content": "<reminder>Update your todos.</reminder>"})
            rounds_since_todo = 0

        prepare_context(messages)
        context = update_context(context, messages)
        tools, handlers = assemble_tool_pool()

        try:
            response = call_llm(messages, context, tools, state, max_tokens)
        except Exception as e:
            if is_prompt_too_long_error(e) and not state.has_attempted_reactive_compact:
                messages[:] = reactive_compact(messages)
                state.has_attempted_reactive_compact = True
                continue
            messages.append({"role": "assistant", "content": f"[Error] {type(e).__name__}: {e}"})
            return

        if response.choices[0].finish_reason == "length":
            if not state.has_escalated:
                max_tokens = ESCALATED_MAX_TOKENS
                state.has_escalated = True
                terminal_print(f"  \033[33m[max_tokens] retry with {max_tokens}\033[0m")
                continue
            messages.append({"role": "assistant", "content": response.choices[0].message.content})
            if state.recovery_count < MAX_RECOVERY_RETRIES:
                messages.append({"role": "user", "content": CONTINUATION_PROMPT})
                state.recovery_count += 1
                continue
            return

        max_tokens = DEFAULT_MAX_TOKENS
        state.has_escalated = False
        msg = response.choices[0].message
        tool_calls = [tc.model_dump() for tc in msg.tool_calls] if msg.tool_calls else None
        messages.append({"role": "assistant", "content": msg.content, "tool_calls": tool_calls})

        if not has_tool_use(msg):
            trigger_hooks("Stop", messages)
            return

        results = []
        compacted_now = False
        for tool_call in msg.tool_calls:
            name = tool_call.function.name
            args = json.loads(tool_call.function.arguments)
            tc_id = tool_call.id
            shim = SimpleNamespace(name=name, input=args, id=tc_id)
            terminal_print(f"\033[36m> {name}\033[0m", OutputCategory.TOOL_CALL)

            if name == "compact":
                messages[:] = compact_history(messages)
                messages.append({"role": "user", "content": "[Compacted. Continue with summarized context.]"})
                compacted_now = True
                break

            blocked = trigger_hooks("PreToolUse", shim)
            if blocked:
                results.append({"type": "tool_result", "tool_use_id": tc_id, "content": str(blocked)})
                continue

            if should_run_background(name, args):
                bg_id = start_background_task(shim, handlers)
                output = f"[Background task {bg_id} started] Result will arrive as a task_notification."
                results.append({"type": "tool_result", "tool_use_id": tc_id, "content": output})
                continue

            handler = handlers.get(name)
            output = call_tool_handler(handler, args, name)
            trigger_hooks("PostToolUse", shim, output)
            terminal_print(str(output)[:300], OutputCategory.TOOL_RESULT)

            if name == "todo_write":
                rounds_since_todo = 0
            else:
                rounds_since_todo += 1

            results.append({"type": "tool_result", "tool_use_id": tc_id, "content": output})

        if compacted_now:
            continue

        messages.append({"role": "user", "content": build_user_content(results)})


def print_turn_assistants(messages: list, turn_start: int):
    for msg in messages[turn_start:]:
        if msg.get("role") != "assistant":
            continue
        content = msg.get("content")
        if isinstance(content, str) and content.strip():
            terminal_print(content)


def cron_autorun_loop(history: list, context: dict):
    while True:
        time.sleep(1)
        fired = consume_cron_queue()
        if not fired:
            continue
        with agent_lock:
            turn_start = len(history)
            for job in fired:
                history.append({"role": "user", "content": f"[Scheduled] {job.prompt}"})
                terminal_print(f"  \033[35m[cron auto] {str(job.prompt)[:60]}\033[0m")
            agent_loop(history, context)
            context.update(update_context(context, history))
            print_turn_assistants(history, turn_start)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Agent harness CLI")
    parser.add_argument("--tui", action="store_true", help="Launch TUI mode")
    args = parser.parse_args()

    if args.tui:
        from cli import run_tui
        run_tui()
    else:
        CLI_ACTIVE = True
        print("Enter a question, press Enter to send. Type q to quit.\n")
        history = []
        context = update_context({}, [])
        threading.Thread(target=cron_autorun_loop, args=(history, context), daemon=True).start()

        while True:
            try:
                query = input(PROMPT)
            except (EOFError, KeyboardInterrupt):
                break
            if query.strip().lower() in ("q", "exit", ""):
                break
            trigger_hooks("UserPromptSubmit", query)
            turn_start = len(history)
            history.append({"role": "user", "content": query})
            with agent_lock:
                agent_loop(history, context)
                context = update_context(context, history)
                print_turn_assistants(history, turn_start)

            inbox = consume_lead_inbox(route_protocol=True)
            if inbox:
                def inbox_label(msg):
                    req_id = msg.get("metadata", {}).get("request_id", "")
                    suffix = f" req:{req_id}" if req_id else ""
                    return f"{msg.get('type', 'message')}{suffix}"

                inbox_text = "\n".join(
                    f"From {m['from']} [{inbox_label(m)}]: {m['content'][:200]}"
                    for m in inbox
                )
                history.append({"role": "user", "content": f"[Inbox]\n{inbox_text}"})
            print()


if __name__ == "__main__":
    main()