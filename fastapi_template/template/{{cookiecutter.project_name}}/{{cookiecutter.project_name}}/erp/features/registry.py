"""Discover and enable ERP feature packs from platform.yaml + catalog."""

from __future__ import annotations

import importlib
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from {{cookiecutter.project_name}}.agents.tools import ToolRegistry
from {{cookiecutter.project_name}}.erp.features.base import ErpFeaturePack, ErpFeaturePackMeta
from {{cookiecutter.project_name}}.erp.features.common.context import ErpFeatureContext

_CATALOG_PATH = Path(__file__).with_name("catalog.yaml")

_PACK_MODULES: dict[str, str] = {
    "erp_masters": "{{cookiecutter.project_name}}.erp.features.erp_masters",
    "crm_pipeline": "{{cookiecutter.project_name}}.erp.features.crm_pipeline",
    "pricing_taxes": "{{cookiecutter.project_name}}.erp.features.pricing_taxes",
    "order_to_cash": "{{cookiecutter.project_name}}.erp.features.order_to_cash",
    "procure_to_pay": "{{cookiecutter.project_name}}.erp.features.procure_to_pay",
    "inventory_management": "{{cookiecutter.project_name}}.erp.features.inventory_management",
    "financial_accounting": "{{cookiecutter.project_name}}.erp.features.financial_accounting",
    "billing_collections": "{{cookiecutter.project_name}}.erp.features.billing_collections",
    "support_sla": "{{cookiecutter.project_name}}.erp.features.support_sla",
    "projects_delivery": "{{cookiecutter.project_name}}.erp.features.projects_delivery",
    "manufacturing_ops": "{{cookiecutter.project_name}}.erp.features.manufacturing_ops",
    "assets_quality": "{{cookiecutter.project_name}}.erp.features.assets_quality",
    "reporting_analytics": "{{cookiecutter.project_name}}.erp.features.reporting_analytics",
    "documents_hub": "{{cookiecutter.project_name}}.erp.features.documents_hub",
    "doctype_hub": "{{cookiecutter.project_name}}.erp.features.doctype_hub",
}

_DEFAULT_ENABLED: dict[str, bool] = {
    "erp_masters": {% if cookiecutter.db_info.name != "none" and cookiecutter.add_users in [True, "True", "true", 1, "1"] %}True{% else %}False{% endif %},
    "crm_pipeline": {% if cookiecutter.db_info.name != "none" and cookiecutter.add_users in [True, "True", "true", 1, "1"] %}True{% else %}False{% endif %},
    "pricing_taxes": {% if cookiecutter.db_info.name != "none" %}True{% else %}False{% endif %},
    "order_to_cash": {% if cookiecutter.db_info.name != "none" and cookiecutter.add_users in [True, "True", "true", 1, "1"] %}True{% else %}False{% endif %},
    "procure_to_pay": {% if cookiecutter.db_info.name != "none" and cookiecutter.add_users in [True, "True", "true", 1, "1"] %}True{% else %}False{% endif %},
    "inventory_management": {% if cookiecutter.db_info.name != "none" %}True{% else %}False{% endif %},
    "financial_accounting": {% if cookiecutter.db_info.name != "none" %}True{% else %}False{% endif %},
    "billing_collections": {% if cookiecutter.db_info.name != "none" and cookiecutter.add_users in [True, "True", "true", 1, "1"] %}True{% else %}False{% endif %},
    "support_sla": {% if cookiecutter.db_info.name != "none" and cookiecutter.add_users in [True, "True", "true", 1, "1"] %}True{% else %}False{% endif %},
    "projects_delivery": {% if cookiecutter.db_info.name != "none" and cookiecutter.add_users in [True, "True", "true", 1, "1"] %}True{% else %}False{% endif %},
    "manufacturing_ops": {% if cookiecutter.db_info.name != "none" and cookiecutter.add_users in [True, "True", "true", 1, "1"] %}True{% else %}False{% endif %},
    "assets_quality": {% if cookiecutter.db_info.name != "none" %}True{% else %}False{% endif %},
    "reporting_analytics": {% if cookiecutter.db_info.name != "none" %}True{% else %}False{% endif %},
    "documents_hub": {% if cookiecutter.db_info.name != "none" %}True{% else %}False{% endif %},
    "doctype_hub": {% if cookiecutter.db_info.name != "none" %}True{% else %}False{% endif %},
}


