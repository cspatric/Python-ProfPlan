"""Academic item domain interfaces (ports)."""

from typing import Protocol

from app.modules.academic_items.domain.figures import FigureCandidate


class ImageSearch(Protocol):
    """Finds freely reusable images for a plain-language description.

    A port rather than a direct call so the source can be swapped or layered:
    today Wikimedia Commons, wrapped in a cache; tomorrow the figures already
    embedded in the teacher's own documents, with Commons as the fallback.
    """

    async def search(self, query: str, *, limit: int = 5) -> list[FigureCandidate]:
        """Candidates for this description, best first, already filtered.

        Returns an empty list when nothing usable was found. That is a normal
        outcome, not a failure: not every description has a licensed diagram
        behind it.
        """
        ...
