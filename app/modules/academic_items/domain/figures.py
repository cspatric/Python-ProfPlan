"""What a figure is, and which ones this system is allowed to reuse.

A figure attached to an academic item is not decoration: a student reads facts
off it. So two things are enforced here rather than left to whoever calls the
search.

**The licence must permit reuse, and it must be named.** Wikimedia Commons is
free-licensed by policy, but "free" spans CC0 through share-alike, and an
aggregator pointed at other sources will happily return non-commercial or
no-derivatives material. Anything whose licence cannot be read off the metadata
is rejected — an unknown licence is not a permissive one.

**The bytes must be an image.** The file comes off the public internet, so it
gets the same treatment an upload gets: the declared type is a claim and the
magic bytes are the check.
"""

import re
from dataclasses import dataclass
from enum import StrEnum

from app.modules.academic_items.domain.exceptions import UnusableFigureError

#: Rasterised thumbnails are what the search asks for, so these two are what
#: actually arrives. SVG is deliberately absent: WeasyPrint's SVG support is
#: partial, and a figure that renders on screen but not in the teacher's PDF is
#: worse than one that was never offered.
ALLOWED_MIME_TYPES = {"image/png", "image/jpeg"}

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_JPEG_MAGIC = b"\xff\xd8\xff"

#: Licence names (as the source reports them) that permit reuse in teaching
#: material, including commercially, with attribution.
_ALLOWED_LICENCE_PREFIXES = (
    "cc0",
    "cc by",
    "cc-by",
    "public domain",
    "pd",
    "no restrictions",
)

#: Rejected outright wherever they appear in the licence name. NC forbids the
#: commercial use a paid product is, and ND forbids the cropping and scaling
#: that laying a figure into a handout is.
_FORBIDDEN_LICENCE_TOKENS = ("nc", "nd", "noncommercial", "noderiv")

#: Below this a "diagram" is a thumbnail of a thumbnail: an icon, a flag, a
#: signature scan. Above the ceiling it is a scan nobody needs at full size.
MIN_PIXELS = 200
MAX_BYTES = 5 * 1024 * 1024


class FigureSource(StrEnum):
    """Where a figure came from, kept on the row for the credit line."""

    WIKIMEDIA = "wikimedia"


@dataclass(frozen=True, slots=True)
class FigureCandidate:
    """One search result, before anything has been downloaded or stored."""

    source: FigureSource
    #: The human-facing page for this file, which is what attribution links to.
    source_url: str
    #: The bytes to fetch: a bounded, rasterised rendering, not the original.
    image_url: str
    title: str
    mime_type: str
    width: int
    height: int
    licence: str
    licence_url: str | None
    #: The author string as the source reports it, already stripped of markup.
    attribution: str | None

    @property
    def credit(self) -> str:
        """The one-line credit that has to appear next to the image."""
        who = self.attribution or "Wikimedia Commons"
        return f"{who} — {self.licence}"


def is_licence_allowed(licence: str | None) -> bool:
    """Whether this licence name permits reuse in generated material."""
    if not licence:
        return False  # unknown is not permissive
    name = licence.strip().lower()
    tokens = set(re.split(r"[^a-z0-9]+", name))
    if tokens & set(_FORBIDDEN_LICENCE_TOKENS):
        return False
    return any(name.startswith(prefix) for prefix in _ALLOWED_LICENCE_PREFIXES)


def is_usable(candidate: FigureCandidate) -> bool:
    """Whether a search result is worth downloading at all."""
    return (
        candidate.mime_type in ALLOWED_MIME_TYPES
        and is_licence_allowed(candidate.licence)
        and min(candidate.width, candidate.height) >= MIN_PIXELS
        and bool(candidate.image_url)
    )


def validate_image_bytes(data: bytes, *, mime_type: str) -> None:
    """Reject anything whose real signature is not the image it claims to be.

    Same reasoning as ``validate_document_upload``: the declared type is what
    a remote server said, and the magic bytes are what it actually sent.
    """
    if not data:
        raise UnusableFigureError("empty image body")
    if len(data) > MAX_BYTES:
        raise UnusableFigureError(f"image is larger than {MAX_BYTES} bytes")
    if mime_type not in ALLOWED_MIME_TYPES:
        raise UnusableFigureError(f"unsupported image type {mime_type!r}")
    magic = _PNG_MAGIC if mime_type == "image/png" else _JPEG_MAGIC
    if not data.startswith(magic):
        raise UnusableFigureError(
            f"content does not match the declared type {mime_type!r}"
        )


def suffix_for(mime_type: str) -> str:
    """The file extension to store this image under."""
    return ".png" if mime_type == "image/png" else ".jpg"
