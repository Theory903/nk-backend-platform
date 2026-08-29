from fastapi import APIRouter, Depends
from nats.aio.client import Client as NATS

from {{cookiecutter.project_name}}.services.nats.dependencies import get_nats
from {{cookiecutter.project_name}}.web.api.nats.schema import NatsMessage

router = APIRouter()


@router.post("/")
async def publish_nats_message(
    nats_message: NatsMessage,
    nats: NATS = Depends(get_nats),
) -> None:
    """
    Sends message to nats.

    :param nats: shared NATS client.
    :param nats_message: message to publish.
    """
    await nats.publish(
        nats_message.subject,
        nats_message.message.encode(),
    )
