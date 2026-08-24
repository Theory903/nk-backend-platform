from {{cookiecutter.project_name}}.core.events import EventEnvelope


async def test_envelope_carries_cloudevents_required_members() -> None:
    """
    Envelopes satisfy CloudEvents 1.0 required attributes out of the box.
    """
    envelope = EventEnvelope(type="order.created", source="/orders", data={"id": "1"})

    assert envelope.specversion == "1.0"
    assert envelope.id
    assert envelope.time is not None
    assert envelope.source == "/orders"
    assert envelope.data == {"id": "1"}


async def test_envelope_ids_are_unique_per_instance() -> None:
    """
    Two envelopes of the same type never share an id.
    """
    first = EventEnvelope(type="t", source="/s", data={})
    second = EventEnvelope(type="t", source="/s", data={})

    assert first.id != second.id
