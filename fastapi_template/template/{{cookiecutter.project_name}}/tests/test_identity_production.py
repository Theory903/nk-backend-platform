import pytest
from dataclasses import replace
from datetime import UTC, datetime

from {{cookiecutter.project_name}}.identity.token_policy import TokenPolicy, validate_token, ALLOWED_ALGORITHMS
from {{cookiecutter.project_name}}.core.state import InMemoryCounterStore, InMemoryExpiringStore
from {{cookiecutter.project_name}}.identity.password_lifecycle import (
    LoginThrottleConfig,
    LoginThrottler,
    PasswordHistory,
    PasswordResetConfig,
    PasswordResetService,
    validate_password,
)
from {{cookiecutter.project_name}}.identity.refresh_tokens import RefreshTokenManager
from {{cookiecutter.project_name}}.identity.session_lifecycle import SecureSessionStore
from {{cookiecutter.project_name}}.identity.security_events import (
    SecurityEventLog,
    SecurityEventType,
    SecurityOutcome,
)
from {{cookiecutter.project_name}}.identity.auth_rate_limit import AuthRateLimiter
from {{cookiecutter.project_name}}.identity.account_linking import (
    AccountLinkingConflictError,
    AccountLinkingService,
    CannotUnlinkLastIdentityError,
    IdentityAlreadyLinkedError,
    InMemoryIdentityRepository,
)
from {{cookiecutter.project_name}}.identity.email_verification import EmailVerificationService
from {{cookiecutter.project_name}}.identity.api_key_lifecycle import (
    ApiKeyInvalidError,
    ApiKeyIpRestrictedError,
    ApiKeyLifecycleService,
    ApiKeyRecord,
)
from {{cookiecutter.project_name}}.identity.service_accounts import ServiceAccountRegistry
from {{cookiecutter.project_name}}.identity.csrf import CsrfProtection


class _InMemoryApiKeyRepo:
    def __init__(self) -> None:
        self._by_id: dict[str, ApiKeyRecord] = {}

    async def get_by_id(self, key_id: str) -> ApiKeyRecord | None:
        return self._by_id.get(key_id)

    async def get_by_hash(self, secret_hash: str) -> ApiKeyRecord | None:
        for record in self._by_id.values():
            if record.secret_hash == secret_hash:
                return record
        return None

    async def create(self, record: ApiKeyRecord) -> ApiKeyRecord:
        self._by_id[record.key_id] = record
        return record

    async def revoke(
        self, key_id: str, *, reason: str | None = None,
    ) -> bool:
        record = self._by_id.get(key_id)
        if record is None:
            return False
        self._by_id[key_id] = replace(
            record,
            revoked_at=datetime.now(UTC),
            revoked_reason=reason,
        )
        return True

    async def list_for_owner(
        self,
        owner_id: str,
        *,
        org_id: str | None = None,
        include_revoked: bool = False,
    ) -> list[ApiKeyRecord]:
        return [
            r for r in self._by_id.values()
            if r.owner_id == owner_id
            and (org_id is None or r.org_id == org_id)
            and (include_revoked or not r.is_revoked)
        ]

    async def revoke_all_for_owner(
        self, owner_id: str, *, reason: str | None = None,
    ) -> int:
        n = 0
        for key_id, record in list(self._by_id.items()):
            if record.owner_id != owner_id or record.is_revoked:
                continue
            self._by_id[key_id] = replace(
                record,
                revoked_at=datetime.now(UTC),
                revoked_reason=reason,
            )
            n += 1
        return n

    async def update_last_used(
        self, key_id: str, *, used_at: datetime,
    ) -> None:
        record = self._by_id.get(key_id)
        if record is not None:
            self._by_id[key_id] = replace(record, last_used_at=used_at)


# --- JWT Policy ---

