"""Unit tests for the markdown chunker."""

from app.modules.rag.infrastructure.chunking.chunker import chunk_markdown


def test_empty_text_yields_no_chunks() -> None:
    assert chunk_markdown("   \n\n  ") == []


def test_short_text_is_a_single_chunk() -> None:
    chunks = chunk_markdown("Hello world", max_chars=100)
    assert chunks == ["Hello world"]


def test_paragraphs_are_packed_within_limit() -> None:
    text = "para one\n\npara two\n\npara three"
    chunks = chunk_markdown(text, max_chars=20, overlap=0)
    assert all(len(c) <= 20 for c in chunks)
    assert "para one" in chunks[0]


def test_long_paragraph_is_split_into_windows() -> None:
    text = "x" * 250
    chunks = chunk_markdown(text, max_chars=100, overlap=10)
    assert len(chunks) >= 3
    assert all(len(c) <= 100 for c in chunks)
    # Reassembling (accounting for overlap) preserves all characters.
    assert "".join(chunks).count("x") >= 250


def test_headers_prefix_chunks_with_breadcrumb() -> None:
    text = (
        "# Biology\n\n"
        "## Photosynthesis\n\nPlants convert light to energy.\n\n"
        "## Respiration\n\nCells release energy."
    )
    chunks = chunk_markdown(text, max_chars=200)

    assert any(c.startswith("Biology > Photosynthesis") for c in chunks)
    assert any(c.startswith("Biology > Respiration") for c in chunks)
    assert any("Plants convert light to energy." in c for c in chunks)


def test_section_content_stays_with_its_heading() -> None:
    text = "# A\n\nalpha\n\n# B\n\nbeta"
    chunks = chunk_markdown(text, max_chars=200)

    a_chunk = next(c for c in chunks if "alpha" in c)
    assert a_chunk.startswith("A")
    assert "beta" not in a_chunk
