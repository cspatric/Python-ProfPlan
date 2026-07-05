"""Header-aware semantic chunking of Markdown for embedding.

Splitting happens along Markdown headings first: each chunk stays within a
single section and is prefixed with its heading breadcrumb (e.g.
``Biology > Photosynthesis``) so an embedded chunk carries its context. Long
sections are further packed by paragraph, with a character overlap between
windows to avoid cutting ideas at hard boundaries.
"""

import re

DEFAULT_MAX_CHARS = 1000
DEFAULT_OVERLAP = 100

_HEADER = re.compile(r"^(#{1,6})\s+(.*)$")
_PARAGRAPH_SPLIT = re.compile(r"\n\s*\n")


def _split_sections(text: str) -> list[tuple[str, str]]:
    """Split markdown into (heading breadcrumb, body) sections.

    Content before the first heading is returned with an empty breadcrumb.
    """
    sections: list[tuple[str, str]] = []
    stack: list[tuple[int, str]] = []  # (level, title)
    body: list[str] = []
    breadcrumb = ""

    def flush() -> None:
        joined = "\n".join(body).strip()
        if joined:
            sections.append((breadcrumb, joined))
        body.clear()

    for line in text.splitlines():
        match = _HEADER.match(line.strip())
        if match:
            flush()
            level = len(match.group(1))
            title = match.group(2).strip()
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, title))
            breadcrumb = " > ".join(t for _, t in stack)
        else:
            body.append(line)
    flush()
    return sections


def _pack_paragraphs(text: str, max_chars: int, overlap: int) -> list[str]:
    """Pack paragraphs into windows of at most ``max_chars`` characters."""
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


def chunk_markdown(
    text: str,
    *,
    max_chars: int = DEFAULT_MAX_CHARS,
    overlap: int = DEFAULT_OVERLAP,
) -> list[str]:
    """Return header-aware chunks, each prefixed with its heading breadcrumb."""
    text = text.strip()
    if not text:
        return []

    chunks: list[str] = []
    for breadcrumb, body in _split_sections(text):
        prefix = f"{breadcrumb}\n\n" if breadcrumb else ""
        budget = max(1, max_chars - len(prefix))
        for piece in _pack_paragraphs(body, budget, overlap):
            chunks.append(f"{prefix}{piece}")
    return chunks
