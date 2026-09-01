"""Capability-limited tool sandbox boundary."""

from __future__ import annotations

import asyncio
import os
import signal
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class SandboxPolicy:
    """Explicit allowlist for commands and execution budgets."""

    allowed_commands: frozenset[str] = frozenset()
    timeout_s: float = 10.0
    max_output_bytes: int = 64_000


class Sandbox(Protocol):
    async def execute(self, command: str, args: list[str], *, policy: SandboxPolicy) -> str:
        """Execute one allowlisted command."""


class LocalSandbox:
    """Reference sandbox; disabled unless a command is explicitly allowlisted."""

    async def execute(self, command: str, args: list[str], *, policy: SandboxPolicy) -> str:
        if command not in policy.allowed_commands:
            raise PermissionError(f"sandbox command is not allowed: {command}")
        if policy.timeout_s <= 0 or policy.max_output_bytes <= 0:
            raise ValueError("sandbox limits must be positive")
        process = await asyncio.create_subprocess_exec(
            command,
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env={"PATH": "/usr/local/bin:/usr/bin:/bin"},
            start_new_session=True,
        )

        async def collect() -> tuple[bytes, bool]:
            output = bytearray()
            assert process.stdout is not None
            while chunk := await process.stdout.read(8192):
                output.extend(chunk)
                if len(output) > policy.max_output_bytes:
                    return bytes(output[: policy.max_output_bytes]), True
            return bytes(output), False

        def terminate() -> None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass

        async def terminate_and_wait() -> None:
            terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=1.0)
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()

        try:
            deadline = asyncio.get_running_loop().time() + policy.timeout_s
            output, exceeded = await asyncio.wait_for(
                collect(),
                policy.timeout_s,
            )
            if exceeded:
                await terminate_and_wait()
                raise ValueError("sandbox command exceeded its output limit")
            remaining = deadline - asyncio.get_running_loop().time()
            await asyncio.wait_for(process.wait(), max(0.001, remaining))
            return output.decode("utf-8", errors="replace")
        except asyncio.TimeoutError:
            await terminate_and_wait()
            raise TimeoutError("sandbox command exceeded its timeout") from None


__all__ = ["LocalSandbox", "Sandbox", "SandboxPolicy"]
