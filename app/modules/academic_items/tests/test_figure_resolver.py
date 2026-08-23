"""Resolving a generator's figure request into a stored, credited image.

The behaviour under test is mostly about what happens when things go wrong,
because that is the design: an item is content first and illustrated second, so
every failure costs one illustration and nothing else.
"""

from uuid import uuid4

from app.modules.academic_items.application.figure_service import FigureResolver
from app.modules.academic_items.domain.figures import FigureCandidate, FigureSource

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64


def _candidate(**overrides) -> FigureCandidate:
    defaults = {
        "source": FigureSource.WIKIMEDIA,
        "source_url": "https://commons.wikimedia.org/wiki/File:Neuron.png",
        "image_url": "https://upload.wikimedia.org/thumb/Neuron.png",
        "title": "Neuron.png",
        "mime_type": "image/png",
        "width": 800,
        "height": 600,
        "licence": "CC BY-SA 4.0",
        "licence_url": None,
        "attribution": "Jane Doe",
    }
    return FigureCandidate(**{**defaults, **overrides})


class FakeSearch:
    def __init__(self, results=None, error: Exception | None = None) -> None:
        self._results = results if results is not None else [_candidate()]
        self._error = error
        self.calls: list[str] = []

    async def search(self, query, *, limit=5):
        self.calls.append(query)
        if self._error:
            raise self._error
        return self._results


class FakeDownloader:
    def __init__(self, data: bytes = PNG, content_type: str = "image/png") -> None:
        self._data, self._content_type = data, content_type
        self.calls = 0

    async def fetch(self, url):
        self.calls += 1
        return self._data, self._content_type


class FakeStorage:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def put_object(self, name, data, content_type):
        self.objects[name] = data
        return name


class FakeRepo:
    def __init__(self) -> None:
        self.figures: list = []

    async def replace(self, item_id, figures):
        self.figures = figures


def _resolver(**overrides):
    parts = {
        "search": FakeSearch(),
        "downloader": FakeDownloader(),
        "storage": FakeStorage(),
        "repo": FakeRepo(),
    }
    parts.update(overrides)
    return FigureResolver(**parts), parts


async def _resolve(resolver, markdown):
    return await resolver.resolve(
        markdown=markdown, item_id=uuid4(), user_id=uuid4(), subject_id=uuid4()
    )


async def test_a_placeholder_becomes_a_stored_image() -> None:
    resolver, parts = _resolver()

    result = await _resolve(resolver, "Text\n\n{{figure: a neuron}}\n\nMore")

    assert "{{figure" not in result
    assert "![Neuron.png](figures/" in result
    assert len(parts["storage"].objects) == 1
    assert len(parts["repo"].figures) == 1


async def test_the_credit_is_not_written_into_the_markdown() -> None:
    """It lives on the row, and both renderers read it from there. One source of
    truth for a licence obligation, and no way for the web view and the printed
    handout to disagree about who is owed it."""
    resolver, parts = _resolver()

    result = await _resolve(resolver, "{{figure: a neuron}}")
    [figure] = parts["repo"].figures

    assert "CC BY-SA 4.0" not in result
    assert "CC BY-SA 4.0" in figure.caption
    assert "Jane Doe" in figure.caption


async def test_the_stored_row_carries_what_the_credit_needs() -> None:
    resolver, parts = _resolver()

    await _resolve(resolver, "{{figure: a neuron}}")
    [figure] = parts["repo"].figures

    assert figure.licence == "CC BY-SA 4.0"
    assert figure.attribution == "Jane Doe"
    assert figure.source_url.startswith("https://commons.wikimedia.org")
    assert figure.alt_text  # never blank: a figure with no alt excludes a student
    assert figure.query == "a neuron"


async def test_nothing_found_costs_one_illustration_and_nothing_else() -> None:
    resolver, parts = _resolver(search=FakeSearch(results=[]))

    result = await _resolve(resolver, "Before\n\n{{figure: nobody drew this}}\n\nAfter")

    assert "Before" in result and "After" in result
    assert "{{figure" not in result
    assert parts["repo"].figures == []


async def test_a_failing_search_does_not_fail_the_item() -> None:
    """Commons being slow must not fail a generation the teacher paid tokens
    for."""
    resolver, _ = _resolver(search=FakeSearch(error=RuntimeError("timeout")))

    result = await _resolve(resolver, "Keep this\n\n{{figure: a neuron}}")

    assert "Keep this" in result
    assert "{{figure" not in result


async def test_bytes_that_are_not_an_image_are_refused() -> None:
    """The download came off the public internet: the declared type is a claim."""
    resolver, parts = _resolver(downloader=FakeDownloader(data=b"<html>nope</html>"))

    result = await _resolve(resolver, "{{figure: a neuron}}")

    assert parts["storage"].objects == {}
    assert "![" not in result


async def test_the_next_candidate_is_tried_when_the_first_is_unusable() -> None:
    class OneBadThenGood:
        def __init__(self) -> None:
            self.calls = 0

        async def fetch(self, url):
            self.calls += 1
            if self.calls == 1:
                return b"not an image", "image/png"
            return PNG, "image/png"

    downloader = OneBadThenGood()
    resolver, parts = _resolver(
        search=FakeSearch(results=[_candidate(), _candidate(title="Second.png")]),
        downloader=downloader,
    )

    result = await _resolve(resolver, "{{figure: a neuron}}")

    assert downloader.calls == 2
    assert "Second.png" in result


async def test_the_server_content_type_wins_over_the_search_result() -> None:
    """It is the one that describes the bytes actually in hand."""
    resolver, parts = _resolver(
        search=FakeSearch(results=[_candidate(mime_type="image/png")]),
        downloader=FakeDownloader(
            data=b"\xff\xd8\xff" + b"0" * 64, content_type="image/jpeg"
        ),
    )

    await _resolve(resolver, "{{figure: a neuron}}")
    [figure] = parts["repo"].figures

    assert figure.mime_type == "image/jpeg"
    assert figure.figure_path.endswith(".jpg")


async def test_an_item_with_no_placeholder_touches_nothing() -> None:
    resolver, parts = _resolver()

    result = await _resolve(resolver, "Plain content, no figures.")

    assert result == "Plain content, no figures."
    assert parts["search"].calls == []


async def test_the_same_description_twice_is_downloaded_once() -> None:
    resolver, parts = _resolver()

    result = await _resolve(
        resolver, "{{figure: a neuron}}\n\ntext\n\n{{figure: a neuron}}"
    )

    assert parts["downloader"].calls == 1
    assert result.count("![Neuron.png]") == 2
