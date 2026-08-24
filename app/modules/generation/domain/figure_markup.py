"""The generator's figure placeholder, and how it is filled in.

The item generator writes Markdown, and a model that is asked for an image URL
invents one. So it never emits a URL: it emits a *request* for a figure, in the
form ``{{figure: a labelled diagram of a neuron}}`` on a line of its own, and a
separate step resolves that description into a real, licensed image.

That split is the whole point. Hallucination stays out of the asset layer, the
resolution is cacheable and testable on its own, and a figure that cannot be
found degrades to nothing instead of to a broken image.

The syntax is deliberately not Markdown's own ``![]()``: if a placeholder ever
leaks unresolved into a PDF it must read as an obvious placeholder rather than
as a broken image.
"""

import re

#: ``{{figure: <description>}}`` — one per line, description free text.
PLACEHOLDER = re.compile(r"\{\{\s*figure\s*:\s*(?P<query>[^}]{3,300}?)\s*\}\}", re.I)

#: A single item asking for more than this is a model that misunderstood the
#: instruction, not a page that needs eight diagrams.
MAX_FIGURES_PER_ITEM = 3


def extract_queries(markdown: str) -> list[str]:
    """The figure descriptions requested in this item, in order, deduplicated.

    Deduplicated because the same description twice is one image used twice,
    not two lookups and two stored copies.
    """
    seen: dict[str, None] = {}
    for match in PLACEHOLDER.finditer(markdown):
        query = " ".join(match.group("query").split())
        if query:
            seen.setdefault(query, None)
    return list(seen)[:MAX_FIGURES_PER_ITEM]


def replace(markdown: str, rendered: dict[str, str]) -> str:
    """Swap each placeholder for its rendered Markdown, dropping the rest.

    A description with no entry in ``rendered`` is one nothing was found for.
    It is removed rather than left behind: an item with one fewer figure is
    fine, an item showing ``{{figure: ...}}`` to a student is not.
    """

    def _swap(match: re.Match[str]) -> str:
        query = " ".join(match.group("query").split())
        return rendered.get(query, "")

    cleaned = PLACEHOLDER.sub(_swap, markdown)
    # Removing a placeholder that sat on its own line leaves a triple newline.
    return re.sub(r"\n{3,}", "\n\n", cleaned).strip()
