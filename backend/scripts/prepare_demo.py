"""Writes the labelled invoices as PDFs and adds their purchase orders to MongoDB.

Run from backend/: uv run python scripts/prepare_demo.py
Upload the PDFs in numbered order, because split billing and duplicates depend on
what came before. POs that already exist are left alone.
"""

import asyncio
import re
import sys
from pathlib import Path

from pymongo import AsyncMongoClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import settings  # noqa: E402
from app.domain.errors import DuplicatePurchaseOrderError  # noqa: E402
from app.domain.models import PurchaseOrder  # noqa: E402
from app.infrastructure.purchase_order_repository import (  # noqa: E402
    MongoPurchaseOrderRepository,
)
from tests.eval.cases import CASES, PURCHASE_ORDERS  # noqa: E402

OUTPUT = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "demo"


def write_invoices() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    lines = []
    for index, case in enumerate(CASES, start=1):
        slug = re.sub(r"[^a-z0-9]+", "-", case.name.lower()).strip("-")
        filename = f"{index:02d}-{slug}.pdf"
        (OUTPUT / filename).write_bytes(case.invoice.to_pdf())
        answer = f" (answer {case.answer_po})" if case.answer_po else ""
        lines.append(f"{filename}: {case.expected}{answer}")
    (OUTPUT / "expected.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {len(CASES)} invoices to {OUTPUT}")


async def seed_purchase_orders() -> None:
    client = AsyncMongoClient(settings.MONGO_DB_URL)
    repository = MongoPurchaseOrderRepository(client[settings.MONGO_DB_NAME])
    await repository.ensure_indexes()
    added = 0
    for order in PURCHASE_ORDERS:
        try:
            await repository.insert(PurchaseOrder(**order))
            added += 1
        except DuplicatePurchaseOrderError:
            pass
    await client.close()
    print(f"Added {added} purchase orders to {settings.MONGO_DB_NAME}")


if __name__ == "__main__":
    write_invoices()
    asyncio.run(seed_purchase_orders())
