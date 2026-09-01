"""Tests for OpenAPI export helpers used by ``nk export-openapi``."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.export_openapi import (
    enhance_for_postman,
    resolve_postman_defaults,
    write_openapi,
    write_postman_environment,
)


def test_write_openapi_json_and_yaml(tmp_path: Path) -> None:
    schema = {
        "openapi": "3.1.0",
        "info": {"title": "demo", "version": "0.1.0"},
        "paths": {"/api/health": {"get": {"responses": {"200": {"description": "ok"}}}}},
        "servers": [{"url": "http://127.0.0.1:8000"}],
    }
    written = write_openapi(schema, tmp_path / "docs" / "openapi.json", fmt="both")
    assert len(written) == 2
    json_path, yaml_path = written
    assert json_path.exists()
    assert yaml_path.exists()
    loaded = json.loads(json_path.read_text(encoding="utf-8"))
    assert loaded["info"]["title"] == "demo"
    assert "/api/health" in loaded["paths"]
    assert "openapi:" in yaml_path.read_text(encoding="utf-8")


def test_enhance_for_postman_sets_variables_and_auth_examples() -> None:
    defaults = resolve_postman_defaults()
    schema = {
        "info": {"title": "demo", "version": "0.1.0"},
        "paths": {
            "/api/auth/register": {
                "post": {"requestBody": {"content": {"application/json": {}}}},
            },
            "/api/auth/jwt/login": {
                "post": {
                    "requestBody": {
                        "content": {"application/x-www-form-urlencoded": {}},
                    },
                },
            },
        },
        "components": {
            "securitySchemes": {
                "OAuth2PasswordBearer": {
                    "type": "oauth2",
                    "flows": {"password": {"tokenUrl": "auth/jwt/login", "scopes": {}}},
                },
            },
            "schemas": {
                "Body_auth_jwt_login_api_auth_jwt_login_post": {
                    "properties": {"username": {"type": "string"}, "password": {}},
                },
            },
        },
    }

    enhanced = enhance_for_postman(schema, defaults)

    server = enhanced["servers"][0]
    assert server["url"] == "{baseUrl}"
    assert server["variables"]["baseUrl"]["default"] == defaults["baseUrl"]

    oauth = enhanced["components"]["securitySchemes"]["OAuth2PasswordBearer"]
    assert oauth["flows"]["password"]["tokenUrl"] == "/api/auth/jwt/login"
    assert "HTTPBearer" in enhanced["components"]["securitySchemes"]

    login_example = enhanced["paths"]["/api/auth/jwt/login"]["post"]["requestBody"][
        "content"
    ]["application/x-www-form-urlencoded"]["examples"]["dev-login"]["value"]
    assert login_example["username"] == defaults["testEmail"]
    assert login_example["password"] == defaults["testPassword"]


def test_write_postman_environment(tmp_path: Path) -> None:
    defaults = resolve_postman_defaults()
    path = write_postman_environment(defaults, tmp_path / "docs" / "postman-environment.json")
    loaded = json.loads(path.read_text(encoding="utf-8"))
    keys = {item["key"] for item in loaded["values"]}
    assert {"baseUrl", "host", "port", "testEmail", "testPassword", "accessToken"} <= keys
