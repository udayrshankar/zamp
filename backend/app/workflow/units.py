"""Units of measure, so a line billed in kg can be checked against a PO line in
tonnes.

Every known unit belongs to a dimension (mass, volume, length or count) and has
a size in that dimension's base unit. Units of one dimension convert into each
other. Anything else, such as kg against litres, or a box against a carton, is
left for a person: a wrong conversion would make a line look over or under the
PO by a factor of a thousand.
"""

import re
from dataclasses import dataclass

_PLACEHOLDERS = {"", "null", "none", "n/a", "na", "-", "unknown"}


@dataclass(frozen=True, slots=True)
class Unit:
    label: str
    dimension: str
    # How many of the dimension's base unit one of this unit holds.
    size: float


_KNOWN: dict[str, Unit] = {}


def _add(dimension: str, label: str, size: float, *aliases: str) -> None:
    unit = Unit(label, dimension, size)
    for alias in (label, *aliases):
        _KNOWN[alias] = unit


# Mass, in kg. Indian invoices and POs use "ton" and "MT" for the metric tonne.
_add("mass", "kg", 1, "kgs", "kilo", "kilos", "kilogram", "kilograms", "kilogramme")
_add("mass", "g", 0.001, "gm", "gms", "gram", "grams", "gramme", "grammes")
_add("mass", "mg", 0.000001, "milligram", "milligrams")
_add("mass", "quintal", 100, "quintals", "qtl", "qtls")
_add(
    "mass", "tonne", 1000,
    "tonnes", "t", "ton", "tons", "mt", "mts", "metric ton", "metric tons", "metric tonne", "metric tonnes",
)
_add("mass", "lb", 0.45359237, "lbs", "pound", "pounds")
# Volume, in litres.
_add("volume", "litre", 1, "l", "ltr", "ltrs", "lit", "litres", "liter", "liters")
_add("volume", "ml", 0.001, "millilitre", "millilitres", "milliliter", "milliliters")
_add("volume", "kl", 1000, "kilolitre", "kilolitres", "kiloliter", "kiloliters")
# Length, in metres.
_add("length", "metre", 1, "m", "mtr", "mtrs", "metres", "meter", "meters", "rmt", "running metre")
_add("length", "cm", 0.01, "centimetre", "centimetres", "centimeter", "centimeters")
_add("length", "mm", 0.001, "millimetre", "millimetres", "millimeter", "millimeters")
_add("length", "km", 1000, "kilometre", "kilometres", "kilometer", "kilometers")
_add("length", "ft", 0.3048, "feet", "foot", "rft")
# Count, in pieces.
_add("count", "nos", 1, "no", "number", "numbers", "pcs", "pc", "piece", "pieces", "each", "ea", "unit", "units")
_add("count", "pair", 2, "pairs", "pr", "prs")
_add("count", "dozen", 12, "dozens", "doz", "dz")

# Words that can name a product as well as a unit ("foot pump"), so they still
# count when descriptions are compared.
_ALSO_PRODUCT_WORDS = {"foot", "feet", "pound", "pounds", "number", "numbers"}
# Single words that name a unit, so describing an item never depends on them.
UNIT_WORDS = frozenset(
    word
    for alias in _KNOWN
    for word in alias.split()
    if word.isalpha() and word not in _ALSO_PRODUCT_WORDS
)

_ALIASES = "|".join(sorted((re.escape(alias) for alias in _KNOWN), key=len, reverse=True))
# Units named inside a description: "(in kg)", "(per tonne)", "per kg", "in metres".
_IN_TEXT = re.compile(
    rf"\(\s*(?:in\s+|per\s+)?({_ALIASES})\s*\)|\b(?:per|in)\s+({_ALIASES})\b",
    re.IGNORECASE,
)


def _clean(text: str) -> str:
    text = " ".join(text.casefold().replace(".", " ").split())
    return text.removeprefix("per ").removeprefix("in ")


def parse(text: str | None) -> Unit | None:
    """The unit a label names. A label it doesn't know, such as "box", is still a
    unit, but only the same label matches it."""
    if text is None:
        return None
    cleaned = _clean(text)
    if cleaned in _PLACEHOLDERS:
        return None
    known = _KNOWN.get(cleaned) or _KNOWN.get(cleaned.removesuffix("s"))
    if known:
        return known
    label = cleaned.removesuffix("es") if cleaned.endswith("xes") else cleaned.removesuffix("s")
    return Unit(label=label, dimension=f"other:{label}", size=1)


def in_text(text: str) -> Unit | None:
    """A unit a description names for its quantity, like "Steel rod (in kg)"."""
    match = _IN_TEXT.search(text)
    return parse(match.group(1) or match.group(2)) if match else None


def ratio(source: Unit, target: Unit) -> float | None:
    """How many target units one source unit makes, or None if they don't convert."""
    if source.dimension != target.dimension:
        return None
    return source.size / target.size
