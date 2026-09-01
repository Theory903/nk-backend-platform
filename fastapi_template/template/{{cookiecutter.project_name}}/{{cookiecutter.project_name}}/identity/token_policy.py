"""
JWT validation and issuance (production policy layer).

This module is the identity JWT policy/validation API. It uses PyJWT with an
explicit server-side algorithm allowlist and structured ValidationResult.

``identity.jwt`` remains low-level HS256/RS256 encode/decode primitives
(hand-rolled, kid support). Prefer ``create_token`` / ``validate_token`` here
for access-token issuance and policy-gated verification so callers do not
maintain a second conflicting validation path.

Security properties:

- Explicit algorithm allowlist.
- Algorithm is selected by server configuration, never by token input.
- Signature verification is mandatory.
- Required claims are enforced.
- Issuer and audience are validated when configured.
- exp / iat / nbf validation uses configurable clock skew.
- Maximum token age is enforced.
- jti is cryptographically random.
- Validation never falls back to an insecure algorithm.
- Validation returns a structured result instead of leaking exceptions.
"""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass, field
from typing import Any

import jwt as _jwt_lib


# ---------------------------------------------------------------------------
# Policy
# ---------------------------------------------------------------------------


ALLOWED_ALGORITHMS = frozenset(
    {
        "HS256",
        "RS256",
        "ES256",
    }
)


@dataclass(frozen=True, slots=True)
class TokenPolicy:
    """
    Server-side JWT validation policy.

    The JWT header is untrusted input.

    The token may advertise an algorithm, but that algorithm is accepted
    only when it is explicitly allowed by this server-side policy.
    """

    algorithms: frozenset[str] = ALLOWED_ALGORITHMS

    expected_issuer: str | None = None

    expected_audiences: frozenset[str] = frozenset()

    required_claims: frozenset[str] = frozenset(
        {
            "sub",
            "exp",
            "iat",
            "jti",
        }
    )

    max_token_age_s: int = 86400

    clock_skew_s: int = 30

    def __post_init__(self) -> None:
        if not self.algorithms:
            raise ValueError(
                "at least one JWT algorithm must be configured"
            )

        unsupported = self.algorithms - ALLOWED_ALGORITHMS

        if unsupported:
            raise ValueError(
                f"unsupported JWT algorithms: {sorted(unsupported)}"
            )

        if self.max_token_age_s <= 0:
            raise ValueError(
                "max_token_age_s must be greater than zero"
            )

        if self.clock_skew_s < 0:
            raise ValueError(
                "clock_skew_s cannot be negative"
            )


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ValidationResult:
    valid: bool
    claims: dict[str, Any] = field(
        default_factory=dict
    )
    error: str | None = None


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_token(
    token: str,
    key: str | bytes,
    *,
    policy: TokenPolicy,
) -> ValidationResult:
    """
    Validate a JWT against an explicit server-side policy.

    The token header is inspected only to determine whether its advertised
    algorithm is permitted. It is NOT trusted for cryptographic policy.

    PyJWT is then explicitly restricted to the configured algorithm set.
    """
    if not token or not isinstance(token, str):
        return ValidationResult(
            valid=False,
            error="token is empty or invalid",
        )

    if not key:
        return ValidationResult(
            valid=False,
            error="verification key is empty",
        )

    try:
        # ---------------------------------------------------------------
        # Inspect untrusted header.
        # ---------------------------------------------------------------

        unverified_header = _jwt_lib.get_unverified_header(
            token
        )

        algorithm = unverified_header.get(
            "alg"
        )

        if not isinstance(algorithm, str):
            return ValidationResult(
                valid=False,
                error="token algorithm is missing",
            )

        if algorithm not in policy.algorithms:
            return ValidationResult(
                valid=False,
                error=(
                    f"algorithm '{algorithm}' "
                    "is not allowed"
                ),
            )

        # ---------------------------------------------------------------
        # Build PyJWT validation options.
        # ---------------------------------------------------------------

        options: dict[str, Any] = {
            "verify_signature": True,
            "verify_exp": True,
            "verify_iat": True,
            "verify_nbf": True,
            "verify_iss": bool(
                policy.expected_issuer
            ),
            "verify_aud": bool(
                policy.expected_audiences
            ),
            "require": list(
                policy.required_claims
            ),
        }

        decode_kwargs: dict[str, Any] = {
            "algorithms": [algorithm],
            "options": options,
            "leeway": policy.clock_skew_s,
        }

        # ---------------------------------------------------------------
        # Issuer validation.
        # ---------------------------------------------------------------

        if policy.expected_issuer is not None:
            decode_kwargs["issuer"] = (
                policy.expected_issuer
            )

        # ---------------------------------------------------------------
        # Audience validation.
        # ---------------------------------------------------------------

        if policy.expected_audiences:
            decode_kwargs["audience"] = list(
                policy.expected_audiences
            )

        # ---------------------------------------------------------------
        # Cryptographic + claim validation.
        # ---------------------------------------------------------------

        claims = _jwt_lib.decode(
            token,
            key,
            **decode_kwargs,
        )

        if not isinstance(claims, dict):
            return ValidationResult(
                valid=False,
                error="JWT payload is not an object",
            )

        # ---------------------------------------------------------------
        # Validate subject.
        # ---------------------------------------------------------------

        subject = claims.get("sub")

        if not isinstance(subject, str) or not subject:
            return ValidationResult(
                valid=False,
                error="invalid subject claim",
            )

        # ---------------------------------------------------------------
        # Validate jti.
        # ---------------------------------------------------------------

        if "jti" in policy.required_claims:
            jti = claims.get("jti")

            if not isinstance(jti, str) or not jti:
                return ValidationResult(
                    valid=False,
                    error="invalid jti claim",
                )

        # ---------------------------------------------------------------
        # Maximum token age.
        # ---------------------------------------------------------------

        iat = claims.get("iat")

        if iat is not None:
            if not isinstance(iat, (int, float)):
                return ValidationResult(
                    valid=False,
                    error="invalid iat claim",
                )

            now = time.time()
            age = now - float(iat)

            # Future-issued tokens beyond clock skew are rejected by PyJWT's
            # iat validation. This check protects the maximum age independently.
            if age > (
                policy.max_token_age_s
                + policy.clock_skew_s
            ):
                return ValidationResult(
                    valid=False,
                    error="token too old",
                )

            # A token with an iat far in the future should not be accepted.
            if age < -policy.clock_skew_s:
                return ValidationResult(
                    valid=False,
                    error="token issued in the future",
                )

        return ValidationResult(
            valid=True,
            claims=claims,
        )

    except _jwt_lib.ExpiredSignatureError:
        return ValidationResult(
            valid=False,
            error="token expired",
        )

    except _jwt_lib.ImmatureSignatureError:
        return ValidationResult(
            valid=False,
            error="token not yet valid",
        )

    except _jwt_lib.InvalidIssuedAtError:
        return ValidationResult(
            valid=False,
            error="invalid issued-at claim",
        )

    except _jwt_lib.InvalidIssuerError:
        return ValidationResult(
            valid=False,
            error="wrong issuer",
        )

    except _jwt_lib.InvalidAudienceError:
        return ValidationResult(
            valid=False,
            error="wrong audience",
        )

    except _jwt_lib.MissingRequiredClaimError as exc:
        return ValidationResult(
            valid=False,
            error=f"missing required claim: {exc}",
        )

    except _jwt_lib.InvalidAlgorithmError:
        return ValidationResult(
            valid=False,
            error="algorithm not allowed",
        )

    except _jwt_lib.InvalidSignatureError:
        return ValidationResult(
            valid=False,
            error="invalid signature",
        )

    except _jwt_lib.DecodeError:
        return ValidationResult(
            valid=False,
            error="malformed token",
        )

    except _jwt_lib.InvalidTokenError:
        # Do not expose detailed cryptographic errors to clients.
        return ValidationResult(
            valid=False,
            error="invalid token",
        )

    except Exception:
        # Authentication code should fail closed.
        return ValidationResult(
            valid=False,
            error="token validation failed",
        )


