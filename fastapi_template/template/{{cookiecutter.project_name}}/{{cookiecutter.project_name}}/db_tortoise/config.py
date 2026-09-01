from typing import List

from {{cookiecutter.project_name}}.settings import settings

MODELS_MODULES: List[str] = [{%- if cookiecutter.add_dummy in [True, "True", "true", 1, "1"] %}"{{cookiecutter.project_name}}.db.models.dummy_model"{%- endif %}]

TORTOISE_CONFIG = {
    "connections": {
        "default": str(settings.db_url),
    },
    "apps": {
        "models": {
            "models": {%- if cookiecutter.enable_migrations in [True, "True", "true", 1, "1"] %} [*MODELS_MODULES,  "aerich.models"] {%- else %} MODELS_MODULES {%- endif %} ,
            "default_connection": "default",
        },
    },
}
