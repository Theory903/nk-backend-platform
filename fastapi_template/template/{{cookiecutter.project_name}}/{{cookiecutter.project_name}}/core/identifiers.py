import uuid


def new_id(prefix: str) -> str:
    """
    Generate a prefixed unique identifier such as ``usr_1f3a...``.
    """
    return f"{prefix}_{uuid.uuid4().hex}"
