from app.domain.models import TextLine
from app.extraction.line_grouping import group_into_lines, weighted_confidence


def fragment(text, x, y, height=10, confidence=None):
    return TextLine(text=text, bbox=(x, y, x + 40, y + height), confidence=confidence)


def test_joins_a_table_row_left_to_right_whatever_the_input_order():
    lines = group_into_lines([fragment("1,180.00", 300, 100), fragment("Total", 50, 101)])

    assert [line.text for line in lines] == ["Total 1,180.00"]


def test_orders_rows_top_to_bottom():
    lines = group_into_lines([fragment("second", 50, 200), fragment("first", 50, 100)])

    assert [line.text for line in lines] == ["first", "second"]


def test_keeps_tightly_packed_rows_apart():
    lines = group_into_lines([fragment("upper", 50, 100), fragment("lower", 50, 111)])

    assert len(lines) == 2


def test_line_box_spans_all_its_fragments():
    line = group_into_lines([fragment("a", 50, 100), fragment("b", 300, 102)])[0]

    assert line.bbox == (50, 100, 340, 112)


def test_no_fragments_means_no_lines():
    assert group_into_lines([]) == []


def test_confidence_is_weighted_by_length():
    lines = [
        TextLine(text="x", bbox=(0, 0, 1, 1), confidence=0.0),
        TextLine(text="yyy", bbox=(0, 0, 1, 1), confidence=1.0),
    ]

    assert weighted_confidence(lines) == 0.75


def test_native_lines_have_no_confidence():
    assert weighted_confidence([TextLine(text="x", bbox=(0, 0, 1, 1))]) is None
