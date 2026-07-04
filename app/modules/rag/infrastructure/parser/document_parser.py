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


def parse_to_markdown(filename: str, data: bytes) -> str:
    """Return the markdown/plain-text representation of a document."""
    suffix = Path(filename).suffix.lower()
    if suffix in _TEXT_SUFFIXES:
        return data.decode("utf-8", errors="replace").strip()
    if suffix == ".pdf":
        return _parse_pdf(data)
    raise UnsupportedFormatError(f"Unsupported document format: {suffix}")
