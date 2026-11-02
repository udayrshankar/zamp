"""Reads Nemotron Parse output, which looks like this:

    <x_0.08><y_0.15>**Invoice No:**INV-2041<x_0.33><y_0.16><class_Text>

Each block has a text body between two corners, in coordinates from 0 to 1.
Table bodies are LaTeX.
"""

import re
from dataclasses import dataclass

from app.domain.models import BBox, TextLine

TABLE_CLASS = "Table"
CELL_SEPARATOR = " | "

_BLOCK = re.compile(
    r"<x_([\d.]+)><y_([\d.]+)>(.*?)<x_([\d.]+)><y_([\d.]+)><class_([^>]+)>",
    re.DOTALL,
)
_BOLD = re.compile(r"\*\*(.+?)\*\*")
_TABULAR_START = re.compile(r"\\begin\{tabular\}\{[^{}]*\}")
_TABULAR_END = re.compile(r"\\end\{tabular\}")
_RULE = re.compile(r"\\(?:hline|toprule|midrule|bottomrule)\b")
# \thead{Qty} and \multicolumn{2}{c}{Total} both keep only their last argument.
# The lookahead skips a command whose arguments still contain a nested command.
_COMMAND = re.compile(r"\\[a-zA-Z]+\*?((?:\{[^{}]*\})+)(?!\{)")
_ROW_BREAK = re.compile(r"\\\\")
_CELL_BREAK = re.compile(r"(?<!\\)&")
_ESCAPED = re.compile(r"\\([&%$_#{}])")


@dataclass(frozen=True, slots=True)
class ParsedBlock:
    text: str
    bbox: BBox
    kind: str


def parse_blocks(content: str) -> list[ParsedBlock]:
    return [
        ParsedBlock(text=body, bbox=_ordered(x0, y0, x1, y1), kind=kind)
        for x0, y0, body, x1, y1, kind in _BLOCK.findall(content)
    ]


def to_lines(block: ParsedBlock, width: int, height: int) -> list[TextLine]:
    """Splits a block into lines, with bboxes in image pixels."""
    rows = _table_rows(block.text) if block.kind == TABLE_CLASS else _text_rows(block.text)
    if not rows:
        return []

    x0, y0, x1, y1 = block.bbox
    # The model only locates whole blocks, so lines share the height evenly.
    row_height = (y1 - y0) / len(rows)
    return [
        TextLine(
            text=row,
            bbox=(
                x0 * width,
                (y0 + index * row_height) * height,
                x1 * width,
                (y0 + (index + 1) * row_height) * height,
            ),
        )
        for index, row in enumerate(rows)
    ]


def _ordered(x0: str, y0: str, x1: str, y1: str) -> BBox:
    xs = sorted((float(x0), float(x1)))
    ys = sorted((float(y0), float(y1)))
    return xs[0], ys[0], xs[1], ys[1]


def _text_rows(text: str) -> list[str]:
    # The model drops the space after bold text: **Subtotal**1,000.00
    spaced = _BOLD.sub(r" \1 ", text)
    rows = (" ".join(row.split()) for row in spaced.splitlines())
    return [row for row in rows if row]


def _table_rows(latex: str) -> list[str]:
    if not _TABULAR_START.search(latex):
        return _text_rows(latex)

    body = _TABULAR_END.sub("", _TABULAR_START.sub("", latex))
    body = _RULE.sub("", _unwrap_commands(body))

    rows = []
    for row in _ROW_BREAK.split(body):
        cells = [_clean_cell(cell) for cell in _CELL_BREAK.split(row)]
        if any(cells):
            rows.append(CELL_SEPARATOR.join(cells))
    return rows


def _unwrap_commands(latex: str) -> str:
    # Commands nest, so each pass unwraps the innermost and exposes the next.
    replacements = 1
    while replacements:
        latex, replacements = _COMMAND.subn(_last_argument, latex)
    return latex


def _last_argument(match: re.Match[str]) -> str:
    argument = match.group(1).rsplit("{", 1)[-1].rstrip("}")
    # A line break inside a cell must not read as the end of the row.
    return argument.replace("\\\\", " ")


def _clean_cell(cell: str) -> str:
    return " ".join(_ESCAPED.sub(r"\1", cell).split())
