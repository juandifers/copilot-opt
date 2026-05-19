"""Unit tests for the backend abstraction layer.

These are pure unit tests — they do NOT make API calls or invoke the
claude CLI.  They verify the interface contract and safety invariants.

Run with:
    python experiment/src/test_backends.py
or:
    python -m pytest experiment/src/test_backends.py -v
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

# Add experiment/src to path so backends module is importable.
_SRC = Path(__file__).resolve().parent
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from backends.base import HaltError, ModelBackend, ModelResponse
from backends import get_backend
from backends.claude_code import _assert_no_bare, _run_subprocess


class TestModelResponseDataclass(unittest.TestCase):

    def test_response_dataclass_fields_complete(self) -> None:
        """ModelResponse must have all 8 required fields with correct types."""
        r = ModelResponse(
            answer_text="42 vehicles",
            structured_output={"answer_text": "42 vehicles", "claimed_objective": 42.0},
            raw_response={"id": "msg_abc"},
            model_version="claude-haiku-4-5-20251001",
            input_tokens=100,
            output_tokens=50,
            latency_ms=1200,
            backend_name="api",
        )
        self.assertIsInstance(r.answer_text, str)
        self.assertIsInstance(r.structured_output, dict)
        self.assertIsInstance(r.raw_response, dict)
        self.assertIsInstance(r.model_version, str)
        self.assertIsInstance(r.input_tokens, int)
        self.assertIsInstance(r.output_tokens, int)
        self.assertIsInstance(r.latency_ms, int)
        self.assertIsInstance(r.backend_name, str)

    def test_response_structured_output_can_be_none(self) -> None:
        r = ModelResponse(
            answer_text="",
            structured_output=None,
            raw_response={},
            model_version="claude-haiku-4-5",
            input_tokens=0,
            output_tokens=0,
            latency_ms=0,
            backend_name="claude-code",
        )
        self.assertIsNone(r.structured_output)


class TestClaudeCodeCommandAssertions(unittest.TestCase):

    def test_bare_flag_rejected(self) -> None:
        """--bare must be rejected by _assert_no_bare."""
        cmd_with_bare = ["claude", "-p", "--bare", "--model", "claude-haiku-4-5"]
        with self.assertRaises(HaltError) as ctx:
            _assert_no_bare(cmd_with_bare)
        self.assertIn("--bare", str(ctx.exception))

    def test_bare_flag_absent_passes(self) -> None:
        """Command without --bare must pass the assertion."""
        cmd_no_bare = [
            "claude", "-p",
            "--model", "claude-haiku-4-5",
            "--system-prompt-file", "/tmp/sp.txt",
            "--output-format", "json",
            "--json-schema", "{}",
            "--allowedTools", "",
        ]
        _assert_no_bare(cmd_no_bare)  # Must not raise.

    def test_command_includes_required_flags(self) -> None:
        """Verify _run_subprocess builds the correct command shape.

        We mock out the subprocess call by inspecting what flags are present
        in the constructed command via a temporary spy.
        """
        import subprocess as _sp
        import tempfile

        captured_cmd: list[list[str]] = []
        original_run = _sp.run

        def _spy_run(cmd, **kwargs):
            captured_cmd.append(list(cmd))
            class _FakeResult:
                returncode = 0
                stdout = '{"result": "{}", "modelUsage": {"claude-haiku-4-5-20251001": {"input_tokens": 10, "output_tokens": 5}}, "usage": {"input_tokens": 10, "output_tokens": 5}}'
                stderr = ""
            return _FakeResult()

        _sp.run = _spy_run
        try:
            with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as tf:
                tf.write(b"test system prompt")
                sp_path = Path(tf.name)
            try:
                _run_subprocess(
                    model="claude-haiku-4-5",
                    system_prompt_path=sp_path,
                    json_schema={"type": "object"},
                    user_message="test",
                    timeout_s=5,
                )
            except Exception:
                pass  # May fail on JSON parse; we only care about the cmd.
        finally:
            _sp.run = original_run
            sp_path.unlink(missing_ok=True)

        self.assertTrue(captured_cmd, "spy was not called")
        cmd = captured_cmd[0]

        self.assertNotIn("--bare", cmd, "--bare must not appear in the command")
        self.assertIn("--allowedTools", cmd, "--allowedTools must be present")
        self.assertIn("--model", cmd, "--model must be present")
        self.assertIn("--system-prompt-file", cmd,
                      "--system-prompt-file must be used (not --append-system-prompt-file)")
        self.assertNotIn("--append-system-prompt-file", cmd,
                         "--append-system-prompt-file is not the locked shape")
        self.assertIn("-p", cmd, "-p (print) flag must be present")


class TestAPIBackendNoKeyHalts(unittest.TestCase):

    def test_api_backend_no_api_key_raises_halt_error(self) -> None:
        """APIBackend() with ANTHROPIC_API_KEY unset must raise HaltError."""
        import os
        original = os.environ.pop("ANTHROPIC_API_KEY", None)
        try:
            from backends.api import APIBackend
            with self.assertRaises(HaltError) as ctx:
                APIBackend()
            self.assertIn("ANTHROPIC_API_KEY", str(ctx.exception))
        finally:
            if original is not None:
                os.environ["ANTHROPIC_API_KEY"] = original

    def test_api_backend_empty_key_raises_halt_error(self) -> None:
        import os
        original = os.environ.get("ANTHROPIC_API_KEY")
        os.environ["ANTHROPIC_API_KEY"] = ""
        try:
            from backends.api import APIBackend
            with self.assertRaises(HaltError) as ctx:
                APIBackend()
            self.assertIn("ANTHROPIC_API_KEY", str(ctx.exception))
        finally:
            if original is not None:
                os.environ["ANTHROPIC_API_KEY"] = original
            else:
                os.environ.pop("ANTHROPIC_API_KEY", None)


class TestGetBackendDispatch(unittest.TestCase):

    def test_claude_code_returns_correct_class(self) -> None:
        from backends.claude_code import ClaudeCodeBackend
        backend = get_backend("claude-code")
        self.assertIsInstance(backend, ClaudeCodeBackend)
        self.assertEqual(backend.name(), "claude-code")

    def test_api_returns_correct_class(self) -> None:
        import os
        original = os.environ.get("ANTHROPIC_API_KEY")
        os.environ["ANTHROPIC_API_KEY"] = "sk-ant-test00000000fake0000fake"
        try:
            from backends.api import APIBackend
            backend = get_backend("api")
            self.assertIsInstance(backend, APIBackend)
            self.assertEqual(backend.name(), "api")
        finally:
            if original is not None:
                os.environ["ANTHROPIC_API_KEY"] = original
            else:
                os.environ.pop("ANTHROPIC_API_KEY", None)

    def test_unknown_backend_raises_value_error(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            get_backend("foo")
        self.assertIn("foo", str(ctx.exception))
        self.assertIn("claude-code", str(ctx.exception))
        self.assertIn("api", str(ctx.exception))

    def test_claude_code_is_model_backend(self) -> None:
        backend = get_backend("claude-code")
        self.assertIsInstance(backend, ModelBackend)


class TestAPIKeyFingerprint(unittest.TestCase):

    def test_fingerprint_never_exposes_full_key(self) -> None:
        import os
        from backends.api import _fingerprint

        key = "sk-ant-api03-ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        fp = _fingerprint(key)
        self.assertNotEqual(fp, key)
        self.assertIn("...", fp)
        self.assertTrue(fp.startswith(key[:8]))
        self.assertTrue(fp.endswith(key[-4:]))
        self.assertLess(len(fp), len(key))

    def test_fingerprint_short_key(self) -> None:
        from backends.api import _fingerprint
        self.assertEqual(_fingerprint("short"), "***")


if __name__ == "__main__":
    unittest.main(verbosity=2)
