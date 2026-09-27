"""Validation policy for commands requested by an agent."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence


class CommandRejected(ValueError):
    """Raised when a requested command violates the sandbox policy."""


@dataclass(frozen=True)
class CommandPolicy:
    """Small allowlist and input limits applied before Docker execution."""

    allowed_programs: frozenset[str] = field(
        default_factory=lambda: frozenset(
            {"cat", "find", "ls", "pwd", "python", "python3", "pytest", "rg"}
        )
    )
    max_arguments: int = 100
    max_argument_chars: int = 10_000
    max_timeout_seconds: float = 60.0

    def validate(self, command: Sequence[str], timeout_seconds: float) -> tuple[str, ...]:
        """Return an immutable command after validating it."""
        if not command:
            raise CommandRejected("A command is required")

        program = command[0]
        if program not in self.allowed_programs:
            allowed = ", ".join(sorted(self.allowed_programs))
            raise CommandRejected(f"Program '{program}' is not allowed. Allowed: {allowed}")

        if len(command) - 1 > self.max_arguments:
            raise CommandRejected(f"A command may have at most {self.max_arguments} arguments")

        for argument in command:
            if not isinstance(argument, str):
                raise CommandRejected("Every command argument must be a string")
            if "\x00" in argument:
                raise CommandRejected("Command arguments cannot contain null bytes")
            if len(argument) > self.max_argument_chars:
                raise CommandRejected(
                    f"Each command argument must be at most {self.max_argument_chars} characters"
                )

        if not 0 < timeout_seconds <= self.max_timeout_seconds:
            raise CommandRejected(
                f"Timeout must be between 0 and {self.max_timeout_seconds:g} seconds"
            )

        return tuple(command)
