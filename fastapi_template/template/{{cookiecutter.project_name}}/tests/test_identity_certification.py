"""P7.5 Identity Certification — tenant isolation, cascade effects, key rotation, store abstraction."""
from __future__ import annotations

import pytest

from {{cookiecutter.project_name}}.identity.account_lifecycle import (
    AccountLifecycleManager,
    AccountStatus,
    InMemoryAccountRepository,
    InvalidAccountTransition,
)
from {{cookiecutter.project_name}}.identity.api_key_lifecycle import ApiKeyLifecycleService
from {{cookiecutter.project_name}}.identity.tenant_context import (
    InMemoryMembershipRegistry,
    InMemoryResourceOwnershipRegistry,
    create_tenant_authorization,
)
from {{cookiecutter.project_name}}.identity.key_rotation import KeyRotationManager
from {{cookiecutter.project_name}}.identity.principal import Principal
from {{cookiecutter.project_name}}.identity.refresh_tokens import RefreshTokenManager
from {{cookiecutter.project_name}}.identity.service_accounts import ServiceAccountRegistry
from {{cookiecutter.project_name}}.identity.session_lifecycle import SecureSessionStore
from {{cookiecutter.project_name}}.identity.stores.base import InMemoryExpiringStore, InMemorySetStore, InMemoryCounterStore
from {{cookiecutter.project_name}}.core.errors import Problem


class _WiredCascadeEffects:
    """Test adapter: sync session/refresh/SA stores behind async CascadeEffects."""

    def __init__(
        self,
        sessions: SecureSessionStore,
        refresh: RefreshTokenManager,
        api_keys: ApiKeyLifecycleService | None = None,
        service_accounts: ServiceAccountRegistry | None = None,
    ) -> None:
        self._sessions = sessions
        self._refresh = refresh
        self._api_keys = api_keys
        self._service_accounts = service_accounts

    async def revoke_all_sessions(self, user_id: str) -> int:
        return self._sessions.revoke_all_for_principal(user_id)

    async def revoke_all_refresh_tokens(self, user_id: str) -> int:
        return self._refresh.revoke_all_for_user(user_id)

    async def revoke_all_api_keys(self, owner_id: str) -> int:
        if self._api_keys is None:
            return 0
        return await self._api_keys.revoke_all_for_owner(owner_id)

    async def deactivate_service_accounts(
        self,
        *,
        org_id: str | None,
        owner_id: str,
    ) -> int:
        if self._service_accounts is None:
            return 0
        return self._service_accounts.deactivate_created_by(
            owner_id,
            org_id=org_id,
        )


# === TENANT ISOLATION ===