# ---------------------------------------------------------------------------
# Token creation
# ---------------------------------------------------------------------------


def create_token(
    subject: str,
    key: str | bytes,
    *,
    algorithm: str = "HS256",
    expires_in_s: int = 3600,
    issuer: str | None = None,
    audiences: list[str] | None = None,
    extra_claims: dict[str, Any] | None = None,
    policy: TokenPolicy | None = None,
) -> str:
    """
    Create a signed JWT.

    Algorithm selection is controlled by the server/application,
    never by arbitrary token input.

    When ``policy`` is supplied, ``algorithm`` must also be in
    ``policy.algorithms`` (in addition to ``ALLOWED_ALGORITHMS``).
    """
    if not subject:
        raise ValueError(
            "subject is required"
        )

    if not key:
        raise ValueError(
            "signing key is required"
        )

    if algorithm not in ALLOWED_ALGORITHMS:
        raise ValueError(
            f"algorithm '{algorithm}' is not allowed"
        )

    if policy is not None and algorithm not in policy.algorithms:
        raise ValueError(
            f"algorithm '{algorithm}' is not allowed by policy"
        )

    if expires_in_s <= 0:
        raise ValueError(
            "expires_in_s must be greater than zero"
        )

    now = int(time.time())

    payload: dict[str, Any] = {
        "sub": subject,
        "iat": now,
        "exp": now + expires_in_s,
        "jti": secrets.token_urlsafe(24),
    }

    if issuer:
        payload["iss"] = issuer

    if audiences:
        payload["aud"] = audiences

    if extra_claims:
        # Reserved claims must not be silently overwritten.
        reserved = {
            "sub",
            "iat",
            "exp",
            "jti",
        }

        collisions = reserved.intersection(
            extra_claims
        )

        if collisions:
            raise ValueError(
                "extra_claims cannot override reserved "
                f"claims: {sorted(collisions)}"
            )

        payload.update(extra_claims)

    return _jwt_lib.encode(
        payload,
        key,
        algorithm=algorithm,
    )


__all__ = [
    "ALLOWED_ALGORITHMS",
    "TokenPolicy",
    "ValidationResult",
    "create_token",
    "validate_token",
]