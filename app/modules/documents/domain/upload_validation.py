"""Validation for uploaded documents.

Never trust the client. Before a file is stored we check three things:

1. **Extension** — must be one we actually parse.
2. **Content type** — the declared MIME must be in the allow-list (a generic
   ``application/octet-stream`` is tolerated because many clients send it).
3. **Magic bytes** — the *real* file signature must match the extension, so a
   ``virus.exe`` renamed to ``notes.pdf`` is rejected regardless of what the
   name or the declared MIME claim.

Size is enforced separately at the transport edge (bounded read in the router)
so a huge upload can never be fully buffered into memory.
"""

from pathlib import Path

from app.modules.documents.domain.exceptions import UnsupportedDocumentTypeError

SUPPORTED_SUFFIXES = {".pdf", ".docx", ".pptx", ".xlsx", ".txt", ".md", ".markdown"}

_TEXT_SUFFIXES = {".txt", ".md", ".markdown"}
_ZIP_SUFFIXES = {".docx", ".pptx", ".xlsx"}  # OOXML files are ZIP archives

# Authoritative content signatures (first bytes of the file).
_PDF_MAGIC = (b"%PDF-",)
_ZIP_MAGIC = (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")

_ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/msword",
    "application/vnd.ms-excel",
    "application/vnd.ms-powerpoint",
    "text/plain",
    "text/markdown",
    "text/x-markdown",
    "application/octet-stream",  # generic; magic bytes are the real check
    "",
}


def _looks_like_text(data: bytes) -> bool:
    """Heuristic: a text file has no NUL bytes and decodes as UTF-8/Latin-1."""
    sample = data[:4096]
    if b"\x00" in sample:
        return False
    try:
        sample.decode("utf-8")
    except UnicodeDecodeError:
        try:
            sample.decode("latin-1")
        except UnicodeDecodeError:
            return False
    return True


def validate_document_upload(*, filename: str, content_type: str, data: bytes) -> None:
    """Raise UnsupportedDocumentTypeError unless the upload is a supported file.

    Size is validated by the caller (see the router's bounded read).
    """
    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise UnsupportedDocumentTypeError(
            f"Unsupported file extension '{suffix or filename}'. Allowed: "
            + ", ".join(sorted(SUPPORTED_SUFFIXES))
        )

    declared = (content_type or "").split(";")[0].strip().lower()
    if declared not in _ALLOWED_CONTENT_TYPES:
        raise UnsupportedDocumentTypeError(f"Unsupported content type '{declared}'")

    if not data:
        raise UnsupportedDocumentTypeError("Empty file")

    # Suffixes are mutually exclusive; check the real signature for each family.
    if suffix in _TEXT_SUFFIXES and not _looks_like_text(data):
        raise UnsupportedDocumentTypeError("File content is not valid text")
    if suffix == ".pdf" and not data.startswith(_PDF_MAGIC):
        raise UnsupportedDocumentTypeError("File content is not a valid PDF")
    if suffix in _ZIP_SUFFIXES and not data.startswith(_ZIP_MAGIC):
        raise UnsupportedDocumentTypeError(
            "File content is not a valid Office (OOXML) document"
        )
