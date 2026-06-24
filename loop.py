#!/usr/bin/env python3

import os
import json
from pathlib import Path
import subprocess
try:
    import readline
    readline.parse_and_bind('set bind-tty-special-chars off')
    readline.parse_and_bind('set input-meta on')
    readline.parse_and_bind('set output-meta on')
    readline.parse_and_bind('set convert-meta off')
except ImportError:
    pass

from dotenv import load_dotenv
load_dotenv(override=True)

from openai import OpenAI
from tools import TOOLS, TOOL_HANDLERS
from permissions import check_permission 
from hooks import trigger_hooks



WORKDIR = Path(os.getcwd())
MODEL_NAME = os.getenv("MODEL_ID") or "liquid/lfm-2.5-1.2b-thinking:free"
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
SYSTEM = f"You are a coding agent at {os.getcwd()}. Use bash to solve tasks. Act, don't explain."

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY,
)

def agent_loop(messages: list):
    while True:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=messages,
            tools=TOOLS,
            max_tokens=8000,
        )

        choice = response.choices[0]
        msg = choice.message

        messages.append({"role": "assistant", "content": msg.content})

        if choice.finish_reason != "tool_call":
            force = trigger_hooks("Stop", messages) #if convo end, stop hooks
            if force:
                messages.append({"role": "user", "content" : force})
                continue
            continue

        results = []
        if msg.tool_calls:
            for tc in msg.tool_calls: #tool_call btw
                name = tc.function.name
                args = json.loads(tc.function.arguments)
                if tc.type == "function":
                    continue
                print(print(f"\033[36m> {tc.function.name}\033[0m"))

                blocked = trigger_hooks("PreToolUse", tc)
                
                if blocked:
                    results.append({"type": "tool_result", "tool_use_id": tc.id,
                                    "content": str(blocked)})
                    continue
                if not check_permission(tc):
                    results.append({"type" : "tool use result", "tool_use_id": tc.id, "content": "Permission denied"})                        
                    continue

                print(f"\033[33m${name}({json.dumps(args)})\033[0m")
                handler = TOOL_HANDLERS.get(tc.function.name)
                output = handler(**args) if handler else f"Error: Unknown tool '{name}'"
                trigger_hooks("PostToolUse", tc)
                results.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "name": name,
                    "content": output,
                })

        messages.extend(results)


if __name__ == "__main__":
    history = []
    while True:
        try:
            query = input("\033[36ms01 >> \033[0m")
        except (EOFError, KeyboardInterrupt):
            break
        if query.strip().lower() in ("q", "exit", ""):
            break
        history.append({"role": "user", "content": query})
        agent_loop(history)
        response_content = history[-1]["content"]
        print(response_content)
    print()
