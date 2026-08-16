"""Which class of model a call deserves.

One plan is not one kind of work. Deciding the roadmap is one call that shapes
everything downstream: a bad roadmap makes eight good activities about the
wrong things. Writing one activity is bulk work against a roadmap that is
already decided, and it is where the tokens are, seven or eight calls with long
outputs.

Paying frontier prices for the bulk to protect the one decision is the wrong
way round, so the two are separated and each gets its own chain of providers.
"""

from enum import StrEnum


class Tier(StrEnum):
    """The class of model to answer with."""

    #: The call that decides something: the roadmap, its repair, the judge.
    STANDARD = "standard"
    #: Bulk drafting against a decision already made: one activity.
    FAST = "fast"
