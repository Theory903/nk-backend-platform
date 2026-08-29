"""ServiceAccount + ServiceAccountRegistry production behaviour."""

from __future__ import annotations

import pytest

from {{cookiecutter.project_name}}.identity.service_accounts import (
    ServiceAccount,
    ServiceAccountRegistry,
)


def test_create_unique_per_org() -> None:
    registry = ServiceAccountRegistry()
    a = registry.create("worker", org_id="org_a", created_by="u1")
    b = registry.create("worker", org_id="org_b", created_by="u1")

    assert a.account_id != b.account_id
    assert a.org_id == "org_a"
    assert b.org_id == "org_b"
    assert isinstance(a.roles, frozenset)
    assert isinstance(a.allowed_ips, tuple)
    assert "service" in a.roles


def test_duplicate_name_same_org_raises() -> None:
    registry = ServiceAccountRegistry()
    registry.create("Worker-1", org_id="org_a")

    with pytest.raises(ValueError, match="already exists"):
        registry.create("worker-1", org_id="org_a")


def test_get_hides_inactive_unless_include_inactive() -> None:
    registry = ServiceAccountRegistry()
    sa = registry.create("bot", org_id="org_a")

    assert registry.get(sa.account_id) is not None
    assert registry.deactivate(sa.account_id) is True
    assert registry.get(sa.account_id) is None

    inactive = registry.get(sa.account_id, include_inactive=True)
    assert inactive is not None
    assert inactive.is_active is False


def test_get_active_ip_cidr_allow_deny_and_empty_allowlist() -> None:
    registry = ServiceAccountRegistry()
    open_sa = registry.create("open", org_id="org_a")
    assert registry.get_active(open_sa.account_id) is not None
    assert registry.get_active(open_sa.account_id, client_ip=None) is not None

    locked = registry.create(
        "locked",
        org_id="org_a",
        allowed_ips=["10.0.0.0/24", "192.168.1.10"],
    )
    assert registry.get_active(
        locked.account_id,
        client_ip="10.0.0.42",
    ) is not None
    assert registry.get_active(
        locked.account_id,
        client_ip="192.168.1.10",
    ) is not None
    assert registry.get_active(
        locked.account_id,
        client_ip="10.0.1.1",
    ) is None
    assert registry.get_active(locked.account_id, client_ip=None) is None
    assert registry.get_active(locked.account_id) is None


def test_deactivate_activate_and_deactivate_created_by() -> None:
    registry = ServiceAccountRegistry()
    sa1 = registry.create("a", org_id="org_a", created_by="owner")
    sa2 = registry.create("b", org_id="org_a", created_by="owner")
    other = registry.create("c", org_id="org_a", created_by="other")

    assert registry.deactivate(sa1.account_id) is True
    assert registry.activate(sa1.account_id) is True
    assert registry.get(sa1.account_id) is not None

    count = registry.deactivate_created_by("owner", org_id="org_a")
    assert count == 2
    assert registry.get(sa1.account_id) is None
    assert registry.get(sa2.account_id) is None
    assert registry.get(other.account_id) is not None


def test_org_id_filter_isolation() -> None:
    registry = ServiceAccountRegistry()
    a = registry.create("shared-name", org_id="org_a", created_by="u1")
    b = registry.create("shared-name", org_id="org_b", created_by="u1")

    assert registry.get(a.account_id, org_id="org_b") is None
    assert registry.get(a.account_id, org_id="org_a") is a
    assert registry.get_by_name("org_a", "shared-name") is a
    assert registry.get_by_name("org_b", "shared-name") is b

    assert [x.account_id for x in registry.list_for_org("org_a")] == [a.account_id]
    assert registry.deactivate(a.account_id, org_id="org_b") is False
    assert registry.get(a.account_id) is a

    deactivated = registry.deactivate_created_by("u1", org_id="org_a")
    assert deactivated == 1
    assert registry.get(a.account_id) is None
    assert registry.get(b.account_id) is b


def test_invalid_cidr_raises_on_create() -> None:
    registry = ServiceAccountRegistry()

    with pytest.raises(ValueError, match="invalid IP/CIDR"):
        registry.create(
            "bad",
            org_id="org_a",
            allowed_ips=["not-an-ip"],
        )


def test_allows_ip_on_account() -> None:
    sa = ServiceAccount(
        account_id="sa_x",
        name="x",
        org_id="org_a",
        allowed_ips=("10.0.0.0/8",),
    )
    assert sa.allows_ip("10.1.2.3") is True
    assert sa.allows_ip("11.0.0.1") is False
    assert sa.allows_ip(None) is False

    open_sa = ServiceAccount(
        account_id="sa_y",
        name="y",
        org_id="org_a",
    )
    assert open_sa.allows_ip(None) is True
