import os
from pathlib import Path

from bioops.rag.chunking import chunk_files
from bioops.rag.embeddings import AzureEmbeddingClient
from bioops.rag.qdrant_store import QdrantKnowledgeStore
from bioops.rag.schemas import KnowledgeChunk
from bioops.rag.yandex_wiki import (
    YandexWikiClient,
    env_flag,
    wiki_pages_to_chunks,
)


DOCS_DIR = Path("docs")
ALLOWED_EXTENSIONS = {".md", ".txt", ".yaml", ".yml", ".pdf"}


def find_source_files() -> list[Path]:
    """Find documentation files inside docs/ only."""
    return [
        path
        for path in DOCS_DIR.rglob("*")
        if path.is_file() and path.suffix.lower() in ALLOWED_EXTENSIONS
    ]


def ingest_chunks(
    *,
    chunks: list[KnowledgeChunk],
    embedder: AzureEmbeddingClient,
    collection_name: str | None = None,
    vector_size: int | None = None,
) -> int:
    vectors = embedder.embed_texts([chunk.text for chunk in chunks]) if chunks else []
    resolved_size = vector_size or (len(vectors[0]) if vectors else 1536)
    store = QdrantKnowledgeStore(
        collection_name=collection_name,
        vector_size=resolved_size,
    )
    store.recreate_collection()

    if chunks:
        store.upsert_chunks(chunks, vectors)

    return resolved_size


def main() -> None:
    source_files = find_source_files()

    if not source_files:
        raise ValueError(f"No source files found in {DOCS_DIR}")

    docs_chunks = chunk_files(source_files)
    wiki_enabled = env_flag("YANDEX_WIKI_ENABLED")
    wiki_chunks: list[KnowledgeChunk] = []

    if wiki_enabled:
        root_slug = os.getenv("YANDEX_WIKI_ROOT_SLUG", "")
        max_pages = max(1, int(os.getenv("YANDEX_WIKI_MAX_PAGES", "1000")))
        wiki_client = YandexWikiClient()
        wiki_pages = wiki_client.fetch_subtree(
            root_slug,
            max_pages=max_pages,
        )
        wiki_chunks = wiki_pages_to_chunks(
            wiki_pages,
            web_url=wiki_client.web_url,
        )

        print(f"Number of Yandex Wiki pages: {len(wiki_pages)}")
        print(f"Number of Yandex Wiki chunks: {len(wiki_chunks)}")

    embedder = AzureEmbeddingClient()

    print(f"Number of source files: {len(source_files)}")
    print(f"Number of bundled docs chunks: {len(docs_chunks)}")

    vector_size = ingest_chunks(
        chunks=docs_chunks,
        embedder=embedder,
    )
    print(f"Embedding dimension: {vector_size}")
    print(f"Ingested {len(docs_chunks)} bundled docs chunks into Qdrant.")

    if wiki_enabled:
        docs_collection = os.getenv(
            "QDRANT_COLLECTION",
            "bioops_knowledge",
        )
        wiki_collection = os.getenv(
            "QDRANT_WIKI_COLLECTION",
            f"{docs_collection}_wiki",
        )
        ingest_chunks(
            chunks=wiki_chunks,
            embedder=embedder,
            collection_name=wiki_collection,
            vector_size=vector_size,
        )
        print(
            f"Ingested {len(wiki_chunks)} Yandex Wiki chunks "
            f"into {wiki_collection}."
        )


if __name__ == "__main__":
    main()
