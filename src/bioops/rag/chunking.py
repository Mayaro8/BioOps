import re
from pathlib import Path

from bioops.rag.schemas import KnowledgeChunk


def split_into_sentences(text: str) -> list[str]:
    """Split text into sentence-like units while keeping simple markdown/YAML lines usable."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    units = []

    for line in lines:
        # Keep structured lines as their own units.
        if (
            line.startswith(("#", "-", "*", "|"))
            or ":" in line
            or line.startswith(("```", "{", "}"))
        ):
            units.append(line)
            continue

        # Split prose into sentences.
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

            current_units = current_units[-overlap_sentences:] if overlap_sentences else []
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
    text = path.read_text(encoding="utf-8")

    return chunk_text(
        text=text,
        source=str(path),
    )


def chunk_files(paths: list[str | Path]) -> list[KnowledgeChunk]:
    all_chunks = []

    for path in paths:
        all_chunks.extend(chunk_file(path))

    return all_chunks
