"""Unit tests for slicing an embedding job into requests.

The rule is not about speed, which the model decides, but about each request
finishing: one call carrying every chunk of a large document could not complete
inside any sane timeout, so large documents never indexed at all.
"""

import httpx
import pytest

from app.modules.rag.infrastructure.embedding.ollama_embedding import OllamaEmbedding


class RecordingTransport(httpx.AsyncBaseTransport):
    """Answers /api/embed and remembers how many texts each call carried."""

    def __init__(self) -> None:
        self.batches: list[int] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        import json

        texts = json.loads(request.content)["input"]
        self.batches.append(len(texts))
        return httpx.Response(
            200, json={"embeddings": [[float(i)] for i in range(len(texts))]}
        )


@pytest.fixture
def transport(monkeypatch) -> RecordingTransport:
    recorder = RecordingTransport()
    original = httpx.AsyncClient.__init__

    def patched(self, *args, **kwargs):
        kwargs["transport"] = recorder
        original(self, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", patched)
    return recorder


async def test_a_long_document_is_split_into_several_requests(transport) -> None:
    embedder = OllamaEmbedding(batch_size=8)

    vectors = await embedder.embed_texts([f"chunk {i}" for i in range(20)])

    assert transport.batches == [8, 8, 4]
    # Every chunk still comes back, in order, exactly once.
    assert len(vectors) == 20


async def test_a_short_document_is_one_request(transport) -> None:
    embedder = OllamaEmbedding(batch_size=8)

    await embedder.embed_texts(["a", "b", "c"])

    assert transport.batches == [3]


async def test_nothing_to_embed_makes_no_request(transport) -> None:
    embedder = OllamaEmbedding(batch_size=8)

    assert await embedder.embed_texts([]) == []
    assert transport.batches == []


async def test_a_single_text_still_works(transport) -> None:
    embedder = OllamaEmbedding(batch_size=8)

    assert await embedder.embed_text("only this") == [0.0]
    assert transport.batches == [1]
