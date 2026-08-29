"""Workspace abstraction for agent file operations.

The protocol keeps agent logic independent from the backing filesystem.
Implementations may use local disk, object storage, sandboxed storage, etc.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol


class WorkspaceError(RuntimeError):
    """Base workspace error."""


class WorkspacePathError(WorkspaceError):
    """Raised when a workspace path is invalid or escapes the workspace."""


class WorkspaceBackend(Protocol):
    """Backend contract for agent workspace operations."""

    def read(self, path: str) -> str:
        """Read a UTF-8 text file."""
        ...

    def write(
        self,
        path: str,
        content: str,
    ) -> None:
        """Write a UTF-8 text file."""
        ...

    def list(self, path: str = ".") -> list[str]:
        """List entries below a workspace path."""
        ...


class LocalWorkspace:
    """
    Sandboxed local filesystem implementation.

    All paths are resolved relative to `root`; path traversal and symlink
    escapes are rejected.
    """

    def __init__(
        self,
        root: str | Path,
    ) -> None:
        self._root = Path(root).expanduser().resolve(
            strict=False
        )

        self._root.mkdir(
            parents=True,
            exist_ok=True,
        )

    def read(self, path: str) -> str:
        target = self._resolve(path)

        if not target.is_file():
            raise WorkspaceError(
                f"workspace file not found: {path!r}"
            )

        try:
            return target.read_text(
                encoding="utf-8"
            )
        except OSError as exc:
            raise WorkspaceError(
                f"failed to read workspace file {path!r}: {exc}"
            ) from exc

    def write(
        self,
        path: str,
        content: str,
    ) -> None:
        target = self._resolve(path)

        try:
            target.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            target.write_text(
                content,
                encoding="utf-8",
            )
        except OSError as exc:
            raise WorkspaceError(
                f"failed to write workspace file {path!r}: {exc}"
            ) from exc

    def list(
        self,
        path: str = ".",
    ) -> list[str]:
        target = self._resolve(path)

        if not target.is_dir():
            raise WorkspaceError(
                f"workspace directory not found: {path!r}"
            )

        try:
            return sorted(
                entry.name
                for entry in target.iterdir()
            )
        except OSError as exc:
            raise WorkspaceError(
                f"failed to list workspace path {path!r}: {exc}"
            ) from exc

    def _resolve(self, path: str) -> Path:
        if not isinstance(path, str):
            raise WorkspacePathError(
                "workspace path must be a string"
            )

        path = path.strip()

        if not path:
            raise WorkspacePathError(
                "workspace path cannot be empty"
            )

        candidate = Path(path)

        if candidate.is_absolute():
            raise WorkspacePathError(
                f"absolute paths are not allowed: {path!r}"
            )

        resolved = (
            self._root / candidate
        ).resolve(strict=False)

        try:
            resolved.relative_to(self._root)
        except ValueError as exc:
            raise WorkspacePathError(
                f"path escapes workspace: {path!r}"
            ) from exc

        return resolved


__all__ = [
    "LocalWorkspace",
    "WorkspaceBackend",
    "WorkspaceError",
    "WorkspacePathError",
]