"""Reading a Commons search response.

No network: what is worth pinning is the shape of the answer and the filtering,
because that is what silently changes and what a wrong reading turns into an
unlicensed image in a teacher's handout.
"""

from app.modules.academic_items.infrastructure.images.wikimedia import (
    WikimediaImageSearch,
)


def _page(**overrides) -> dict:
    info = {
        "descriptionurl": "https://commons.wikimedia.org/wiki/File:Neuron.png",
        "thumburl": "https://upload.wikimedia.org/thumb/800px-Neuron.png",
        "thumbmime": "image/png",
        "thumbwidth": 800,
        "thumbheight": 600,
        "mime": "image/svg+xml",
        "extmetadata": {
            "LicenseShortName": {"value": "CC BY-SA 4.0"},
            "LicenseUrl": {"value": "https://creativecommons.org/x"},
            "Artist": {"value": '<a href="/wiki/User:Jane">Jane &amp; Co</a>'},
        },
    }
    info.update(overrides.pop("imageinfo", {}))
    return {"title": "File:Neuron.png", "imageinfo": [info], **overrides}


async def _search(monkeypatch, pages: list[dict], limit: int = 5):
    search = WikimediaImageSearch()

    async def _get(params):
        return {"query": {"pages": pages}}

    monkeypatch.setattr(search, "_get", _get)
    return await search.search("labelled diagram of a neuron", limit=limit)


async def test_a_result_is_read_into_a_candidate(monkeypatch) -> None:
    [candidate] = await _search(monkeypatch, [_page()])

    assert candidate.title == "Neuron.png"
    assert candidate.licence == "CC BY-SA 4.0"
    assert candidate.width == 800


async def test_the_thumbnail_is_downloaded_not_the_original(monkeypatch) -> None:
    """iiurlwidth makes Commons rasterise the file, which is how an SVG diagram
    becomes something WeasyPrint can lay into a PDF — and a 40 KB download
    instead of a multi-megabyte one."""
    [candidate] = await _search(monkeypatch, [_page()])

    assert candidate.image_url.endswith("800px-Neuron.png")
    # The thumbnail's type, not the original's, because that is what arrives.
    assert candidate.mime_type == "image/png"


async def test_the_attribution_is_stripped_of_markup(monkeypatch) -> None:
    """extmetadata values are HTML fragments and a credit line is not."""
    [candidate] = await _search(monkeypatch, [_page()])

    assert candidate.attribution == "Jane & Co"
    assert "<" not in candidate.attribution


async def test_a_restrictively_licensed_result_is_dropped(monkeypatch) -> None:
    page = _page()
    page["imageinfo"][0]["extmetadata"]["LicenseShortName"] = {"value": "CC BY-NC 4.0"}

    assert await _search(monkeypatch, [page]) == []


async def test_a_result_with_no_readable_licence_is_dropped(monkeypatch) -> None:
    page = _page()
    page["imageinfo"][0]["extmetadata"] = {}

    assert await _search(monkeypatch, [page]) == []


async def test_a_page_with_no_imageinfo_is_skipped(monkeypatch) -> None:
    assert await _search(monkeypatch, [{"title": "File:X.png"}]) == []


async def test_the_limit_is_respected(monkeypatch) -> None:
    assert len(await _search(monkeypatch, [_page() for _ in range(9)], limit=2)) == 2


async def test_an_empty_query_makes_no_request(monkeypatch) -> None:
    search = WikimediaImageSearch()

    async def _boom(params):
        raise AssertionError("should not have called the API")

    monkeypatch.setattr(search, "_get", _boom)

    assert await search.search("   ") == []


async def test_the_request_identifies_the_application(monkeypatch) -> None:
    """Wikimedia's policy requires a descriptive User-Agent. A generic client is
    answered with 403, not with results — so this is a test, not a nicety."""
    search = WikimediaImageSearch()
    captured: dict = {}

    async def _get(params):
        captured.update(params)
        return {"query": {"pages": []}}

    monkeypatch.setattr(search, "_get", _get)
    await search.search("a neuron")

    assert "ProfPlan" in search._user_agent
    assert captured["gsrnamespace"] == "6"  # the File: namespace
    assert "filetype:bitmap|drawing" in captured["gsrsearch"]
    assert captured["iiurlwidth"]


# --------------------------------------------------------------------------- #
# The real response shape, captured from commons.wikimedia.org. Every field
# below is there (or absent) because that is how the API actually answered a
# search for "labelled diagram of a neuron".
# --------------------------------------------------------------------------- #

_REAL_SVG_PAGE = {
    "title": "File:Complete neuron cell diagram en.svg",
    "imageinfo": [
        {
            "size": 237779,
            "width": 819,
            "height": 596,
            # Rendered to PNG, and carrying a tracking query string.
            "thumburl": (
                "https://upload.wikimedia.org/wikipedia/commons/thumb/a/a9/"
                "Complete_neuron_cell_diagram_en.svg/960px-"
                "Complete_neuron_cell_diagram_en.svg.png"
                "?utm_source=commons.wikimedia.org&utm_campaign=imageinfo"
            ),
            "thumbwidth": 800,
            "thumbheight": 582,
            # The ORIGINAL's type. There is no `thumbmime` field at all.
            "mime": "image/svg+xml",
            "descriptionurl": (
                "https://commons.wikimedia.org/wiki/"
                "File:Complete_neuron_cell_diagram_en.svg"
            ),
            "extmetadata": {"LicenseShortName": {"value": "Public domain"}},
        }
    ],
}


async def test_an_svg_diagram_survives_as_its_png_thumbnail(monkeypatch) -> None:
    """The regression this file exists for.

    Reading the type off `mime` would see image/svg+xml and drop the result —
    and the labelled diagrams, which are the whole point, are almost all SVG on
    Commons. The thumbnail is a PNG and its URL is what says so.
    """
    [candidate] = await _search(monkeypatch, [_REAL_SVG_PAGE])

    assert candidate.mime_type == "image/png"
    assert candidate.licence == "Public domain"
    assert candidate.title == "Complete neuron cell diagram en.svg"


async def test_a_tracking_query_string_does_not_confuse_the_type(monkeypatch) -> None:
    page = {**_REAL_SVG_PAGE}
    info = dict(page["imageinfo"][0])
    info["thumburl"] = info["thumburl"].replace(".png?", ".jpg?")
    page["imageinfo"] = [info]

    [candidate] = await _search(monkeypatch, [page])

    assert candidate.mime_type == "image/jpeg"


async def test_a_thumbnail_type_we_cannot_render_is_dropped(monkeypatch) -> None:
    page = {**_REAL_SVG_PAGE}
    info = dict(page["imageinfo"][0])
    info["thumburl"] = "https://upload.wikimedia.org/x/diagram.svg"
    page["imageinfo"] = [info]

    assert await _search(monkeypatch, [page]) == []
