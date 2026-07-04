"""Unit tests for the document parser."""

import pytest

from app.modules.rag.infrastructure.parser.document_parser import (
    UnsupportedFormatError,
    parse_to_markdown,
)


def test_parses_markdown_and_text() -> None:
    assert parse_to_markdown("notes.md", b"# Title\n\nbody") == "# Title\n\nbody"
    assert parse_to_markdown("plain.txt", b"just text") == "just text"


def test_unknown_extension_raises() -> None:
    with pytest.raises(UnsupportedFormatError):
        parse_to_markdown("archive.zip", b"...")
