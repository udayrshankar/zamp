"""Builds the sample invoices used by tests and demos.

Run from backend/: uv run python scripts/generate_sample_invoices.py
"""

import json
from pathlib import Path

import numpy as np
import pymupdf

FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures"
A4 = (595, 842)
GARBAGE = "#%&@!?*~^=+" * 12

INVOICE = {
    "number": "INV-2041",
    "date": "12 Oct 2026",
    "po": "PO-88213",
    "total": "1,180.00",
}
LINE_ITEMS = [
    ("Ergonomic office chair", "2", "250.00", "500.00"),
    ("Standing desk frame", "1", "450.00", "450.00"),
    ("Monitor arm, dual", "1", "50.00", "50.00"),
]
SECOND_PAGE_MARKER = "Delivery note DN-5519"


def draw_invoice(page: pymupdf.Page) -> None:
    page.insert_text((50, 70), "Northwind Office Supplies Pvt Ltd", fontsize=18, fontname="hebo")
    page.insert_text((50, 92), "14 Residency Road, Bengaluru 560025", fontsize=10)
    page.insert_text((400, 70), "TAX INVOICE", fontsize=16, fontname="hebo")

    details = [
        ("Invoice No:", INVOICE["number"]),
        ("Invoice Date:", INVOICE["date"]),
        ("PO Reference:", INVOICE["po"]),
        ("Bill To:", "Acme Manufacturing Ltd"),
    ]
    for row, (label, value) in enumerate(details):
        y = 140 + row * 18
        page.insert_text((50, y), label, fontsize=11, fontname="hebo")
        page.insert_text((150, y), value, fontsize=11)

    columns = (50, 320, 390, 480)
    for x, heading in zip(columns, ("Description", "Qty", "Unit Price", "Amount")):
        page.insert_text((x, 250), heading, fontsize=11, fontname="hebo")
    page.draw_line((50, 256), (545, 256))
    for row, item in enumerate(LINE_ITEMS):
        for x, value in zip(columns, item):
            page.insert_text((x, 276 + row * 20), value, fontsize=11)

    totals = [("Subtotal", "1,000.00"), ("GST 18%", "180.00"), ("Total Due", INVOICE["total"])]
    for row, (label, value) in enumerate(totals):
        y = 370 + row * 20
        page.insert_text((390, y), label, fontsize=11, fontname="hebo")
        page.insert_text((480, y), value, fontsize=11)
    page.insert_text((50, 460), "Payment terms: Net 30. Bank transfer only.", fontsize=10)


def draw_delivery_note(page: pymupdf.Page) -> None:
    page.insert_text((50, 80), SECOND_PAGE_MARKER, fontsize=18, fontname="hebo")
    page.insert_text((50, 120), f"Against invoice {INVOICE['number']}", fontsize=12)
    page.insert_text((50, 145), "All goods received in good condition", fontsize=12)
    page.insert_text((50, 170), "Signed by the stores team at Acme Manufacturing", fontsize=12)


def native_page(draw) -> pymupdf.Document:
    document = pymupdf.open()
    draw(document.new_page(width=A4[0], height=A4[1]))
    return document


def scanned_image(page: pymupdf.Page, seed: int = 7) -> bytes:
    """Renders a page the way a cheap office scanner would: low DPI, noisy, JPEG."""
    pixmap = page.get_pixmap(dpi=150, colorspace=pymupdf.csRGB, alpha=False)
    pixels = np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(
        pixmap.height, pixmap.width, pixmap.n
    )
    noise = np.random.default_rng(seed).normal(0, 12, pixels.shape)
    noisy = np.clip(pixels.astype(np.float32) * 0.96 + noise, 0, 255).astype(np.uint8)
    degraded = pymupdf.Pixmap(
        pymupdf.csRGB, pixmap.width, pixmap.height, noisy.tobytes(), False
    )
    return degraded.tobytes("jpeg", jpg_quality=70)


def add_scanned_page(document: pymupdf.Document, draw) -> pymupdf.Page:
    source = native_page(draw)
    page = document.new_page(width=A4[0], height=A4[1])
    page.insert_image(page.rect, stream=scanned_image(source[0]))
    return page


def build_native() -> bytes:
    return native_page(draw_invoice).tobytes()


def build_scanned() -> bytes:
    document = pymupdf.open()
    add_scanned_page(document, draw_invoice)
    return document.tobytes()


def build_mixed() -> bytes:
    document = native_page(draw_invoice)
    add_scanned_page(document, draw_delivery_note)
    return document.tobytes()


def build_garbled() -> bytes:
    """Looks fine on screen but has a junk text layer, as broken font maps produce."""
    document = pymupdf.open()
    page = add_scanned_page(document, draw_invoice)
    for row in range(8):
        page.insert_text((50, 100 + row * 40), GARBAGE, fontsize=8, render_mode=3)
    return document.tobytes()


def build_blank() -> bytes:
    document = pymupdf.open()
    document.new_page(width=A4[0], height=A4[1])
    return document.tobytes()


def build_blank_scan() -> bytes:
    """An empty page through a scanner: grey noise and dust. Parsing models
    invent text on pages like this, so it must never reach one."""
    rng = np.random.default_rng(11)
    height, width = 1169, 827
    pixels = np.clip(245 + rng.normal(0, 10, (height, width, 3)), 0, 255).astype(np.uint8)
    for _ in range(25):
        y, x = rng.integers(0, height - 3), rng.integers(0, width - 3)
        pixels[y : y + 2, x : x + 2] = 40
    scan = pymupdf.Pixmap(pymupdf.csRGB, width, height, pixels.tobytes(), False)
    document = pymupdf.open()
    page = document.new_page(width=A4[0], height=A4[1])
    page.insert_image(page.rect, stream=scan.tobytes("jpeg", jpg_quality=70))
    return document.tobytes()


def build_encrypted() -> bytes:
    return native_page(draw_invoice).tobytes(
        encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="secret", owner_pw="owner"
    )


def build_corrupt() -> bytes:
    # A valid signature so it passes the upload check and fails at parse time.
    return b"%PDF-1.7\n" + bytes(range(256)) * 40


def main() -> None:
    FIXTURES.mkdir(parents=True, exist_ok=True)
    builders = {
        "native": build_native,
        "scanned": build_scanned,
        "mixed": build_mixed,
        "garbled": build_garbled,
        "blank": build_blank,
        "blank_scan": build_blank_scan,
        "encrypted": build_encrypted,
        "corrupt": build_corrupt,
    }
    for name, build in builders.items():
        (FIXTURES / f"{name}.pdf").write_bytes(build())

    invoice_strings = list(INVOICE.values())
    expected = {
        "native": {"methods": ["native"], "contains": invoice_strings},
        "scanned": {"methods": ["ocr"], "contains": invoice_strings},
        "mixed": {
            "methods": ["native", "ocr"],
            "contains": [*invoice_strings, SECOND_PAGE_MARKER],
        },
        "garbled": {"methods": ["ocr"], "contains": invoice_strings},
        "blank": {"methods": ["blank"], "contains": []},
        "blank_scan": {"methods": ["blank"], "contains": []},
        "encrypted": {"error": "ENCRYPTED_PDF"},
        "corrupt": {"error": "CORRUPT_PDF"},
    }
    (FIXTURES / "expected.json").write_text(json.dumps(expected, indent=2) + "\n")
    print(f"Wrote {len(builders)} fixtures to {FIXTURES}")


if __name__ == "__main__":
    main()