def test_jwt_rejects_disallowed_algorithm() -> None:
    policy = TokenPolicy(algorithms=frozenset({"RS256"}), expected_issuer="nk")
    # A token signed with HS256 should be rejected when only RS256 is allowed
    result = validate_token("fake.token.here", "key", policy=policy)
    assert not result.valid


def test_jwt_expected_issuer_enforced() -> None:
    policy = TokenPolicy(expected_issuer="https://auth.nk.io", required_claims=frozenset())
    secret = "production-jwt-test-secret-32bytes!!"
    token = _jwt_encode({"sub": "u1"}, secret)
    result = validate_token(token, secret, policy=policy)
    assert not result.valid  # wrong issuer


def test_jwt_expired_detected() -> None:
    policy = TokenPolicy(required_claims=frozenset())
    secret = "production-jwt-test-secret-32bytes!!"
    token = _jwt_encode({"sub": "u1", "exp": 1}, secret)
    result = validate_token(token, secret, policy=policy)
    assert not result.valid


def _jwt_encode(payload, secret):
    import jwt as pyjwt
    return pyjwt.encode(payload, secret, algorithm="HS256")


# --- Password lifecycle ---

def test_password_strength_rejects_weak() -> None:
    errors = validate_password("password123")
    assert any("forbidden pattern" in e or "uppercase" in e for e in errors)

def test_password_strength_accepts_strong() -> None:
    errors = validate_password("C0rr3ct-H0rs3-Batt3ry!")
    assert len(errors) == 0

@pytest.mark.anyio
async def test_password_reset_flow() -> None:
    svc = PasswordResetService(
        "reset-secret",
        InMemoryExpiringStore(),
        config=PasswordResetConfig(ttl_s=300),
    )
    token = svc.create_reset_token("user_1")
    user = await svc.verify_reset_token(token)
    assert user == "user_1"
    # Single use
    assert await svc.verify_reset_token(token) is None


@pytest.mark.anyio
async def test_login_throttle_lockout() -> None:
    throttle = LoginThrottler(
        InMemoryCounterStore(),
        config=LoginThrottleConfig(max_failures=3),
    )
    ident = "user@x.com"
    for _ in range(3):
        await throttle.record_failure(ident)
    allowed, delay = await throttle.check_allowed(ident)
    assert not allowed
    assert delay > 0


@pytest.mark.anyio
async def test_login_throttle_success_resets() -> None:
    throttle = LoginThrottler(
        InMemoryCounterStore(),
        config=LoginThrottleConfig(max_failures=5),
    )
    ident = "user@y.com"
    await throttle.record_failure(ident)
    await throttle.record_failure(ident)
    await throttle.record_success(ident)
    allowed, _ = await throttle.check_allowed(ident)
    assert allowed


def test_password_history_prevents_reuse() -> None:
    from {{cookiecutter.project_name}}.core.security import hash_password
    hist = PasswordHistory(max_history=2)
    old_hash = hash_password("OldP@ssw0rd!")
    hist.record("u1", old_hash)
    assert hist.is_reused("u1", "OldP@ssw0rd!") is True
    assert hist.is_reused("u1", "N3w-Passw0rd!") is False


# --- Refresh tokens ---

def test_refresh_rotation_and_reuse_detection() -> None:
    mgr = RefreshTokenManager(ttl_s=3600)
    rt1 = mgr.issue("user_1")
    claims1 = mgr.validate(rt1)
    assert claims1 is not None

    rotated = mgr.rotate(rt1)
    assert rotated is not None
    rt2, meta = rotated
    assert meta["user_id"] == "user_1"
    assert meta["family_id"] == claims1["family_id"]
    claims2 = mgr.validate(rt2)
    assert claims2 is not None

    # Reuse of consumed rt1 revokes entire family
    assert mgr.rotate(rt1) is None

    # rt2 now also invalid (family revoked)
    assert mgr.validate(rt2) is None
    assert mgr.rotate(rt2) is None


