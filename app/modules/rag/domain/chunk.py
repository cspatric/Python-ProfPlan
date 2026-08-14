"""RAG domain value objects."""

from dataclasses import dataclass


@dataclass(slots=True)
class ChunkInput:
    """A chunk ready to be indexed for a document content."""

    chunk_index: int
    content: str
    token_count: int | None = None
    embedding: list[float] | None = None


@dataclass(slots=True)
class SearchResult:
    """A retrieved chunk with its cosine distance to the query (lower closer)."""

    chunk_id: str
    document_content_id: str
    content: str
    distance: float

    @property
    def section(self) -> str | None:
        """The heading breadcrumb the chunker prefixed this passage with.

        The chunker writes "Chapter 2 > Gradient Descent\n\n<text>", so the
        breadcrumb is recovered by reading it back rather than stored twice.
        It is a heuristic and it says so: a passage from before the first
        heading has none, and a first paragraph that happens to be one line
        would be mistaken for one. Both cases cost a slightly wrong label on a
        citation, which is why the excerpt is shown next to it.
        """
        head, separator, _ = self.content.partition("\n\n")
        if not separator or len(head) > 200 or "\n" in head:
            return None
        return head.strip() or None
