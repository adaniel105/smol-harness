# smol-harness
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Code style](https://img.shields.io/badge/code%20style-ruff-000000)](https://docs.astral.sh/ruff)

![design sketch](docs/image.png)

smol agent harness built atop OpenRouter, with out-of-the-box sandboxing capabilities for subagent management using [`forkd()`](https://github.com/deeplethe/forkd). 

## MicroVM Setup

smol-harness uses [`forkd()`](https://github.com/deeplethe/forkd) to sandbox subagents inside KVM-isolated microVMs. forkd is a microVM runtime built on [Firecracker](https://github.com/firecracker-microvm/firecracker), purpose-built for AI agent fan-out, spawning many short-lived sandboxes from a single warmed parent instead of cold-booting each one independently.

**How snapshot CoW works.** The parent VM boots once, imports your runtime (Python + dependencies, JIT-warmed JVM, loaded ML model, anything that's expensive to initialize), and is paused to disk as a snapshot. Each child is a separate Firecracker process that `mmap`s the parent's memory image with `MAP_PRIVATE`. The kernel implements copy-on-write at the page level: children share the parent's resident memory until they diverge, at which point only the modified pages are duplicated. The result is per-child KVM isolation with a spawn cost closer to `fork(2)` than to a cold-boot VM.

### Why forkd

| Project | Primitive | Cold-start (N=100) | Fork-from-warm | Memory / child | Isolation |
|---|---|---|---|---|---|
| **[forkd](https://github.com/deeplethe/forkd)** | Firecracker + snapshot CoW | **101 ms** | yes | 0.12 MiB | KVM |
| [CubeSandbox](https://github.com/TencentCloud/CubeSandbox) | RustVMM + KVM | 1.06 s | "coming soon" | <5 MiB | KVM |
| [E2B](https://github.com/e2b-dev/E2B) | Firecracker (managed) | not in OSS | no | platform | KVM |
| [BoxLite](https://github.com/boxlite-ai/boxlite) | KVM + Hypervisor.framework | 113 s | no | n/a | KVM + seccomp |
| Firecracker (raw) | microVM only | 759 ms | manual | 84 MiB | KVM |
| Docker (runc) | OCI container | 335 s | no | 4 MiB | namespace |
| gVisor (runsc) | userspace kernel | 289 s | no | n/a | userspace |

Numbers from [forkd's published benchmarks](https://github.com/deeplethe/forkd/tree/main/bench) on identical hardware (Ubuntu 24.04, 20 vCPU, 30 GiB, KVM). forkd's key advantage: children inherit the parent's warmed runtime (imports, JIT, model weights) through CoW at ~10 ms per spawn, while still getting a full Linux kernel per child, not a container namespace.

### Prerequisites

- x86_64 Linux with KVM enabled (`/dev/kvm` must exist)
- Ubuntu 22.04 or newer

### 1. Install forkd

Download the latest CLI + controller binaries:

```bash
curl -sSL https://github.com/deeplethe/forkd/releases/download/v0.5.2/forkd-v0.5.2-x86_64-linux.tar.gz \
  | sudo tar -xz -C /usr/local/bin/
```

### 2. Install the Python SDK

```bash
pip install forkd
```

### 3. Verify your install

`forkd doctor` runs 17 checks: KVM, hardware virt, cgroup v2, Firecracker binary, kernel image, controller reachability, and more. Fix anything it flags before continuing:

```bash
forkd doctor
```

All checks should pass green. If any fail, scripts are provided at source https://github.com/deeplethe/forkd to fix/navigate issues, such as follows in 4.

### 4. Set up host networking (one-time)

```bash
git clone https://github.com/deeplethe/forkd.git
cd forkd
sudo bash scripts/setup-host.sh          # KVM + tap device
sudo bash scripts/netns-setup.sh 3       # per-child network namespaces
```

### 5. Generate and export your token

The controller requires a bearer token for all API calls. Generate one and export it into your shell:

```bash
FORKD_TOKEN=$(openssl rand -hex 32)
export FORKD_TOKEN
export FORKD_CONTROLLER_URL="http://127.0.0.1:8889"
export FORKD_SNAPSHOT_TAG="agent-harness-base"
```

To persist across sessions, add the exports to your `~/.bashrc` or `~/.zshrc`.

## License
MIT
