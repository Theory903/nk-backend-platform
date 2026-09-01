"""SQLAlchemy persistence adapters."""

{%- if cookiecutter.add_users in [True, "True", "true", 1, "1"] %}
from .scim import ScimUserRow, SqlalchemyScimRepository

__all__ = ["ScimUserRow", "SqlalchemyScimRepository"]
{%- else %}
__all__: list[str] = []
{%- endif %}
