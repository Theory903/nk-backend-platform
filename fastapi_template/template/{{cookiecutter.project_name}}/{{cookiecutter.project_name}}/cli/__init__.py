"""NK app CLI — Next.js-style verbs for a generated project.

Commands: doctor, validate, check, dev, build, start, migrate, seed,
generate, export-openapi, eval, jobs replay, deploy, scale-status
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path
from collections.abc import Sequence


def _project_root() -> Path:
    cwd = Path.cwd()
    if (cwd / "platform.yaml").exists():
        return cwd
    # Allow running from package subdirs
    for parent in cwd.parents:
        if (parent / "platform.yaml").exists():
            return parent
    return cwd


def _load_manifest(root: Path) -> dict:
    path = root / "platform.yaml"
    if not path.exists():
        return {}
    try:
        import yaml
    except ImportError:
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def needs_compose(root: Path | None = None) -> bool:
    """True when platform needs Docker Compose infra (db/redis/brokers)."""
    root = root or _project_root()
    manifest = _load_manifest(root)
    providers = manifest.get("providers") or {}
    modules = manifest.get("modules") or {}
    db = providers.get("database")
    if db not in (None, "none", False, "False"):
        return True
    for key in ("redis", "rabbitmq", "kafka", "nats", "taskiq"):
        if modules.get(key) in (True, "True", "true", 1):
            return True
    return False


def _select_port(
    env_name: str,
    preferred: int,
    *,
    reserved: set[int] | None = None,
) -> int:
    """Use an explicit port or select the next available local port."""
    reserved = reserved or set()
    configured = os.environ.get(env_name)
    if configured is not None:
        try:
            port = int(configured)
        except ValueError as exc:
            raise ValueError(f"{env_name} must be an integer port") from exc
        if not 1 <= port <= 65535:
            raise ValueError(f"{env_name} must be between 1 and 65535")
        if port in reserved:
            raise ValueError(f"{env_name} conflicts with another development port")
        if not _port_is_available(port):
            raise ValueError(
                f"{env_name}={port} is already in use; choose another port"
            )
        return port

    port = preferred
    while port <= 65535:
        if port in reserved:
            port += 1
            continue
        if _port_is_available(port):
            os.environ[env_name] = str(port)
            return port
        port += 1

    raise ValueError(f"no available port found for {env_name}")


def _port_is_available(port: int) -> bool:
    """Return whether a TCP listener can be bound to the local port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def _load_dotenv_port_overrides(project: str) -> None:
    """Load port-related values from ``.env`` without overriding the shell."""
    env_file = _project_root() / ".env"
    if not env_file.exists():
        return

    names = {
        "COMPOSE_PROJECT_NAME",
        "GRAFANA_PORT",
        "PORT",
        f"{project.upper()}_PORT",
    }
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, separator, value = line.partition("=")
        key = key.strip()
        if (
            separator
            and (key in names or key.startswith("NK_"))
            and key not in os.environ
        ):
            os.environ[key] = value.strip().strip("\"'")


def _dotenv_has_key(root: Path, key_name: str) -> bool:
    """Check whether a key exists in ``.env`` without exposing its value."""
    env_file = root / ".env"
    if not env_file.exists():
        return False
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("export "):
            line = line[7:].lstrip()
        if line.partition("=")[0].strip() == key_name:
            return True
    return False


def _project_port(project: str) -> int:
    """Read the generated app's preferred port from environment."""
    env_name = f"{project.upper()}_PORT"
    configured = os.environ.get(env_name)
    if not configured:
        return 8000
    try:
        port = int(configured)
    except ValueError as exc:
        raise ValueError(f"{env_name} must be an integer port") from exc
    if not 1 <= port <= 65535:
        raise ValueError(f"{env_name} must be between 1 and 65535")
    return port


def _select_api_port(project: str) -> int:
    """Resolve the API host port, preferring the Compose-specific override."""
    _load_dotenv_port_overrides(project)
    project_port = _project_port(project)
    if "NK_API_PORT" in os.environ:
        return _select_port("NK_API_PORT", project_port)

    port = _select_port("PORT", project_port)
    os.environ["NK_API_PORT"] = str(port)
    return port


def _configure_dev_ports(manifest: dict, *, otlp: bool = False) -> int:
    """Configure collision-free host ports for local development."""
    project = manifest.get("project") or _project_root().name
    api_port = _select_api_port(project)
    selected_ports = {api_port}

    providers = manifest.get("providers") or {}
    database = providers.get("database")
    database_ports = {"postgresql": 5432, "mysql": 3306, "mongodb": 27017}
    if database in database_ports:
        db_port = _select_port(
            "NK_DB_PORT",
            database_ports[database],
            reserved=selected_ports,
        )
        selected_ports.add(db_port)

    modules = manifest.get("modules") or {}
    service_ports = {
        "redis": ("redis", 6379),
        "rabbitmq": ("rabbit", 5672),
        "kafka": ("kafka", 9094),
        "nats": ("nats", 4222),
    }
    for module, (env_name, preferred) in service_ports.items():
        if modules.get(module) in (True, "True", "true", 1):
            service_port = _select_port(
                f"NK_{env_name.upper()}_PORT",
                preferred,
                reserved=selected_ports,
            )
            selected_ports.add(service_port)
            if module == "rabbitmq":
                management_port = _select_port(
                    "NK_RABBIT_MANAGEMENT_PORT",
                    15672,
                    reserved=selected_ports,
                )
                selected_ports.add(management_port)

    if otlp:
        if "NK_GRAFANA_PORT" not in os.environ and "GRAFANA_PORT" in os.environ:
            os.environ["NK_GRAFANA_PORT"] = os.environ["GRAFANA_PORT"]
        _select_port("NK_GRAFANA_PORT", 3000, reserved=selected_ports)

    if modules.get("llm") in (True, "True", "true", 1):
        _select_port(
            "NK_OLLAMA_PORT",
            11434,
            reserved=selected_ports,
        )

    if modules.get("vector") in (True, "True", "true", 1):
        _select_port(
            "NK_QDRANT_PORT",
            6333,
            reserved=selected_ports,
        )

    return int(os.environ["NK_API_PORT"])


def _compose_command(
    project_name: str,
    *args: str,
    otlp: bool = False,
) -> list[str]:
    """Build a Compose command scoped to one isolated project name."""
    command = [
        "docker",
        "compose",
        "--project-name",
        project_name,
        "-f",
        "docker-compose.yml",
        "-f",
        "docker-compose.dev.yml",
    ]
    if otlp:
        command.extend(["-f", "deploy/docker-compose.otlp.yml"])
    command.extend(args)
    return command


