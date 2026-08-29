from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

@dataclass(frozen=True, slots=True)
class ExternalIdentity:
    """
    Maps an external provisioning identity to an internal user.

    Example:

        provider = "scim"
        external_id = "00u123"
        user_id = "usr_abc"
        org_id = "org_xyz"
    """

    provider: str
    external_id: str
    user_id: str
    org_id: str
    created_at: datetime
    updated_at: datetime

__all__ = ["ExternalIdentity"]
