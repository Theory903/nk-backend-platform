from typing import Any
import taskiq_fastapi
from taskiq import (
    AsyncBroker,
    AsyncResultBackend,
    InMemoryBroker,
    TaskiqEvents,
    TaskiqState,
{%- if cookiecutter.enable_rmq not in [True, "True", "true", 1, "1"] and cookiecutter.enable_redis not in [True, "True", "true", 1, "1"] %}
    ZeroMQBroker,
{%- endif %}
)
from {{cookiecutter.project_name}}.settings import settings
from {{cookiecutter.project_name}}.operations.metrics import (
    mark_worker_process_dead,
    set_worker_heartbeat,
)

{%- if cookiecutter.enable_redis in [True, "True", "true", 1, "1"] %}
from taskiq_redis import RedisAsyncResultBackend
{%- if cookiecutter.enable_rmq not in [True, "True", "true", 1, "1"] %}
from taskiq_redis import ListQueueBroker
{%- endif %}

{%- endif %}

{%- if cookiecutter.enable_rmq in [True, "True", "true", 1, "1"] %}
from taskiq_aio_pika import AioPikaBroker

{%- endif %}

{%- if cookiecutter.enable_redis in [True, "True", "true", 1, "1"] %}
result_backend: AsyncResultBackend[Any] = RedisAsyncResultBackend(
    redis_url=str(settings.redis_url.with_path("/1")),
)
{%- endif %}


{%- if cookiecutter.enable_rmq in [True, "True", "true", 1, "1"] %}
broker: AsyncBroker = AioPikaBroker(
    str(settings.rabbit_url),
){%- if cookiecutter.enable_redis in [True, "True", "true", 1, "1"] %}.with_result_backend(result_backend){%- endif %}
{%- elif cookiecutter.enable_redis in [True, "True", "true", 1, "1"] %}
broker: AsyncBroker = ListQueueBroker(
    str(settings.redis_url.with_path("/1")),
).with_result_backend(result_backend)
{%- else %}
broker: AsyncBroker = ZeroMQBroker()
{%- endif %}

if settings.environment.lower() == "pytest":
    broker = InMemoryBroker()

taskiq_fastapi.init(
    broker,
    "{{cookiecutter.project_name}}.web.application:get_app",
)


@broker.on_event(TaskiqEvents.WORKER_STARTUP)
async def worker_startup(state: TaskiqState) -> None:
    """Publish a worker heartbeat when Taskiq starts consuming."""
    set_worker_heartbeat(True)
    state.nk_worker_started = True


@broker.on_event(TaskiqEvents.WORKER_SHUTDOWN)
async def worker_shutdown(state: TaskiqState) -> None:
    """Clear the worker heartbeat before Taskiq exits."""
    set_worker_heartbeat(False)
    mark_worker_process_dead()