@pytest.mark.anyio
class TestTenantIsolation:
    def _setup(self):
        memberships = InMemoryMembershipRegistry()
        resources = InMemoryResourceOwnershipRegistry()
        authz = create_tenant_authorization(memberships, resources)
        alice = Principal(user_id="alice", org_id="org_a")
        bob = Principal(user_id="bob", org_id="org_b")
        memberships.add_membership(
            user_id="alice",
            org_id="org_a",
            roles=frozenset({"editor"}),
        )
        memberships.add_membership(
            user_id="alice",
            org_id="org_b",
            roles=frozenset({"viewer"}),
        )
        memberships.add_membership(
            user_id="bob",
            org_id="org_b",
            roles=frozenset({"admin"}),
        )
        resources.register(resource_key="res:doc_1", org_id="org_a")
        resources.register(resource_key="res:doc_2", org_id="org_b")
        return authz, memberships, resources, alice, bob

    async def test_alice_can_access_org_a_resource(self) -> None:
        authz, _, _, alice, _ = self._setup()
        ctx = await authz.resolve_context(alice, org_id="org_a")
        await authz.authorize_resource(
            ctx,
            resource_key="res:doc_1",
            permission="read",
        )

    async def test_tenant_escape_blocked(self) -> None:
        """Tenant A user cannot access Tenant B resource."""
        authz, _, _, alice, _ = self._setup()
        ctx_a = await authz.resolve_context(alice, org_id="org_a")
        with pytest.raises(Problem) as exc_info:
            await authz.authorize_resource(
                ctx_a,
                resource_key="res:doc_2",
                permission="read",
            )
        assert exc_info.value.status_code == 403

    async def test_non_member_cannot_resolve_context(self) -> None:
        """Bob is not a member of org_a; resolving that context must fail."""
        authz, _, _, _, bob = self._setup()
        with pytest.raises(Problem) as exc_info:
            await authz.resolve_context(bob, org_id="org_a")
        assert "not" in str(exc_info.value.detail).lower()
        assert "member" in str(exc_info.value.detail).lower()

    async def test_cross_tenant_api_key_blocked(self) -> None:
        """Service principal in org_a cannot authorize org_b resources."""
        from dataclasses import replace
        from datetime import UTC, datetime

        from {{cookiecutter.project_name}}.identity.api_key_lifecycle import (
            ApiKeyLifecycleService,
            ApiKeyRecord,
        )

        class _Repo:
            def __init__(self) -> None:
                self._by_id: dict[str, ApiKeyRecord] = {}

            async def get_by_id(self, key_id: str) -> ApiKeyRecord | None:
                return self._by_id.get(key_id)

            async def get_by_hash(self, secret_hash: str) -> ApiKeyRecord | None:
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
                return []

            async def revoke_all_for_owner(
                self, owner_id: str, *, reason: str | None = None,
            ) -> int:
                return 0

            async def update_last_used(
                self, key_id: str, *, used_at: datetime,
            ) -> None:
                return None

        svc = ApiKeyLifecycleService(_Repo())
        raw, rec = await svc.create(
            "org-a-key",
            owner_id="svc_a",
            org_id="org_a",
            scopes={"*"},
        )
        verified = await svc.authenticate(raw)
        assert verified is not None
        assert verified.org_id == "org_a"

        memberships = InMemoryMembershipRegistry()
        resources = InMemoryResourceOwnershipRegistry()
        authz = create_tenant_authorization(memberships, resources)
        memberships.add_membership(
            user_id=f"svc:{rec.key_id}",
            org_id="org_a",
            roles=frozenset({"admin"}),
        )
        resources.register(resource_key="res:b_doc", org_id="org_b")
        principal = Principal(
            user_id=f"svc:{rec.key_id}",
            org_id="org_a",
            roles=frozenset({"admin"}),
            is_service=True,
        )
        ctx = await authz.resolve_context(principal, org_id="org_a")
        with pytest.raises(Problem) as exc_info:
            await authz.authorize_resource(
                ctx,
                resource_key="res:b_doc",
                permission="read",
            )
        assert exc_info.value.status_code == 403

    async def test_revoked_membership_blocks_access(self) -> None:
        authz, memberships, _, alice, _ = self._setup()
        memberships.remove_membership(user_id="alice", org_id="org_a")
        with pytest.raises(Problem):
            await authz.resolve_context(alice, org_id="org_a")

    async def test_org_wide_revoke_blocks_all_members(self) -> None:
        authz, memberships, _, _, bob = self._setup()
        memberships.revoke_org("org_b")
        with pytest.raises(Problem):
            await authz.resolve_context(bob, org_id="org_b")


# === ACCOUNT LIFECYCLE CASCADES ===

@pytest.mark.anyio
class TestAccountLifecycle:
    def _make_manager(self):
        sessions = SecureSessionStore(max_concurrent_sessions=10)
        refresh = RefreshTokenManager(ttl_s=3600)
        service_accounts = ServiceAccountRegistry()
        repo = InMemoryAccountRepository()
        cascade = _WiredCascadeEffects(
            sessions,
            refresh,
            service_accounts=service_accounts,
        )
        mgr = AccountLifecycleManager(repo, cascade)
        return mgr, repo, sessions, refresh, service_accounts

    async def test_suspension_kills_sessions_and_tokens(self) -> None:
        mgr, repo, sessions, refresh, service_accounts = self._make_manager()
        user_id = "user_to_suspend"
        repo.seed(user_id, AccountStatus.ACTIVE)
        sid = sessions.create(user_id)
        rt = refresh.issue(user_id)
        sa = service_accounts.create(
            "worker",
            org_id="org_a",
            created_by=user_id,
        )
        # Verify they work before suspension
        assert sessions.get(sid) is not None
        assert refresh.validate(rt) is not None
        assert service_accounts.get(sa.account_id) is not None
        # Suspend → cascade revokes everything (incl. SAs via deactivate_created_by)
        await mgr.transition(
            user_id,
            AccountStatus.SUSPENDED,
            org_id="org_a",
        )
        assert sessions.get(sid) is None  # dead
        assert refresh.validate(rt) is None  # family revoked
        assert service_accounts.get(sa.account_id) is None
        # User can no longer authenticate
        assert not await mgr.can_authenticate(user_id)

    async def test_invalid_transition_rejected(self) -> None:
        mgr, repo, *_ = self._make_manager()
        repo.seed("u1", AccountStatus.ACTIVE)
        with pytest.raises(InvalidAccountTransition, match="invalid account transition"):
            await mgr.transition("u1", AccountStatus.CREATED)

    async def test_deactivated_cannot_go_back_to_active(self) -> None:
        mgr, repo, *_ = self._make_manager()
        repo.seed("u2", AccountStatus.ACTIVE)
        await mgr.transition("u2", AccountStatus.DEACTIVATED)
        with pytest.raises(InvalidAccountTransition):
            await mgr.transition("u2", AccountStatus.ACTIVE)


