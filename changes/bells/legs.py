"""Directed display legs: one from→to window. Reverse = call build_leg twice."""
from __future__ import annotations

from dataclasses import dataclass

from django.core.paginator import Paginator

from bells.functions import db_process, rounds_from_patterns
from bells.models import Pattern


@dataclass
class Leg:
    from_pattern: Pattern
    to_pattern: Pattern
    lines: list  # demucked row dicts for one column


def build_leg(from_pat: Pattern, to_pat: Pattern, max_lines: int = 20) -> Leg:
    """
    Single directed leg. Does not compute the reverse.
    If from_pat is named Rounds, start from prescribed rounds for to_pat's
    digit set (e.g. Westminster chimes → 2347, not DB 1234).

    """
    # Lazy import avoids circular import with views during refactor
    from bells.views import demuck_result, demuck_result_list

    from_row: str = from_pat.pattern
    to_row: str = to_pat.pattern

    if (from_pat.name or "").lower() == "rounds":
        from_row = rounds_from_patterns(to_row)
    if (to_pat.name or "").lower() == "rounds":
        to_row = rounds_from_patterns(from_row)

    _calls, result, _swappair = db_process(from_row, to_row)
    rows = demuck_result_list(result)
    page = Paginator(rows, max_lines).get_page(1).object_list
    lines = demuck_result(page)
    return Leg(from_pattern=from_pat, to_pattern=to_pat, lines=lines)
