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
from fastapi_template.profiles import (
    PROFILES,
    complete_profile,
    expand_profile,
    use_case_profile,
)

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
    "enable_fintech": False,
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


def _generate_use_case(use_case: str, name: str) -> dict:
    profile = use_case_profile(use_case)
    assert profile is not None
    ctx = complete_profile(
        profile,
        BuilderContext(
            project_name=name,
            profile=profile,
            use_case=use_case,
            force=True,
        ),
    )
    ctx = _run_pipeline(ctx)
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
    assert Path("smoke_agentic/smoke_agentic/platform/contracts.py").exists()
    assert Path("smoke_agentic/smoke_agentic/agents/runtime.py").exists()
    assert Path("smoke_agentic/smoke_agentic/web/api/knowledge.py").exists()
    for source in (
        "smoke_agentic/smoke_agentic/platform/contracts.py",
        "smoke_agentic/smoke_agentic/platform/control_plane.py",
        "smoke_agentic/smoke_agentic/platform/reproducibility.py",
        "smoke_agentic/smoke_agentic/platform/state.py",
        "smoke_agentic/smoke_agentic/agents/runtime.py",
        "smoke_agentic/smoke_agentic/agents/security.py",
        "smoke_agentic/smoke_agentic/ai/knowledge/answer.py",
        "smoke_agentic/smoke_agentic/ai/knowledge/ingestion.py",
        "smoke_agentic/smoke_agentic/ai/knowledge/retrieval.py",
        "smoke_agentic/smoke_agentic/ai/knowledge/runtime.py",
        "smoke_agentic/smoke_agentic/web/api/agent_protocol.py",
        "smoke_agentic/scripts/backup.py",
        "smoke_agentic/scripts/restore.py",
    ):
        compile(Path(source).read_text(encoding="utf-8"), source, "exec")
    assert not Path("smoke_agentic/smoke_agentic/data/adapters/mongo").exists()


def test_use_case_generates_requested_intent_and_resolved_profile() -> None:
    manifest = _generate_use_case("enterprise-saas", "smoke_enterprise_saas")

    assert manifest["use_case"] == "enterprise-saas"
    assert manifest["profile"] == "saas"
    assert manifest["modules"]["users"] is True
    assert manifest["providers"]["database"] == "postgresql"


def test_manual_composition_uses_empty_profile_metadata() -> None:
    ctx = _run_pipeline(_fully_scripted_context("minimal", "smoke_manual_composition"))
    ctx.data.pop("profile", None)
    ctx.data.pop("use_case", None)
    generate_project(ctx)

    manifest = yaml.safe_load(
        Path("smoke_manual_composition/platform.yaml").read_text(),
    )
    assert manifest["profile"] == ""
    assert manifest["use_case"] is None


def test_minimal_profile_ships_no_data_layer() -> None:
    ctx = _fully_scripted_context("minimal", "smoke_minimal_solo")
    ctx = _run_pipeline(ctx)
    generate_project(ctx)

    manifest = yaml.safe_load(Path("smoke_minimal_solo/platform.yaml").read_text())
    assert manifest["use_case"] is None
    assert manifest["modules"]["agents"] is False
    assert manifest["providers"]["database"] == "none"
    assert not Path("smoke_minimal_solo/smoke_minimal_solo/data").exists()
    assert not Path("smoke_minimal_solo/deploy/helm").exists()
    assert not Path("smoke_minimal_solo/deploy/gitops/application.yaml").exists()


_HEAVY_AI_IMPORTS = ("langchain", "fastembed", "any_llm", "langgraph")


def test_minimal_grep_guard_no_heavy_ai_imports() -> None:
    """Gold rule: minimal tree must not import heavy AI stacks."""
    name = "smoke_minimal_grep"
    _generate("minimal", name)
    pkg = Path(name) / name
    offenders: list[str] = []
    for py_file in pkg.rglob("*.py"):
        text = py_file.read_text(encoding="utf-8")
        for needle in _HEAVY_AI_IMPORTS:
            if f"import {needle}" in text or f"from {needle}" in text:
                offenders.append(f"{py_file.relative_to(name)}:{needle}")
    assert not offenders, f"minimal leaked AI imports: {offenders}"
    assert not (pkg / "core" / "crud.py").exists()
    assert not (pkg / "core" / "event_emitter.py").exists()


