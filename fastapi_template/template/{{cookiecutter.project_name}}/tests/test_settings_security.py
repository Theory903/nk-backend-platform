from __future__ import annotations

import pytest

from {{cookiecutter.project_name}}.settings import Settings


def test_production_requires_identity() -> None:
    with pytest.raises(ValueError, match="identity provider"):
        Settings(
            environment="prod",
            security_identity_enabled=False,
        )


def test_credentialed_cors_rejects_wildcard() -> None:
    with pytest.raises(ValueError, match="wildcard origin"):
        Settings(
            cors_allowed_origins=["*"],
            cors_allow_credentials=True,
        )

{%- if cookiecutter.prometheus_enabled in [True, "True", "true", 1, "1"] and cookiecutter.add_users in [True, "True", "true", 1, "1"] %}

def test_production_requires_metrics_auth_token() -> None:
    with pytest.raises(ValueError, match="METRICS_AUTH_TOKEN"):
        Settings(
            environment="prod",
            security_identity_enabled=True,
            security_require_auth=True,
            allowed_hosts=["api.example.com"],
            users_secret="production-users-secret-32chars!!",
            auth_store_backend="postgresql",
            metrics_auth_token=None,
        )
{%- endif %}
