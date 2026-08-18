"""The language a generated plan is written in.

Chosen by the teacher rather than inferred. Inferring works right up until it
does not: a one-line request ("plano de física") gives the model almost nothing
to read the language from, and — the real problem — the *items* are generated
later, in a worker, from a sub-prompt the planner itself wrote. Two items of the
same plan could come back in two different languages, and the teacher would have
no way to ask for otherwise.

Storing the choice on the run is what makes every call downstream agree: the
planner, the repair, the judge and one task per item all read the same value.
"""

from enum import StrEnum


class PlanLanguage(StrEnum):
    """The languages the product is offered in."""

    EN = "en"
    ES = "es"
    PT = "pt"


# Said twice, in English and in the target language. A model steered in the
# language it is meant to answer in holds that language better across a long
# answer than one told about it in English only.
_INSTRUCTION: dict[PlanLanguage, str] = {
    PlanLanguage.EN: "Write your entire answer in English.",
    PlanLanguage.ES: (
        "Write your entire answer in Spanish. Escribe toda tu respuesta en español."
    ),
    PlanLanguage.PT: (
        "Write your entire answer in Brazilian Portuguese. "
        "Escreva toda a sua resposta em português do Brasil."
    ),
}

# The old behaviour, kept for runs created before the choice existed. Those have
# no language stored, and rewriting history to guess one would be worse than
# doing what they already did.
_INFER = "Respond in the same language as the teacher's input."


def language_rule(language: PlanLanguage | None) -> str:
    """The sentence to append to a system prompt."""
    return _INSTRUCTION[language] if language else _INFER


def parse_language(value: object) -> PlanLanguage | None:
    """Read a stored value back, tolerating anything that is not a language.

    The run's `input` is JSONB written by an older version of this code, so it
    may hold no language at all — or, one day, one that has been removed. Either
    way the answer is "infer", never a crash halfway through a plan.
    """
    try:
        return PlanLanguage(value)
    except ValueError:
        return None
