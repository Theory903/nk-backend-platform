"""Convention-based discovery for business module routers."""

from __future__ import annotations

import importlib
import sys
from dataclasses import dataclass
from pathlib import Path

from fastapi import APIRouter


class ModuleDiscoveryError(RuntimeError):
    """Raised when a business module cannot be mounted safely."""


@dataclass(frozen=True, slots=True)
class DiscoveredRouter:
    """A business router and the domain namespace that owns it."""

    module_name: str
    domain: str
    router: APIRouter

    @property
    def mount_prefix(self) -> str:
        """Return the versioned domain prefix for this router."""
        return f"/v1/{self.domain}"

    @property
    def route_prefix(self) -> str:
        """Return the complete versioned route prefix."""
        suffix = self.router.prefix.rstrip("/")
        return f"{self.mount_prefix}{suffix}"


def discover_business_routers(
    root: Path | None = None,
) -> list[DiscoveredRouter]:
    """Discover routers below ``business/modules`` in deterministic order."""
    project_root = root or Path(__file__).resolve().parents[2]
    modules_root = project_root / "business" / "modules"
    if not modules_root.exists():
        return []

    routers: list[DiscoveredRouter] = []
    prefixes: dict[str, str] = {}
    for router_path in sorted(modules_root.rglob("router.py")):
        relative = router_path.relative_to(project_root)
        parts = relative.with_suffix("").parts
        if len(parts) != 5 or parts[:2] != ("business", "modules"):
            raise ModuleDiscoveryError(
                f"invalid business router path {relative}; expected "
                "business/modules/<domain>/<module>/router.py",
            )

        module_name = ".".join(parts)
        domain = parts[2]
        router = _load_router(module_name, relative, project_root)
        discovered = DiscoveredRouter(
            module_name=module_name,
            domain=domain,
            router=router,
        )
        previous = prefixes.get(discovered.route_prefix)
        if previous is not None:
            raise ModuleDiscoveryError(
                f"duplicate business route prefix {discovered.route_prefix!r} "
                f"in {previous} and {relative}",
            )
        prefixes[discovered.route_prefix] = str(relative)
        routers.append(discovered)
    return routers


def include_business_routers(
    api_router: APIRouter,
    *,
    root: Path | None = None,
) -> list[DiscoveredRouter]:
    """Discover and mount business routers on the shared API router."""
    discovered = discover_business_routers(root=root)
    mounted = getattr(api_router, "_nk_business_route_prefixes", set())
    for item in discovered:
        if item.route_prefix in mounted:
            continue
        api_router.include_router(
            item.router,
            prefix=item.mount_prefix,
        )
        mounted.add(item.route_prefix)
    setattr(api_router, "_nk_business_route_prefixes", mounted)
    return discovered


def _load_router(
    module_name: str,
    relative: Path,
    project_root: Path,
) -> APIRouter:
    """Import one router module and provide an actionable failure."""
    root_string = str(project_root)
    if root_string in sys.path:
        sys.path.remove(root_string)
    sys.path.insert(0, root_string)
    importlib.invalidate_caches()
    _clear_business_module_cache(project_root)
    _clear_project_module_cache(project_root)
    try:
        module = importlib.import_module(module_name)
    except Exception as exc:
        raise ModuleDiscoveryError(
            f"could not import business router {relative}: "
            f"{type(exc).__name__}: {exc}",
        ) from exc

    router = getattr(module, "router", None)
    if not isinstance(router, APIRouter):
        raise ModuleDiscoveryError(
            f"business router {relative} must export an APIRouter named 'router'",
        )
    return router


def _clear_business_module_cache(project_root: Path) -> None:
    """Avoid loading a router cached from another generated project."""
    for name in tuple(sys.modules):
        if name == "business" or name.startswith("business."):
            module = sys.modules[name]
            origin = getattr(module, "__file__", None)
            if origin is None or not _is_within_project(origin, project_root):
                sys.modules.pop(name, None)


def _clear_project_module_cache(project_root: Path) -> None:
    """Avoid loading a same-named generated package from another project."""
    package_names = {
        path.name
        for path in project_root.iterdir()
        if path.is_dir() and (path / "core").is_dir()
    }
    for name in tuple(sys.modules):
        if any(
            name == package or name.startswith(f"{package}.")
            for package in package_names
        ):
            module = sys.modules[name]
            origin = getattr(module, "__file__", None)
            if origin is None or not _is_within_project(origin, project_root):
                sys.modules.pop(name, None)


def _is_within_project(origin: str, project_root: Path) -> bool:
    """Return whether an imported module originated in this project."""
    try:
        return Path(origin).resolve().is_relative_to(project_root.resolve())
    except (OSError, RuntimeError):
        return False


__all__ = [
    "DiscoveredRouter",
    "ModuleDiscoveryError",
    "discover_business_routers",
    "include_business_routers",
]
