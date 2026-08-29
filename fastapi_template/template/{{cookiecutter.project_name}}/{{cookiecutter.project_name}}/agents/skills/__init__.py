from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Final


_FRONTMATTER_RE: Final[re.Pattern[str]] = re.compile(
    r"\A---[ \t]*\n(?P<meta>.*?)\n---[ \t]*(?:\n|$)",
    re.DOTALL,
)

_NAME_RE: Final[re.Pattern[str]] = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$",
)

_DEFAULT_MAX_SKILL_BYTES: Final[int] = 512 * 1024


class SkillError(RuntimeError):
    """Base exception for skill loading errors."""


class SkillNotFound(SkillError, KeyError):
    """Raised when a requested skill does not exist."""


class SkillNotTrusted(SkillError):
    """Raised when a skill exists but is not trusted."""


class SkillConflict(SkillError):
    """Raised when multiple skills resolve to the same name."""


class SkillInvalid(SkillError):
    """Raised when a skill is malformed or unsafe."""


@dataclass(frozen=True, slots=True)
class Skill:
    """
    Immutable discovered skill.

    `path` points to the skill directory rather than SKILL.md itself.
    """

    name: str
    description: str
    path: Path
    instructions: str

    @property
    def marker(self) -> Path:
        """Return the SKILL.md marker path."""
        return self.path / "SKILL.md"


@dataclass(frozen=True, slots=True)
class SkillLoaderConfig:
    """Configuration for skill discovery and loading."""

    max_skill_bytes: int = _DEFAULT_MAX_SKILL_BYTES
    recursive: bool = False
    strict_conflicts: bool = True

    def __post_init__(self) -> None:
        if self.max_skill_bytes <= 0:
            raise ValueError("max_skill_bytes must be greater than zero.")


def _parse_frontmatter(
    text: str,
) -> tuple[dict[str, str], str]:
    """
    Parse simple YAML-like frontmatter.

    This intentionally supports only scalar `key: value` pairs.
    Full YAML parsing is unnecessary for the loader's security boundary.
    """
    match = _FRONTMATTER_RE.match(text)

    if match is None:
        return {}, text

    metadata: dict[str, str] = {}

    for line_number, line in enumerate(
        match.group("meta").splitlines(),
        start=1,
    ):
        stripped = line.strip()

        if not stripped or stripped.startswith("#"):
            continue

        if ":" not in line:
            raise SkillInvalid(
                f"invalid frontmatter line {line_number}: {line!r}"
            )

        key, _, value = line.partition(":")

        key = key.strip()
        value = value.strip()

        if not key:
            raise SkillInvalid(
                f"frontmatter line {line_number} has an empty key."
            )

        if key in metadata:
            raise SkillInvalid(
                f"duplicate frontmatter key: {key!r}"
            )

        metadata[key] = value

    return metadata, text[match.end() :]


def _validate_name(name: str) -> str:
    name = name.strip()

    if not name:
        raise SkillInvalid("skill name cannot be empty.")

    if not _NAME_RE.fullmatch(name):
        raise SkillInvalid(
            f"invalid skill name {name!r}; "
            "allowed characters are letters, numbers, '.', '_' and '-'."
        )

    return name


