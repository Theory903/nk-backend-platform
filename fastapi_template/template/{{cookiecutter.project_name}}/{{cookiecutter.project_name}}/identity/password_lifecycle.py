"""Password lifecycle management.

Provides:

- Password policy validation
- Password hashing and verification (via ``core.security``)
- Login throttling and lockout (``CounterStore``; delay must be
  enforced by the caller / login route)
- Password-reset tokens (HMAC + ``ExpiringStore`` single-use consume)
- Password history (hashes only; in-memory store is **not** durable
  across workers — use a shared repo in production)
- PasswordLifecycleService facade

After a successful password reset, callers should cascade-revoke
sessions / refresh tokens (next step; not done here).

Mutable state is injected through storage abstractions so development can
use in-memory implementations while production can use Redis/database
backends.

Security-sensitive secrets must never be logged or returned after issuance.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import re
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass

from {{cookiecutter.project_name}}.core.security import (
    hash_password,
    verify_password,
)
from {{cookiecutter.project_name}}.core.state import (
    CounterStore,
    ExpiringStore,
)

__all__ = [
    "PasswordPolicyConfig",
    "validate_password",
    "make_password_hasher",
    "LoginThrottleConfig",
    "LoginThrottler",
    "PasswordResetConfig",
    "PasswordResetService",
    "PasswordHistory",
    "PasswordLifecycleService",
]


# ============================================================================
# Password policy
# ============================================================================


@dataclass(frozen=True)
class PasswordPolicyConfig:
    min_length: int = 12

    require_upper: bool = True
    require_lower: bool = True
    require_digit: bool = True
    require_special: bool = True

    max_repeated: int = 3

    forbidden_patterns: tuple[str, ...] = (
        "password",
        "123456",
        "qwerty",
        "admin",
        "letmein",
        "welcome",
        "monkey",
        "dragon",
        "master",
        "login",
    )


def validate_password(
    password: str,
    config: PasswordPolicyConfig | None = None,
) -> list[str]:
    """Return password-policy violations."""

    cfg = config or PasswordPolicyConfig()
    errors: list[str] = []

    if len(password) < cfg.min_length:
        errors.append(
            f"minimum {cfg.min_length} characters required"
        )

    if cfg.require_upper and not re.search(
        r"[A-Z]",
        password,
    ):
        errors.append(
            "at least one uppercase letter required"
        )

    if cfg.require_lower and not re.search(
        r"[a-z]",
        password,
    ):
        errors.append(
            "at least one lowercase letter required"
        )

    if cfg.require_digit and not re.search(
        r"\d",
        password,
    ):
        errors.append(
            "at least one digit required"
        )

    if cfg.require_special and not re.search(
        r"""[!@#$%^&*(),.?":{}|\[\]\\/~`_+\-=;']""",
        password,
    ):
        errors.append(
            "at least one special character required"
        )

    if cfg.max_repeated > 0:
        # Concatenate braces so cookiecutter/Jinja does not treat
        # `{cfg.max_repeated}` as a template expression.
        repeated_pattern = (
            "(.)\\1{" + str(cfg.max_repeated) + ",}"
        )

        if re.search(
            repeated_pattern,
            password,
        ):
            errors.append(
                f"no more than {cfg.max_repeated} "
                "repeated characters"
            )

    normalized = password.casefold()

    for pattern in cfg.forbidden_patterns:
        if pattern.casefold() in normalized:
            errors.append(
                f"password contains forbidden pattern "
                f"'{pattern}'"
            )
            break

    return errors


def make_password_hasher(
    config: PasswordPolicyConfig | None = None,
) -> Callable[[str], str]:
    """Return a validating password-hashing callable.

    Uses ``core.security.hash_password`` (scrypt) after policy checks.
    """

    cfg = config or PasswordPolicyConfig()

    def validate_and_hash(password: str) -> str:
        errors = validate_password(
            password,
            cfg,
        )

        if errors:
            raise ValueError(
                "; ".join(errors)
            )

        return hash_password(password)

    return validate_and_hash


