from unittest.mock import patch, MagicMock
import json
import pytest

from sandbox.subagent import (
    spawn_subagent_sandboxed,
    extract_text,
    has_tool_use,
)


@pytest.fixture
def mock_sandbox():
    sb = MagicMock()
    sb.exec.return_value = "command output"
    sb.read_file.return_value = "file content"
    sb.write_file.return_value = ""
    sb.glob.return_value = "a.py\nb.py"
    return sb


@pytest.fixture
def mock_pool():
    pool = MagicMock()
    pool.acquire.return_value = MagicMock()
    return pool


def make_mock_message(content: str, tool_calls: list | None = None):
    msg = MagicMock()
    msg.content = content
    if tool_calls:
        calls = []
        for tc in tool_calls:
            call = MagicMock()
            call.id = tc.get("id", "call_1")
            call.function.name = tc["name"]
            call.function.arguments = json.dumps(tc.get("args", {}))
            call.model_dump.return_value = {
                "id": call.id,
                "type": "function",
                "function": {
                    "name": call.function.name,
                    "arguments": call.function.arguments,
                },
            }
            calls.append(call)
        msg.tool_calls = calls
    else:
        msg.tool_calls = None
    return msg


def make_choice(message):
    choice = MagicMock()
    choice.message = message
    return choice


def make_response(choices):
    resp = MagicMock()
    resp.choices = choices
    return resp


class TestSubagentHelpers:
    def test_extract_text_from_string(self):
        assert extract_text("hello") == "hello"

    def test_extract_text_from_list(self):
        data = [{"type": "text", "text": "hello world"}]
        assert extract_text(data) == "hello world"

    def test_extract_text_from_non_text(self):
        assert extract_text(42) == "42"

    def test_has_tool_use_true(self):
        msg = make_mock_message(
            "", [{"name": "bash", "args": {"command": "ls"}, "id": "c1"}]
        )
        assert has_tool_use(msg) is True

    def test_has_tool_use_false(self):
        msg = make_mock_message("done", None)
        assert has_tool_use(msg) is False


