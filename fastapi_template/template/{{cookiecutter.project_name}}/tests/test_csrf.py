"""CSRF protection + CookiePolicy unit tests."""

from __future__ import annotations

import hashlib
import hmac

import pytest

from {{cookiecutter.project_name}}.identity.csrf import (
    COOKIE_POLICY_DEFAULTS,
    CookiePolicy,
    CsrfProtection,
    require_csrf,
)

SECRET = "a" * 32
OTHER_SECRET = "b" * 32


@pytest.fixture
def csrf() -> CsrfProtection:
    return CsrfProtection(secret=SECRET)


def test_generate_validate_roundtrip(csrf: CsrfProtection) -> None:
    token = csrf.generate_token("session_abc")
    assert ":" in token
    assert csrf.validate_token("session_abc", token) is True


def test_wrong_session_fails(csrf: CsrfProtection) -> None:
    token = csrf.generate_token("session_abc")
    assert csrf.validate_token("session_other", token) is False


def test_wrong_action_fails(csrf: CsrfProtection) -> None:
    token = csrf.generate_token("session_abc", action="profile.update")
    assert csrf.validate_token("session_abc", token, action="profile.delete") is False
    assert csrf.validate_token("session_abc", token, action="") is False


def test_action_binding_isolation(csrf: CsrfProtection) -> None:
    update = csrf.generate_token("s1", action="profile.update")
    delete = csrf.generate_token("s1", action="profile.delete")
    unbound = csrf.generate_token("s1")

    assert csrf.validate_token("s1", update, action="profile.update") is True
    assert csrf.validate_token("s1", delete, action="profile.delete") is True
    assert csrf.validate_token("s1", unbound) is True

    assert csrf.validate_token("s1", update, action="profile.delete") is False
    assert csrf.validate_token("s1", delete, action="profile.update") is False
    assert csrf.validate_token("s1", update) is False
    assert csrf.validate_token("s1", unbound, action="profile.update") is False


@pytest.mark.parametrize(
    "token",
    [
        "",
        "no-colon",
        ":",
        "nonce:",
        ":deadbeef",
        "nonce:not-hex-!!!!",
        "nonce:" + "ab" * 16,  # too short for sha256 hex
        "nonce:" + "zz" * 32,  # wrong length + non-hex handled
    ],
)
def test_malformed_token_rejected(csrf: CsrfProtection, token: str) -> None:
    assert csrf.validate_token("session_abc", token) is False


def test_empty_session_rejected(csrf: CsrfProtection) -> None:
    token = csrf.generate_token("session_abc")
    assert csrf.validate_token("", token) is False
    with pytest.raises(ValueError, match="session_id"):
        csrf.generate_token("")


def test_short_secret_rejected() -> None:
    with pytest.raises(ValueError, match="32 bytes"):
        CsrfProtection(secret="too-short")
    with pytest.raises(ValueError, match="32 bytes"):
        CsrfProtection(secret=b"x" * 31)


def test_secret_accepts_bytes() -> None:
    csrf = CsrfProtection(secret=b"c" * 32)
    token = csrf.generate_token("sid")
    assert csrf.validate_token("sid", token) is True


def test_cookie_policy_defaults() -> None:
    assert COOKIE_POLICY_DEFAULTS.httponly is True
    assert COOKIE_POLICY_DEFAULTS.secure is True
    assert COOKIE_POLICY_DEFAULTS.samesite == "lax"
    assert COOKIE_POLICY_DEFAULTS.path == "/"


def test_cookie_policy_samesite_none_requires_secure() -> None:
    with pytest.raises(ValueError, match="SameSite=None requires Secure"):
        CookiePolicy(samesite="none", secure=False)
    # Mixed case still enforces the rule
    with pytest.raises(ValueError, match="SameSite=None requires Secure"):
        CookiePolicy(samesite="None", secure=False)
    ok = CookiePolicy(samesite="none", secure=True)
    assert ok.samesite == "none"


def test_cookie_policy_invalid_samesite() -> None:
    with pytest.raises(ValueError, match="invalid SameSite"):
        CookiePolicy(samesite="weird")


def test_cookie_policy_empty_path() -> None:
    with pytest.raises(ValueError, match="path"):
        CookiePolicy(path="")


def test_tampered_signature_compare_digest(csrf: CsrfProtection) -> None:
    token = csrf.generate_token("session_abc")
    nonce, signature = token.split(":", 1)
    # Flip one hex nibble so length/hex remain valid but digest mismatches
    flipped = ("0" if signature[0] != "0" else "1") + signature[1:]
    tampered = f"{nonce}:{flipped}"
    assert csrf.validate_token("session_abc", tampered) is False


def test_wrong_secret_fails() -> None:
    a = CsrfProtection(secret=SECRET)
    b = CsrfProtection(secret=OTHER_SECRET)
    token = a.generate_token("sid")
    assert b.validate_token("sid", token) is False


def test_length_prefixed_payload_ambiguity() -> None:
    """Length-prefixing must not allow session/action boundary confusion."""
    csrf = CsrfProtection(secret=SECRET)
    # Crafted fields that would collide under naive concatenation
    # session="ab" action="c:de" vs session="ab3:c" action="de" etc.
    t1 = csrf.generate_token("ab", action="c:x")
    assert csrf.validate_token("abc:x", t1, action="") is False
    assert csrf.validate_token("ab", t1, action="c:x") is True


def test_require_csrf_dependency_validates(csrf: CsrfProtection) -> None:
    from {{cookiecutter.project_name}}.core.errors import Problem

    dep = require_csrf(csrf, action="post.create")
    token = csrf.generate_token("sess-1", action="post.create")

    # Happy path — cookie session + CSRF header only
    dep(x_csrf_token=token, x_session_id="sess-1")

    with pytest.raises(Problem) as exc:
        dep(x_csrf_token=token, x_session_id="other-sess")
    assert exc.value.status_code == 403

    with pytest.raises(Problem):
        dep(x_csrf_token=None, x_session_id="sess-1")


def test_manual_hmac_matches_implementation(csrf: CsrfProtection) -> None:
    """Sanity-check compare_digest path against raw HMAC construction."""
    token = csrf.generate_token("sid", action="act")
    nonce, signature = token.split(":", 1)
    payload = f"{3}:sid{3}:act{len(nonce)}:{nonce}".encode("utf-8")
    expected = hmac.new(SECRET.encode(), payload, hashlib.sha256).hexdigest()
    assert hmac.compare_digest(signature, expected) is True
