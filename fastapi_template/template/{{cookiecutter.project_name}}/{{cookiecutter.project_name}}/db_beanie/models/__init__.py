"""{{cookiecutter.project_name}} models."""

{%- if cookiecutter.add_dummy == "True" %}
from {{cookiecutter.project_name}}.db.models.dummy_model import DummyModel
{%- endif %}
{%- if cookiecutter.orm == "beanie" %}
from {{cookiecutter.project_name}}.data.adapters.mongo.documents import RecordDocument
from {{cookiecutter.project_name}}.data.adapters.mongo.outbox import OutboxDocument
{%- endif %}

from beanie import Document
from collections.abc import Sequence

def load_all_models() -> Sequence[type[Document]]:
    """Load all models from this folder."""
    return [
{%- if cookiecutter.add_dummy == "True" %}
        DummyModel,
{%- endif %}
{%- if cookiecutter.orm == "beanie" %}
        RecordDocument,
        OutboxDocument,
{%- endif %}
    ]
