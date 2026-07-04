# forkd Integration — Sandboxed Subagent Execution

## What is forkd?

[forkd](https://github.com/deeplethe/forkd) (v0.5.2) is a **microVM sandbox runtime for AI agent fan-out**, built on AWS Firecracker (KVM). It "forks" children from a warmed parent snapshot, sharing its address space copy-on-write — similar to `fork(2)` but for microVMs.

- **Language:** Rust (4 crates: `forkd-vmm`, `forkd-cli`, `forkd-controller`, `forkd-uffd`)
- **License:** Apache 2.0
- **Status:** Alpha (pre-1.0)

## Why integrate forkd?

The project's README already states: *"sandboxing for agent fan out using `forkd()`"*. Currently, `spawn_subagent` runs subagents in-process with zero OS-level isolation — just message history isolation. forkd adds:

| Layer | Current | With forkd |
|---|---|---|
| Process | Same process (in-process LLM loop) | Separate Firecracker microVM |
| Filesystem | Shared host filesystem | Overlayfs (shared lower + per-child upper) |
| Network | Host network | Per-child network namespace |
| Memory | Unlimited | cgroup v2 `memory.max` |
| Kernel | Host kernel | Guest kernel (vmlinux-6.1.141, fixed) |
| Seccomp | None | Firecracker built-in seccomp filters |

## Architecture

```
User prompt
    │
    ▼
┌──────────────────────────────┐
│    agent_loop (host)         │
│  ┌────────────────────────┐  │
│  │ task tool              │  │
│  │ → spawn_subagent       │  │
│  │ → spawn_subagent_sbx() │──┼────► ForkdSandboxPool.acquire()
│  └────────────────────────┘  │         │
└──────────────────────────────┘         │
                                          ▼
                               ┌──────────────────────┐
                               │  ForkdSandbox         │
                               │  (Firecracker microVM)│
                               │  ┌────────────────┐  │
                               │  │ LLM API call   │  │
                               │  │ (host, via     │  │
                               │  │  OpenAI SDK)   │  │
                               │  │                │  │
                               │  │ Tool execution │  │
                               │  │ → sandbox.exec │  │
                               │  │ → sandbox.read │  │
                               │  │ → sandbox.write│  │
                               │  └────────────────┘  │
                               └──────────────────────┘
```

The LLM API call remains on the host (it needs internet access). Only **tool execution** (bash, file ops) runs inside the sandbox.

## Integration Points

### 1. `ForkdSandbox` — per-microVM wrapper

Wraps forkd's REST API (`http://127.0.0.1:8889`):

```
POST /v1/sandboxes           → acquire() — fork a child from snapshot
POST /v1/sandboxes/:id/exec  → exec() — run command, get stdout/stderr
DELETE /v1/sandboxes/:id     → release() — destroy sandbox
```

### 2. `ForkdSandboxPool` — lifecycle manager

- `acquire(tag, memory_mb)` → `ForkdSandbox`
- `release(sandbox)` → destroy and remove from active set
- `close_all()` → clean shutdown
- Context manager support (`with ForkdSandboxPool() as pool:`)

### 3. `spawn_subagent_sandboxed` — sandboxed LLM loop

Same logic as the original `spawn_subagent` but tool handlers are routed through the sandbox:

| Original | Sandboxed |
|---|---|
| `run_bash(cmd)` → `subprocess.run` on host | `sandbox.exec(cmd)` via REST to microVM |
| `run_read(path)` → host filesystem | `sandbox.read_file(path)` via exec `cat` |
| `run_write(path, content)` → host filesystem | `sandbox.write_file(path, content)` via exec `python3 -c "..."` |
| `run_edit(path, old, new)` → host filesystem | `sandbox.exec(python3 -c "sed script")` |
| `run_glob(pattern)` → host filesystem | `sandbox.glob(pattern)` via exec `python3 -c "glob..."` |

## Files Created

### `sandbox/` (self-contained package)

| File | Purpose |
|---|---|
| `__init__.py` | Public API re-exports |
| `config.py` | Env-driven config (`FORKD_CONTROLLER_URL`, `FORKD_SNAPSHOT_TAG`, etc.) |
| `forkd_sandbox.py` | `ForkdSandbox` + `ForkdSandboxPool` — REST wrapper over forkd daemon |
| `subagent.py` | `spawn_subagent_sandboxed` — LLM loop with sandboxed tool dispatch |
| `tools.py` | Sandboxed tool schemas + `make_handlers(sandbox)` factory |
| `tests/__init__.py` | Test package |
| `tests/test_forkd_sandbox.py` | 15 tests for sandbox + pool |
| `tests/test_subagent.py` | 16 tests for subagent routing + lifecycle |

### `docs/integrations/forkd.md`

This file.

## Usage

```python
from sandbox import spawn_subagent_sandboxed

# Option 1: auto-manage sandbox
summary = spawn_subagent_sandboxed("Refactor the auth module")
print(summary)

# Option 2: reuse a pool
from sandbox import ForkdSandboxPool, spawn_subagent_sandboxed

pool = ForkdSandboxPool()
result1 = spawn_subagent_sandboxed("task 1", pool=pool)
result2 = spawn_subagent_sandboxed("task 2", pool=pool)
pool.close_all()

# Option 3: provide an existing sandbox
from sandbox import ForkdSandboxPool, spawn_subagent_sandboxed

pool = ForkdSandboxPool()
sb = pool.acquire(tag="my-snapshot", memory_mb=1024)
result = spawn_subagent_sandboxed("task", sandbox=sb)
sb.close()
```

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `FORKD_ENABLED` | `false` | Enable sandboxed subagents |
| `FORKD_CONTROLLER_URL` | `http://127.0.0.1:8889` | forkd daemon URL |
| `FORKD_SNAPSHOT_TAG` | `agent-harness-base` | Default snapshot tag |
| `FORKD_DEFAULT_MEMORY_MB` | `512` | Per-sandbox memory limit (MB) |
| `FORKD_DEFAULT_TIMEOUT` | `120` | Default exec timeout (seconds) |
| `FORKD_SANDBOX_POOL_SIZE` | `4` | Max concurrent sandboxes |

## Snapshot Setup (one-time)

```bash
# Install forkd and check prerequisites
forkd quickstart
forkd doctor                # verify KVM, cgroups, netns, etc.

# Build a base snapshot with Python 3.13
forkd from-image python:3.13-slim --tag agent-harness-base

# Or build from a running sandbox
forkd snapshot --from-sandbox <id> --live --tag agent-harness-base
```

## Dependencies

- **Host:** Linux x86_64 with KVM, cgroup v2, `ip` (iproute2)
- **forkd runtime:** `forkd` CLI + `forkd-controller` daemon
- **Python SDK:** `pip install forkd` (optional — sandbox uses REST directly)

## Design Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Sandbox lifecyle | 1 sandbox : 1 subagent (ephemeral) | Cleanest isolation; no shared state |
| File I/O | exec-based (cat/echo/python) | No need for SSHFS or 9p; simpler |
| LLM call location | Host | Requires internet; microVM netns may restrict |
| Config | Environment variables | Matches existing `.env` pattern |
| Error handling | Graceful fallback to error message | Subagent returns `[SandboxError]` if daemon unavailable |

## Test Suite

```bash
cd /path/to/project
source .venv/bin/activate
python -m pytest sandbox/tests/ -v
```

All tests mock forkd and the LLM client — no real sandbox or API calls.

## Future Work

- [ ] Add `sandboxed=True` parameter to the main `task` tool schema
- [ ] Pre-warm sandbox pool for faster subagent startup
- [ ] Per-subagent resource profiles (memory, CPU quota)
- [ ] Diff-snapshot chains for faster snapshot loading
- [ ] Live BRANCH for mid-execution checkpointing
- [ ] MCP connector for forkd sandbox management
