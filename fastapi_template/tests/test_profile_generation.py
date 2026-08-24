from pathlib import Path

import yaml

from fastapi_template.__main__ import generate_project
from fastapi_template.cli import (
    api_menu,
    ci_menu,
    db_menu,
    features_menu,
    orm_menu,
    users_backend_menu,
)
from fastapi_template.input_model import BuilderContext
from fastapi_template.profiles import PROFILES, expand_profile

MENUS = [api_menu, db_menu, orm_menu, ci_menu, features_menu, users_backend_menu]

SCRIPTED_DEFAULTS = {
    "api_type": "rest",
    "ci_type": "none",
    "enable_taskiq": False,
    "enable_redis": False,
    "enable_rmq": False,
    "enable_kafka": False,
    "enable_nats": False,
    "add_users": False,
    "enable_migrations": False,
    "add_dummy": False,
    "enable_routers": False,
    "self_hosted_swagger": False,
    "prometheus_enabled": False,
    "sentry_enabled": False,
    "enable_loguru": False,
    "otlp_enabled": False,
    "traefik_labels": False,
    "gunicorn": False,
    "cookie_auth": False,
    "jwt_auth": False,
    "enable_llm": False,
    "enable_vector": False,
    "enable_rag_traditional": False,
    "enable_agents": False,
    "enable_graphrag": False,
    "enable_audit": False,
    "enable_idempotency": False,
}


def _fully_scripted_context(profile: str, name: str) -> BuilderContext:
    ctx = BuilderContext(project_name=name, force=True)
    ctx.profile = profile
    ctx = expand_profile(profile, ctx)
    data = ctx.dict()
    for key, value in SCRIPTED_DEFAULTS.items():
        if data.get(key) is None:
            ctx[key] = value
    return ctx


def _run_pipeline(ctx: BuilderContext) -> BuilderContext:
    for menu in MENUS:
        assert not menu.need_ask(ctx), f"menu {menu.title} would prompt interactively"
        ctx = BuilderContext(**menu.after_ask(context=ctx).dict())
    return ctx


def _generate(profile: str, name: str) -> dict:
    ctx = _run_pipeline(_fully_scripted_context(profile, name))
    generate_project(ctx)
    manifest_path = Path(name) / "platform.yaml"
    assert manifest_path.exists()
    return yaml.safe_load(manifest_path.read_text())


def test_agentic_profile_generates_manifest() -> None:
    manifest = _generate("agentic", "smoke_agentic")

    assert manifest["project"] == "smoke_agentic"
    assert manifest["profile"] == "agentic"
    assert manifest["providers"]["database"] == "postgresql"
    assert manifest["modules"]["agents"] is True
    assert manifest["modules"]["graphrag"] is True
    assert manifest["modules"]["llm"] is True
    assert manifest["modules"]["kafka"] is False

    assert Path("smoke_agentic/smoke_agentic/data/protocols.py").exists()
    assert Path(
        "smoke_agentic/smoke_agentic/data/adapters/sqlalchemy/repository.py",
    ).exists()
    assert not Path("smoke_agentic/smoke_agentic/data/adapters/mongo").exists()


def test_minimal_profile_ships_no_data_layer() -> None:
    ctx = _fully_scripted_context("minimal", "smoke_minimal_solo")
    ctx = _run_pipeline(ctx)
    generate_project(ctx)

    manifest = yaml.safe_load(Path("smoke_minimal_solo/platform.yaml").read_text())
    assert manifest["modules"]["agents"] is False
    assert manifest["providers"]["database"] == "none"
    assert not Path("smoke_minimal_solo/smoke_minimal_solo/data").exists()


def test_every_profile_generates_without_prompts() -> None:
    for idx, profile in enumerate(PROFILES):
        name = f"smoke_all_{idx}_{profile.replace('-', '_')}"
        manifest = _generate(profile, name)
        assert manifest["profile"] == profile
