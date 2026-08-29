from __future__ import annotations

from copy import deepcopy
from typing import Any

from .scim import ScimError, ScimName, ScimPatchOperation, ScimUser

class ScimPatchEngine:
    """
    Applies SCIM PATCH operations to a normalized ScimUser.

    Supported:
        add
        replace
        remove

    Supports simple nested paths such as:

        active
        displayName
        name.givenName
        name.familyName
        externalId
    """

    MUTABLE_FIELDS = {
        "externalId",
        "userName",
        "active",
        "displayName",
        "name",
        "name.givenName",
        "name.familyName",
        "name.middleName",
        "name.formatted",
        "emails",
    }

    @classmethod
    def apply(
        cls,
        user: ScimUser,
        operations: list[ScimPatchOperation],
    ) -> ScimUser:
        result = deepcopy(user)

        for operation in operations:
            cls._apply_operation(result, operation)

        return result

    @classmethod
    def _apply_operation(
        cls,
        user: ScimUser,
        operation: ScimPatchOperation,
    ) -> None:
        path = operation.path

        if path:
            path = path.strip()

        if path and path not in cls.MUTABLE_FIELDS:
            raise ScimError(
                f"unsupported SCIM path: {path}",
                status_code=400,
                scim_type="invalidPath",
            )

        if operation.op == "remove":
            cls._remove(user, path)
            return

        if path is None:
            cls._apply_complex_value(user, operation.value)
            return

        cls._set(user, path, operation.value)

    @staticmethod
    def _set(
        user: ScimUser,
        path: str,
        value: Any,
    ) -> None:
        if path == "active":
            user.active = bool(value)
            return

        if path == "externalId":
            user.externalId = str(value)
            return

        if path == "userName":
            user.userName = str(value)
            return

        if path == "displayName":
            user.displayName = str(value)
            return

        if path.startswith("name."):
            if user.name is None:
                user.name = ScimName()

            field_name = path.split(".", 1)[1]
            setattr(user.name, field_name, value)
            return

        if path == "emails":
            if not isinstance(value, list):
                value = [value]

            user.emails = value
            return

        raise ScimError(
            f"invalid SCIM path: {path}",
            status_code=400,
            scim_type="invalidPath",
        )

    @staticmethod
    def _remove(
        user: ScimUser,
        path: str | None,
    ) -> None:
        if path is None:
            raise ScimError(
                "remove requires a path",
                status_code=400,
                scim_type="noTarget",
            )

        if path == "active":
            user.active = False
            return

        if path == "displayName":
            user.displayName = None
            return

        if path == "externalId":
            user.externalId = None
            return

        if path.startswith("name."):
            if user.name is not None:
                field_name = path.split(".", 1)[1]
                setattr(user.name, field_name, None)
            return

        if path == "emails":
            user.emails = []
            return

        raise ScimError(
            f"invalid SCIM path: {path}",
            status_code=400,
            scim_type="invalidPath",
        )

    @classmethod
    def _apply_complex_value(
        cls,
        user: ScimUser,
        value: Any,
    ) -> None:
        if not isinstance(value, dict):
            raise ScimError(
                "SCIM PATCH value must be an object",
                status_code=400,
                scim_type="invalidValue",
            )

        for key, field_value in value.items():
            cls._set(user, key, field_value)

__all__ = ["ScimPatchEngine"]
