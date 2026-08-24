"""Image search against Wikimedia Commons.

Commons is the right first source for teaching material for one reason that has
nothing to do with it being free: the diagrams on it were drawn to be read. A
labelled neuron, the Krebs cycle, a phase diagram — these exist there because
someone made them for a textbook or an article, and they carry a licence and an
author that can be printed next to them.

Three details of this API are worth knowing, because each one is a bug if you
miss it.

**Ask for a thumbnail, not the file.** ``iiurlwidth`` makes Commons render the
file at a bounded width and hand back a PNG or JPEG — including for SVG
originals, which is how a vector diagram becomes something WeasyPrint can lay
into a PDF without needing SVG support. It also means the download is tens of
kilobytes instead of the multi-megabyte original.

**Send a real User-Agent.** Wikimedia's policy requires a descriptive agent
identifying the application, and generic clients are refused. This is not
politeness, it is a 403.

**Read the licence off ``extmetadata``, and believe nothing else.** The field is
HTML, so it is stripped; a file whose licence cannot be read is dropped by
``is_usable`` rather than assumed to be free.
"""

import html
import re
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import urlparse

import httpx

from app.core.config import get_settings
from app.modules.academic_items.domain.figures import (
    FigureCandidate,
    FigureSource,
    is_usable,
)
from app.shared.decorators.retry import external_call

#: Commons' File: namespace. Searching without this returns article pages.
_FILE_NAMESPACE = 6

_TAG = re.compile(r"<[^>]+>")

#: The rendered thumbnail's type, read off its own URL.
#:
#: The API has no field for it: ``mime`` describes the *original*, which for the
#: labelled diagrams that matter here is ``image/svg+xml``. Trusting that would
#: throw away exactly the results worth having, because Commons renders SVG
#: thumbnails to PNG — the extension on the thumbnail path is the only honest
#: answer, and the query string it carries has to be stripped before reading it.
_THUMB_MIME_BY_SUFFIX = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}


def _thumb_mime(thumb_url: str) -> str:
    suffix = PurePosixPath(urlparse(thumb_url).path).suffix.lower()
    return _THUMB_MIME_BY_SUFFIX.get(suffix, "")


def _plain(value: str | None) -> str | None:
    """extmetadata values are HTML fragments; a credit line is not."""
    if not value:
        return None
    text = html.unescape(_TAG.sub(" ", value))
    collapsed = " ".join(text.split())
    return collapsed or None


def _meta(extmetadata: dict[str, Any], key: str) -> str | None:
    entry = extmetadata.get(key)
    if isinstance(entry, dict):
        return _plain(entry.get("value"))
    return None


class WikimediaImageSearch:
    """Finds freely licensed images on Wikimedia Commons."""

    def __init__(self) -> None:
        settings = get_settings()
        self._endpoint = settings.commons_api_url
        self._timeout = settings.figure_search_timeout_seconds
        self._thumb_width = settings.figure_thumbnail_width
        self._user_agent = settings.figure_user_agent

    async def search(self, query: str, *, limit: int = 5) -> list[FigureCandidate]:
        """Usable candidates for this description, best match first."""
        if not query.strip():
            return []
        payload = await self._get(
            {
                "action": "query",
                "format": "json",
                "formatversion": "2",
                "generator": "search",
                # `filetype:bitmap|drawing` keeps out audio, video and PDFs,
                # which the File: namespace is also full of.
                "gsrsearch": f"{query} filetype:bitmap|drawing",
                "gsrnamespace": str(_FILE_NAMESPACE),
                "gsrlimit": str(max(1, min(limit * 3, 30))),
                "prop": "imageinfo",
                "iiprop": "url|mime|size|extmetadata",
                "iiurlwidth": str(self._thumb_width),
            }
        )
        pages = (payload.get("query") or {}).get("pages") or []
        candidates = [c for c in map(self._to_candidate, pages) if c and is_usable(c)]
        return candidates[:limit]

    @external_call()
    async def _get(self, params: dict[str, str]) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.get(
                self._endpoint,
                params=params,
                headers={"User-Agent": self._user_agent},
            )
            response.raise_for_status()
            return response.json()

    def _to_candidate(self, page: dict[str, Any]) -> FigureCandidate | None:
        info_list = page.get("imageinfo") or []
        if not info_list:
            return None
        info = info_list[0]
        # The rendered thumbnail, never the original: bounded size, and a
        # raster even when the source is a vector.
        image_url = info.get("thumburl")
        if not image_url:
            return None
        extmetadata = info.get("extmetadata") or {}
        return FigureCandidate(
            source=FigureSource.WIKIMEDIA,
            source_url=info.get("descriptionurl") or "",
            image_url=image_url,
            title=str(page.get("title") or "").removeprefix("File:"),
            # The thumbnail's type, which is what gets downloaded — not the
            # original's, which for an SVG would be image/svg+xml.
            mime_type=_thumb_mime(image_url),
            width=int(info.get("thumbwidth") or 0),
            height=int(info.get("thumbheight") or 0),
            licence=_meta(extmetadata, "LicenseShortName") or "",
            licence_url=_meta(extmetadata, "LicenseUrl"),
            attribution=_meta(extmetadata, "Artist") or _meta(extmetadata, "Credit"),
        )


class ImageDownloader:
    """Fetches the bytes of a candidate, bounded and with the same agent."""

    def __init__(self) -> None:
        settings = get_settings()
        self._timeout = settings.figure_search_timeout_seconds
        self._user_agent = settings.figure_user_agent

    @external_call()
    async def fetch(self, url: str) -> tuple[bytes, str]:
        """The image bytes and the content type the server actually sent."""
        async with httpx.AsyncClient(
            timeout=self._timeout, follow_redirects=True
        ) as client:
            response = await client.get(url, headers={"User-Agent": self._user_agent})
            response.raise_for_status()
            content_type = (
                response.headers.get("content-type", "").split(";")[0].strip().lower()
            )
            return response.content, content_type
