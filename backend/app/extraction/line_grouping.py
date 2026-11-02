from collections.abc import Iterable

from app.domain.models import BBox, TextLine


def group_into_lines(fragments: Iterable[TextLine]) -> list[TextLine]:
    """Merges positioned fragments into top-to-bottom, left-to-right lines.

    Invoices are tables, so keeping a row together is what keeps "Total" beside
    its amount. Both extraction paths use this, which gives them the same layout.
    """
    rows: list[list[TextLine]] = []
    for fragment in sorted(fragments, key=_centre_y):
        if rows and _same_row(fragment, rows[-1]):
            rows[-1].append(fragment)
        else:
            rows.append([fragment])
    return [_merge(row) for row in rows]


def _centre_y(fragment: TextLine) -> float:
    return (fragment.bbox[1] + fragment.bbox[3]) / 2


def _height(fragment: TextLine) -> float:
    return fragment.bbox[3] - fragment.bbox[1]


def _same_row(fragment: TextLine, row: list[TextLine]) -> bool:
    row_centre = sum(_centre_y(item) for item in row) / len(row)
    row_height = sum(_height(item) for item in row) / len(row)
    return abs(_centre_y(fragment) - row_centre) <= min(_height(fragment), row_height) / 2


def _merge(row: list[TextLine]) -> TextLine:
    ordered = sorted(row, key=lambda item: item.bbox[0])
    return TextLine(
        text=" ".join(item.text for item in ordered),
        bbox=_union(item.bbox for item in ordered),
        confidence=weighted_confidence(ordered),
    )


def _union(boxes: Iterable[BBox]) -> BBox:
    x0, y0, x1, y1 = zip(*boxes)
    return min(x0), min(y0), max(x1), max(y1)


def weighted_confidence(lines: list[TextLine]) -> float | None:
    """Mean confidence weighted by length, so one misread stamp can't dominate a page."""
    scored = [line for line in lines if line.confidence is not None]
    total_chars = sum(len(line.text) for line in scored)
    if not total_chars:
        return None
    return sum(line.confidence * len(line.text) for line in scored) / total_chars
