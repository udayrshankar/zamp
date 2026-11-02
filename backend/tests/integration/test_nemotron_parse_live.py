"""Calls the real NVIDIA API, so it needs NVIDIA_KEY and sends sample pages to it.

Run it explicitly: uv run pytest tests/integration
"""

import json
from pathlib import Path

import pytest

from app.core.config import Settings
from app.core.pipeline_factory import build_pipeline

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
EXPECTED = json.loads((FIXTURES / "expected.json").read_text())

settings = Settings()
pipeline = build_pipeline(settings)

pytestmark = pytest.mark.skipif(not settings.NVIDIA_KEY, reason="NVIDIA_KEY is not set")


def run(name: str):
    return pipeline.run((FIXTURES / f"{name}.pdf").read_bytes())


@pytest.mark.parametrize("name", ["scanned", "garbled"])
def test_scanned_pages_are_read_by_parse(name):
    result = run(name)

    assert [page.method for page in result.pages] == ["parse"]
    assert result.warnings == []
    for expected in EXPECTED[name]["contains"]:
        assert expected in result.pages[0].text


def test_mixed_document_uses_native_text_and_parse():
    result = run("mixed")

    assert [page.method for page in result.pages] == ["native", "parse"]
    assert "Delivery note DN-5519" in result.pages[1].text


def test_amounts_stay_beside_their_labels():
    assert "Total Due 1,180.00" in run("scanned").pages[0].text


@pytest.mark.parametrize("name", ["blank", "blank_scan"])
def test_empty_pages_do_not_produce_invented_text(name):
    result = run(name)

    assert [page.method for page in result.pages] == ["blank"]
    assert result.pages[0].text == ""
