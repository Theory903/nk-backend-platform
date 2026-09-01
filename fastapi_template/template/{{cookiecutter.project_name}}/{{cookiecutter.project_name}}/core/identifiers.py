"""Platform-wide unique identifier generation."""

from __future__ import annotations

import re
import uuid
from typing import Final


_PREFIX_RE: Final[re.Pattern[str]] = re.compile(
    r"^[a-z][a-z0-9_]{0,31}$"
)


class IdentifierError(ValueError):
    """Raised when an identifier prefix is invalid."""


def new_id(prefix: str) -> str:
    """
    Generate a globally unique, prefixed identifier.

    Example:
        new_id("usr") -> "usr_01J..."

    UUID4 provides 122 bits of effective randomness, making collisions
    negligible for normal distributed-system workloads.
    """

    prefix = prefix.strip().lower()

    if not _PREFIX_RE.fullmatch(prefix):
        raise IdentifierError(
            "prefix must start with a letter and contain only "
            "lowercase letters, digits, and underscores "
            "(maximum 32 characters)"
        )

    return f"{prefix}_{uuid.uuid4().hex}"


def is_valid_id(
    value: str,
    *,
    prefix: str | None = None,
) -> bool:
    """Validate a generated platform identifier."""

    if not isinstance(value, str):
        return False

    if prefix is not None:
        prefix = prefix.strip().lower()

        if not _PREFIX_RE.fullmatch(prefix):
            return False

        suffix_pattern = "[0-9a-f]{32}"
        return bool(
            re.fullmatch(
                f"{re.escape(prefix)}_{suffix_pattern}",
                value,
            )
        )

    return bool(
        re.fullmatch(
            r"[a-z][a-z0-9_]{0,31}_[0-9a-f]{32}",
            value,
        )
    )


__all__ = [
    "IdentifierError",
    "is_valid_id",
    "new_id",
]
