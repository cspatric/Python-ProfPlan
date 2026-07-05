"""Convert an uploaded document into markdown/plain text.

Supports plain text/markdown and PDF for now; other formats can be added as
dedicated parsers under this package.
"""

from io import BytesIO
from pathlib import Path

from app.shared.exceptions.base import UnprocessableError

_TEXT_SUFFIXES = {".txt", ".md", ".markdown"}


class UnsupportedFormatError(UnprocessableError):
    """Raised when a document format cannot be parsed."""

    detail = "Unsupported document format"


def _parse_pdf(data: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(BytesIO(data))
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n\n".join(pages).strip()


def _parse_docx(data: bytes) -> str:
    from docx import Document

    document = Document(BytesIO(data))
    paragraphs = [p.text for p in document.paragraphs if p.text.strip()]
    return "\n\n".join(paragraphs).strip()


def _parse_pptx(data: bytes) -> str:
    from pptx import Presentation

    presentation = Presentation(BytesIO(data))
    lines: list[str] = []
    for slide in presentation.slides:
        for shape in slide.shapes:
            if shape.has_text_frame and shape.text_frame.text.strip():
                lines.append(shape.text_frame.text.strip())
    return "\n\n".join(lines).strip()


_PARSERS = {
    ".pdf": _parse_pdf,
    ".docx": _parse_docx,
    ".pptx": _parse_pptx,
}


def parse_to_markdown(filename: str, data: bytes) -> str:
    """Return the markdown/plain-text representation of a document."""
    suffix = Path(filename).suffix.lower()
    if suffix in _TEXT_SUFFIXES:
        return data.decode("utf-8", errors="replace").strip()
    parser = _PARSERS.get(suffix)
    if parser is not None:
        return parser(data)
    raise UnsupportedFormatError(f"Unsupported document format: {suffix}")