class SkillLoader:
    """
    Discover and securely load SKILL.md based skills.

    Trust model:

    - trusted_names: explicit allow-list.
    - trusted_all: trust every discovered skill.
    - neither: discovery is allowed, loading is denied.

    Discovery and trust are deliberately separate. Merely placing a skill
    under a configured directory does not grant it execution/prompt trust.
    """

    __slots__ = (
        "_roots",
        "_trusted_names",
        "_trusted_all",
        "_config",
        "_cache",
    )

    def __init__(
        self,
        roots: list[Path],
        trusted_names: set[str] | None = None,
        trusted_all: bool = False,
        *,
        config: SkillLoaderConfig | None = None,
    ) -> None:
        if not roots:
            raise ValueError("at least one skill root is required.")

        self._roots = tuple(
            self._normalize_root(root)
            for root in roots
        )

        self._trusted_names = frozenset(
            _validate_name(name)
            for name in (trusted_names if trusted_names is not None else set())
        )

        self._trusted_all = trusted_all
        self._config = config or SkillLoaderConfig()
        self._cache: dict[str, Skill] | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def available(self) -> list[str]:
        """Return deterministically sorted discovered skill names."""
        return sorted(self._scan())

    def discover(self) -> tuple[Skill, ...]:
        """
        Return all discovered skills without requiring trust.

        Useful for diagnostics, UI, indexing, and audit tooling.
        """
        return tuple(
            self._scan().values()
        )

    def load(self, name: str) -> str:
        """
        Load trusted skill instructions.

        Raises:
            SkillNotFound
            SkillNotTrusted
        """
        name = _validate_name(name)

        skill = self._scan().get(name)

        if skill is None:
            raise SkillNotFound(
                f"skill {name!r} not found"
            )

        self._ensure_trusted(name)

        return self._render(skill)

    def get(self, name: str) -> Skill:
        """
        Return discovered skill metadata without applying trust.

        Use `load()` when instructions are actually needed.
        """
        name = _validate_name(name)

        skill = self._scan().get(name)

        if skill is None:
            raise SkillNotFound(
                f"skill {name!r} not found"
            )

        return skill

    def is_trusted(self, name: str) -> bool:
        """Return whether a skill is currently trusted."""
        name = _validate_name(name)

        return (
            self._trusted_all
            or name in self._trusted_names
        )

    def invalidate(self) -> None:
        """Invalidate the discovery cache."""
        self._cache = None

    # ------------------------------------------------------------------
    # Trust
    # ------------------------------------------------------------------

    def _ensure_trusted(self, name: str) -> None:
        if self._trusted_all:
            return

        if name in self._trusted_names:
            return

        raise SkillNotTrusted(
            f"skill {name!r} is not trusted; "
            "add it to trusted_names or enable trusted_all."
        )

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def _scan(self) -> dict[str, Skill]:
        if self._cache is not None:
            return self._cache

        found: dict[str, Skill] = {}

        for root in self._roots:
            if not root.is_dir():
                continue

            markers = self._find_markers(root)

            for marker in markers:
                skill = self._read_skill(
                    marker,
                    root,
                )

                existing = found.get(skill.name)

                if existing is not None:
                    if self._config.strict_conflicts:
                        raise SkillConflict(
                            f"duplicate skill name {skill.name!r}: "
                            f"{existing.marker} and {skill.marker}"
                        )

                    # Deterministic first-root-wins behavior when strict
                    # conflict detection is intentionally disabled.
                    continue

                found[skill.name] = skill

        self._cache = found

        return found

    def _find_markers(
        self,
        root: Path,
    ) -> list[Path]:
        pattern = "**/SKILL.md" if self._config.recursive else "*/SKILL.md"

        markers: list[Path] = []

        for marker in sorted(root.glob(pattern)):
            if not marker.is_file():
                continue

            if marker.is_symlink():
                continue

            if not self._is_within_root(marker, root):
                continue

            markers.append(marker)

        return markers

    def _read_skill(
        self,
        marker: Path,
        root: Path,
    ) -> Skill:
        try:
            resolved = marker.resolve(strict=True)
        except OSError as exc:
            raise SkillInvalid(
                f"unable to resolve skill file {marker}: {exc}"
            ) from exc

        if not self._is_within_root(resolved, root):
            raise SkillInvalid(
                f"skill escapes configured root: {marker}"
            )

        try:
            size = resolved.stat().st_size
        except OSError as exc:
            raise SkillInvalid(
                f"unable to stat skill file {resolved}: {exc}"
            ) from exc

        if size > self._config.max_skill_bytes:
            raise SkillInvalid(
                f"skill file {resolved} exceeds "
                f"{self._config.max_skill_bytes} bytes."
            )

        try:
            raw = resolved.read_text(
                encoding="utf-8",
            )
        except UnicodeDecodeError as exc:
            raise SkillInvalid(
                f"skill file {resolved} is not valid UTF-8."
            ) from exc
        except OSError as exc:
            raise SkillInvalid(
                f"unable to read skill file {resolved}: {exc}"
            ) from exc

        metadata, body = _parse_frontmatter(raw)

        name = _validate_name(
            metadata.get("name") or marker.parent.name
        )

        description = metadata.get(
            "description",
            "",
        ).strip()

        instructions = body.strip()

        if not instructions:
            raise SkillInvalid(
                f"skill {name!r} contains no instructions."
            )

        return Skill(
            name=name,
            description=description,
            path=marker.parent,
            instructions=instructions,
        )

    # ------------------------------------------------------------------
    # Filesystem safety
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_root(root: Path) -> Path:
        root = Path(root).expanduser()

        try:
            return root.resolve(strict=False)
        except OSError as exc:
            raise SkillInvalid(
                f"unable to resolve skill root {root}: {exc}"
            ) from exc

    @staticmethod
    def _is_within_root(
        path: Path,
        root: Path,
    ) -> bool:
        try:
            path.resolve(strict=False).relative_to(
                root.resolve(strict=False)
            )
            return True
        except ValueError:
            return False

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    @staticmethod
    def _render(skill: Skill) -> str:
        """
        Render the trusted skill into the agent context.

        Keep this format stable because it becomes part of the model-facing
        contract.
        """
        parts = [
            f"# Skill: {skill.name}",
        ]

        if skill.description:
            parts.append(skill.description)

        parts.append(skill.instructions)

        return "\n\n".join(parts)


__all__ = [
    "Skill",
    "SkillConflict",
    "SkillError",
    "SkillInvalid",
    "SkillLoader",
    "SkillLoaderConfig",
    "SkillNotFound",
    "SkillNotTrusted",
]