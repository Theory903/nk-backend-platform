"""Tenant-safe document ACL and version checks for retrieval."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True, slots=True)
class DocumentAccess:
    document_id: str
    org_id: str
    allowed_principals: frozenset[str] = frozenset()
    version: str = "1"

    def allows(self, *, principal_id: str, org_id: str) -> bool:
        return (
            self.org_id == org_id
            and (
                not self.allowed_principals
                or principal_id in self.allowed_principals
            )
        )


class AccessControlledRetriever:
    """Filter candidates before ranking or prompt construction."""

    def __init__(self, access: Iterable[DocumentAccess]) -> None:
        self._access = {item.document_id: item for item in access}

    def filter(
        self,
        candidates: Iterable[dict[str, object]],
        *,
        principal_id: str,
        org_id: str,
    ) -> list[dict[str, object]]:
        visible: list[dict[str, object]] = []
        for candidate in candidates:
            document_id = str(candidate.get("document_id", ""))
            access = self._access.get(document_id)
            if access is not None and access.allows(
                principal_id=principal_id,
                org_id=org_id,
            ):
                visible.append(dict(candidate))
        return visible


__all__ = ["AccessControlledRetriever", "DocumentAccess"]
