"""Hybrid retrieval, against a real Postgres.

The embeddings here are written by hand rather than produced by the embedder.
That is the point: with vectors nobody chose, a test of fusion is a test of
whichever model happens to be installed, and it cannot state what it is
asserting. With chosen vectors, each case says exactly what it means, "the
vector search hates this chunk and the words love it", and the assertion is
about the fusion.
"""

import uuid

import pytest
from sqlalchemy import select

from app.core.constants import EMBEDDING_DIMENSIONS
from app.infrastructure.database.session import SessionFactory
from app.modules.documents.infrastructure.models import (
    Document,
    DocumentContent,
    DocumentFormat,
)
from app.modules.rag.infrastructure.models import Chunk
from app.modules.rag.infrastructure.repository import ChunkRepository
from app.modules.subjects.infrastructure.models import Subject

pytestmark = pytest.mark.integration

RRF_K = 60
POOL = 30


def _vector(first: float, second: float = 0.0) -> list[float]:
    """A unit-ish vector whose direction is set by its first two components."""
    return [first, second] + [0.0] * (EMBEDDING_DIMENSIONS - 2)


async def _corpus(user_id, passages: list[tuple[str, list[float]]]):
    """Index these passages verbatim, with the embedding each one is given."""
    async with SessionFactory() as session:
        subject = Subject(user_id=user_id, name="Biology")
        session.add(subject)
        await session.flush()
        # The format table is a catalogue with a unique key, so a second
        # corpus in the same test reuses the row rather than inserting it.
        fmt = await session.scalar(
            select(DocumentFormat).where(DocumentFormat.format == "md")
        )
        if fmt is None:
            fmt = DocumentFormat(format="md")
            session.add(fmt)
            await session.flush()
        document = Document(
            subject_id=subject.uuid,
            document_format_id=fmt.uuid,
            title="Notes",
            document_path="s3://bucket/notes.md",
        )
        session.add(document)
        await session.flush()
        content = DocumentContent(document_id=document.uuid, markdown="x", version=1)
        session.add(content)
        await session.flush()
        for index, (body, embedding) in enumerate(passages):
            session.add(
                Chunk(
                    document_content_id=content.uuid,
                    chunk_index=index,
                    content=body,
                    embedding=embedding,
                )
            )
        await session.commit()
        return content.uuid


async def test_a_passage_only_the_words_find_is_retrieved(user_factory):
    """The case hybrid search exists for.

    A surname carries no meaning to average, so the embedding of a question
    about it can sit nowhere near the passage that answers it. The word is
    still right there in the text.
    """
    user = await user_factory(email=f"hybrid-{uuid.uuid4().hex[:8]}@test.com")
    content_id = await _corpus(
        user.uuid,
        [
            ("Photosynthesis converts light into chemical energy.", _vector(1.0)),
            ("Respiration releases the energy stored in glucose.", _vector(0.9, 0.1)),
            ("Van Helmont grew a willow for five years.", _vector(0.0, 1.0)),
        ],
    )
    # A query embedding that points at the first two passages and away from
    # the third, which is the one that actually answers it.
    query = _vector(1.0)

    async with SessionFactory() as session:
        chunks = ChunkRepository(session)

        semantic = await chunks.search_similar(query, limit=2, content_ids=[content_id])
        fused = await chunks.search_hybrid(
            query,
            "van Helmont willow",
            limit=2,
            content_ids=[content_id],
            pool=POOL,
            rrf_k=RRF_K,
        )

    assert not any("Helmont" in chunk.content for chunk, _ in semantic)
    assert any("Helmont" in chunk.content for chunk, _, _, _ in fused)


async def test_agreement_between_the_two_searches_wins(user_factory):
    """RRF's whole behaviour in one assertion: a passage both halves liked
    beats one that only the vector search put first."""
    user = await user_factory(email=f"hybrid-{uuid.uuid4().hex[:8]}@test.com")
    content_id = await _corpus(
        user.uuid,
        [
            # Closest by vector, and shares no word with the query.
            ("Energy conversion in living systems.", _vector(1.0)),
            # Second by vector, and the words match.
            ("The Calvin cycle fixes carbon dioxide.", _vector(0.95, 0.05)),
        ],
    )
    query = _vector(1.0)

    async with SessionFactory() as session:
        chunks = ChunkRepository(session)
        fused = await chunks.search_hybrid(
            query,
            "Calvin cycle carbon dioxide",
            limit=2,
            content_ids=[content_id],
            pool=POOL,
            rrf_k=RRF_K,
        )

    assert "Calvin" in fused[0][0].content
    # And it says so: found by both halves, which is the signal.
    _, _, vector_rank, lexical_rank = fused[0]
    assert vector_rank is not None and lexical_rank is not None


async def test_a_question_of_only_stopwords_still_searches(user_factory):
    """ "How does it work" has no searchable word once stopwords are gone. The
    lexical half has nothing to do, and the answer must be the vector search
    rather than an empty list."""
    user = await user_factory(email=f"hybrid-{uuid.uuid4().hex[:8]}@test.com")
    content_id = await _corpus(
        user.uuid, [("Photosynthesis in the thylakoid membrane.", _vector(1.0))]
    )

    async with SessionFactory() as session:
        fused = await ChunkRepository(session).search_hybrid(
            _vector(1.0),
            "how does it do that",
            limit=3,
            content_ids=[content_id],
            pool=POOL,
            rrf_k=RRF_K,
        )

    assert len(fused) == 1
    assert fused[0][3] is None  # nothing came from the lexical half


async def test_the_word_search_is_scoped_to_the_owner(user_factory):
    """The lexical half is a second way into the data, so it needs the same
    fence. An unscoped word search would be a way to read somebody else's
    documents by guessing a term."""
    mine = await user_factory(email=f"hybrid-{uuid.uuid4().hex[:8]}@test.com")
    theirs = await user_factory(email=f"hybrid-{uuid.uuid4().hex[:8]}@test.com")
    my_content = await _corpus(mine.uuid, [("My own notes on mitosis.", _vector(1.0))])
    await _corpus(theirs.uuid, [("Their secret notes on mitosis.", _vector(1.0))])

    async with SessionFactory() as session:
        chunks = ChunkRepository(session)
        lexical = await chunks.search_lexical(
            "mitosis notes", limit=10, content_ids=[my_content]
        )
        fused = await chunks.search_hybrid(
            _vector(1.0),
            "mitosis notes",
            limit=10,
            content_ids=[my_content],
            pool=POOL,
            rrf_k=RRF_K,
        )

    assert [c.content for c, _ in lexical] == ["My own notes on mitosis."]
    assert [c.content for c, _, _, _ in fused] == ["My own notes on mitosis."]


async def test_the_word_search_ranks_rather_than_filters(user_factory):
    """A natural question rarely has all of its words in one passage. With AND
    semantics the lexical half returns nothing for most real questions, which
    is how a feature ends up switched on and doing nothing."""
    user = await user_factory(email=f"hybrid-{uuid.uuid4().hex[:8]}@test.com")
    content_id = await _corpus(
        user.uuid,
        [
            (
                "Food chains are short because energy is lost at each level.",
                _vector(1.0),
            ),
            ("Chains of amino acids fold into proteins.", _vector(0.5)),
        ],
    )

    async with SessionFactory() as session:
        lexical = await ChunkRepository(session).search_lexical(
            "why are food chains short", limit=5, content_ids=[content_id]
        )

    # Both share a word, so both are candidates; the ranking is what separates
    # them, and the passage sharing three terms comes first.
    assert len(lexical) == 2
    assert "Food chains" in lexical[0][0].content
