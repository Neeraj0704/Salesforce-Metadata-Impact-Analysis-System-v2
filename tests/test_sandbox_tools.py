"""Tests for the framework-neutral agent tool adapter."""

import unittest
from unittest.mock import Mock

from src.sandbox.controller import CommandResult
from src.sandbox.tools import SandboxToolAdapter


class SandboxToolAdapterTests(unittest.TestCase):
    def test_returns_serializable_command_result(self) -> None:
        manager = Mock()
        manager.execute.return_value = CommandResult(0, "hello\n", "")
        adapter = SandboxToolAdapter(manager, "abcdef123456")

        result = adapter.run_sandbox_command(
            program="python",
            arguments=["script.py"],
            timeout_seconds=12,
        )

        manager.execute.assert_called_once_with(
            "abcdef123456",
            ["python", "script.py"],
            timeout_seconds=12,
        )
        self.assertEqual(
            result,
            {"exit_code": 0, "succeeded": True, "stdout": "hello\n", "stderr": ""},
        )


if __name__ == "__main__":
    unittest.main()
