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
    #: 1-based position in each half of the hybrid search, None when that half
    #: did not return this chunk. Both None means the plain vector search ran.
    vector_rank: int | None = None
    lexical_rank: int | None = None

    @property
    def matched_by(self) -> str:
        """How this passage was found: by meaning, by words, or by both.

        Worth keeping rather than deriving later: "both" is the strongest
        signal the retrieval produces, and it is the only evidence that the
        lexical half is earning its place.
        """
        if self.vector_rank is not None and self.lexical_rank is not None:
            return "both"
        if self.lexical_rank is not None:
            return "keyword"
        return "semantic"

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
