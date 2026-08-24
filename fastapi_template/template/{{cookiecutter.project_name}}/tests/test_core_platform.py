from {{cookiecutter.project_name}}.core.platform import get_platform_config


async def test_platform_manifest_loads() -> None:
    """
    The generated platform.yaml parses into a typed config.
    """
    config = get_platform_config()

    assert config.project
    assert config.providers.database == "{{ cookiecutter.db_info.name }}"
    assert config.module_enabled("agents") is {{ cookiecutter.enable_agents }}


async def test_module_lookup_defaults_to_disabled() -> None:
    """
    Unknown modules report disabled instead of raising.
    """
    config = get_platform_config()

    assert config.module_enabled("never-defined-module") is False
