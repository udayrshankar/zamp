"""Runs the real PDF reader and OCR model over every sample invoice.

Slower than the other suites, so run it explicitly: uv run pytest tests/integration
"""

import json
from pathlib import Path

import pytest

from app.core.config import Settings
from app.core.pipeline_factory import build_pipeline
from app.domain.errors import ExtractionError

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
EXPECTED = json.loads((FIXTURES / "expected.json").read_text())

# No key: this suite covers the offline OCR path, and stays free and deterministic.
pipeline = build_pipeline(Settings(NVIDIA_KEY=""))


def read(name: str) -> bytes:
    return (FIXTURES / f"{name}.pdf").read_bytes()


@pytest.mark.parametrize("name", [name for name, spec in EXPECTED.items() if "methods" in spec])
def test_pages_are_routed_and_read_correctly(name):
    result = pipeline.run(read(name))

    assert [page.method for page in result.pages] == EXPECTED[name]["methods"]
    text = "\n".join(page.text for page in result.pages)
    for expected in EXPECTED[name]["contains"]:
        assert expected in text


@pytest.mark.parametrize("name", [name for name, spec in EXPECTED.items() if "error" in spec])
def test_unreadable_files_fail_with_their_code(name):
    with pytest.raises(ExtractionError) as failure:
        pipeline.run(read(name))

    assert failure.value.code == EXPECTED[name]["error"]


def test_table_rows_stay_together_on_a_scan():
    text = pipeline.run(read("scanned")).pages[0].text

    assert "Total Due 1,180.00" in text
