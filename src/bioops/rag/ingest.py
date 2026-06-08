from pathlib import Path

from bioops.rag.chunking import chunk_files
from bioops.rag.embeddings import AzureEmbeddingClient
from bioops.rag.qdrant_store import QdrantKnowledgeStore


DOCS_DIR = Path("docs")
ALLOWED_EXTENSIONS = {".md", ".txt", ".yaml", ".yml", ".pdf"}


def find_source_files() -> list[Path]:
    """Find documentation files inside docs/ only."""
    return [
        path
        for path in DOCS_DIR.rglob("*")
        if path.is_file() and path.suffix.lower() in ALLOWED_EXTENSIONS
    ]


def main() -> None:
    source_files = find_source_files()

    if not source_files:
        raise ValueError(f"No source files found in {DOCS_DIR}")

    chunks = chunk_files(source_files)

    embedder = AzureEmbeddingClient()
    vectors = embedder.embed_texts([chunk.text for chunk in chunks])

    print(f"Number of source files: {len(source_files)}")
    print(f"Number of chunks/embeddings: {len(vectors)}")
    print(f"Embedding dimension: {len(vectors[0])}")

    vector_size = len(vectors[0])

    store = QdrantKnowledgeStore(vector_size=vector_size)
    store.recreate_collection()
    store.upsert_chunks(chunks, vectors)

    print(f"Ingested {len(chunks)} chunks into Qdrant.")


if __name__ == "__main__":
    main()