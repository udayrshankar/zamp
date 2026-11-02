# Backend API

FastAPI service for invoice processing. It currently covers the first stage: reading text from a PDF, whether the PDF has a text layer or is a scan.

## Prerequisites

- [uv](https://docs.astral.sh/uv/) package manager
- Python 3.13+
- A MongoDB connection string

- Optional: an NVIDIA API key for Nemotron Parse (`NVIDIA_KEY`)

Tesseract and Poppler are not needed. OCR models ship with the `rapidocr` package.

## Getting Started

### 1. Configure

Copy `.env.example` to `.env` and set `MONGO_DB_URL` and `MONGO_DB_NAME`.

### 2. Run the development server

From the `backend` directory:

```bash
uv run uvicorn main:app --reload --port 8000
```

or simply:

```bash
uv run python main.py
```

The server won't start if MongoDB is unreachable, because it creates indexes and recovers interrupted runs at startup.

### 3. Available Endpoints

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/v1/documents` | Upload a PDF (multipart field `file`). Returns 202 and processes in the background. |
| GET | `/api/v1/documents` | Run history, newest first, without page text. Supports `limit` and `offset`. |
| GET | `/api/v1/documents/{id}` | Full result, including the text of each page. |
| GET | `/api/v1/documents/{id}/file` | The original PDF. |
| POST | `/api/v1/purchase-orders` | Create a purchase order. |
| GET | `/api/v1/purchase-orders` | List purchase orders, newest first. Supports `limit` and `offset`. |
| GET | `/api/v1/purchase-orders/{id}` | Get one purchase order. |
| PUT | `/api/v1/purchase-orders/{id}` | Replace a purchase order. |
| DELETE | `/api/v1/purchase-orders/{id}` | Delete a purchase order. |
| POST | `/api/v1/runs` | Upload an invoice and start a run. Returns 202 and works in the background. |
| GET | `/api/v1/runs` | Run history, newest first. |
| GET | `/api/v1/runs/{id}` | A run with its stages, checks and decision. Poll this for live progress. |
| DELETE | `/api/v1/runs/{id}` | Delete a run, its document and its PDF. Returns 204, or 409 `RUN_IN_PROGRESS` while it is queued or running. |
| POST | `/api/v1/runs/{id}/purchase-order` | Answer a paused run with `{"po_number": "..."}`. |
| POST | `/api/v1/runs/{id}/no-purchase-order` | Say a paused run has no PO, which sends it to review. |
| GET | `/health` | Health check. |

Interactive docs are at [http://localhost:8000/docs](http://localhost:8000/docs).

## How an invoice gets a decision

```text
Upload → Extract text → Detect PO ──found──→ Verify → Rule checks → Decision
                            │                  ↑                    accept / review / reject
                            └─not found→ Ask user
```

Every stage is saved to `invoice_runs` with its status, timing and result, so the live view and the audit trail come from the same record.

The LLM reads and compares. Code does the arithmetic and makes the decision, because an LLM can sound sure about a wrong total.

1. **Detect the PO.** The LLM lists candidates with the line each came from. Code drops any that aren't really in the text, then looks the rest up in `purchase_orders`, ignoring case and punctuation. A long digit run can also match, so `88213/ACME` finds `PO-88213`.
2. **Ask the user.** No match, several matches, or an LLM failure pauses the run as `awaiting_po`. A paused run survives a restart.
3. **Verify.** The LLM reports what both documents say, naming the PO field each value came from. That is how free-form field names like `grand_total` work.
4. **Rule checks.** See `app/workflow/checks.py`: required fields are really on the invoice, reported amounts exist in the sources, arithmetic, duplicates, vendor, currency, amount against the PO including earlier accepted invoices, extraction quality, and line-level conflicts on itemised POs.
5. **Decide.** The strictest check wins.

| Decision | When |
|---|---|
| Accept | Every check passes and billing is at most `ACCEPT_TOLERANCE_PERCENT` over the PO |
| Review | Over the PO by up to `REJECT_TOLERANCE_PERCENT`, missing fields, arithmetic that doesn't add up, an unclear vendor, a shaky reading, or any failure along the way |
| Reject | A duplicate, clearly the wrong vendor, or more than `REJECT_TOLERANCE_PERCENT` over the PO |

Deleting a run also removes it from history: an accepted invoice stops counting towards its PO, and it can no longer be caught as a duplicate.

Billing under the PO is accepted as partial billing, because vendors may split a PO across invoices. Anything uncertain goes to a person, so a failure can never produce an accept.

The model is set by `LLM_MODEL` and works with any endpoint that accepts this request format.

## Purchase orders

Only `po_number` is required, and it must be unique. Everything else goes in `fields`, which the user defines per PO. Values can be any JSON, including lists and nested objects:

```json
{
  "po_number": "PO-88213",
  "fields": {
    "vendor": "Northwind Office Supplies",
    "handling_charges": 25.5,
    "line_items": [{ "description": "Chair", "qty": 2, "unit_price": 250.0 }]
  }
}
```

`PUT` replaces the whole PO, so a field left out of the request is removed. Field names can't be blank, contain `.`, or start with `$`. A PO number already in use returns 409.

## How extraction works

Each page is routed on its own, so one PDF can mix a text page and a scanned page. A page goes to OCR when any of these is true:

1. It has fewer than `MIN_TEXT_CHARS` non-whitespace characters.
2. Its text looks garbled: under `MIN_ALNUM_RATIO` alphanumeric, or it contains U+FFFD.
3. Images cover at least `IMAGE_COVERAGE_THRESHOLD` of the page and it has fewer than `SPARSE_TEXT_CHARS` characters.

Otherwise the embedded text is used, which is exact, free and needs no network. All paths produce the same result shape, with lines in reading order and positions in PDF points. All thresholds are in `app/core/config.py`.

Pages that need reading from their image go to [Nemotron 3.5 Parse](https://huggingface.co/nvidia/Nemotron-3.5-Parse) on NVIDIA's hosted API, with local RapidOCR as the backup:

- **Near-empty pages skip Parse.** Given a blank or nearly blank page the model invents plausible text and gives no confidence score. A page under `PARSE_MIN_INK_RATIO` of ink goes straight to OCR, which doesn't invent text.
- **Any Parse failure falls back to OCR**, including errors, timeouts, rate limits and cut-off or unreadable output. The page gets a `PARSE_FALLBACK` warning with the reason.
- **Without `NVIDIA_KEY`**, OCR reads these pages and no data leaves the machine.

Parse results have no confidence score. Table rows use ` | ` between cells so columns stay distinct, but the model can place a value in the wrong column on tables with merged cells, so amounts should be validated by a later stage.

Sending a page to Parse sends its image to NVIDIA, under the [API Trial Terms](https://docs.api.nvidia.com/). Check those terms before using real invoices.

| Input | Result |
|---|---|
| Empty, over `MAX_UPLOAD_MB`, or not a PDF | Rejected at upload with 400, 413 or 415 |
| Password-protected | `failed`, `ENCRYPTED_PDF` |
| Corrupt | `failed`, `CORRUPT_PDF` |
| Over `MAX_PAGES` | `failed`, `TOO_MANY_PAGES` |
| Server restarted mid-run | `failed`, `INTERRUPTED` |
| One page can't be read | `completed`, page marked `failed`, warning `PAGE_FAILED` |
| Nemotron Parse failed on a page | `completed`, page read by OCR, warning `PARSE_FALLBACK` |
| OCR confidence under `LOW_OCR_CONFIDENCE` | `completed`, warning `LOW_OCR_CONFIDENCE` |
| Blank page or document | `completed`, warning `BLANK_PAGE`, plus `NO_TEXT_FOUND` if nothing was found at all |

Documents are processed one at a time on a single worker thread, because OCR is CPU-bound and PyMuPDF is not thread-safe. Later uploads wait as `queued`.

## Code layout

```
app/
  domain/          Models, errors, and ports (interfaces). No infrastructure imports.
  extraction/      Routing, the two page extractors, and the pipeline. Depends on ports only.
  infrastructure/  PyMuPDF, RapidOCR, MongoDB and GridFS adapters.
  workflow/        PO detection and matching, verification, rule checks, decision policy.
  services/        Document lifecycle, purchase orders, and the run orchestrator.
  api/             Routes, schemas, and the composition root in dependencies.py.
  core/            Settings and pipeline wiring.
```

To swap the OCR engine or parsing model, write a class matching `OcrEngine` or `PageParser` in `app/domain/ports.py` and pass it in `app/core/pipeline_factory.py`.

## Testing

```bash
uv run pytest                     # unit and API tests, no network or database
uv run pytest tests/integration   # real PDF reader, OCR model and NVIDIA API on the sample invoices
```

The Parse tests in that second suite call NVIDIA and are skipped without `NVIDIA_KEY`.

Measure the whole process against 20 labelled invoices using the real LLM:

```bash
uv run python scripts/run_eval.py --repeat 3
```

It runs in memory and doesn't touch MongoDB. The number that matters most is wrong accepts, which must stay at zero.

## Manual testing

```bash
uv run python scripts/prepare_iitm_samples.py
```

This writes sample invoices of varied quality to `tests/fixtures/iitm` and adds their purchase orders to the configured database. That folder's README lists the upload order and expected results.

## Demo data

```bash
uv run python scripts/prepare_demo.py
```

This writes the labelled invoices to `tests/fixtures/demo`, with the expected results in `expected.txt`, and adds their purchase orders to the configured database. Upload the PDFs in numbered order, because split billing and duplicates depend on earlier invoices.

Try one file without a database:

```bash
uv run python scripts/extract.py tests/fixtures/mixed.pdf --text
```

Sample invoices live in `tests/fixtures`. Rebuild them with `uv run python scripts/generate_sample_invoices.py`.

## Docker

```bash
docker build -t invoice-backend .
docker run --env-file .env -p 8000:8000 invoice-backend
```
