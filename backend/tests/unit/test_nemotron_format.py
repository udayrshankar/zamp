import pytest

from app.infrastructure.nemotron_format import ParsedBlock, parse_blocks, to_lines

# Captured from the real API on tests/fixtures/scanned.pdf, shortened.
REAL_OUTPUT = (
    "<x_0.6689><y_0.0664>**TAX INVOICE**<x_0.8438><y_0.0852><class_Title>\n\n"
    "<x_0.0811><y_0.1539>**Invoice No:**INV-2041<x_0.3301><y_0.1688><class_Text>\n\n"
    "<x_0.0791><y_0.282>\\begin{tabular}{cccc}\n"
    "\\thead{Description} & \\thead{Qty} & \\thead{Unit Price} & \\thead{Amount}\\\\\n"
    "Ergonomic office chair & 2 & 250.00 & 500.00\\\\\n"
    "\\end{tabular}<x_0.916><y_0.382><class_Table>\n\n"
    "<x_0.6523><y_0.4734>**Total Due**1,180.00<x_0.8809><y_0.4898><class_Text>"
)


def table(*rows: str) -> ParsedBlock:
    body = "\\begin{tabular}{ccc}\n" + "\n".join(rows) + "\n\\end{tabular}"
    return ParsedBlock(text=body, bbox=(0, 0, 1, 1), kind="Table")


def text_of(block: ParsedBlock) -> list[str]:
    return [line.text for line in to_lines(block, 100, 100)]


def test_reads_every_block_of_a_real_response():
    blocks = parse_blocks(REAL_OUTPUT)

    assert [block.kind for block in blocks] == ["Title", "Text", "Table", "Text"]
    assert blocks[0].bbox == (0.6689, 0.0664, 0.8438, 0.0852)


def test_real_response_becomes_readable_lines():
    lines = [line.text for block in parse_blocks(REAL_OUTPUT) for line in to_lines(block, 100, 100)]

    assert lines == [
        "TAX INVOICE",
        "Invoice No: INV-2041",
        "Description | Qty | Unit Price | Amount",
        "Ergonomic office chair | 2 | 250.00 | 500.00",
        "Total Due 1,180.00",
    ]


def test_output_with_an_unclosed_block_yields_nothing():
    assert parse_blocks("<x_0.0488><y_0.0>will be able to provide the information") == []


def test_reversed_corners_are_put_in_order():
    block = parse_blocks("<x_0.9><y_0.8>text<x_0.1><y_0.2><class_Text>")[0]

    assert block.bbox == (0.1, 0.2, 0.9, 0.8)


@pytest.mark.parametrize(
    ("cell", "expected"),
    [
        ("\\mbox{}", ""),
        ("\\multicolumn{2}{c}{\\thead{Subtotal}}", "Subtotal"),
        ("\\multirow{2}{*}{Item}", "Item"),
        ("Widget \\& Bolts 50\\%", "Widget & Bolts 50%"),
        ("Freight\\_A \\#12 (\\$)", "Freight_A #12 ($)"),
        ("\\makecell{Two\\\\lines}", "Two lines"),
    ],
)
def test_latex_in_cells_is_cleaned(cell, expected):
    assert text_of(table(f"first & {cell} & last\\\\")) == [f"first | {expected} | last"]


def test_empty_cells_keep_their_column():
    assert text_of(table("\\mbox{} & GST & 180.00\\\\")) == [" | GST | 180.00"]


def test_rules_and_empty_rows_are_dropped():
    assert text_of(table("\\hline", "a & b & c\\\\", "\\hline")) == ["a | b | c"]


def test_table_without_latex_is_read_as_text():
    block = ParsedBlock(text="Total 10.00", bbox=(0, 0, 1, 1), kind="Table")

    assert text_of(block) == ["Total 10.00"]


def test_lines_share_the_block_height_in_pixels():
    block = ParsedBlock(text="one\ntwo", bbox=(0.1, 0.2, 0.5, 0.6), kind="Text")

    first, second = to_lines(block, 1000, 2000)

    assert first.bbox == pytest.approx((100, 400, 500, 800))
    assert second.bbox == pytest.approx((100, 800, 500, 1200))
