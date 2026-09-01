"""ERPNext document lifecycle — docstatus 0/1/2."""

from __future__ import annotations

from enum import IntEnum


class DocStatus(IntEnum):
    DRAFT = 0
    SUBMITTED = 1
    CANCELLED = 2


SUBMITTABLE = {DocStatus.DRAFT}
CANCELLABLE = {DocStatus.SUBMITTED}