# === KEY ROTATION ===

class TestKeyRotation:
    def test_seamless_rotation_no_outage(self) -> None:
        import hmac as hmac_mod, hashlib as hl
        km = KeyRotationManager(grace_period_s=3600.0)
        kid1, secret1 = km.introduce_key()
        msg = b"test-message"
        _, sig_with_k1 = km.sign(msg)
        # Old signature verifies before rotation
        assert km.verify_signature(msg, sig_with_k1) == kid1
        # Rotate to K2
        kid2, secret2 = km.introduce_key()
        # OLD signature STILL verifies (grace period)
        assert km.verify_signature(msg, sig_with_k1) == kid1
        # NEW signing uses K2
        new_kid, new_sig = km.sign(msg)
        assert new_kid == kid2
        # New sig verifies against K2
        assert km.verify_signature(msg, new_sig) == kid2
        # Both keys are active during grace period
        assert set(km.active_key_ids()) == {kid1, kid2}

    def test_retired_key_stops_verifying_after_grace(self) -> None:
        km = KeyRotationManager(grace_period_s=0.01)  # near-instant expiry
        kid1, _ = km.introduce_key()
        msg = b"data"
        _, old_sig = km.sign(msg)
        kid2, _ = km.introduce_key()  # triggers retirement schedule for K1
        import time
        time.sleep(0.02)
        # K1 has expired past its grace period
        assert km.verify_signature(msg, old_sig) != kid1 or km.verify_signature(msg, old_sig) is None

    def test_force_retire_immediate(self) -> None:
        km = KeyRotationManager()
        kid1, _ = km.introduce_key()
        kid2, _ = km.introduce_key()  # K1 enters grace; K2 is signer
        km.force_retire(kid1)
        assert set(km.active_key_ids()) == {kid2}


# === STORE ABSTRACTION (distributed-state readiness) ===

@pytest.mark.anyio
class TestStoreAbstraction:
    async def test_expiring_store_roundtrip_and_expiry(self) -> None:
        import asyncio

        store = InMemoryExpiringStore()
        await store.set("key1", {"data": True}, ttl_s=100)
        assert await store.get("key1") is not None
        assert await store.exists("key1") is True
        await store.set("expired", "gone", ttl_s=0.05)
        await asyncio.sleep(0.06)
        assert await store.get("expired") is None

    async def test_set_store_operations(self) -> None:
        s = InMemorySetStore()
        await s.add("revoked_families", "fam_1")
        await s.add("revoked_families", "fam_2")
        assert await s.contains("revoked_families", "fam_1") is True
        assert await s.contains("revoked_families", "fam_3") is False
        assert len(await s.members("revoked_families")) == 2
        await s.remove("revoked_families", "fam_1")
        assert await s.contains("revoked_families", "fam_1") is False

    async def test_counter_store_increments(self) -> None:
        c = InMemoryCounterStore()
        assert await c.increment("login_failures:user1") == 1
        assert await c.increment("login_failures:user1") == 2
        assert await c.increment("login_failures:user1") == 3
        assert await c.get_value("login_failures:user1") == 3
        assert await c.get_value("nonexistent") == 0
