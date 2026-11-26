"""Convert a quantity to another unit of the same kind, by the conversion factors of the model's units.

    from imaging_metadata_converter.units import normalise

    normalise(1.5, 'mm', 'µm')        # 1500.0
    normalise(0.5, 'rad', 'deg')      # 28.64788975654116

A unit is known by its symbol in the model or any of its aliases ("um", "micron", "degrees"). The factors are
exact numbers, so a conversion rounds once: 1.5 mm is 1500 µm, not 1500.0000000000002.
"""

import json
import unicodedata
from fractions import Fraction
from functools import lru_cache

from .model_files import DEFAULT_MODEL_INDEX_FILE


def _spelling_key(unit):
    # µ and μ (micro sign, Greek mu) and Å and Å (Angstrom sign) are the same unit; case is not (Pm, pm)
    return unicodedata.normalize('NFKC', str(unit).strip())


@lru_cache(maxsize=None)
def _units():
    """{spelling: (kind, factor)} for every symbol and alias of a unit with a conversion factor."""
    with open(DEFAULT_MODEL_INDEX_FILE, encoding='utf-8') as file:
        index = json.load(file)
    units = {}
    for kind, factors in index['unit_factors'].items():
        spellings = dict(index['spellings'].get(kind, {}), **{unit: unit for unit in factors})
        units.update({_spelling_key(spelling): (kind, Fraction(factors[unit]))
                      for spelling, unit in spellings.items() if unit in factors})
    return units


def normalise(value, unit, target):
    """`value` in `unit`, in the unit `target` of the same kind; None for a unit not known, or of another kind, or a
    value that is not a number."""
    units = _units()
    source, goal = units.get(_spelling_key(unit)), units.get(_spelling_key(target))
    if source is None or goal is None or source[0] != goal[0]:
        return None
    try:
        quantity = Fraction(str(value))
    except (TypeError, ValueError):
        return None
    return float(quantity * source[1] / goal[1])