class TestSpawnSubagentSandboxed:
    @patch("sandbox.subagent.trigger_hooks", return_value=None)
    @patch("sandbox.subagent.client")
    def test_returns_final_summary(self, mock_client, mock_hooks, mock_sandbox):
        resp = make_response([make_choice(make_mock_message("final summary", None))])
        mock_client.chat.completions.create.return_value = resp

        result = spawn_subagent_sandboxed("do something", sandbox=mock_sandbox)

        assert result == "final summary"

    @patch("sandbox.subagent.trigger_hooks", return_value=None)
    @patch("sandbox.subagent.client")
    def test_routes_bash_to_sandbox_exec(self, mock_client, mock_hooks, mock_sandbox):
        mock_response = make_response(
            [
                make_choice(
                    make_mock_message(
                        "",
                        [
                            {
                                "name": "bash",
                                "args": {"command": "echo hello"},
                                "id": "c1",
                            },
                        ],
                    )
                ),
            ]
        )
        mock_client.chat.completions.create.side_effect = [
            mock_response,
            make_response([make_choice(make_mock_message("done", None))]),
        ]

        result = spawn_subagent_sandboxed("run command", sandbox=mock_sandbox)

        mock_sandbox.exec.assert_called_once_with("echo hello")
        assert result == "done"

    @patch("sandbox.subagent.trigger_hooks", return_value=None)
    @patch("sandbox.subagent.client")
    def test_routes_read_file_to_sandbox(self, mock_client, mock_hooks, mock_sandbox):
        mock_response = make_response(
            [
                make_choice(
                    make_mock_message(
                        "",
                        [
                            {
                                "name": "read_file",
                                "args": {"path": "/tmp/x.txt"},
                                "id": "c1",
                            },
                        ],
                    )
                ),
            ]
        )
        mock_client.chat.completions.create.side_effect = [
            mock_response,
            make_response([make_choice(make_mock_message("done", None))]),
        ]

        spawn_subagent_sandboxed("read file", sandbox=mock_sandbox)

        mock_sandbox.read_file.assert_called_once_with(
            "/tmp/x.txt", limit=None, offset=0
        )

    @patch("sandbox.subagent.trigger_hooks", return_value=None)
    @patch("sandbox.subagent.client")
    def test_routes_write_file_to_sandbox(self, mock_client, mock_hooks, mock_sandbox):
        mock_response = make_response(
            [
                make_choice(
                    make_mock_message(
                        "",
                        [
                            {
                                "name": "write_file",
                                "args": {"path": "/tmp/x.txt", "content": "hello"},
                                "id": "c1",
                            },
                        ],
                    )
                ),
            ]
        )
        mock_client.chat.completions.create.side_effect = [
            mock_response,
            make_response([make_choice(make_mock_message("done", None))]),
        ]

        spawn_subagent_sandboxed("write file", sandbox=mock_sandbox)

        mock_sandbox.write_file.assert_called_once_with("/tmp/x.txt", "hello")

    @patch("sandbox.subagent.trigger_hooks", return_value=None)
    @patch("sandbox.subagent.client")
    def test_routes_glob_to_sandbox(self, mock_client, mock_hooks, mock_sandbox):
        mock_response = make_response(
            [
                make_choice(
                    make_mock_message(
                        "",
                        [
                            {"name": "glob", "args": {"pattern": "*.py"}, "id": "c1"},
                        ],
                    )
                ),
            ]
        )
        mock_client.chat.completions.create.side_effect = [
            mock_response,
            make_response([make_choice(make_mock_message("done", None))]),
        ]

        spawn_subagent_sandboxed("glob", sandbox=mock_sandbox)

        mock_sandbox.glob.assert_called_once_with("*.py")

    @patch("sandbox.subagent.trigger_hooks", return_value=None)
    @patch("sandbox.subagent.client")
    def test_respects_tool_limit_30(self, mock_client, mock_hooks, mock_sandbox):
        responses = []
        for _ in range(31):
            responses.append(
                make_response(
                    [
                        make_choice(
                            make_mock_message(
                                "",
                                [
                                    {
                                        "name": "bash",
                                        "args": {"command": "ls"},
                                        "id": "c1",
                                    },
                                ],
                            )
                        ),
                    ]
                )
            )
        mock_client.chat.completions.create.side_effect = responses

        result = spawn_subagent_sandboxed("loop", sandbox=mock_sandbox)

        assert "without a text summary" in result

    @patch("sandbox.subagent.trigger_hooks", return_value=None)
    @patch("sandbox.subagent.client")
    def test_creates_and_closes_own_sandbox(self, mock_client, mock_hooks):
        pool = MagicMock()
        sandbox = MagicMock()
        pool.acquire.return_value = sandbox

        mock_client.chat.completions.create.return_value = make_response(
            [make_choice(make_mock_message("done", None))]
        )

        spawn_subagent_sandboxed("task", pool=pool)

        pool.acquire.assert_called_once()
        sandbox.close.assert_called_once()

    @patch("sandbox.subagent.trigger_hooks", return_value=None)
    @patch("sandbox.subagent.client")
    def test_reuses_provided_sandbox(self, mock_client, mock_hooks, mock_sandbox):
        mock_client.chat.completions.create.return_value = make_response(
            [make_choice(make_mock_message("done", None))]
        )

        spawn_subagent_sandboxed("task", sandbox=mock_sandbox)

        mock_sandbox.close.assert_not_called()

    @patch("sandbox.subagent.trigger_hooks", return_value=None)
    @patch("sandbox.subagent.client")
    def test_handles_unknown_tool_gracefully(
        self, mock_client, mock_hooks, mock_sandbox
    ):
        msg = make_mock_message(
            "",
            [
                {"name": "nonexistent_tool", "args": {}, "id": "c1"},
            ],
        )
        mock_client.chat.completions.create.side_effect = [
            make_response([make_choice(msg)]),
            make_response([make_choice(make_mock_message("done", None))]),
        ]

        result = spawn_subagent_sandboxed("run", sandbox=mock_sandbox)
        assert result == "done"

    @patch("sandbox.subagent.trigger_hooks")
    @patch("sandbox.subagent.client")
    def test_hook_can_block_tool(self, mock_client, mock_hooks, mock_sandbox):
        mock_hooks.side_effect = lambda *args: (
            "Blocked by hook" if args[0] == "PreToolUse" else None
        )

        msg = make_mock_message(
            "",
            [
                {"name": "bash", "args": {"command": "rm -rf /"}, "id": "c1"},
            ],
        )
        mock_client.chat.completions.create.side_effect = [
            make_response([make_choice(msg)]),
            make_response([make_choice(make_mock_message("done", None))]),
        ]

        spawn_subagent_sandboxed("run", sandbox=mock_sandbox)
        mock_sandbox.exec.assert_not_called()

    @patch("sandbox.subagent.trigger_hooks")
    @patch("sandbox.subagent.client")
    def test_sandbox_error_returns_message(self, mock_client, mock_hooks):
        pool = MagicMock()
        pool.acquire.side_effect = RuntimeError("forkd not available")

        result = spawn_subagent_sandboxed("task", pool=pool)

        assert "forkd not available" in result