@lru_cache(maxsize=1)
def load_catalog() -> dict[str, Any]:
    if not _CATALOG_PATH.is_file():
        return {"packs": {}, "upstream": []}
    return yaml.safe_load(_CATALOG_PATH.read_text(encoding="utf-8")) or {}


def _pack_enabled(pack_id: str, manifest: dict[str, Any] | None) -> bool:
    features = (manifest or {}).get("erp_features") or {}
    if pack_id in features:
        return bool(features[pack_id])
    return _DEFAULT_ENABLED.get(pack_id, False)


def _requirements_met(pack_id: str, manifest: dict[str, Any] | None) -> bool:
    catalog = load_catalog()
    pack_info = (catalog.get("packs") or {}).get(pack_id) or {}
    modules = manifest.get("modules") if manifest else {}
    for req in pack_info.get("requires") or []:
        if req == "db":
            if not (modules or {}).get("migrations") and (modules or {}).get("users") is None:
                # migrations flag implies db; users module also implies db
                db_name = (manifest or {}).get("providers", {}).get("database", "none")
                if db_name == "none":
                    return False
        elif req == "users":
            if not (modules or {}).get("users"):
                return False
        elif not (modules or {}).get(req):
            # cross-pack deps: check erp_features toggles for other ERP packs
            if req in _PACK_MODULES and not _pack_enabled(req, manifest):
                return False
    return True


def _load_pack_impl(pack_id: str) -> ErpFeaturePack | None:
    module_path = _PACK_MODULES.get(pack_id)
    if not module_path:
        return None
    module = importlib.import_module(module_path)
    return getattr(module, "PACK", None)


def enabled_packs(manifest: dict[str, Any] | None = None) -> tuple[ErpFeaturePack, ...]:
    catalog = load_catalog()
    packs: list[ErpFeaturePack] = []
    for pack_id in sorted((catalog.get("packs") or _PACK_MODULES).keys()):
        if not _pack_enabled(pack_id, manifest):
            continue
        if not _requirements_met(pack_id, manifest):
            continue
        impl = _load_pack_impl(pack_id)
        if impl is not None:
            packs.append(impl)
    return tuple(packs)


def list_packs(manifest: dict[str, Any] | None = None) -> list[ErpFeaturePackMeta]:
    catalog = load_catalog()
    result: list[ErpFeaturePackMeta] = []
    for pack_id, info in sorted((catalog.get("packs") or {}).items()):
        result.append(
            ErpFeaturePackMeta(
                id=pack_id,
                name=str(info.get("name") or pack_id),
                requires=tuple(info.get("requires") or ()),
                upstream_doctypes=int(info.get("upstream_doctypes") or 0),
            )
        )
    return result


def get_pack(pack_id: str) -> ErpFeaturePack:
    impl = _load_pack_impl(pack_id)
    if impl is None:
        raise KeyError(pack_id)
    return impl


def register_erp_tools(
    registry: ToolRegistry,
    *,
    manifest: dict[str, Any] | None = None,
    ctx: ErpFeatureContext | None = None,
) -> list[str]:
    """Register tools from all enabled ERP packs; return tool names added."""
    added: list[str] = []
    context = ctx or ErpFeatureContext()
    for pack in enabled_packs(manifest):
        before = set(registry.names())
        pack.register_tools(registry, ctx=context)
        added.extend(name for name in registry.names() if name not in before)
    return added
