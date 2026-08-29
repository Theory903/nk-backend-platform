{%- if cookiecutter.enable_idempotency == "True" %}
from {{cookiecutter.project_name}}.web.middleware.idempotency import IdempotencyMiddleware
{%- endif %}
from {{cookiecutter.project_name}}.web.middleware.request_id import RequestIdMiddleware
from {{cookiecutter.project_name}}.web.middleware.security_headers import (
    SecurityHeadersMiddleware,
)

__all__ = [
    {%- if cookiecutter.enable_idempotency == "True" %}
    "IdempotencyMiddleware",
    {%- endif %}
    "RequestIdMiddleware",
    "SecurityHeadersMiddleware",
]
