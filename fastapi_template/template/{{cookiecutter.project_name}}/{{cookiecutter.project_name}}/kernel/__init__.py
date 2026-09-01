"""NK plugin kernel — discovery, lifecycle, dependency graph (P21)."""

from {{cookiecutter.project_name}}.kernel.plugins.bootstrap import build_plugin_kernel
from {{cookiecutter.project_name}}.kernel.plugins.contracts import (
    PluginHealth,
    PluginManifest,
    PluginPermissions,
    PluginState,
    PluginType,
)
from {{cookiecutter.project_name}}.kernel.plugins.lifecycle import PluginKernel

__all__ = [
    "PluginHealth",
    "PluginKernel",
    "PluginManifest",
    "PluginPermissions",
    "PluginState",
    "PluginType",
    "build_plugin_kernel",
]
