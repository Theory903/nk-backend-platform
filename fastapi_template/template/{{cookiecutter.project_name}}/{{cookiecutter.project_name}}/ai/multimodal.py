"""Provider-neutral multimodal input contract."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol


MediaKind = Literal["image", "audio", "video", "file"]


@dataclass(frozen=True, slots=True)
class MediaPart:
    kind: MediaKind
    uri: str
    mime_type: str
    size_bytes: int | None = None


class MultimodalProvider(Protocol):
    async def complete(self, *, text: str, media: list[MediaPart]) -> str:
        """Generate a response from text and bounded media references."""


def validate_media(parts: list[MediaPart], *, max_parts: int = 8) -> None:
    """Validate media references before handing them to a provider."""
    if len(parts) > max_parts:
        raise ValueError(f"at most {max_parts} media parts are supported")
    for part in parts:
        if not part.uri or "://" not in part.uri:
            raise ValueError("media URI must be an explicit URI")
        if part.size_bytes is not None and part.size_bytes < 0:
            raise ValueError("media size cannot be negative")


__all__ = ["MediaPart", "MediaKind", "MultimodalProvider", "validate_media"]
