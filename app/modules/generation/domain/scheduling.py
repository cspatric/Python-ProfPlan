"""Give every planned item a real day.

The planner is asked for an ISO date per item and mostly gives one, but it is a
language model: it also writes "semana 3", a date outside the plan, or nothing
at all. Every one of those used to end up stored as free text, which is why the
app showed "Not scheduled" on every single item ever generated.

So the date is taken when it is usable and computed when it is not. Computing
it is not a guess dressed up as data: the module already owns a date range, and
spreading its items evenly across that range is exactly the information the
roadmap carries. What it must never do is leave the field empty, because a plan
whose activities have no day is not a plan.
"""

from datetime import date, timedelta


def parse_planned_date(raw: str | None, *, start: date, end: date) -> date | None:
    """Read an ISO day out of the planner's answer, if it gave a usable one.

    Anything that is not a plain date, or that falls outside the module's
    range, is rejected here and left to the caller's fallback. Accepting a date
    from outside the range would put an activity on a day the module does not
    cover, which reads as a bug to whoever opens the plan.
    """
    if not raw:
        return None
    try:
        parsed = date.fromisoformat(raw.strip()[:10])
    except ValueError:
        return None
    return parsed if start <= parsed <= end else None


def spread_over(start: date, end: date, count: int) -> list[date]:
    """`count` days spaced evenly across [start, end], both ends included.

    One item sits at the start of the module rather than in its middle: it is
    the first thing the module does.
    """
    if count <= 0:
        return []
    if count == 1 or end <= start:
        return [start] * count

    span = (end - start).days
    return [start + timedelta(days=round(span * i / (count - 1))) for i in range(count)]


def schedule_items(
    planned_dates: list[str | None], *, start: date, end: date
) -> list[date]:
    """The final day of each item in a module, in the order they were planned.

    The planner's own dates win where they are usable; the rest fall onto the
    evenly spread slots. The result is sorted, so an item the planner placed
    late never appears before one it placed early.
    """
    fallback = spread_over(start, end, len(planned_dates))
    resolved = [
        parse_planned_date(raw, start=start, end=end) or fallback[index]
        for index, raw in enumerate(planned_dates)
    ]
    return sorted(resolved)
