"""Shared payload for display / random_display pattern windows."""
from __future__ import annotations

import random

from django.http import Http404

from bells.functions import rounds_from_patterns
from bells.legs import build_leg
from bells.models import Pattern


def menu_patterns(number: int) -> dict:
    from_patterns = Pattern.objects.filter(number=number, enable=True).order_by("order")
    to_patterns = Pattern.objects.filter(number=number, enable=True).order_by("order", "name")
    numbers = set(
        Pattern.objects.filter(enable=True)
        .order_by("number")
        .values_list("number", flat=True)
    )
    return {
        "from_patterns": from_patterns,
        "to_patterns": to_patterns,
        "numbers": sorted(numbers),
        "count": to_patterns.count(),
        "number": int(number),
    }


def known_patterns_for(number: int) -> set[str]:
    return set(
        Pattern.objects.filter(number=number, enable=True).values_list("pattern", flat=True)
    )


def compose_directed_legs(
        pairs: list[tuple],
        number: int,
        *,
        from_pattern=None,
        to_pattern=None,
    ) -> dict:
    """
    pairs: [(from_pat, to_pat), ...]  e.g. there-and-back or seed→A, A→B
    """
    legs = [build_leg(a, b) for a, b in pairs]

    path_patterns = []
    for leg in legs:
        if leg.lines:
            path_patterns.append(leg.lines[0]["pattern"])
            path_patterns.append(leg.lines[-1]["pattern"])

    rounds = rounds_from_patterns(*path_patterns) if path_patterns else ""
    known = known_patterns_for(number)

    ctx = menu_patterns(number)
    ctx.update(
        {
            "legs": legs,
            "result": legs[0].lines if legs else [],
            "revresult": legs[1].lines if len(legs) > 1 else [],
            "result_block": [leg.lines for leg in legs],
            "rounds": rounds,
            "known_patterns": known,
            "forward_and_back": True,
            "from_pattern": from_pattern or pairs[0][0],
            "to_pattern": to_pattern or pairs[0][1],
        }
    )
    return ctx

def pick_random_leg_patterns(number: int | None, seed_name: str = "Rounds"):
    """Return (number, seed, random_a, random_b) for seed→A and A→B."""
    base = Pattern.objects.filter(enable=True)

    if number is not None:
        patterns = list(base.filter(number=number))
        if len(patterns) < 2:
            raise Http404(
                f"Need at least 2 enabled patterns on {number} bells for random display"
            )
    else:
        from django.db.models import Count
        candidates = list(
            base.values("number")
            .annotate(n=Count("id"))
            .filter(n__gte=2)
            .values_list("number", flat=True)
        )
        if not candidates:
            raise Http404("Need at least 2 enabled patterns for random display")
        number = random.choice(candidates)
        patterns = list(base.filter(number=number))

    try:
        seed = Pattern.objects.get(
            name__iexact=seed_name, number=number, enable=True
        )
    except Pattern.DoesNotExist:
        seed = patterns[0]

    others = [p for p in patterns if p.pk != seed.pk]
    if not others:
        raise Http404("Need at least 2 enabled patterns for random display")
    if len(others) == 1:
        random_a = random_b = others[0]
    else:
        random_a, random_b = random.sample(others, 2)

    return number, seed, random_a, random_b
