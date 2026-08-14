"""Teaching plan domain types."""

from enum import StrEnum


class PlanLevel(StrEnum):
    """How demanding the plan should be.

    This is the single most load-bearing of the planning inputs: the same
    subject, over the same period, produces a different roadmap for a class
    meeting it for the first time and for one that already has the basics.
    """

    INTRODUCTORY = "introductory"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
