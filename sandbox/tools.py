from sandbox.forkd_sandbox import ForkdSandbox


SUB_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "bash",
            "description": "Run a shell command.",
            "parameters": {
                "type": "object",
                "properties": {"command": {"type": "string"}},
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read file contents.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "limit": {"type": "integer"},
                    "offset": {"type": "integer"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write content to a file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": "Replace exact text in a file once.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "old_text": {"type": "string"},
                    "new_text": {"type": "string"},
                },
                "required": ["path", "old_text", "new_text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "glob",
            "description": "Find files matching a glob pattern.",
            "parameters": {
                "type": "object",
                "properties": {"pattern": {"type": "string"}},
                "required": ["pattern"],
            },
        },
    },
]


def make_handlers(sandbox: ForkdSandbox) -> dict:
    def run_bash(command: str) -> str:
        return sandbox.exec(command)

    def run_read(path: str, limit: int | None = None, offset: int = 0) -> str:
        return sandbox.read_file(path, limit=limit, offset=offset)

    def run_write(path: str, content: str) -> str:
        return sandbox.write_file(path, content)

    def run_edit(path: str, old_text: str, new_text: str) -> str:
        escaped_old = old_text.replace("'", "'\\''")
        escaped_new = new_text.replace("'", "'\\''")
        cmd = f'python3 -c \'import sys; text = open("{path}").read(); text = text.replace("{escaped_old}", "{escaped_new}", 1); open("{path}", "w").write(text)\''
        return sandbox.exec(cmd)

    def run_glob(pattern: str) -> str:
        return sandbox.glob(pattern)

    return {
        "bash": run_bash,
        "read_file": run_read,
        "write_file": run_write,
        "edit_file": run_edit,
        "glob": run_glob,
    }
