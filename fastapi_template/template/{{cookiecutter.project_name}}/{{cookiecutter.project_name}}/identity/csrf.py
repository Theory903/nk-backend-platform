"""
CSRF protection and secure cookie policy.

CSRF protection is intended for browser authentication flows where
credentials are automatically attached by the browser, typically
session cookies.

Bearer tokens and API keys sent explicitly in Authorization headers
are not normally vulnerable to classic cookie-based CSRF — do not
attach ``require_csrf`` to those routes.

Security model:

    session_id + nonce (+ optional action)
            │
            ▼
       HMAC-SHA256
            │
            ▼
    nonce:signature

The server does not need to persist the CSRF token. The session identifier
is the binding secret/context.

The token is safe to expose to the browser because possession of the CSRF
token alone does not authenticate the user.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from collections.abc import Callable
from dataclasses import dataclass


CSRF_TOKEN_BYTES = 32
CSRF_HEADER = "X-CSRF-Token"


@dataclass(frozen=True, slots=True)
class CookiePolicy:
    """
    Security policy for authentication/session cookies.
    """

    httponly: bool = True
    secure: bool = True
    samesite: str = "lax"
    path: str = "/"

    def __post_init__(self) -> None:
        allowed_samesite = {
            "strict",
            "lax",
            "none",
        }

        if self.samesite.lower() not in allowed_samesite:
            raise ValueError(
                f"invalid SameSite policy: {self.samesite!r}",
            )

        if not self.path:
            raise ValueError("cookie path cannot be empty")

        if self.samesite.lower() == "none" and not self.secure:
            raise ValueError(
                "SameSite=None requires Secure cookies",
            )


COOKIE_POLICY_DEFAULTS = CookiePolicy()


class CsrfProtection:
    """
    Stateless CSRF token generator/validator.

    Tokens are cryptographically bound to a session identifier.

    Optional action binding allows different tokens to be issued for
    different operations:

        generate_token(session_id, action="profile.update")

    A token generated for one action cannot be reused for another.
    """

    def __init__(
        self,
        secret: str | bytes,
    ) -> None:
        if isinstance(secret, str):
            secret_bytes = secret.encode("utf-8")
        else:
            secret_bytes = secret

        if len(secret_bytes) < 32:
            raise ValueError(
                "CSRF secret must contain at least 32 bytes",
            )

        self._secret = secret_bytes

    # ------------------------------------------------------------------
    # Token generation
    # ------------------------------------------------------------------

    def generate_token(
        self,
        session_id: str,
        *,
        action: str = "",
    ) -> str:
        """
        Generate a CSRF token bound to a session.

        The plaintext nonce is safe to return to the client.
        """

        self._validate_binding(session_id, action)

        nonce = secrets.token_urlsafe(CSRF_TOKEN_BYTES)

        payload = self._payload(
            session_id=session_id,
            nonce=nonce,
            action=action,
        )

        signature = self._sign(payload)

        return f"{nonce}:{signature}"

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate_token(
        self,
        session_id: str,
        token: str,
        *,
        action: str = "",
    ) -> bool:
        """
        Validate a CSRF token.

        Returns False for every malformed, invalid, or mismatched token.
        """

        if not session_id or not token:
            return False

        try:
            nonce, signature = token.split(":", 1)
        except ValueError:
            return False

        if not nonce or not signature:
            return False

        # The signature is SHA-256 hex.
        if len(signature) != hashlib.sha256().digest_size * 2:
            return False

        if not self._is_hex(signature):
            return False

        payload = self._payload(
            session_id=session_id,
            nonce=nonce,
            action=action,
        )

        expected = self._sign(payload)

        return hmac.compare_digest(
            signature,
            expected,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _payload(
        *,
        session_id: str,
        nonce: str,
        action: str,
    ) -> bytes:
        """
        Construct the canonical HMAC payload.

        Length-prefixing avoids ambiguity between concatenated fields.
        """

        return (
            f"{len(session_id)}:{session_id}"
            f"{len(action)}:{action}"
            f"{len(nonce)}:{nonce}"
        ).encode("utf-8")

    def _sign(
        self,
        payload: bytes,
    ) -> str:
        return hmac.new(
            self._secret,
            payload,
            hashlib.sha256,
        ).hexdigest()

    @staticmethod
    def _validate_binding(
        session_id: str,
        action: str,
    ) -> None:
        if not session_id:
            raise ValueError(
                "session_id is required",
            )

        if not isinstance(action, str):
            raise TypeError(
                "action must be a string",
            )

    @staticmethod
    def _is_hex(value: str) -> bool:
        try:
            bytes.fromhex(value)
        except ValueError:
            return False

        return True


def require_csrf(
    protection: CsrfProtection,
    *,
    action: str = "",
) -> Callable[..., None]:
    """
    Thin FastAPI dependency factory for cookie-session CSRF checks.

    Validates ``X-CSRF-Token`` against ``X-Session-Id``. Does **not** read
    Authorization / API-key headers — keep this off bearer and API-key routes.
    """

    from typing import Annotated

    from fastapi import Header

    from {{cookiecutter.project_name}}.core.errors import Problem

    def _check(
        x_csrf_token: Annotated[str | None, Header(alias=CSRF_HEADER)] = None,
        x_session_id: Annotated[str | None, Header()] = None,
    ) -> None:
        session_id = (x_session_id or "").strip()
        token = (x_csrf_token or "").strip()
        if not protection.validate_token(session_id, token, action=action):
            raise Problem(
                title="CSRF Validation Failed",
                status_code=403,
                detail="missing or invalid CSRF token",
            )

    return _check


__all__ = [
    "COOKIE_POLICY_DEFAULTS",
    "CSRF_HEADER",
    "CSRF_TOKEN_BYTES",
    "CookiePolicy",
    "CsrfProtection",
    "require_csrf",
]
