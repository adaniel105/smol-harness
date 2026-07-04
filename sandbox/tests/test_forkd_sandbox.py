from unittest.mock import patch, MagicMock
import pytest
from sandbox.forkd_sandbox import ForkdSandbox, ForkdSandboxPool


class TestForkdSandbox:
    def test_create_sandbox(self):
        pool = MagicMock(spec=ForkdSandboxPool)
        pool.controller_url = "http://127.0.0.1:8889"
        pool.auth_token = None

        sandbox = ForkdSandbox(pool, sandbox_id="sbx_test1")

        assert sandbox.sandbox_id == "sbx_test1"
        assert sandbox._pool is pool

    def test_exec_returns_output(self):
        pool = MagicMock(spec=ForkdSandboxPool)
        sandbox = ForkdSandbox(pool, sandbox_id="sbx_test1")

        with patch.object(sandbox, "_request") as mock_req:
            mock_req.return_value = {
                "stdout": "hello world\n",
                "stderr": "",
                "exit_code": 0,
            }
            result = sandbox.exec("echo hello world")

            mock_req.assert_called_once_with(
                "POST",
                "/v1/sandboxes/sbx_test1/exec",
                json={"command": "echo hello world", "timeout": 120},
            )
            assert result == "hello world"

    def test_exec_with_exit_code_error(self):
        pool = MagicMock(spec=ForkdSandboxPool)
        sandbox = ForkdSandbox(pool, sandbox_id="sbx_test1")

        with patch.object(sandbox, "_request") as mock_req:
            mock_req.return_value = {
                "stdout": "",
                "stderr": "command not found",
                "exit_code": 127,
            }
            result = sandbox.exec("nonexistent")

            assert "command not found" in result

    def test_exec_respects_custom_timeout(self):
        pool = MagicMock(spec=ForkdSandboxPool)
        sandbox = ForkdSandbox(pool, sandbox_id="sbx_test1")

        with patch.object(sandbox, "_request") as mock_req:
            mock_req.return_value = {"stdout": "done", "stderr": "", "exit_code": 0}
            sandbox.exec("sleep 5", timeout=10)

            mock_req.assert_called_once_with(
                "POST",
                "/v1/sandboxes/sbx_test1/exec",
                json={"command": "sleep 5", "timeout": 10},
            )

    def test_read_file_via_exec(self):
        pool = MagicMock(spec=ForkdSandboxPool)
        sandbox = ForkdSandbox(pool, sandbox_id="sbx_test1")

        with patch.object(sandbox, "exec") as mock_exec:
            mock_exec.return_value = "file content"
            result = sandbox.read_file("/tmp/test.txt")

            mock_exec.assert_called_once_with("cat '/tmp/test.txt'")
            assert result == "file content"

    def test_read_file_with_limit_offset(self):
        pool = MagicMock(spec=ForkdSandboxPool)
        sandbox = ForkdSandbox(pool, sandbox_id="sbx_test1")

        with patch.object(sandbox, "exec") as mock_exec:
            mock_exec.return_value = "line1\nline2\nline3"
            result = sandbox.read_file("/tmp/test.txt", limit=2, offset=1)

            mock_exec.assert_called_once_with("cat '/tmp/test.txt'")
            assert result == "line2\nline3"

    def test_write_file_via_exec(self):
        pool = MagicMock(spec=ForkdSandboxPool)
        sandbox = ForkdSandbox(pool, sandbox_id="sbx_test1")

        with patch.object(sandbox, "exec") as mock_exec:
            mock_exec.return_value = ""
            result = sandbox.write_file("/tmp/test.txt", "hello world")

            assert "mkdir" in mock_exec.call_args_list[0][0][0]
            assert mock_exec.call_args_list[1][0][0].startswith("python3")
            assert "hello world" in mock_exec.call_args_list[1][0][0]
            assert result == ""

    def test_glob_via_exec(self):
        pool = MagicMock(spec=ForkdSandboxPool)
        sandbox = ForkdSandbox(pool, sandbox_id="sbx_test1")

        with patch.object(sandbox, "exec") as mock_exec:
            mock_exec.return_value = "a.py\nb.py\nc.py"
            result = sandbox.glob("*.py")

            mock_exec.assert_called_once()
            assert "glob" in mock_exec.call_args[0][0]
            assert result == "a.py\nb.py\nc.py"

    def test_close_calls_pool_release(self):
        pool = MagicMock(spec=ForkdSandboxPool)
        sandbox = ForkdSandbox(pool, sandbox_id="sbx_test1")
        sandbox.close()
        pool.release.assert_called_once_with(sandbox)


class TestForkdSandboxPool:
    def test_default_config(self):
        pool = ForkdSandboxPool()
        assert pool.controller_url == "http://127.0.0.1:8889"
        assert pool.auth_token is None

    def test_acquire_returns_sandbox(self):
        pool = ForkdSandboxPool()

        with patch.object(pool, "_request") as mock_req:
            mock_req.return_value = {"id": "sbx_abc123"}

            sandbox = pool.acquire()

            assert isinstance(sandbox, ForkdSandbox)
            assert sandbox.sandbox_id == "sbx_abc123"
            mock_req.assert_called_once()

    def test_acquire_sends_snapshot_tag_and_resources(self):
        pool = ForkdSandboxPool()

        with patch.object(pool, "_request") as mock_req:
            mock_req.return_value = {"id": "sbx_def456"}

            _ = pool.acquire(tag="my-snapshot", memory_mb=1024)

            mock_req.assert_called_once_with(
                "POST",
                "/v1/sandboxes",
                json={"snapshot_tag": "my-snapshot", "memory_mb": 1024},
            )

    def test_acquire_raises_on_failure(self):
        pool = ForkdSandboxPool()

        with patch.object(pool, "_request") as mock_req:
            mock_req.side_effect = RuntimeError("Controller unavailable")
            with pytest.raises(RuntimeError, match="Controller unavailable"):
                pool.acquire()

    def test_release_marks_sandbox_closed(self):
        pool = ForkdSandboxPool()
        sandbox = MagicMock(spec=ForkdSandbox)
        sandbox.sandbox_id = "sbx_test1"
        sandbox._closed = False

        pool.release(sandbox)

        assert sandbox._closed is True

    def test_close_all_releases_all_active(self):
        pool = ForkdSandboxPool()
        s1 = MagicMock(spec=ForkdSandbox)
        s1.sandbox_id = "sbx_1"
        s2 = MagicMock(spec=ForkdSandbox)
        s2.sandbox_id = "sbx_2"

        pool._active = [s1, s2]
        pool.close_all()

        s1.close.assert_called_once()
        s2.close.assert_called_once()
        assert pool._active == []
