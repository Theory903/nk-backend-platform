import strawberry
from strawberry.fastapi import GraphQLRouter
from {{cookiecutter.project_name}}.web.gql.context import Context, get_context

{%- if cookiecutter.enable_routers in [True, "True", "true", 1, "1"] %}
from {{cookiecutter.project_name}}.web.gql import echo

{%- if cookiecutter.add_dummy in [True, "True", "true", 1, "1"] and cookiecutter.add_users in [True, "True", "true", 1, "1"] %}
from {{cookiecutter.project_name}}.web.gql import dummy

{%- endif %}
{%- if cookiecutter.enable_redis in [True, "True", "true", 1, "1"] and cookiecutter.add_users in [True, "True", "true", 1, "1"] %}
from {{cookiecutter.project_name}}.web.gql import redis

{%- endif %}
{%- if cookiecutter.enable_rmq in [True, "True", "true", 1, "1"] and cookiecutter.add_users in [True, "True", "true", 1, "1"] %}
from {{cookiecutter.project_name}}.web.gql import rabbit

{%- endif %}
{%- if cookiecutter.enable_kafka in [True, "True", "true", 1, "1"] and cookiecutter.add_users in [True, "True", "true", 1, "1"] %}
from {{cookiecutter.project_name}}.web.gql import kafka

{%- endif %}

{%- if cookiecutter.enable_nats in [True, "True", "true", 1, "1"] and cookiecutter.add_users in [True, "True", "true", 1, "1"] %}
from {{cookiecutter.project_name}}.web.gql import nats

{%- endif %}

{%- endif %}


{%- if cookiecutter.otlp_enabled in [True, "True", "true", 1, "1"] %}
from strawberry.extensions.tracing import OpenTelemetryExtension
{%- endif %}

@strawberry.type
class Query(
    {%- if cookiecutter.enable_routers in [True, "True", "true", 1, "1"] %}
    echo.Query,
{%- if cookiecutter.add_dummy in [True, "True", "true", 1, "1"] and cookiecutter.add_users in [True, "True", "true", 1, "1"] %}
    dummy.Query,
    {%- endif %}
{%- if cookiecutter.enable_redis in [True, "True", "true", 1, "1"] and cookiecutter.add_users in [True, "True", "true", 1, "1"] %}
    redis.Query,
    {%- endif %}
    {%- endif %}
):
    """Main query."""


@strawberry.type
class Mutation(
    {%- if cookiecutter.enable_routers in [True, "True", "true", 1, "1"] %}
    echo.Mutation,
{%- if cookiecutter.add_dummy in [True, "True", "true", 1, "1"] and cookiecutter.add_users in [True, "True", "true", 1, "1"] %}
    dummy.Mutation,
    {%- endif %}
{%- if cookiecutter.enable_redis in [True, "True", "true", 1, "1"] and cookiecutter.add_users in [True, "True", "true", 1, "1"] %}
    redis.Mutation,
    {%- endif %}
{%- if cookiecutter.enable_rmq in [True, "True", "true", 1, "1"] and cookiecutter.add_users in [True, "True", "true", 1, "1"] %}
    rabbit.Mutation,
    {%- endif %}
{%- if cookiecutter.enable_kafka in [True, "True", "true", 1, "1"] and cookiecutter.add_users in [True, "True", "true", 1, "1"] %}
    kafka.Mutation,
    {%- endif %}
{%- if cookiecutter.enable_nats in [True, "True", "true", 1, "1"] and cookiecutter.add_users in [True, "True", "true", 1, "1"] %}
    nats.Mutation,
    {%- endif %}
    {%- endif %}
):
    """Main mutation."""


schema = strawberry.Schema(
    Query,
    Mutation,
    extensions=(
        {%- if cookiecutter.otlp_enabled in [True, "True", "true", 1, "1"] %}
        OpenTelemetryExtension,
        {%- endif %}
    )
)

gql_router: GraphQLRouter[Context, None] = GraphQLRouter(
    schema,
    context_getter=get_context,
)
