"""Reusable field types for request schemas.

Two things every text field on the way in needs, and that are easy to forget
one at a time:

* trim it, so " Maths " and "Maths" are the same subject;
* turn a blank string into None, so an untouched optional field is absent
  rather than an empty fact. This matters most for the planning inputs: an
  empty string reaching the prompt reads to the model as "the audience is
  nothing", which is worse than not mentioning an audience at all.
"""

from typing import Annotated

from pydantic import BeforeValidator


def _clean_optional(value: object) -> object:
    if not isinstance(value, str):
        return value
    return value.strip() or None


def _clean_required(value: object) -> object:
    return value.strip() if isinstance(value, str) else value


#: Optional free text: trimmed, and blank becomes None.
OptionalText = Annotated[str | None, BeforeValidator(_clean_optional)]

#: Required text: trimmed before the length rules run, so a field of spaces
#: fails min_length instead of passing it.
RequiredText = Annotated[str, BeforeValidator(_clean_required)]
