from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from collections.abc import Sequence
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

SCIM_CORE_USER_SCHEMA = "urn:ietf:params:scim:schemas:core:2.0:User"
SCIM_LIST_RESPONSE_SCHEMA = "urn:ietf:params:scim:api:messages:2.0:ListResponse"
SCIM_PATCH_SCHEMA = "urn:ietf:params:scim:api:messages:2.0:PatchOp"
SCIM_ERROR_SCHEMA = "urn:ietf:params:scim:api:messages:2.0:Error"

class ScimErrorType(StrEnum):
    INVALID_FILTER = "invalidFilter"
    TOO_MANY = "tooMany"
    UNIQUENESS = "uniqueness"
    MUTABILITY = "mutability"
    INVALID_VALUE = "invalidValue"
    INVALID_PATH = "invalidPath"
    NO_TARGET = "noTarget"
    SERVER_ERROR = "invalidSyntax"

class ScimError(Exception):
    def __init__(
        self,
        detail: str,
        *,
        status_code: int = 400,
        scim_type: str | None = None,
    ) -> None:
        self.detail = detail
        self.status_code = status_code
        self.scim_type = scim_type
        super().__init__(detail)

class ScimMeta(BaseModel):
    resourceType: str = "User"
    created: str | None = None
    lastModified: str | None = None
    location: str | None = None
    version: str | None = None

class ScimName(BaseModel):
    givenName: str | None = None
    familyName: str | None = None
    middleName: str | None = None
    formatted: str | None = None

class ScimEmail(BaseModel):
    value: str
    type: str | None = None
    primary: bool = False

class ScimUser(BaseModel):
    model_config = ConfigDict(extra="allow")

    schemas: list[str] = Field(
        default_factory=lambda: [SCIM_CORE_USER_SCHEMA],
    )

    id: str | None = None
    externalId: str | None = None
    userName: str

    active: bool = True

    displayName: str | None = None
    name: ScimName | None = None
    emails: list[ScimEmail] = Field(default_factory=list)

    meta: ScimMeta | None = None

    @field_validator("schemas")
    @classmethod
    def validate_schema(cls, value: list[str]) -> list[str]:
        if SCIM_CORE_USER_SCHEMA not in value:
            raise ValueError(
                f"missing required SCIM schema: {SCIM_CORE_USER_SCHEMA}",
            )
        return value

class ScimPatchOperation(BaseModel):
    op: str
    path: str | None = None
    value: Any = None

    @field_validator("op")
    @classmethod
    def normalize_op(cls, value: str) -> str:
        value = value.lower()
        if value not in {"add", "replace", "remove"}:
            raise ValueError(f"unsupported SCIM operation: {value}")
        return value

class ScimPatchRequest(BaseModel):
    schemas: list[str] = Field(
        default_factory=lambda: [SCIM_PATCH_SCHEMA],
    )
    Operations: list[ScimPatchOperation]

class ScimListResponse(BaseModel):
    schemas: list[str] = Field(
        default_factory=lambda: [SCIM_LIST_RESPONSE_SCHEMA],
    )
    totalResults: int
    startIndex: int
    itemsPerPage: int
    Resources: list[ScimUser]

class ScimErrorResponse(BaseModel):
    schemas: list[str] = Field(
        default_factory=lambda: [SCIM_ERROR_SCHEMA],
    )
    status: str
    detail: str
    scimType: str | None = None

@dataclass(frozen=True, slots=True)
class ScimPage:
    resources: Sequence[ScimUser]
    total: int
    start_index: int

__all__ = [
    "SCIM_CORE_USER_SCHEMA",
    "SCIM_LIST_RESPONSE_SCHEMA",
    "SCIM_PATCH_SCHEMA",
    "SCIM_ERROR_SCHEMA",
    "ScimErrorType",
    "ScimError",
    "ScimMeta",
    "ScimName",
    "ScimEmail",
    "ScimUser",
    "ScimPatchOperation",
    "ScimPatchRequest",
    "ScimListResponse",
    "ScimErrorResponse",
    "ScimPage",
]

