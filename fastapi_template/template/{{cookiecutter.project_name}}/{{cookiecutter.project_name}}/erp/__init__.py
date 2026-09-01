"""ERP domain packs — first-party NK module (reference: temp/erpnext, GPL-3.0)."""

from {{cookiecutter.project_name}}.erp.bootstrap import wire_erp_bootstrap
from {{cookiecutter.project_name}}.erp.patterns import PATTERNS, pattern_for
from {{cookiecutter.project_name}}.erp.runtime import ErpRuntime, get_or_create_runtime

__all__ = [
    "ErpRuntime",
    "PATTERNS",
    "get_or_create_runtime",
    "pattern_for",
    "wire_erp_bootstrap",
]