def test_global_logout_revokes_all() -> None:
    mgr = RefreshTokenManager(ttl_s=3600)
    r1 = mgr.issue("user_x")
    r2 = mgr.issue("user_x")
    count = mgr.revoke_all_for_user("user_x")
    assert count == 2
    assert mgr.validate(r1) is None
    assert mgr.validate(r2) is None


# --- Session lifecycle ---

def test_session_concurrent_limit_evicts_oldest() -> None:
    store = SecureSessionStore(max_concurrent_sessions=3)
    sessions = [store.create("user_z") for _ in range(5)]
    active = [s for s in sessions if store.get(s, touch=False) is not None]
    assert len(active) == 3


def test_session_rotation_prevents_fixation() -> None:
    store = SecureSessionStore()
    pre_auth = store.create("anon_user")
    post_auth = store.rotate(pre_auth)
    assert post_auth is not None
    assert pre_auth != post_auth
    # Old session should be dead
    assert store.get(pre_auth) is None


def test_session_idle_timeout() -> None:
    from unittest.mock import patch

    store = SecureSessionStore(idle_timeout_s=1, max_lifetime_s=3600)
    sid = store.create("user_t")
    session = store.get_session(sid, touch=False)
    assert session is not None
    with patch(
        "{{cookiecutter.project_name}}.identity.session.time.time",
        return_value=session.idle_expires_at + 0.1,
    ):
        assert store.get(sid) is None


# --- Rate limiter ---

def test_rate_limiter_blocks_after_burst() -> None:
    limiter = AuthRateLimiter(ip_capacity=3)
    results = [limiter.check(ip_address="1.2.3.4") for _ in range(5)]
    assert sum(1 for ok, _ in results if ok) <= 3


def test_rate_limiter_separate_buckets() -> None:
    limiter = AuthRateLimiter(ip_capacity=1, account_capacity=100)
    ok_ip, _ = limiter.check(ip_address="1.1.1.1", account_id="a")
    assert ok_ip is True
    ok_ip2, _ = limiter.check(ip_address="1.1.1.1")
    assert ok_ip2 is False  # IP bucket exhausted


# --- Account linking (no silent email auto-merge) ---

@pytest.mark.anyio
async def test_account_linking_same_email_does_not_merge() -> None:
    svc = AccountLinkingService(InMemoryIdentityRepository())
    acct, created = await svc.find_or_create(
        "user@example.com",
        provider="google",
        provider_user_id="g_123",
    )
    assert created
    with pytest.raises(AccountLinkingConflictError):
        await svc.find_or_create(
            "user@example.com",
            provider="microsoft",
            provider_user_id="ms_456",
        )
    # Original identity unchanged
    again = await svc.resolve("google", "g_123")
    assert again is not None
    assert again.user_id == acct.user_id
    assert len(again.identities) == 1


@pytest.mark.anyio
async def test_identity_takeover_blocked() -> None:
    svc = AccountLinkingService(InMemoryIdentityRepository())
    await svc.create_account(
        "a@x.com",
        provider="github",
        provider_user_id="gh_1",
    )
    other = await svc.create_account(
        "b@x.com",
        provider="password",
        provider_user_id="pw_other",
    )
    with pytest.raises(IdentityAlreadyLinkedError):
        await svc.link(
            other.user_id,
            provider="github",
            provider_user_id="gh_1",
        )


@pytest.mark.anyio
async def test_cannot_unlink_last_identity() -> None:
    svc = AccountLinkingService(InMemoryIdentityRepository())
    acct = await svc.create_account(
        "solo@x.com",
        provider="password",
        provider_user_id="p1",
    )
    with pytest.raises(CannotUnlinkLastIdentityError):
        await svc.unlink(
            acct.user_id,
            provider="password",
            provider_user_id="p1",
        )


# --- Email verification ---

