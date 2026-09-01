"""PII detection and redaction for agent context (P18)."""

from __future__ import annotations

import re
from dataclasses import dataclass


_EMAIL = re.compile(
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
)
_PHONE = re.compile(
    r"\b(?:\+?\d{1,3}[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?){2}\d{4}\b",
)
_SSN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_API_KEY = re.compile(r"\b(sk-[A-Za-z0-9]{20,}|AKIA[A-Z0-9]{16})\b")


@dataclass(frozen=True, slots=True)
class PIIFinding:
    kind: str
    count: int


class PIIRedactor:
    """Redact common PII and secret patterns from model context."""

    def findings(self, text: str) -> tuple[PIIFinding, ...]:
        counts = (
            ("email", len(_EMAIL.findall(text))),
            ("phone", len(_PHONE.findall(text))),
            ("ssn", len(_SSN.findall(text))),
            ("secret", len(_API_KEY.findall(text))),
        )
        return tuple(
            PIIFinding(kind=kind, count=count)
            for kind, count in counts
            if count
        )

    def redact(self, text: str) -> str:
        redacted = _EMAIL.sub("[REDACTED_EMAIL]", text)
        redacted = _PHONE.sub("[REDACTED_PHONE]", redacted)
        redacted = _SSN.sub("[REDACTED_SSN]", redacted)
        return _API_KEY.sub("[REDACTED_SECRET]", redacted)


__all__ = ["PIIFinding", "PIIRedactor"]
