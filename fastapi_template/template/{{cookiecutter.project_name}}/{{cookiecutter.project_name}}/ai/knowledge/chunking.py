from dataclasses import dataclass


@dataclass
class Chunk:
    text: str
    index: int
    source: str = ""
    start: int = 0
    end: int = 0


class TextChunker:
    """Sliding-window chunking with overlap."""

    def __init__(self, chunk_size: int = 512, overlap: int = 64) -> None:
        self.chunk_size = chunk_size
        self.overlap = overlap

    def chunk(self, text: str, source: str = "") -> list[Chunk]:
        if not text:
            return []
        step = max(1, self.chunk_size - self.overlap)
        chunks: list[Chunk] = []
        for i, start in enumerate(range(0, len(text), step)):
            segment = text[start:start + self.chunk_size]
            if not segment.strip():
                continue
            chunks.append(Chunk(text=segment, index=i, source=source, start=start, end=start + len(segment)))
        return chunks