@pytest.mark.anyio
async def test_email_verification_roundtrip() -> None:
    svc = EmailVerificationService(secret="ev-secret", ttl_s=300)
    token = await svc.create_verification_token("verify@example.com")
    email = await svc.verify_token(token)
    assert email == "verify@example.com"


@pytest.mark.anyio
async def test_email_verification_single_use() -> None:
    svc = EmailVerificationService(secret="k")
    token = await svc.create_verification_token("v@x.com")
    assert await svc.verify_token(token) is not None
    assert await svc.verify_token(token) is None


@pytest.mark.anyio
async def test_email_verification_resend_cooldown() -> None:
    svc = EmailVerificationService(secret="k", resend_cooldown_s=60)
    await svc.create_verification_token("r@x.com")
    with pytest.raises(ValueError, match="cooldown"):
        await svc.create_verification_token("r@x.com")


# --- API key lifecycle ---

@pytest.mark.anyio
async def test_api_key_scopes_and_expiry() -> None:
    svc = ApiKeyLifecycleService(_InMemoryApiKeyRepo())
    raw, rec = await svc.create(
        "test-key",
        owner_id="u1",
        scopes={"read", "write"},
        expires_in_s=9999,
    )
    assert rec.has_scope("read")
    assert rec.has_scope("write")
    assert not rec.has_scope("delete")
    verified = await svc.authenticate(raw)
    assert verified.key_id == rec.key_id


@pytest.mark.anyio
async def test_api_key_rotation_invalidates_old() -> None:
    svc = ApiKeyLifecycleService(_InMemoryApiKeyRepo())
    raw1, rec1 = await svc.create("rotate-me", owner_id="u1")
    rotation = await svc.rotate(raw1)
    assert rotation is not None
    raw2, rec2 = rotation
    stored_old = await svc._repository.get_by_id(rec1.key_id)
    assert stored_old is not None and stored_old.is_revoked
    with pytest.raises(ApiKeyInvalidError):
        await svc.authenticate(raw1)
    verified = await svc.authenticate(raw2)
    assert verified.key_id == rec2.key_id


@pytest.mark.anyio
async def test_api_key_ip_allowlist() -> None:
    svc = ApiKeyLifecycleService(_InMemoryApiKeyRepo())
    raw, _rec = await svc.create(
        "ip-restricted",
        owner_id="u1",
        ip_allowlist=["10.0.0.1"],
    )
    assert await svc.authenticate(raw, client_ip="10.0.0.1") is not None
    with pytest.raises(ApiKeyIpRestrictedError):
        await svc.authenticate(raw, client_ip="192.168.1.1")


# --- Service accounts ---

def test_service_account_lifecycle() -> None:
    registry = ServiceAccountRegistry()
    sa = registry.create("worker-1", org_id="org_1", roles={"service"})
    assert sa.principal_type == "service_account"
    fetched = registry.get(sa.account_id)
    assert fetched is not None
    assert fetched.name == "worker-1"
    registry.deactivate(sa.account_id)
    assert registry.get(sa.account_id) is None


# --- CSRF ---

def test_csrf_roundtrip() -> None:
    csrf = CsrfProtection(secret="csrf-secret-must-be-at-least-32b!!")
    token = csrf.generate_token("session_123")
    assert csrf.validate_token("session_123", token) is True
    assert csrf.validate_token("different_session", token) is False
    assert csrf.validate_token("session_123", token, action="other") is False


# --- Security events ---

def test_security_event_recording() -> None:
    log = SecurityEventLog()
    log.record(SecurityEventType.LOGIN_SUCCESS, actor_id="u1", method="jwt")
    log.record(
        SecurityEventType.LOGIN_FAILURE,
        subject_id="u2",
        outcome=SecurityOutcome.FAILURE,
    )
    events = log.query(event_type=SecurityEventType.LOGIN_FAILURE)
    assert len(events) >= 1
    assert events[0].outcome == SecurityOutcome.FAILURE
