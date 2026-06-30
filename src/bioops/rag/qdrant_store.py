import os
from typing import Any

from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from bioops.rag.schemas import KnowledgeChunk, RetrievedChunk

load_dotenv()


class QdrantKnowledgeStore:
    """Stores and searches knowledge chunks in Qdrant."""

    def __init__(
        self,
        url: str | None = None,
        collection_name: str | None = None,
        vector_size: int = 1536,
    ):
        self.url = url or os.getenv("QDRANT_URL", "http://localhost:6333")
        self.collection_name = collection_name or os.getenv(
            "QDRANT_COLLECTION",
            "bioops_knowledge",
        )
        self.vector_size = vector_size
        self.client = QdrantClient(url=self.url)

    def recreate_collection(self) -> None:
        self.client.recreate_collection(
            collection_name=self.collection_name,
            vectors_config=VectorParams(
                size=self.vector_size,
                distance=Distance.COSINE,
            ),
        )

    def upsert_chunks(
        self,
        chunks: list[KnowledgeChunk],
        vectors: list[list[float]],
    ) -> None:
        if len(chunks) != len(vectors):
            raise ValueError("chunks and vectors must have the same length")

        points = []

        for idx, (chunk, vector) in enumerate(zip(chunks, vectors)):
            points.append(
                PointStruct(
                    id=idx,
                    vector=vector,
                    payload={
                        "chunk_id": chunk.chunk_id,
                        "text": chunk.text,
                        "metadata": chunk.metadata,
                    },
                )
            )

        self.client.upsert(
            collection_name=self.collection_name,
            points=points,
        )

    def search(
        self,
        query_vector: list[float],
        limit: int = 5,
    ) -> list[RetrievedChunk]:
        response = self.client.query_points(
            collection_name=self.collection_name,
            query=query_vector,
            limit=limit,
        )

        retrieved = []

        for point in response.points:
            payload: dict[str, Any] = point.payload or {}

            retrieved.append(
                RetrievedChunk(
                    chunk_id=payload.get("chunk_id", ""),
                    text=payload.get("text", ""),
                    metadata=payload.get("metadata", {}),
                    score=point.score,
                )
            )

        return retrieved
