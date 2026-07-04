"""Split parsed markdown into overlapping chunks for embedding."""

import re

DEFAULT_MAX_CHARS = 1000
DEFAULT_OVERLAP = 100

_PARAGRAPH_SPLIT = re.compile(r"\n\s*\n")


def chunk_markdown(
    text: str,
    *,
    max_chars: int = DEFAULT_MAX_CHARS,
    overlap: int = DEFAULT_OVERLAP,
) -> list[str]:
    """Return a list of chunks, each at most ``max_chars`` characters.

    Paragraphs are kept together when possible; a paragraph longer than
    ``max_chars`` is split into overlapping windows.
    """
    text = text.strip()
    if not text:
        return []

    step = max(1, max_chars - overlap)
    pieces: list[str] = []
    for paragraph in (p.strip() for p in _PARAGRAPH_SPLIT.split(text)):
        if not paragraph:
            continue
        if len(paragraph) <= max_chars:
            pieces.append(paragraph)
        else:
            for start in range(0, len(paragraph), step):
                pieces.append(paragraph[start : start + max_chars])

    chunks: list[str] = []
    current = ""
    for piece in pieces:
        candidate = piece if not current else f"{current}\n\n{piece}"
        if len(candidate) <= max_chars:
            current = candidate
        else:
            if current:
                chunks.append(current)
            current = piece
    if current:
        chunks.append(current)
    return chunks
