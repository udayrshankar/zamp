FROM python:3.13-slim

ENV UV_LINK_MODE=copy

RUN pip install --no-cache-dir uv

WORKDIR /srv
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY main.py ./
COPY app ./app

# Loads the OCR models now, so a missing system library fails the build
# rather than the first scanned invoice.
RUN .venv/bin/python -c "from rapidocr import RapidOCR; RapidOCR()"

EXPOSE 8000
CMD [".venv/bin/uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