# ============================================================================
# Login throttling
# ============================================================================


@dataclass(frozen=True)
class LoginThrottleConfig:
    max_failures: int = 5
    base_delay_s: float = 2.0
    backoff_multiplier: float = 2.0
    lockout_s: float = 900.0
    window_s: float = 3600.0


class LoginThrottler:
    """
    Login throttling using an injected async CounterStore.

    Production should use an atomic Redis-backed counter implementation.

    Keys should normally combine multiple dimensions, for example:

        login:ip:<ip>
        login:account:<account_id>

    Do not rely on account-only throttling because it can become an
    account-enumeration or denial-of-service vector.

    ``check_allowed`` returns ``(allowed, retry_after_seconds)``. The
    delay / lockout must be enforced by the caller (login route); this
    class only computes state.
    """

    def __init__(
        self,
        counters: CounterStore,
        *,
        config: LoginThrottleConfig | None = None,
    ) -> None:
        self.counters = counters
        self.config = config or LoginThrottleConfig()

    def _failure_key(
        self,
        identifier: str,
    ) -> str:
        return f"login:failures:{identifier}"

    def _lock_key(
        self,
        identifier: str,
    ) -> str:
        return f"login:locked:{identifier}"

    async def _failure_count(
        self,
        identifier: str,
    ) -> int:
        return await self.counters.get_value(
            self._failure_key(identifier)
        )

    async def check_allowed(
        self,
        identifier: str,
    ) -> tuple[bool, float]:
        """
        Return:

            (allowed, retry_after_seconds)

        Caller must enforce the delay before accepting another attempt.
        """

        failures = await self._failure_count(
            identifier
        )

        if failures >= self.config.max_failures:
            return False, self.config.lockout_s

        if failures == 0:
            return True, 0.0

        delay = (
            self.config.base_delay_s
            * (
                self.config.backoff_multiplier
                ** (failures - 1)
            )
        )

        return True, delay

    async def record_failure(
        self,
        identifier: str,
    ) -> int:
        """
        Record a failed attempt.

        Returns the resulting failure count.
        """

        return await self.counters.increment(
            self._failure_key(identifier),
            ttl_s=self.config.window_s,
        )

    async def record_success(
        self,
        identifier: str,
    ) -> None:
        """Clear throttling state after successful authentication."""

        await self.counters.delete(
            self._failure_key(identifier)
        )


# ============================================================================
# Password reset tokens
# ============================================================================


@dataclass(frozen=True)
class PasswordResetConfig:
    ttl_s: int = 1800
    token_bytes: int = 32


class PasswordResetService:
    """
    Stateless HMAC reset tokens with externally stored single-use state.

    The plaintext token is returned only at creation time.

    Production should use Redis for the used-token store. Consume uses
    atomic ``ExpiringStore.set_if_absent``.
    """

    def __init__(
        self,
        secret: str,
        used_tokens: ExpiringStore,
        *,
        config: PasswordResetConfig | None = None,
    ) -> None:
        if not secret:
            raise ValueError(
                "password reset secret must not be empty"
            )

        self.secret = secret.encode()
        self.used_tokens = used_tokens
        self.config = (
            config or PasswordResetConfig()
        )

    def _sign(
        self,
        payload: str,
    ) -> str:
        return hmac.new(
            self.secret,
            payload.encode(),
            hashlib.sha256,
        ).hexdigest()

    def create_reset_token(
        self,
        user_id: str,
    ) -> str:
        """
        Create a short-lived reset token.

        The payload is encoded so delimiters in user IDs cannot corrupt
        token parsing.
        """

        if not user_id:
            raise ValueError(
                "user_id must not be empty"
            )

        expires = int(
            time.time() + self.config.ttl_s
        )

        nonce = secrets.token_urlsafe(
            self.config.token_bytes
        )

        encoded_user = base64.urlsafe_b64encode(
            user_id.encode()
        ).decode()

        payload = (
            f"{encoded_user}.{expires}.{nonce}"
        )

        signature = self._sign(payload)

        return f"{payload}.{signature}"

    async def verify_reset_token(
        self,
        token: str,
    ) -> str | None:
        """
        Validate and consume a reset token.

        Returns the user ID on success. Invalid at exact expiry
        (``time.time() >= expires``).
        """

        try:
            encoded_user, expires_raw, nonce, signature = (
                token.split(".", 3)
            )

            expires = int(expires_raw)

            payload = (
                f"{encoded_user}.{expires}.{nonce}"
            )

            expected = self._sign(payload)

            if not hmac.compare_digest(
                signature,
                expected,
            ):
                return None

            if time.time() >= expires:
                return None

            user_id = base64.urlsafe_b64decode(
                encoded_user.encode()
            ).decode()

        except (
            ValueError,
            TypeError,
            UnicodeDecodeError,
            binascii.Error,
        ):
            return None

        token_hash = hashlib.sha256(
            token.encode()
        ).hexdigest()

        used_key = f"password-reset:used:{token_hash}"

        accepted = await self.used_tokens.set_if_absent(
            used_key,
            "1",
            ttl_s=max(
                1.0,
                float(expires - int(time.time())),
            ),
        )

        if not accepted:
            return None

        return user_id