def test_minimal_boot_surface_has_no_pruned_deps() -> None:
    """Minimal app sources must not hard-import pruned optional modules."""
    name = "smoke_minimal_boot"
    _generate("minimal", name)
    pkg = Path(name) / name
    assert not (pkg / "core" / "crud.py").exists()
    assert not (pkg / "core" / "event_emitter.py").exists()
    views = (pkg / "web" / "api" / "monitoring" / "views.py").read_text(
        encoding="utf-8",
    )
    assert "operations.metrics" not in views
    assert "/metrics" not in views
    app_src = (pkg / "web" / "application.py").read_text(encoding="utf-8")
    assert "identity.deps" not in app_src
    assert "platform.files" not in app_src


def test_minimal_redis_does_not_import_identity_routes() -> None:
    """Optional infrastructure must not break identity-free profiles."""
    ctx = _fully_scripted_context("minimal", "smoke_minimal_redis")
    ctx.enable_redis = True
    ctx = _run_pipeline(ctx)
    generate_project(ctx)
    router_source = Path(
        "smoke_minimal_redis/smoke_minimal_redis/web/api/router.py",
    ).read_text(encoding="utf-8")
    assert "web.api import redis" not in router_source
    assert "identity.deps" not in router_source


def test_every_profile_generates_key_paths() -> None:
    """Quiet bake each profile offline; assert profile-specific paths."""
    expectations = {
        "minimal": lambda root, pkg: (
            not (pkg / "agents").exists(),
            not (pkg / "data").exists(),
            not (pkg / "ai" / "providers").exists(),
        ),
        "saas": lambda root, pkg: (
            (pkg / "identity").exists(),
            (root / "platform.yaml").exists(),
        ),
        "ai-saas": lambda root, pkg: (
            (pkg / "ai").exists(),
            True,
        ),
        "agentic": lambda root, pkg: (
            (pkg / "agents").exists(),
            True,
        ),
        "fintech": lambda root, pkg: (
            (pkg / "industry" / "fintech").exists(),
            True,
        ),
    }
    for idx, profile in enumerate(PROFILES):
        name = f"smoke_all_{idx}_{profile.replace('-', '_')}"
        manifest = _generate(profile, name)
        assert manifest["profile"] == profile
        root = Path(name)
        pkg = root / name
        checks = expectations[profile](root, pkg)
        assert all(checks), f"{profile} path checks failed: {checks}"

        # nk CLI must ship in every profile
        assert (pkg / "cli" / "__init__.py").exists()
        cli_source = (pkg / "cli" / "__init__.py").read_text(encoding="utf-8")
        assert "--new" in cli_source
        assert "_configure_dev_ports" in cli_source
        pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")
        assert 'nk = "' in pyproject or "nk =" in pyproject
        helm_values = root / "deploy" / "helm" / "nk-backend" / "values.yaml"
        if helm_values.exists():
            helm_source = helm_values.read_text(encoding="utf-8")
            assert "{{ cookiecutter." not in helm_source
            assert "__" not in helm_source
            assert isinstance(yaml.safe_load(helm_source), dict)
            assert f"ownerRole: {name}_owner" in helm_source
        if manifest["observability"]["opentelemetry"]:
            assert "opentelemetry-instrumentation-logging" in pyproject
        if manifest["modules"]["users"]:
            app_source = (pkg / "web" / "application.py").read_text(
                encoding="utf-8",
            )
            router_source = (pkg / "web" / "api" / "router.py").read_text(
                encoding="utf-8",
            )
            assert "CORSMiddleware" in app_source
            assert "TrustedHostMiddleware" in app_source
            assert "protected_router" in router_source
        if manifest["providers"]["database"] == "postgresql":
            assert (
                root / "deploy" / "postgres-init-runtime-role.sh"
            ).exists()
