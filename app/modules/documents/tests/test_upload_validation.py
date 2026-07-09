"""Unit tests for upload validation (never trust the client)."""

import pytest

from app.modules.documents.domain.exceptions import UnsupportedDocumentTypeError
from app.modules.documents.domain.upload_validation import validate_document_upload

_PDF = b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n1 0 obj"
_DOCX = b"PK\x03\x04\x14\x00\x06\x00" + b"\x00" * 20  # ZIP signature (OOXML)
_TEXT = b"# Fotossintese\n\nProcesso que converte luz em energia."
_EXE = b"MZ\x90\x00\x03\x00\x00\x00"  # PE/DOS executable header


class TestAcceptsValidFiles:
    def test_pdf(self):
        validate_document_upload(
            filename="notes.pdf", content_type="application/pdf", data=_PDF
        )

    def test_docx(self):
        validate_document_upload(
            filename="doc.docx",
            content_type="application/vnd.openxmlformats-officedocument."
            "wordprocessingml.document",
            data=_DOCX,
        )

    def test_markdown_text(self):
        validate_document_upload(
            filename="a.md", content_type="text/markdown", data=_TEXT
        )

    def test_generic_octet_stream_is_tolerated_when_magic_matches(self):
        # Clients often send octet-stream; the magic bytes are the real check.
        validate_document_upload(
            filename="notes.pdf",
            content_type="application/octet-stream",
            data=_PDF,
        )


class TestRejectsBadFiles:
    def test_unsupported_extension(self):
        with pytest.raises(UnsupportedDocumentTypeError):
            validate_document_upload(
                filename="malware.exe",
                content_type="application/octet-stream",
                data=_EXE,
            )

    def test_executable_renamed_to_pdf_is_caught_by_magic_bytes(self):
        with pytest.raises(UnsupportedDocumentTypeError):
            validate_document_upload(
                filename="notes.pdf", content_type="application/pdf", data=_EXE
            )

    def test_binary_content_for_text_extension(self):
        with pytest.raises(UnsupportedDocumentTypeError):
            validate_document_upload(
                filename="notes.txt", content_type="text/plain", data=_EXE
            )

    def test_disallowed_content_type(self):
        with pytest.raises(UnsupportedDocumentTypeError):
            validate_document_upload(
                filename="notes.pdf", content_type="text/html", data=_PDF
            )

    def test_empty_file(self):
        with pytest.raises(UnsupportedDocumentTypeError):
            validate_document_upload(
                filename="notes.pdf", content_type="application/pdf", data=b""
            )
