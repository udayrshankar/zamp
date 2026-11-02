"""Runs the extraction pipeline on one PDF, with no database.

Run from backend/: uv run python scripts/extract.py path/to/invoice.pdf
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import settings  # noqa: E402
from app.core.pipeline_factory import build_pipeline  # noqa: E402
from app.domain.errors import ExtractionError  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--text", action="store_true", help="print the text of each page")
    args = parser.parse_args()

    try:
        result = build_pipeline(settings).run(args.pdf.read_bytes())
    except ExtractionError as error:
        print(f"FAILED {error.code}: {error.message}")
        return 1

    for page in result.pages:
        confidence = "" if page.confidence is None else f" confidence={page.confidence:.2f}"
        print(f"page {page.number}: {page.method} ({page.routing_reason}){confidence}")
        if args.text:
            print(page.text, end="\n\n")
    for warning in result.warnings:
        print(f"warning {warning.code}: {warning.message}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
