"""Directed display legs: one from→to window. Reverse = call build_leg twice."""
from __future__ import annotations

from dataclasses import dataclass

from django.core.paginator import Paginator

from bells.functions import db_process
from bells.models import Pattern


@dataclass
class Leg:
    from_pattern: Pattern
    to_pattern: Pattern
    lines: list  # demucked row dicts for one column


def build_leg(from_pat: Pattern, to_pat: Pattern, max_lines: int = 20) -> Leg:
    """
    Single directed leg. Does not compute the reverse.
    """
    # Lazy import avoids circular import with views during refactor
    from bells.views import demuck_result, demuck_result_list

    _calls, result, _swappair = db_process(from_pat.pattern, to_pat.pattern)
    rows = demuck_result_list(result)
    page = Paginator(rows, max_lines).get_page(1).object_list
    lines = demuck_result(page)
    return Leg(from_pattern=from_pat, to_pattern=to_pat, lines=lines)
