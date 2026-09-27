"""Tests for agent command validation."""

import unittest

from src.sandbox.policy import CommandPolicy, CommandRejected


class CommandPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = CommandPolicy()

    def test_allows_argument_vector_for_known_program(self) -> None:
        command = self.policy.validate(["python", "script.py"], 30)
        self.assertEqual(command, ("python", "script.py"))

    def test_rejects_unknown_program(self) -> None:
        with self.assertRaisesRegex(CommandRejected, "not allowed"):
            self.policy.validate(["docker", "ps"], 30)

    def test_rejects_excessive_timeout(self) -> None:
        with self.assertRaisesRegex(CommandRejected, "between 0 and 60"):
            self.policy.validate(["pwd"], 61)


if __name__ == "__main__":
    unittest.main()
