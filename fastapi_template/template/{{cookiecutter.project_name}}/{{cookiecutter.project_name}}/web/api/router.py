from fastapi.routing import APIRouter

{%- if cookiecutter.add_users in [True, "True", "true", 1, "1"] %}
from fastapi import Depends
from {{cookiecutter.project_name}}.identity.deps import CurrentUser, RequireCsrf
{%- endif %}

{%- if cookiecutter.add_users in [True, "True", "true", 1, "1"] %}
from {{cookiecutter.project_name}}.identity import http as identity_http
{%- endif %}
{%- if cookiecutter.enable_routers in [True, "True", "true", 1, "1"] %}
{%- if cookiecutter.api_type == 'rest' %}
from {{cookiecutter.project_name}}.web.api import echo

{%- if cookiecutter.add_dummy in [True, "True", "true", 1, "1"] and cookiecutter.add_users in [True, "True", "true", 1, "1"] %}
from {{cookiecutter.project_name}}.web.api import dummy

{%- endif %}
{%- if cookiecutter.enable_redis in [True, "True", "true", 1, "1"] and cookiecutter.add_users in [True, "True", "true", 1, "1"] %}
from {{cookiecutter.project_name}}.web.api import redis

{%- endif %}
{%- if cookiecutter.enable_rmq in [True, "True", "true", 1, "1"] and cookiecutter.add_users in [True, "True", "true", 1, "1"] %}
from {{cookiecutter.project_name}}.web.api import rabbit

{%- endif %}
{%- if cookiecutter.enable_nats in [True, "True", "true", 1, "1"] and cookiecutter.add_users in [True, "True", "true", 1, "1"] %}
from {{cookiecutter.project_name}}.web.api import nats

{%- endif %}
{%- if cookiecutter.enable_kafka in [True, "True", "true", 1, "1"] and cookiecutter.add_users in [True, "True", "true", 1, "1"] %}
from {{cookiecutter.project_name}}.web.api import kafka

{%- endif %}
{%- endif %}
{%- endif %}
from {{cookiecutter.project_name}}.web.api import docs
from {{cookiecutter.project_name}}.web.api import monitoring
{%- if cookiecutter.enable_rag_traditional in [True, "True", "true", 1, "1"] %}
from {{cookiecutter.project_name}}.web.api import knowledge
{%- endif %}
{%- if cookiecutter.orm in ['sqlalchemy', 'beanie'] %}
from {{cookiecutter.project_name}}.core.module_discovery import (
    include_business_routers,
)
{%- endif %}
{%- if cookiecutter.enable_llm in [True, "True", "true", 1, "1"] %}
from {{cookiecutter.project_name}}.llm.features.router import build_features_router
{%- endif %}
{%- if cookiecutter.db_info.name != "none" and cookiecutter.orm == "sqlalchemy" %}
from {{cookiecutter.project_name}}.erp.features.router import build_erp_router
{%- endif %}
{%- if cookiecutter.enable_agents in [True, "True", "true", 1, "1"] %}
from {{cookiecutter.project_name}}.web.api import agent_protocol
{%- endif %}

api_router = APIRouter()
api_router.include_router(monitoring.router)
api_router.include_router(docs.router)
{%- if cookiecutter.enable_rag_traditional in [True, "True", "true", 1, "1"] %}
api_router.include_router(knowledge.router)
{%- endif %}
{%- if cookiecutter.enable_agents in [True, "True", "true", 1, "1"] %}
api_router.include_router(agent_protocol.router)
{%- endif %}
{%- if cookiecutter.enable_llm in [True, "True", "true", 1, "1"] %}
api_router.include_router(build_features_router())
{%- endif %}
{%- if cookiecutter.db_info.name != "none" and cookiecutter.orm == "sqlalchemy" %}
api_router.include_router(build_erp_router())
{%- endif %}
{%- if cookiecutter.add_users in [True, "True", "true", 1, "1"] %}
api_router.include_router(identity_http.router)
{%- endif %}
{%- if cookiecutter.add_users in [True, "True", "true", 1, "1"] %}
protected_router = APIRouter(
    dependencies=[
        Depends(CurrentUser),
        Depends(RequireCsrf()),
    ],
)
{%- else %}
protected_router = api_router
{%- endif %}
{%- if cookiecutter.enable_routers in [True, "True", "true", 1, "1"] %}
{%- if cookiecutter.api_type == 'rest' %}
protected_router.include_router(echo.router, prefix="/echo", tags=["echo"])
{%- if cookiecutter.add_dummy in [True, "True", "true", 1, "1"] and cookiecutter.add_users in [True, "True", "true", 1, "1"] %}
protected_router.include_router(dummy.router, prefix="/dummy", tags=["dummy"])
{%- endif %}
{%- if cookiecutter.enable_redis in [True, "True", "true", 1, "1"] and cookiecutter.add_users in [True, "True", "true", 1, "1"] %}
protected_router.include_router(redis.router, prefix="/redis", tags=["redis"])
{%- endif %}
{%- if cookiecutter.enable_rmq in [True, "True", "true", 1, "1"] and cookiecutter.add_users in [True, "True", "true", 1, "1"] %}
protected_router.include_router(rabbit.router, prefix="/rabbit", tags=["rabbit"])
{%- endif %}
{%- if cookiecutter.enable_nats in [True, "True", "true", 1, "1"] and cookiecutter.add_users in [True, "True", "true", 1, "1"] %}
protected_router.include_router(nats.router, prefix="/nats", tags=["nats"])
{%- endif %}
{%- if cookiecutter.enable_kafka in [True, "True", "true", 1, "1"] and cookiecutter.add_users in [True, "True", "true", 1, "1"] %}
protected_router.include_router(kafka.router, prefix="/kafka", tags=["kafka"])
{%- endif %}
{%- endif %}
{%- endif %}
{%- if cookiecutter.orm in ['sqlalchemy', 'beanie'] %}
include_business_routers(protected_router)
{%- endif %}
{%- if cookiecutter.add_users in [True, "True", "true", 1, "1"] %}
api_router.include_router(protected_router)
{%- endif %}