def _compose_has_containers(root: Path, project_name: str) -> bool:
    """Return whether Compose already has containers for this project."""
    result = subprocess.run(
        _compose_command(project_name, "ps", "-aq"),
        cwd=str(root),
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0 and bool(result.stdout.strip())


def _compose_project_is_used(root: Path, project_name: str) -> bool:
    """Return whether containers or persistent Compose resources use a name."""
    if _compose_has_containers(root, project_name):
        return True
    label = f"com.docker.compose.project={project_name}"
    for resource in ("volume", "network"):
        result = subprocess.run(
            ["docker", resource, "ls", "--filter", f"label={label}", "-q"],
            cwd=str(root),
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            return True
    return False


def _compose_api_port(
    root: Path,
    project_name: str,
    container_port: int = 8000,
) -> int | None:
    """Read the host port assigned to an existing API container."""
    result = subprocess.run(
        _compose_command(project_name, "port", "api", str(container_port)),
        cwd=str(root),
        capture_output=True,
        text=True,
        check=False,
    )
    endpoint = result.stdout.strip().splitlines()
    if endpoint:
        try:
            return int(endpoint[0].rsplit(":", 1)[-1].rstrip("]"))
        except ValueError:
            pass
    return None


def _next_compose_project_name(root: Path, project_name: str) -> str:
    """Find an unused project name for a second local stack."""
    suffix = 2
    while True:
        candidate = f"{project_name}-{suffix}"
        if not _compose_project_is_used(root, candidate):
            return candidate
        suffix += 1


def _choose_compose_project(
    root: Path,
    manifest: dict,
    args: argparse.Namespace,
) -> tuple[str, bool]:
    """Choose whether to reuse the current stack or create an isolated one."""
    project = manifest.get("project") or root.name
    _load_dotenv_port_overrides(project)
    project_name = os.environ.get("COMPOSE_PROJECT_NAME") or project
    if getattr(args, "new_stack", False):
        return _next_compose_project_name(root, project_name), False
    project_is_used = _compose_project_is_used(root, project_name)
    if getattr(args, "reuse", False) and not project_is_used:
        raise ValueError(
            f"Compose project '{project_name}' does not exist; "
            "remove --reuse or use --new."
        )
    if not project_is_used:
        return project_name, False

    if getattr(args, "reuse", False):
        return project_name, True

    try:
        answer = input(
            f"Compose project '{project_name}' already exists. "
            "Use existing containers? [Y/n] "
        )
    except EOFError:
        answer = ""
    if answer.strip().lower() not in {"n", "no"}:
        return project_name, True
    return _next_compose_project_name(root, project_name), False


def _run(cmd: Sequence[str], *, cwd: Path | None = None) -> int:
    print("+", " ".join(cmd))
    return subprocess.call(list(cmd), cwd=str(cwd or _project_root()))


def cmd_doctor(_: argparse.Namespace) -> int:
    root = _project_root()
    sys.path.insert(0, str(root))
    from scripts.doctor import run_doctor

    ok = run_doctor(root)
    return 0 if ok else 1


def cmd_ai_doctor(_: argparse.Namespace) -> int:
    root = _project_root()
    sys.path.insert(0, str(root))
    from scripts.ai_doctor import run_ai_doctor

    ok = run_ai_doctor(root)
    return 0 if ok else 1


def cmd_ai_routes(_: argparse.Namespace) -> int:
    root = _project_root()
    sys.path.insert(0, str(root))
    from {{cookiecutter.project_name}}.ai.gateway import get_router

    router = get_router()
    print("Capability routes:")
    for capability in router.capabilities:
        route = router.for_capability(capability)
        fallbacks = ", ".join(f"{p}/{m}" for p, m in route.fallback) or "none"
        print(f"  {capability:12} {route.provider}/{route.model}  fallback: {fallbacks}")
    print("\nTask aliases:")
    for task, capability in sorted(router.task_aliases.items()):
        print(f"  {task:12} -> {capability}")
    return 0


def cmd_ai_runtime_modes(_: argparse.Namespace) -> int:
    root = _project_root()
    sys.path.insert(0, str(root))
    from {{cookiecutter.project_name}}.agents.types import RuntimeMode

    print("Agent runtime ladder:")
    for mode in RuntimeMode:
        if mode is RuntimeMode.AUTO:
            print(f"  {mode.value:12} auto-select from task + tools")
        elif mode is RuntimeMode.LOOP:
            print(f"  {mode.value:12} tool loop / lightweight Q&A")
        elif mode is RuntimeMode.GRAPH:
            print(f"  {mode.value:12} LangGraph workflow + checkpointing")
        elif mode is RuntimeMode.SUPERVISOR:
            print(f"  {mode.value:12} planner + worker delegation")
    print("\nExample: POST /agent/runs {\"runtime_mode\": \"supervisor\", ...}")
    return 0


def cmd_ai_tools_list(_: argparse.Namespace) -> int:
    root = _project_root()
    sys.path.insert(0, str(root))
    from {{cookiecutter.project_name}}.agents.tool_policy import load_tool_policy_manifest
    from {{cookiecutter.project_name}}.agents.tools import ToolRegistry
    from {{cookiecutter.project_name}}.llm.features.registry import register_feature_tools
    from {{cookiecutter.project_name}}.llm.features.runtime import get_or_create_runtime
    from {{cookiecutter.project_name}}.platform.contracts import Scope, ToolDescriptor

    registry = ToolRegistry()
    runtime = get_or_create_runtime(None)
    register_feature_tools(registry, runtime)
    manifest = load_tool_policy_manifest()
    policy = manifest.policy
    scope = Scope(principal_id="cli", organization_id="local")

    print("Registered tools:")
    for name in sorted(registry.names()):
        tool = registry.get(name)
        if tool is None:
            continue
        descriptor = ToolDescriptor(
            name=tool.name,
            description=tool.description,
            input_schema=tool.parameters,
            risk=tool.risk,
            requires_approval=tool.requires_approval,
        )
        decision = policy.authorize(scope, descriptor)
        flags: list[str] = []
        if not decision.allowed:
            flags.append("denied")
        elif decision.requires_approval:
            flags.append("approval")
        suffix = f" ({', '.join(flags)})" if flags else ""
        print(f"  {name:24} {tool.risk.value}{suffix}")

    print(f"\nMCP servers configured: {len(manifest.mcp_servers)}")
    for spec in manifest.mcp_servers:
        status = "enabled" if spec.enabled else "disabled"
        print(f"  {spec.name:16} {spec.transport}  {status}")
    return 0


def _cli_scope(args: argparse.Namespace):
    root = _project_root()
    sys.path.insert(0, str(root))
    from {{cookiecutter.project_name}}.platform.contracts import Scope

    return Scope(
        principal_id=getattr(args, "principal", "cli"),
        organization_id=getattr(args, "org", "local"),
    )


async def _cli_session_runtime():
    root = _project_root()
    sys.path.insert(0, str(root))
    from {{cookiecutter.project_name}}.agents.session_runtime import SessionRuntime
    from {{cookiecutter.project_name}}.agents.session_store import SessionEventStore
    from {{cookiecutter.project_name}}.platform.state import InMemoryStateStore, RedisStateStore
    from {{cookiecutter.project_name}}.settings import settings

    redis_url = getattr(settings, "redis_url", None)
    if redis_url:
        from redis.asyncio import Redis

        client = Redis.from_url(str(redis_url))
        store = RedisStateStore(client)
    else:
        store = InMemoryStateStore()
    return SessionRuntime(SessionEventStore(store))


def cmd_ai_inspect(args: argparse.Namespace) -> int:
    import asyncio
    from uuid import UUID

    async def _run() -> int:
        runtime = await _cli_session_runtime()
        scope = _cli_scope(args)
        payload = await runtime.inspect(scope, UUID(args.run_id))
        print(json.dumps(payload, indent=2, default=str))
        return 0

    return asyncio.run(_run())


def cmd_ai_replay(args: argparse.Namespace) -> int:
    import asyncio
    from uuid import UUID

    async def _run() -> int:
        runtime = await _cli_session_runtime()
        scope = _cli_scope(args)
        events = await runtime.replay(scope, UUID(args.run_id))
        if not events:
            print(f"no events for run {args.run_id}")
            return 1
        for event in events:
            print(
                f"[{event.sequence:03d}] {event.kind.value:18} "
                f"{json.dumps(event.payload, default=str)}",
            )
        return 0

    return asyncio.run(_run())


def cmd_ai_fork(args: argparse.Namespace) -> int:
    import asyncio
    from uuid import UUID

    async def _run() -> int:
        runtime = await _cli_session_runtime()
        scope = _cli_scope(args)
        new_id = await runtime.fork(
            scope,
            UUID(args.run_id),
            through_sequence=args.through_sequence,
        )
        print(str(new_id))
        return 0

    return asyncio.run(_run())


def cmd_ai_resume(args: argparse.Namespace) -> int:
    import asyncio
    from uuid import UUID

    async def _run() -> int:
        runtime = await _cli_session_runtime()
        scope = _cli_scope(args)
        try:
            payload = await runtime.resume_context(scope, UUID(args.run_id))
        except ValueError as exc:
            print(str(exc))
            return 1
        print(json.dumps(payload, indent=2, default=str))
        return 0

    return asyncio.run(_run())


def _default_scenarios_path(root: Path) -> Path:
    for candidate in (
        root / "tests" / "evals" / "scenarios.yaml",
        root / "tests" / "evals" / "golden.yaml",
    ):
        if candidate.is_file():
            return candidate
    return root / "tests" / "evals" / "scenarios.yaml"


async def _harness_execute(args: argparse.Namespace, mode: str) -> int:
    from {{cookiecutter.project_name}}.agents.evaluation import format_report
    from {{cookiecutter.project_name}}.agents.harness import (
        HarnessMode,
        ScenarioRunner,
        load_scenarios_yaml,
    )
    from {{cookiecutter.project_name}}.agents.tools import ToolRegistry
    from {{cookiecutter.project_name}}.ai.gateway.router import get_router
    from {{cookiecutter.project_name}}.llm.features.registry import register_feature_tools
    from {{cookiecutter.project_name}}.llm.features.runtime import get_or_create_runtime

    root = _project_root()
    path = Path(args.scenarios) if getattr(args, "scenarios", None) else _default_scenarios_path(root)
    scenarios = load_scenarios_yaml(path)
    registry = ToolRegistry()
    register_feature_tools(registry, get_or_create_runtime(None))
    harness_mode = HarnessMode(mode)
    runner = ScenarioRunner(
        get_router().model_for(),
        tools=registry,
        mode=harness_mode,
        fixture_dir=getattr(args, "fixture_dir", None) or root / "tests" / "evals" / "fixtures",
    )
    report = await runner.run_scenarios(scenarios)
    print(format_report(report.eval))
    print(f"Harness mode: {report.mode.value}")
    for item in report.trajectories:
        tools = ", ".join(item.trajectory.tools) or "none"
        print(f"  trajectory {item.scenario}/{item.case_name}: tools=[{tools}]")
    if report.fixtures_written:
        print("Fixtures written:")
        for fixture in report.fixtures_written:
            print(f"  {fixture}")
    return 0 if report.failed == 0 else 1


def cmd_ai_harness_run(args: argparse.Namespace) -> int:
    import asyncio

    return asyncio.run(_harness_execute(args, "run"))


def cmd_ai_harness_record(args: argparse.Namespace) -> int:
    import asyncio

    return asyncio.run(_harness_execute(args, "record"))


def cmd_ai_harness_replay(args: argparse.Namespace) -> int:
    import asyncio

    return asyncio.run(_harness_execute(args, "replay"))


def cmd_ai_harness_list(args: argparse.Namespace) -> int:
    root = _project_root()
    sys.path.insert(0, str(root))
    from {{cookiecutter.project_name}}.agents.harness import load_scenarios_yaml

    path = Path(args.scenarios) if args.scenarios else _default_scenarios_path(root)
    scenarios = load_scenarios_yaml(path)
    print(f"Scenarios in {path}:")
    for scenario in scenarios:
        print(f"  {scenario.name:20} mode={scenario.runtime_mode} cases={len(scenario.cases)}")
        if scenario.description:
            print(f"    {scenario.description}")
    return 0


def cmd_ai_eval_list(_: argparse.Namespace) -> int:
    root = _project_root()
    sys.path.insert(0, str(root))
    from {{cookiecutter.project_name}}.agents.evaluation.adapters import list_adapters

    print("Evaluation adapters:")
    for info in list_adapters():
        status = "installed" if info.installed else "missing"
        hint = f" ({info.install_hint})" if info.install_hint and not info.installed else ""
        print(f"  {info.name:12} {info.description}  [{status}]{hint}")
    return 0


async def _eval_run_execute(args: argparse.Namespace) -> int:
    from {{cookiecutter.project_name}}.agents.evaluation import format_report
    from {{cookiecutter.project_name}}.agents.evaluation.adapters import get_adapter
    from {{cookiecutter.project_name}}.agents.harness import load_scenarios_yaml
    from {{cookiecutter.project_name}}.agents.tools import ToolRegistry
    from {{cookiecutter.project_name}}.ai.gateway.router import get_router
    from {{cookiecutter.project_name}}.llm.features.registry import register_feature_tools
    from {{cookiecutter.project_name}}.llm.features.runtime import get_or_create_runtime

    root = _project_root()
    path = Path(args.dataset) if args.dataset else _default_scenarios_path(root)
    scenarios = load_scenarios_yaml(path)
    cases = [case for scenario in scenarios for case in scenario.cases]
    adapter = get_adapter(args.adapter)
    registry = ToolRegistry()
    register_feature_tools(registry, get_or_create_runtime(None))
    model = get_router().model_for()

    if args.adapter == "harness":
        report = await adapter.run(
            cases,
            None,
            scenarios_path=path,
            model=model,
            tools=registry,
        )
    elif args.adapter == "promptfoo":
        from {{cookiecutter.project_name}}.agents.factory import AgentRuntimeFactory
        from {{cookiecutter.project_name}}.platform.contracts import Scope

        scope = Scope(principal_id="eval", organization_id="eval")

        async def runner(user_input: str) -> dict[str, object]:
            runtime = AgentRuntimeFactory.create(
                "loop",
                model=model,
                tools=registry,
                scope=scope,
                task=user_input,
            )
            result = await runtime.run(user_input)
            return {"output": str(getattr(result, "content", result) or ""), "tools": []}

        report = await adapter.run(
            cases,
            runner,
            export_path=root / "tests" / "evals" / "promptfoo.yaml",
            invoke_cli=getattr(args, "invoke_promptfoo", False),
        )
    else:
        from {{cookiecutter.project_name}}.agents.factory import AgentRuntimeFactory
        from {{cookiecutter.project_name}}.platform.contracts import Scope

        scope = Scope(principal_id="eval", organization_id="eval")

        async def runner(user_input: str) -> dict[str, object]:
            runtime = AgentRuntimeFactory.create(
                "loop",
                model=model,
                tools=registry,
                scope=scope,
                task=user_input,
            )
            result = await runtime.run(user_input)
            content = str(getattr(result, "content", result) or "")
            tools = []
            if hasattr(result, "trace"):
                tools = [
                    str(step[1])
                    for step in result.trace
                    if len(step) >= 2 and step[0] == "tool"
                ]
            return {"output": content, "tools": tools}

        report = await adapter.run(cases, runner)

    print(format_report(report))
    print(f"Adapter: {args.adapter}")
    return 0 if report.failed == 0 else 1


def cmd_ai_eval_run(args: argparse.Namespace) -> int:
    import asyncio

    return asyncio.run(_eval_run_execute(args))


def cmd_ai_security_audit(_: argparse.Namespace) -> int:
    root = _project_root()
    sys.path.insert(0, str(root))
    from {{cookiecutter.project_name}}.agents.security_invariants import (
        format_invariant_report,
        run_security_invariants,
    )

    results = run_security_invariants()
    print(format_invariant_report(results))
    return 0 if all(item.passed for item in results) else 1


def cmd_ai_metrics(_: argparse.Namespace) -> int:
    root = _project_root()
    sys.path.insert(0, str(root))
    from {{cookiecutter.project_name}}.ai.usage import get_tracker

    records = get_tracker().all()
    print("LLM usage (in-process tracker)")
    print("==============================")
    if not records:
        print("No completions recorded yet.")
        return 0
    total_cost = 0.0
    for provider, rec in sorted(records.items()):
        total_cost += rec.cost_usd
        print(
            f"  {provider:16} calls={rec.calls:4}  "
            f"in={rec.prompt_tokens:6} out={rec.completion_tokens:6}  "
            f"cost=${rec.cost_usd:.4f}",
        )
    print(f"\nTotal estimated cost: ${total_cost:.4f} USD")
    print("Prometheus: nk_llm_request_duration_seconds, nk_genai_tool_duration_seconds")
    print("OTel: gen_ai.chat / gen_ai.tool.invoke / gen_ai.agent.run spans when OTLP enabled")
    return 0


def _load_platform_manifest(root: Path) -> dict:
    path = root / "platform.yaml"
    if not path.is_file():
        return {}
    import yaml

    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def cmd_ai_plugins_list(_: argparse.Namespace) -> int:
    root = _project_root()
    sys.path.insert(0, str(root))
    from {{cookiecutter.project_name}}.kernel.plugins.lifecycle import format_plugin_report
    from {{cookiecutter.project_name}}.kernel.plugins.bootstrap import build_plugin_kernel

    kernel = build_plugin_kernel(_load_platform_manifest(root))
    print(format_plugin_report(kernel))
    providers = kernel.capability_providers()
    if providers:
        print("\nCapabilities:")
        for capability, plugin in sorted(providers.items()):
            print(f"  {capability:20} -> {plugin}")
    return 0


def cmd_ai_plugins_health(_: argparse.Namespace) -> int:
    root = _project_root()
    sys.path.insert(0, str(root))
    from {{cookiecutter.project_name}}.kernel.plugins.lifecycle import format_health_report
    from {{cookiecutter.project_name}}.kernel.plugins.bootstrap import build_plugin_kernel

    kernel = build_plugin_kernel(_load_platform_manifest(root))
    kernel.start_all()
    print(format_health_report(kernel.health_all()))
    return 0


def cmd_ai_experiment_hypotheses(_: argparse.Namespace) -> int:
    root = _project_root()
    sys.path.insert(0, str(root))
    from {{cookiecutter.project_name}}.research.experiments.runtime import (
        format_hypothesis_catalog,
        load_hypothesis_catalog,
    )

    print(format_hypothesis_catalog(load_hypothesis_catalog()))
    return 0


def cmd_ai_experiment_leaderboard(args: argparse.Namespace) -> int:
    root = _project_root()
    sys.path.insert(0, str(root))
    from {{cookiecutter.project_name}}.research.experiments.runtime import (
        build_experiment_runtime,
        format_leaderboard,
    )

    runtime = build_experiment_runtime()
    print(format_leaderboard(runtime.leaderboard()))
    return 0


async def _run_experiment_case_runner(
    args: argparse.Namespace,
    config: dict[str, object],
) -> tuple[str, list[dict[str, object]]]:
    from {{cookiecutter.project_name}}.agents.factory import AgentRuntimeFactory
    from {{cookiecutter.project_name}}.agents.harness.scenarios import load_scenarios_yaml
    from {{cookiecutter.project_name}}.platform.contracts import Scope

    root = _project_root()
    path = Path(args.scenarios) if args.scenarios else root / "tests" / "evals" / "scenarios.yaml"
    scenarios = load_scenarios_yaml(path)
    cases = [case for scenario in scenarios for case in scenario.cases]
    scope = Scope(principal_id="experiment", organization_id="experiment")

    async def runner(user_input: str) -> dict[str, object]:
        runtime = AgentRuntimeFactory.create(
            str(config.get("runtime_mode", "loop")),
            model=get_router().model_for(),
            tools=ToolRegistry(),
            scope=scope,
            task=user_input,
        )
        result = await runtime.run(user_input)
        content = str(getattr(result, "content", result) or "")
        return {"output": content, "tools": []}

    passed = 0
    tool_calls: list[dict[str, object]] = []
    for case in cases:
        try:
            outcome = await runner(case.input)
            if any(expected in str(outcome.get("output", "")) for expected in (case.expected or [])):
                passed += 1
        except Exception:
            pass
        tool_calls.append({"case": case.name, "runner": "agent-runtime"})
    score = passed / max(1, len(cases))
    return score, tool_calls


def cmd_ai_experiment_run(args: argparse.Namespace) -> int:
    import asyncio

    root = _project_root()
    sys.path.insert(0, str(root))
    from {{cookiecutter.project_name}}.agents.tools import ToolRegistry
    from {{cookiecutter.project_name}}.ai.gateway.router import get_router
    from {{cookiecutter.project_name}}.research.experiments.mutations import apply_mutation
    from {{cookiecutter.project_name}}.research.experiments.runtime import (
        build_experiment_runtime,
        default_pass_rate_score,
        load_hypothesis_catalog,
    )

    runtime = build_experiment_runtime()
    catalog = load_hypothesis_catalog()
    hypothesis = catalog.get(args.hypothesis_id)
    if hypothesis is None:
        print(f"unknown hypothesis: {args.hypothesis_id}", file=sys.stderr)
        return 1

    base_config: dict[str, object] = {"runtime_mode": hypothesis.target_ref}
    if hypothesis.mutation.changes.get("capability"):
        base_config["capability"] = hypothesis.mutation.changes["capability"]

    candidate_config = apply_mutation(base_config, hypothesis.mutation)
    score, _ = asyncio.run(_run_experiment_case_runner(args, candidate_config))
    record = asyncio.run(
        runtime.run(
            args.hypothesis_id,
            [],
            base_config=base_config,
        ),
    )
    record = record.model_copy(update={"candidate_score": score})
    runtime.store.add(record)
    print(f"hypothesis: {record.hypothesis_id}")
    print(f"baseline: {record.baseline_score:.3f}")
    print(f"candidate: {record.candidate_score:.3f}")
    print(f"outcome: {record.outcome.value}")
    return 0 if record.outcome.value != "failed" else 1


def cmd_ai_experiment_rollback(args: argparse.Namespace) -> int:
    root = _project_root()
    sys.path.insert(0, str(root))
    from {{cookiecutter.project_name}}.research.experiments.runtime import build_experiment_runtime

    runtime = build_experiment_runtime()
    record = runtime.rollback(args.experiment_id)
    if record is None:
        print(f"unknown experiment: {args.experiment_id}", file=sys.stderr)
        return 1
    print(f"rolled back {args.experiment_id} -> {record.outcome.value}")
    return 0


def cmd_ai_self_improving_propose(args: argparse.Namespace) -> int:
    root = _project_root()
    sys.path.insert(0, str(root))
    from {{cookiecutter.project_name}}.research.self_improving.pipeline import build_self_improving_pipeline

    pipeline = build_self_improving_pipeline()
    try:
        proposal = pipeline.propose_from_experiment(args.hypothesis_id)
    except KeyError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"proposal: {proposal.title or proposal.hypothesis_id}")
    print(f"expected_delta: {proposal.expected_delta}")
    print(f"signals: {', '.join(proposal.signals) or '-'}")
    return 0


def cmd_ai_self_improving_runs(_: argparse.Namespace) -> int:
    root = _project_root()
    sys.path.insert(0, str(root))
    from {{cookiecutter.project_name}}.research.self_improving.pipeline import (
        build_self_improving_pipeline,
        format_pipeline_report,
    )

    pipeline = build_self_improving_pipeline()
    print(format_pipeline_report(pipeline))
    return 0


def cmd_validate(_: argparse.Namespace) -> int:
    root = _project_root()
    sys.path.insert(0, str(root))
    from scripts.validate import run_validate

    ok = run_validate(root)
    return 0 if ok else 1


def cmd_check(_: argparse.Namespace) -> int:
    root = _project_root()
    pkg = None
    for child in root.iterdir():
        if child.is_dir() and (child / "__init__.py").exists() and child.name not in {
            "tests",
            "scripts",
            "business",
            "deploy",
        }:
            # prefer directory matching project name from platform.yaml
            pkg = child
            break
    manifest = _load_manifest(root)
    project = manifest.get("project")
    if project and (root / project).is_dir():
        pkg = root / project
    pkg_name = pkg.name if pkg else "."

    steps = [
        ["uv", "run", "ruff", "format", "--check", "."],
        ["uv", "run", "ruff", "check", "."],
        ["uv", "run", "mypy", pkg_name, "tests"],
        ["uv", "run", "pytest", "-q"],
    ]
    for step in steps:
        code = _run(step, cwd=root)
        if code != 0:
            print(f"nk check failed at: {' '.join(step)}", file=sys.stderr)
            print("Fix: re-run that command, then `uv run nk check`", file=sys.stderr)
            return code
    print("nk check: all green")
    return 0


def cmd_dev(args: argparse.Namespace) -> int:
    root = _project_root()
    manifest = _load_manifest(root)
    project = manifest.get("project") or root.name
    if getattr(args, "app_only", False):
        os.environ.setdefault(f"{project.upper()}_ENVIRONMENT", "dev")
    host = os.environ.get("HOST", "0.0.0.0")
    compose_mode = (
        (
            needs_compose(root)
            or getattr(args, "otlp", False)
            or getattr(args, "reuse", False)
            or getattr(args, "new_stack", False)
        )
        and not getattr(args, "app_only", False)
    )
    if compose_mode:
        if shutil.which("docker") is None:
            print(
                "Docker is required for this profile. "
                "Install Docker or pass --app-only for uvicorn only.",
                file=sys.stderr,
            )
            return 1
        if getattr(args, "otlp", False) and not (
            root / "deploy" / "docker-compose.otlp.yml"
        ).exists():
            print(
                "The OpenTelemetry overlay is not enabled in this project.",
                file=sys.stderr,
            )
            return 2
        if getattr(args, "otlp", False) and not (
            os.environ.get("GRAFANA_ADMIN_PASSWORD")
            or _dotenv_has_key(root, "GRAFANA_ADMIN_PASSWORD")
        ):
            print(
                "Set GRAFANA_ADMIN_PASSWORD in the environment or .env "
                "before using --otlp.",
                file=sys.stderr,
            )
            return 2
        try:
            compose_project, reuse_existing = _choose_compose_project(root, manifest, args)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        os.environ["COMPOSE_PROJECT_NAME"] = compose_project
        if compose_project != project:
            os.environ.setdefault(
                f"{project.upper()}_TRAEFIK_HOST",
                f"{compose_project}.localhost",
            )
        if reuse_existing:
            if getattr(args, "otlp", False):
                print(
                    "Cannot add the OpenTelemetry overlay while reusing "
                    "existing containers; use --new instead.",
                    file=sys.stderr,
                )
                return 2
            try:
                port = _compose_api_port(
                    root,
                    compose_project,
                    8000,
                )
            except ValueError as exc:
                print(f"Invalid development port: {exc}", file=sys.stderr)
                return 2
            print(f"Reusing existing Compose project '{compose_project}'.")
            if port is None:
                print("The existing stack has no host API port mapping.")
            else:
                print(f"Docs will be at http://localhost:{port}/api/docs")
            return _run(
                _compose_command(
                    compose_project,
                    "up",
                    "--no-build",
                    "--no-recreate",
                    otlp=getattr(args, "otlp", False),
                ),
                cwd=root,
            )
        try:
            port = _configure_dev_ports(manifest, otlp=getattr(args, "otlp", False))
        except ValueError as exc:
            print(f"Invalid development port: {exc}", file=sys.stderr)
            return 2
        print(
            f"Using local API port {port}; "
            "occupied service ports are shifted automatically."
        )
        compose = _compose_command(
            compose_project,
            "up",
            "--build",
            otlp=getattr(args, "otlp", False),
        )
        print(f"Docs will be at http://localhost:{port}/api/docs")
        return _run(compose, cwd=root)

    # minimal / no-infra: uvicorn reload only
    try:
        port = _select_api_port(project)
    except ValueError as exc:
        print(f"Invalid development port: {exc}", file=sys.stderr)
        return 2
    app = f"{project}.web.application:get_app"
    cmd = [
        "uv",
        "run",
        "uvicorn",
        app,
        "--factory",
        "--reload",
        "--host",
        host,
        "--port",
        str(port),
    ]
    print(f"Starting {app}")
    print(f"Open http://localhost:{port}/api/docs")
    return _run(cmd, cwd=root)


def cmd_build(_: argparse.Namespace) -> int:
    root = _project_root()
    if shutil.which("docker") is None:
        print("Docker is required for `nk build`.", file=sys.stderr)
        return 1
    manifest = _load_manifest(root)
    project = manifest.get("project") or root.name
    _load_dotenv_port_overrides(project)
    compose_project = os.environ.get("COMPOSE_PROJECT_NAME") or project
    tags = [
        "--tag",
        f"{compose_project}-api:local",
        "--tag",
        f"{compose_project}-api:latest",
    ]
    modules = manifest.get("modules") or {}
    if modules.get("taskiq") in (True, "True", "true", 1):
        tags.extend(
            [
                "--tag",
                f"{compose_project}-worker:local",
                "--tag",
                f"{compose_project}-worker:latest",
            ]
        )
    providers = manifest.get("providers") or {}
    if (
        modules.get("migrations") in (True, "True", "true", 1)
        and providers.get("orm") != "psycopg"
    ):
        tags.extend(
            [
                "--tag",
                f"{compose_project}-migrator:local",
                "--tag",
                f"{compose_project}-migrator:latest",
            ]
        )
    return _run(
        ["docker", "build", "--target", "prod", *tags, "."],
        cwd=root,
    )


def cmd_start(args: argparse.Namespace) -> int:
    """Start the production application without autoreload."""
    root = _project_root()
    manifest = _load_manifest(root)
    project = manifest.get("project") or root.name
    command = [
        "uvicorn",
        f"{project}.web.application:get_app",
        "--factory",
        "--host",
        args.host,
        "--port",
        str(args.port),
    ]
    if manifest.get("modules", {}).get("gunicorn"):
        command = [
            "gunicorn",
            "-c",
            f"{project}.gunicorn_runner",
            f"{project}.web.application:get_app",
        ]
    return _run(command, cwd=root)


def cmd_migrate(_: argparse.Namespace) -> int:
    """Apply database migrations through Alembic when enabled."""
    root = _project_root()
    if not (root / "alembic.ini").exists():
        print("No Alembic configuration is present; migrations are disabled.", file=sys.stderr)
        return 2
    return _run(["alembic", "upgrade", "head"], cwd=root)


def cmd_seed(args: argparse.Namespace) -> int:
    """Run the project seed entry point when one is provided."""
    root = _project_root()
    seed_script = root / "scripts" / "seed.py"
    if not seed_script.exists():
        print("No scripts/seed.py exists; add a seed implementation before running nk seed.", file=sys.stderr)
        return 2
    command = ["python", str(seed_script)]
    if args.name:
        command.append(args.name)
    return _run(command, cwd=root)


def cmd_eval(args: argparse.Namespace) -> int:
    """Run the generated evaluation entry point against a dataset."""
    root = _project_root()
    eval_script = root / "scripts" / "eval.py"
    if not eval_script.exists():
        print("No scripts/eval.py exists; add an evaluation runner before running nk eval.", file=sys.stderr)
        return 2
    return _run(["python", str(eval_script), args.dataset], cwd=root)


def cmd_jobs_replay(args: argparse.Namespace) -> int:
    """Replay one or more persisted dead-letter jobs."""
    root = _project_root()
    project = (_load_manifest(root).get("project") or root.name)
    return _run(
        ["python", "-m", f"{project}.jobs", "replay", *args.ids],
        cwd=root,
    )


def cmd_deploy(args: argparse.Namespace) -> int:
    """Deploy the generated Helm chart for a named environment."""
    root = _project_root()
    chart = root / "deploy" / "helm" / "nk-backend"
    if not chart.exists():
        print("Generated Helm chart is not present; deployment is unavailable.", file=sys.stderr)
        return 2
    values_name = "prod-s2" if args.environment == "prod" else args.environment
    values = root / "deploy" / "helm" / "values" / f"{values_name}.yaml"
    if not values.exists():
        print(f"Helm values file is missing: {values}", file=sys.stderr)
        return 2
    if shutil.which("helm") is None:
        print("Helm is required for nk deploy; install it or use the generated GitOps manifests.", file=sys.stderr)
        return 1
    if not args.image_digest.startswith("sha256:"):
        print(
            "An immutable --image-digest (sha256:...) is required for deployment.",
            file=sys.stderr,
        )
        return 2
    command = [
        "helm",
        "upgrade",
        "--install",
        args.release,
        str(chart),
        "--namespace",
        args.namespace,
        "--create-namespace",
        "-f",
        str(values),
        "--set",
        f"image.digest={args.image_digest}",
        "--wait",
    ]
    if args.dry_run:
        command.append("--dry-run")
    return _run(command, cwd=root)


def cmd_scale_status(_: argparse.Namespace) -> int:
    """Show the configured stage and the next scale trigger."""
    root = _project_root()
    manifest = _load_manifest(root)
    scale = manifest.get("scale") or {}
    stage = str(scale.get("stage") or "S0")
    next_stage = f"S{min(int(stage.removeprefix('S')) + 1, 6)}"
    print(f"scale stage: {stage}")
    print(f"next stage: {next_stage}")
    print("Advance only after measured SLO, saturation, and failure-recovery evidence.")
    return 0


def cmd_worker(_: argparse.Namespace) -> int:
    """Start the configured background worker."""
    root = _project_root()
    manifest = _load_manifest(root)
    project = manifest.get("project") or root.name
    if not manifest.get("modules", {}).get("taskiq"):
        print("Taskiq is not enabled in platform.yaml.", file=sys.stderr)
        return 2
    return _run(
        ["taskiq", "worker", f"{project}.tkq:broker"],
        cwd=root,
    )


def cmd_generate(args: argparse.Namespace) -> int:
    root = _project_root()
    sys.path.insert(0, str(root))
    from scripts.generate_module import generate_module

    fields = []
    for item in args.fields or []:
        if ":" not in item:
            print(f"invalid field {item!r}; use name:type", file=sys.stderr)
            return 2
        name, ftype = item.split(":", 1)
        fields.append((name, ftype))
    created = generate_module(
        args.module,
        fields=fields or None,
        project_root=root,
    )
    for path in created:
        print(f"created {path}")
    return 0


def cmd_export_openapi(args: argparse.Namespace) -> int:
    """Export OpenAPI JSON/YAML for Postman and other API clients."""
    root = _project_root()
    sys.path.insert(0, str(root))
    from scripts.export_openapi import main as export_main

    argv: list[str] = ["--project-root", str(root), "--format", args.fmt]
    if args.output is not None:
        argv.extend(["--output", str(args.output)])
    for server in args.server or []:
        argv.extend(["--server", server])
    return int(export_main(argv))


def cmd_skills_list(args: argparse.Namespace) -> int:
    from ..agents.skills.factory import build_skill_runtime
    from ..agents.skills.runtime import format_manifest_report

    runtime = build_skill_runtime(trusted_all=True)
    if getattr(args, "manifests", False):
        print(format_manifest_report(runtime))
        return 0
    skills = runtime.loader.discover()
    print(f"agent skills ({len(skills)})")
    for skill in skills:
        trust = "trusted" if runtime.loader.is_trusted(skill.name) else "discovered"
        desc = skill.description[:60] + "…" if len(skill.description) > 60 else skill.description
        manifest = runtime.manifest(skill.name)
        tools = len(manifest.tools)
        print(f"  {skill.name:32} {trust:10} tools={tools:2} {desc}")
    return 0


def cmd_skills_manifest(args: argparse.Namespace) -> int:
    from ..agents.skills import SkillNotFound
    from ..agents.skills.factory import build_skill_runtime

    runtime = build_skill_runtime(trusted_all=True)
    try:
        manifest = runtime.manifest(args.name)
    except SkillNotFound:
        print(f"unknown skill: {args.name}", file=sys.stderr)
        return 1
    print(f"name: {manifest.name}")
    print(f"description: {manifest.description or '-'}")
    print(f"tools: {', '.join(manifest.tools) or '-'}")
    print(
        f"permissions: network={manifest.permissions.network} "
        f"filesystem={manifest.permissions.filesystem}",
    )
    evaluation = manifest.evaluation.harness or "-"
    print(f"evaluation.harness: {evaluation}")
    issues = runtime.validate(args.name)
    if issues:
        print("issues:")
        for issue in issues:
            print(f"  - {issue}")
    return 0


def cmd_skills_presets(_: argparse.Namespace) -> int:
    from ..agents.skills.factory import build_skill_runtime
    from ..agents.skills.runtime import load_skill_presets

    runtime = build_skill_runtime(trusted_all=True)
    presets = load_skill_presets()
    print("Skill presets")
    print("=============")
    for name, skills in presets.items():
        resolved = runtime.resolve_preset(name)
        print(f"  {name}: {', '.join(resolved) or '(none found)'}")
    return 0


def cmd_skills_show(args: argparse.Namespace) -> int:
    from ..agents.skills import SkillNotFound, SkillNotTrusted
    from ..agents.skills.factory import build_skill_loader

    loader = build_skill_loader(trusted_all=True)
    try:
        print(loader.load(args.name))
    except SkillNotFound:
        print(f"unknown skill: {args.name}", file=sys.stderr)
        return 1
    except SkillNotTrusted:
        print(f"skill not trusted: {args.name}", file=sys.stderr)
        return 1
    return 0


def cmd_features_list(args: argparse.Namespace) -> int:
    from ..llm.features.registry import enabled_packs, list_packs

    root = _project_root()
    manifest: dict = {}
    catalog_path = root / "platform.yaml"
    if catalog_path.is_file():
        import yaml

        manifest = yaml.safe_load(catalog_path.read_text(encoding="utf-8")) or {}
    all_packs = list_packs(manifest)
    active = {p.meta.id for p in enabled_packs(manifest)}
    print(f"llm feature packs ({len(active)}/{len(all_packs)} enabled)")
    for pack in all_packs:
        flag = "on " if pack.id in active else "off"
        print(
            f"  [{flag}] {pack.id:20} upstream={pack.upstream_templates:3d}  requires={','.join(pack.requires)}"
        )
    return 0


def cmd_erp_features_list(args: argparse.Namespace) -> int:
    from ..erp.features.registry import enabled_packs, list_packs

    root = _project_root()
    manifest: dict = {}
    catalog_path = root / "platform.yaml"
    if catalog_path.is_file():
        import yaml

        manifest = yaml.safe_load(catalog_path.read_text(encoding="utf-8")) or {}
    all_packs = list_packs(manifest)
    active = {p.meta.id for p in enabled_packs(manifest)}
    print(f"erp feature packs ({len(active)}/{len(all_packs)} enabled)")
    for pack in all_packs:
        flag = "on " if pack.id in active else "off"
        print(
            f"  [{flag}] {pack.id:22} doctypes={pack.upstream_doctypes:3d}  requires={','.join(pack.requires)}"
        )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="nk",
        description="NK Backend OS — Next.js-style project CLI",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_doctor = sub.add_parser("doctor", help="Environment health checks")
    p_doctor.set_defaults(func=cmd_doctor)

    p_validate = sub.add_parser("validate", help="Validate project structure")
    p_validate.set_defaults(func=cmd_validate)

    p_check = sub.add_parser("check", help="format + lint + types + tests")
    p_check.set_defaults(func=cmd_check)

    p_dev = sub.add_parser("dev", help="Run local app (compose or uvicorn)")
    p_dev.add_argument(
        "--app-only",
        action="store_true",
        help="Force uvicorn only (skip Docker Compose)",
    )
    p_dev.add_argument(
        "--otlp",
        action="store_true",
        help="Include the local OpenTelemetry/Grafana Compose overlay",
    )
    compose_choice = p_dev.add_mutually_exclusive_group()
    compose_choice.add_argument(
        "--reuse",
        action="store_true",
        help="Reuse an existing Compose project without rebuilding",
    )
    compose_choice.add_argument(
        "--new",
        dest="new_stack",
        action="store_true",
        help="Create a new isolated Compose project",
    )
    p_dev.set_defaults(func=cmd_dev)

    p_build = sub.add_parser("build", help="Build production Docker image")
    p_build.set_defaults(func=cmd_build)

    p_start = sub.add_parser("start", help="Start the production application")
    p_start.add_argument("--host", default=os.environ.get("HOST", "0.0.0.0"))
    p_start.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    p_start.set_defaults(func=cmd_start)

    p_migrate = sub.add_parser("migrate", help="Apply database migrations")
    p_migrate.set_defaults(func=cmd_migrate)

    p_seed = sub.add_parser("seed", help="Run project seed data")
    p_seed.add_argument("name", nargs="?")
    p_seed.set_defaults(func=cmd_seed)

    p_gen = sub.add_parser("generate", help="Scaffold a business module")
    p_gen.add_argument("module", help="dotted path, e.g. crm.leads")
    p_gen.add_argument(
        "--fields",
        nargs="*",
        default=[],
        help="field specs name:type",
    )
    p_gen.set_defaults(func=cmd_generate)

    p_openapi = sub.add_parser(
        "export-openapi",
        help="Export OpenAPI for Postman / Insomnia / Bruno import",
    )
    p_openapi.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Output path (default: docs/openapi.json)",
    )
    p_openapi.add_argument(
        "--format",
        choices=("json", "yaml", "both"),
        default="json",
        dest="fmt",
        help="Serialization format (default: json)",
    )
    p_openapi.add_argument(
        "--server",
        action="append",
        default=[],
        metavar="URL",
        help="OpenAPI servers[].url (repeatable)",
    )
    p_openapi.set_defaults(func=cmd_export_openapi)

    p_skills = sub.add_parser("skills", help="List and inspect agent skills")
    skills_sub = p_skills.add_subparsers(dest="skills_command", required=True)
    p_skills_list = skills_sub.add_parser("list", help="List discovered skills")
    p_skills_list.add_argument(
        "--manifests",
        action="store_true",
        help="Print full manifest report with tool/eval validation",
    )
    p_skills_list.set_defaults(func=cmd_skills_list)
    p_skills_manifest = skills_sub.add_parser("manifest", help="Show skill manifest")
    p_skills_manifest.add_argument("name")
    p_skills_manifest.set_defaults(func=cmd_skills_manifest)
    p_skills_presets = skills_sub.add_parser("presets", help="List skill presets")
    p_skills_presets.set_defaults(func=cmd_skills_presets)
    p_skills_show = skills_sub.add_parser("show", help="Print trusted skill instructions")
    p_skills_show.add_argument("name")
    p_skills_show.set_defaults(func=cmd_skills_show)

    p_features = sub.add_parser("features", help="List LLM feature packs")
    features_sub = p_features.add_subparsers(dest="features_command", required=True)
    p_features_list = features_sub.add_parser("list", help="Show enabled feature packs")
    p_features_list.set_defaults(func=cmd_features_list)

    p_ai = sub.add_parser("ai", help="AI platform commands")
    ai_sub = p_ai.add_subparsers(dest="ai_command", required=True)
    p_ai_doctor = ai_sub.add_parser("doctor", help="Check Ollama, vectors, worker, and feature packs")
    p_ai_doctor.set_defaults(func=cmd_ai_doctor)
    p_ai_routes = ai_sub.add_parser("routes", help="List capability-based model routes")
    p_ai_routes.set_defaults(func=cmd_ai_routes)
    p_ai_runtime = ai_sub.add_parser("runtime", help="Agent runtime ladder commands")
    runtime_sub = p_ai_runtime.add_subparsers(dest="runtime_command", required=True)
    p_runtime_modes = runtime_sub.add_parser("modes", help="Show loop/graph/supervisor routing ladder")
    p_runtime_modes.set_defaults(func=cmd_ai_runtime_modes)
    p_ai_tools = ai_sub.add_parser("tools", help="Tool gateway commands")
    tools_sub = p_ai_tools.add_subparsers(dest="tools_command", required=True)
    p_tools_list = tools_sub.add_parser("list", help="List registered tools and policy status")
    p_tools_list.set_defaults(func=cmd_ai_tools_list)
    for name, handler, help_text in (
        ("inspect", cmd_ai_inspect, "Inspect run metadata and events"),
        ("replay", cmd_ai_replay, "Print append-only event timeline"),
        ("resume", cmd_ai_resume, "Show resume hints for a run"),
    ):
        parser = ai_sub.add_parser(name, help=help_text)
        parser.add_argument("run_id", help="Session run UUID")
        parser.add_argument("--org", default="local", help="Tenant organization id")
        parser.add_argument("--principal", default="cli", help="Principal id for scope")
        parser.set_defaults(func=handler)
    p_ai_fork = ai_sub.add_parser("fork", help="Fork a run into a new run id")
    p_ai_fork.add_argument("run_id", help="Session run UUID")
    p_ai_fork.add_argument("--org", default="local", help="Tenant organization id")
    p_ai_fork.add_argument("--principal", default="cli", help="Principal id for scope")
    p_ai_fork.add_argument(
        "--through-sequence",
        type=int,
        default=None,
        help="Copy events through this sequence number",
    )
    p_ai_fork.set_defaults(func=cmd_ai_fork)
    p_ai_harness = ai_sub.add_parser("harness", help="Harness scenario commands")
    harness_sub = p_ai_harness.add_subparsers(dest="harness_command", required=True)
    for name, handler, help_text in (
        ("run", cmd_ai_harness_run, "Run harness scenarios with trajectory capture"),
        ("record", cmd_ai_harness_record, "Run scenarios and record tool fixtures"),
        ("replay", cmd_ai_harness_replay, "Replay scenarios from recorded fixtures"),
        ("list", cmd_ai_harness_list, "List harness scenarios"),
    ):
        parser = harness_sub.add_parser(name, help=help_text)
        parser.add_argument(
            "scenarios",
            nargs="?",
            default=None,
            help="Scenario YAML path (default: tests/evals/scenarios.yaml)",
        )
        if name in {"run", "record", "replay"}:
            parser.add_argument(
                "--fixture-dir",
                default=None,
                help="Directory for recorded fixtures",
            )
        parser.set_defaults(func=handler)

    p_ai_eval = ai_sub.add_parser("eval", help="Evaluation adapter commands")
    eval_sub = p_ai_eval.add_subparsers(dest="eval_command", required=True)
    p_eval_list = eval_sub.add_parser("list", help="List evaluation adapters")
    p_eval_list.set_defaults(func=cmd_ai_eval_list)
    p_eval_run = eval_sub.add_parser("run", help="Run evaluation via an adapter")
    p_eval_run.add_argument(
        "dataset",
        nargs="?",
        default=None,
        help="Scenario YAML path (default: tests/evals/scenarios.yaml)",
    )
    p_eval_run.add_argument(
        "--adapter",
        default="native",
        choices=("native", "harness", "ragas", "deepeval", "promptfoo"),
        help="Evaluation backend",
    )
    p_eval_run.add_argument(
        "--invoke-promptfoo",
        action="store_true",
        help="Run npx promptfoo eval after export (promptfoo adapter)",
    )
    p_eval_run.set_defaults(func=cmd_ai_eval_run)

    p_ai_security = ai_sub.add_parser("security", help="AI security commands")
    security_sub = p_ai_security.add_subparsers(dest="security_command", required=True)
    p_security_audit = security_sub.add_parser(
        "audit",
        help="Run automated security invariant checks",
    )
    p_security_audit.set_defaults(func=cmd_ai_security_audit)

    p_ai_metrics = ai_sub.add_parser("metrics", help="Show in-process LLM usage and metric names")
    p_ai_metrics.set_defaults(func=cmd_ai_metrics)

    p_ai_plugins = ai_sub.add_parser("plugins", help="Plugin kernel commands")
    plugins_sub = p_ai_plugins.add_subparsers(dest="plugins_command", required=True)
    p_plugins_list = plugins_sub.add_parser("list", help="List registered plugins and capabilities")
    p_plugins_list.set_defaults(func=cmd_ai_plugins_list)
    p_plugins_health = plugins_sub.add_parser("health", help="Probe plugin module health")
    p_plugins_health.set_defaults(func=cmd_ai_plugins_health)

    p_ai_experiment = ai_sub.add_parser("experiment", help="Experiment runtime commands")
    experiment_sub = p_ai_experiment.add_subparsers(dest="experiment_command", required=True)
    p_experiment_hypotheses = experiment_sub.add_parser("hypotheses", help="List experiment hypotheses")
    p_experiment_hypotheses.set_defaults(func=cmd_ai_experiment_hypotheses)
    p_experiment_leaderboard = experiment_sub.add_parser("leaderboard", help="Show experiment leaderboard")
    p_experiment_leaderboard.set_defaults(func=cmd_ai_experiment_leaderboard)
    p_experiment_run = experiment_sub.add_parser("run", help="Run one experiment hypothesis")
    p_experiment_run.add_argument("hypothesis_id", help="Hypothesis id from catalog")
    p_experiment_run.add_argument("--scenarios", default=None, help="Scenario YAML path")
    p_experiment_run.set_defaults(func=cmd_ai_experiment_run)
    p_experiment_rollback = experiment_sub.add_parser("rollback", help="Rollback an experiment by id")
    p_experiment_rollback.add_argument("experiment_id", help="Experiment record id")
    p_experiment_rollback.set_defaults(func=cmd_ai_experiment_rollback)

    p_ai_self_improving = ai_sub.add_parser("self-improving", help="Self-improving pipeline commands")
    self_improving_sub = p_ai_self_improving.add_subparsers(dest="self_improving_command", required=True)
    p_self_improving_propose = self_improving_sub.add_parser("propose", help="Build improvement proposal from experiment")
    p_self_improving_propose.add_argument("hypothesis_id", help="Hypothesis id from catalog")
    p_self_improving_propose.set_defaults(func=cmd_ai_self_improving_propose)
    p_self_improving_runs = self_improving_sub.add_parser("runs", help="Show self-improving pipeline runs")
    p_self_improving_runs.set_defaults(func=cmd_ai_self_improving_runs)

    p_erp = sub.add_parser("erp", help="ERP domain packs (ERPNext upstream)")
    erp_sub = p_erp.add_subparsers(dest="erp_command", required=True)
    p_erp_list = erp_sub.add_parser("list", help="Show enabled ERP feature packs")
    p_erp_list.set_defaults(func=cmd_erp_features_list)

    p_eval = sub.add_parser("eval", help="Run the project evaluation dataset")
    p_eval.add_argument("dataset", nargs="?", default="tests/evals/golden.yaml")
    p_eval.set_defaults(func=cmd_eval)

    p_jobs = sub.add_parser("jobs", help="Manage background jobs")
    jobs_sub = p_jobs.add_subparsers(dest="jobs_command", required=True)
    p_replay = jobs_sub.add_parser("replay", help="Replay dead-letter jobs")
    p_replay.add_argument("ids", nargs="*", help="DLQ item IDs; omit to replay the available queue")
    p_replay.set_defaults(func=cmd_jobs_replay)

    p_deploy = sub.add_parser("deploy", help="Deploy with the generated Helm chart")
    p_deploy.add_argument("environment", choices=("staging", "prod", "prod-s2", "prod-s3", "prod-s4"))
    p_deploy.add_argument("--release", default="nk-backend")
    p_deploy.add_argument("--namespace", default="nk")
    p_deploy.add_argument(
        "--image-digest",
        required=True,
        help="Immutable application image digest (sha256:...).",
    )
    p_deploy.add_argument("--dry-run", action="store_true")
    p_deploy.set_defaults(func=cmd_deploy)

    p_scale = sub.add_parser("scale-status", help="Show the configured scale stage")
    p_scale.set_defaults(func=cmd_scale_status)

    p_worker = sub.add_parser("worker", help="Start the background worker")
    p_worker.set_defaults(func=cmd_worker)

    return parser


def main(argv: Sequence[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    code = int(args.func(args))
    raise SystemExit(code)


if __name__ == "__main__":
    main()
