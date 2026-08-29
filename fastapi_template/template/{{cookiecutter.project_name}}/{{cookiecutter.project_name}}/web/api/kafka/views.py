from fastapi import APIRouter
from {{cookiecutter.project_name}}.services.kafka.dependencies import KafkaProducer
from {{cookiecutter.project_name}}.web.api.kafka.schema import KafkaMessage

router = APIRouter()


@router.post("/")
async def send_kafka_message(
    kafka_message: KafkaMessage,
    producer: KafkaProducer,
) -> None:
    """
    Sends message to kafka.

    :param producer: kafka's producer.
    :param kafka_message: message to publish.
    """
    await producer.send(
        topic=kafka_message.topic,
        value=kafka_message.message.encode(),
    )