# ============================================================================
# Password history
# ============================================================================


class PasswordHistory:
    """
    Password reuse prevention.

    Hashes are stored, never plaintext passwords.

    This in-memory implementation is **not** multi-worker durable.
    Production should back history with a shared repository.
    """

    def __init__(
        self,
        *,
        max_history: int = 5,
    ) -> None:
        if max_history < 1:
            raise ValueError(
                "max_history must be >= 1"
            )

        self.max_history = max_history
        self._history: dict[
            str,
            list[str],
        ] = {}

    def record(
        self,
        user_id: str,
        hashed: str,
    ) -> None:
        history = self._history.setdefault(
            user_id,
            [],
        )

        history.append(hashed)

        if len(history) > self.max_history:
            del history[
                : len(history) - self.max_history
            ]

    def is_reused(
        self,
        user_id: str,
        password: str,
    ) -> bool:
        return any(
            verify_password(
                password,
                previous_hash,
            )
            for previous_hash in self._history.get(
                user_id,
                [],
            )
        )


# ============================================================================
# Password lifecycle facade
# ============================================================================


class PasswordLifecycleService:
    """
    High-level password lifecycle service.

    This keeps policy, throttling, reset, and history decisions behind
    one application-facing boundary.

    After reset, the application should cascade-revoke active sessions
    (not implemented here).
    """

    def __init__(
        self,
        *,
        hasher: Callable[[str], str],
        history: PasswordHistory,
        reset_service: PasswordResetService,
        policy: PasswordPolicyConfig | None = None,
    ) -> None:
        self.hasher = hasher
        self.history = history
        self.reset_service = reset_service
        self.policy = (
            policy or PasswordPolicyConfig()
        )

    def validate(
        self,
        password: str,
    ) -> list[str]:
        return validate_password(
            password,
            self.policy,
        )

    def set_password(
        self,
        user_id: str,
        password: str,
    ) -> str:
        errors = self.validate(password)

        if errors:
            raise ValueError(
                "; ".join(errors)
            )

        if self.history.is_reused(
            user_id,
            password,
        ):
            raise ValueError(
                "password was recently used"
            )

        hashed = self.hasher(password)

        self.history.record(
            user_id,
            hashed,
        )

        return hashed

    def verify_password(
        self,
        password: str,
        stored_hash: str,
    ) -> bool:
        return verify_password(
            password,
            stored_hash,
        )

    def create_reset_token(
        self,
        user_id: str,
    ) -> str:
        return self.reset_service.create_reset_token(
            user_id
        )

    async def consume_reset_token(
        self,
        token: str,
    ) -> str | None:
        return await self.reset_service.verify_reset_token(
            token
        )
