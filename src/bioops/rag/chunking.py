import re
from pathlib import Path

import fitz  # PyMuPDF

from bioops.rag.schemas import KnowledgeChunk


SUPPORTED_EXTENSIONS = {".md", ".txt", ".yaml", ".yml", ".json", ".pdf"}


def read_pdf_text(path: Path) -> str:
    """Extract text from a PDF file using PyMuPDF."""
    pages: list[str] = []

    with fitz.open(path) as document:
        for page in document:
            page_text = page.get_text("text") or ""
            pages.append(page_text)

    return "\n".join(pages)


def read_document_text(path: Path) -> str:
    """Read supported document types as text."""
    suffix = path.suffix.lower()

    if suffix == ".pdf":
        return read_pdf_text(path)

    return path.read_text(encoding="utf-8", errors="replace")


def split_into_sentences(text: str) -> list[str]:
    """Split text into sentence-like units while keeping simple markdown/YAML lines usable."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    units = []

    for line in lines:
        if (
            line.startswith(("#", "-", "*", "|"))
            or ":" in line
            or line.startswith(("```", "{", "}"))
        ):
            units.append(line)
            continue

        parts = re.split(r"(?<=[.!?])\s+", line)
        units.extend(part.strip() for part in parts if part.strip())

    return units


def chunk_text(
    text: str,
    source: str,
    chunk_size: int = 900,
    overlap_sentences: int = 1,
) -> list[KnowledgeChunk]:
    units = split_into_sentences(text)

    chunks = []
    current_units = []
    current_length = 0
    chunk_number = 0

    for unit in units:
        unit_length = len(unit)

        if current_units and current_length + unit_length > chunk_size:
            chunk_text_value = "\n".join(current_units).strip()

            chunks.append(
                KnowledgeChunk(
                    chunk_id=f"{source}:{chunk_number}",
                    text=chunk_text_value,
                    metadata={
                        "source": source,
                        "chunk_number": chunk_number,
                    },
                )
            )

            chunk_number += 1

            current_units = (
                current_units[-overlap_sentences:]
                if overlap_sentences
                else []
            )
            current_length = sum(len(item) for item in current_units)

        current_units.append(unit)
        current_length += unit_length

    if current_units:
        chunks.append(
            KnowledgeChunk(
                chunk_id=f"{source}:{chunk_number}",
                text="\n".join(current_units).strip(),
                metadata={
                    "source": source,
                    "chunk_number": chunk_number,
                },
            )
        )

    return chunks


def chunk_file(path: str | Path) -> list[KnowledgeChunk]:
    path = Path(path)

    if not path.is_file():
        return []

    if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        return []

    text = read_document_text(path)

    if not text.strip():
        return []

    return chunk_text(
        text=text,
        source=str(path),
    )


def chunk_files(paths: list[str | Path]) -> list[KnowledgeChunk]:
    all_chunks = []

    for path in paths:
        all_chunks.extend(chunk_file(path))

    return all_chunks