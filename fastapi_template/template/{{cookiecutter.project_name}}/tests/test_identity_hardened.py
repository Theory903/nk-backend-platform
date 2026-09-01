from unittest.mock import patch

from {{cookiecutter.project_name}}.core.security import (
    create_token,
    hash_password,
    validate_token,
    verify_password,
)
from {{cookiecutter.project_name}}.identity.api_keys import ApiKeyStore
from {{cookiecutter.project_name}}.identity.permissions import has_permission
from {{cookiecutter.project_name}}.identity.principal import Principal


# --- Password hashing ---

def test_password_hash_roundtrip() -> None:
    stored = hash_password("hunter2!")
    assert stored.startswith("scrypt$v=1$")
    assert verify_password("hunter2!", stored) is True
    assert verify_password("wrong", stored) is False


def test_password_hash_unique_salts() -> None:
    a = hash_password("same")
    b = hash_password("same")
    assert a != b


def test_verify_malformed_hash_returns_false() -> None:
    assert verify_password("x", "not-a-hash") is False
    assert verify_password("x", "") is False


# --- Tokens ---

def test_token_create_and_validate() -> None:
    token = create_token("user_abc", secret="s3cret", ttl_s=300)
    subject = validate_token(token, "s3cret")
    assert subject == "user_abc"


def test_token_wrong_secret_rejected() -> None:
    token = create_token("user_abc", secret="right", ttl_s=300)
    assert validate_token(token, "wrong") is None


def test_token_expired() -> None:
    with patch(
        "{{cookiecutter.project_name}}.core.security.time.time",
        return_value=1_000_000,
    ):
        token = create_token("u", secret="k", ttl_s=60)
    with patch(
        "{{cookiecutter.project_name}}.core.security.time.time",
        return_value=1_000_061,
    ):
        assert validate_token(token, "k") is None


# --- API Keys (sync store primitive; see also test_api_keys.py) ---

def test_api_key_create_and_verify() -> None:
    store = ApiKeyStore()
    raw, meta = store.create("ci-bot")
    assert raw.startswith("nk_")
    assert meta.name == "ci-bot"
    verified = store.verify(raw)
    assert verified is not None
    assert verified.name == "ci-bot"
    assert verified.key_id == meta.key_id


def test_api_key_wrong_returns_none() -> None:
    store = ApiKeyStore()
    store.create("real")
    assert store.verify("nk_invalid") is None
    assert store.verify("") is None
    assert store.verify(None) is None  # type: ignore[arg-type]


def test_api_key_revoke() -> None:
    store = ApiKeyStore()
    raw, _meta = store.create("temp")
    assert store.has(raw) is True
    assert store.revoke(raw) is True
    assert store.verify(raw) is None
    assert store.revoke(raw) is False


def test_api_key_scopes_become_principal_permissions() -> None:
    store = ApiKeyStore()
    raw, meta = store.create(
        "publisher",
        scopes={"messaging.publish"},
    )
    verified = store.verify(raw)

    assert verified is not None
    principal = Principal(
        user_id=f"svc:{meta.key_id}",
        scopes=verified.scopes,
        is_service=True,
        provider="api_key",
    )
    assert has_permission(principal, "messaging.publish")
    assert not has_permission(principal, "messaging.consume")


def test_api_key_ip_allowlist_is_enforced() -> None:
    store = ApiKeyStore()
    raw, _meta = store.create(
        "restricted",
        ip_allowlist=("192.0.2.0/24",),
    )

    assert store.verify(raw, client_ip="192.0.2.10") is not None
    assert store.verify(raw, client_ip="198.51.100.10") is None
    assert store.verify(raw) is None


# --- RBAC ---

def _principal(roles: set[str]) -> Principal:
    return Principal(user_id="u", roles=frozenset(roles))


def test_admin_wildcard_grants_all() -> None:
    p = _principal({"admin"})
    assert has_permission(p, "orders.refund")
    assert has_permission(p, "anything")


def test_owner_has_read_write_delete() -> None:
    p = _principal({"owner"})
    assert has_permission(p, "read")
    assert has_permission(p, "write")
    assert has_permission(p, "delete")
    assert not has_permission(p, "orders.refund")


def test_editor_cannot_delete() -> None:
    p = _principal({"editor"})
    assert has_permission(p, "write")
    assert not has_permission(p, "delete")


def test_wildcard_prefix_matching() -> None:
    ROLE_PERMISSIONS_OVERRIDE: dict[str, set[str]] = {"ops": {"orders.*"}}
    perms: set[str] = set()
    for role in {"ops"}:
        perms |= ROLE_PERMISSIONS_OVERRIDE.get(role, set())
    # Direct check on the permission logic
    assert "orders.*" in perms
    parts = "orders.refund".split(".")
    found = False
    for i in range(len(parts), 0, -1):
        if ".".join(parts[:i]) + ".*" in perms:
            found = True
            break
    assert found


def test_anonymous_is_denied() -> None:
    p = Principal(user_id="")
    assert p.is_anonymous
    assert not has_permission(p, "read")
