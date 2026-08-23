"""Turning a generator's figure request into a stored, credited illustration.

The item generator writes ``{{figure: a labelled diagram of a neuron}}`` and
this is what makes that real. The order of operations is the whole design:

1. **Search**, cached, so forty items of one plan are not forty round trips.
2. **Download the rendered thumbnail**, not the original file.
3. **Validate the bytes**, because they came off the public internet and the
   declared type is a claim — the same rule an upload lives under.
4. **Store in MinIO**, so the handout does not depend on a remote host still
   serving that URL when it is printed.
5. **Record the credit**, because a licence that is not printed is a licence
   that is not honoured.

Best-effort throughout. A description nothing was found for, a host that timed
out, a file that turned out not to be an image: each one costs the item that one
illustration and nothing else. An item is content first and illustrated second,
and failing the whole generation because Commons was slow would be the wrong
trade.
"""

import logging
from uuid import UUID, uuid4

from app.core.config import get_settings
from app.modules.academic_items.domain.figures import (
    FigureCandidate,
    suffix_for,
    validate_image_bytes,
)
from app.modules.academic_items.domain.interfaces import ImageSearch
from app.modules.academic_items.infrastructure.figure_repository import (
    AcademicItemFigureRepository,
)
from app.modules.academic_items.infrastructure.models import AcademicItemFigure
from app.modules.generation.domain import figure_markup

logger = logging.getLogger("app.figures")


class FigureResolver:
    """Resolves the figure placeholders in one item's Markdown."""

    def __init__(
        self,
        *,
        search: ImageSearch,
        downloader,
        storage,
        repo: AcademicItemFigureRepository,
    ) -> None:
        self._search = search
        self._downloader = downloader
        self._storage = storage
        self._repo = repo
        self._settings = get_settings()

    async def resolve(
        self, *, markdown: str, item_id: UUID, user_id: UUID, subject_id: UUID | None
    ) -> str:
        """Replace every placeholder in ``markdown`` with a stored figure.

        Returns the rewritten Markdown. Placeholders that could not be resolved
        are removed, so nothing that reaches a student mentions a figure that is
        not there.
        """
        queries = figure_markup.extract_queries(markdown)
        if not queries or not self._settings.figures_enabled:
            # Still strip the placeholders: a disabled resolver must not leave
            # `{{figure: ...}}` in a handout.
            return figure_markup.replace(markdown, {})

        figures: list[AcademicItemFigure] = []
        rendered: dict[str, str] = {}
        for position, query in enumerate(queries):
            figure = await self._resolve_one(
                query=query,
                position=position,
                item_id=item_id,
                user_id=user_id,
                subject_id=subject_id,
            )
            if figure is None:
                continue
            figures.append(figure)
            rendered[query] = _render(figure)

        await self._repo.replace(item_id, figures)
        return figure_markup.replace(markdown, rendered)

    async def _resolve_one(
        self,
        *,
        query: str,
        position: int,
        item_id: UUID,
        user_id: UUID,
        subject_id: UUID | None,
    ) -> AcademicItemFigure | None:
        try:
            candidates = await self._search.search(
                query, limit=self._settings.figure_search_limit
            )
        except Exception as exc:  # noqa: BLE001 - best effort by design
            logger.warning("figure search failed for %r: %s", query, exc)
            return None

        for candidate in candidates:
            figure = await self._store(
                candidate=candidate,
                query=query,
                position=position,
                item_id=item_id,
                user_id=user_id,
                subject_id=subject_id,
            )
            if figure is not None:
                return figure
        logger.info("no usable figure for %r", query)
        return None

    async def _store(
        self,
        *,
        candidate: FigureCandidate,
        query: str,
        position: int,
        item_id: UUID,
        user_id: UUID,
        subject_id: UUID | None,
    ) -> AcademicItemFigure | None:
        """Download, validate and store one candidate; None if unusable."""
        try:
            data, content_type = await self._downloader.fetch(candidate.image_url)
            # The server's content type wins over the search result's: it is the
            # one that describes the bytes actually in hand.
            mime_type = content_type or candidate.mime_type
            validate_image_bytes(data, mime_type=mime_type)
        except Exception as exc:  # noqa: BLE001 - best effort by design
            logger.warning("figure %r rejected: %s", candidate.image_url, exc)
            return None

        # Same key shape as an uploaded document, under a figures prefix so the
        # two never collide in the bucket.
        scope = subject_id or user_id
        object_name = f"figures/{scope}/{uuid4().hex}{suffix_for(mime_type)}"
        self._storage.put_object(object_name, data, mime_type)

        return AcademicItemFigure(
            academic_item_id=item_id,
            user_id=user_id,
            position=position,
            query=query[:300],
            alt_text=(candidate.title or query)[:500],
            caption=_caption(candidate),
            source=candidate.source,
            source_url=candidate.source_url or None,
            figure_path=object_name,
            mime_type=mime_type,
            width=candidate.width or None,
            height=candidate.height or None,
            licence=candidate.licence[:200],
            licence_url=candidate.licence_url,
            attribution=(candidate.attribution or None) and candidate.attribution[:500],
        )


def _caption(candidate: FigureCandidate) -> str:
    """The visible caption: what it is, then who is owed the credit."""
    return f"{candidate.title} — {candidate.credit}"[:500]


def _render(figure: AcademicItemFigure) -> str:
    """The Markdown that replaces the placeholder: the image, and nothing else.

    The path is the object name rather than a URL, because whatever renders this
    resolves it — the PDF embeds the bytes, the API streams them.

    The caption is deliberately NOT written into the Markdown. It lives on the
    row, and both renderers read it from there: one source of truth for a credit
    line that is a licence obligation, and no way for the web view and the
    printed handout to disagree about who is owed it.
    """
    alt = figure.alt_text.replace("]", " ").replace("[", " ")
    return f"![{alt}]({figure.figure_path})"
