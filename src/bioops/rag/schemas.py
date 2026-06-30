from dataclasses import dataclass
from typing import Any


@dataclass
class KnowledgeChunk:
    """A searchable documentation/code chunk."""

    chunk_id: str
    text: str
    metadata: dict[str, Any]


@dataclass
class RetrievedChunk:
    """A chunk returned by vector search."""

    chunk_id: str
    text: str
    metadata: dict[str, Any]
    score: float | None = None

