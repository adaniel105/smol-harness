import json
import urllib.request
import urllib.error
from pathlib import Path
from config.config import (
    FORKD_CONTROLLER_URL,
    FORKD_SNAPSHOT_TAG,
    FORKD_DEFAULT_MEMORY_MB,
    FORKD_DEFAULT_TIMEOUT,
    FORKD_TOKEN
)


class ForkdSandbox:
    def __init__(self, pool: "ForkdSandboxPool", sandbox_id: str):
        self._pool = pool
        self.sandbox_id = sandbox_id
        self._closed = False

    def _request(self, method: str, path: str, **kwargs) -> dict:
        return self._pool._request(method, path, **kwargs)

    def exec(self, command: str, timeout: int | None = None) -> str:
        timeout = timeout or FORKD_DEFAULT_TIMEOUT
        body = {"command": command, "timeout": timeout}
        resp = self._request("POST", f"/v1/sandboxes/{self.sandbox_id}/exec", json=body)
        parts = [resp.get("stdout", "")]
        stderr = resp.get("stderr", "")
        if stderr:
            parts.append(stderr)
        return "\n".join(parts).strip()

    def read_file(self, path: str, limit: int | None = None, offset: int = 0) -> str:
        escaped = path.replace("'", "'\\''")
        content = self.exec(f"cat '{escaped}'")
        lines = content.splitlines(keepends=True)
        start = max(int(offset), 0)
        if limit is not None:
            limit = int(limit)
            selected = lines[start : start + limit]
            if limit < len(lines) - start:
                selected.append(f"... ({len(lines) - start - limit} more lines)")
        else:
            selected = lines[start:]
        return "".join(selected).rstrip("\n")

    def write_file(self, path: str, content: str) -> str:
        parent = str(Path(path).parent)
        escaped_parent = parent.replace("'", "'\\''")
        self.exec(f"mkdir -p '{escaped_parent}'")
        self.exec(
            f"python3 -c 'import sys; sys.stdout.write({json.dumps(content)})' > {json.dumps(path)}"
        )
        return ""

    def glob(self, pattern: str) -> str:
        code = (
            "import glob, os; "
            f"results = glob.glob({json.dumps(pattern)}); "
            "print('\\n'.join(results))"
        )
        return self.exec(f"python3 -c {json.dumps(code)}")

    def close(self):
        if not self._closed:
            self._closed = True
            self._pool.release(self)


class ForkdSandboxPool:
    def __init__(
        self, controller_url: str | None = None, auth_token: str | None = FORKD_TOKEN
    ):
        self.controller_url = (controller_url or FORKD_CONTROLLER_URL).rstrip("/")
        self.auth_token = auth_token
        self._active: list[ForkdSandbox] = []

    def _request(self, method: str, path: str, **kwargs) -> dict:
        url = f"{self.controller_url}{path}"
        data = None
        if "json" in kwargs:
            data = json.dumps(kwargs["json"]).encode("utf-8")
        headers = {"Content-Type": "application/json"} if data else {}
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = resp.read().decode("utf-8")
                return json.loads(body) if body else {}
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"forkd HTTP {e.code}: {body}") from e
        except urllib.error.URLError as e:
            raise RuntimeError(f"forkd controller unreachable: {e.reason}") from e

    def acquire(
        self, tag: str | None = None, memory_mb: int | None = None
    ) -> ForkdSandbox:
        body = {}
        if tag:
            body["snapshot_tag"] = tag
        else:
            body["snapshot_tag"] = FORKD_SNAPSHOT_TAG
        body["memory_mb"] = memory_mb or FORKD_DEFAULT_MEMORY_MB
        resp = self._request("POST", "/v1/sandboxes", json=body)
        sandbox_id = resp.get("id")
        if not sandbox_id:
            raise RuntimeError(f"forkd did not return a sandbox id: {resp}")
        sb = ForkdSandbox(self, sandbox_id=sandbox_id)
        self._active.append(sb)
        return sb

    def release(self, sandbox: ForkdSandbox):
        sandbox._closed = True
        if sandbox in self._active:
            self._active.remove(sandbox)
        try:
            self._request("DELETE", f"/v1/sandboxes/{sandbox.sandbox_id}")
        except RuntimeError:
            pass

    def close_all(self):
        for sb in list(self._active):
            sb.close()
        self._active.clear()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close_all()