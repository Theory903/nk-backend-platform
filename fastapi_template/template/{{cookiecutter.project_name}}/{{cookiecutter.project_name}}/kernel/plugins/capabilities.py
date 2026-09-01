"""Plugin dependency graph and capability resolution (P21)."""

from __future__ import annotations

from {{cookiecutter.project_name}}.kernel.plugins.contracts import PluginManifest


def resolve_load_order(
    plugins: dict[str, PluginManifest],
    *,
    enabled: set[str] | None = None,
) -> list[str]:
    """Topological sort of plugins by ``requires`` edges."""
    active = enabled or set(plugins.keys())
    indegree: dict[str, int] = {name: 0 for name in active if name in plugins}
    dependents: dict[str, list[str]] = {name: [] for name in indegree}

    for name in indegree:
        manifest = plugins[name]
        for requirement in manifest.requires:
            if requirement not in plugins:
                raise ValueError(f"plugin {name!r} requires unknown plugin {requirement!r}")
            if requirement not in indegree:
                continue
            indegree[name] += 1
            dependents[requirement].append(name)

    queue = sorted(name for name, degree in indegree.items() if degree == 0)
    ordered: list[str] = []
    while queue:
        current = queue.pop(0)
        ordered.append(current)
        for child in sorted(dependents[current]):
            indegree[child] -= 1
            if indegree[child] == 0:
                queue.append(child)

    if len(ordered) != len(indegree):
        raise ValueError("plugin dependency graph contains a cycle")

    return ordered


def capability_index(plugins: dict[str, PluginManifest]) -> dict[str, str]:
    """Map provided capability name → plugin name."""
    index: dict[str, str] = {}
    for name, manifest in plugins.items():
        for capability in manifest.provides:
            index[capability] = name
    return index


__all__ = ["capability_index", "resolve_load_order"]
