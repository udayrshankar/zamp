from concurrent.futures import ThreadPoolExecutor

import pytest

from app.domain.errors import (
    DocumentNotFoundError,
    EmptyFileError,
    EncryptedPdfError,
    FileTooLargeError,
    NotAPdfError,
)
from app.domain.models import DocumentStatus, ErrorCode
from app.services.document_service import DocumentService
from tests.fakes import FakeExtractor, FakeRepository, FakeStorage

PDF = b"%PDF-1.7 content"


@pytest.fixture
def executor():
    with ThreadPoolExecutor(max_workers=1) as pool:
        yield pool


def make_service(executor, extractor=None):
    return DocumentService(
        repository=FakeRepository(),
        storage=FakeStorage(),
        extractor=extractor or FakeExtractor(),
        executor=executor,
        max_upload_bytes=100,
    )


async def test_upload_stores_the_file_and_queues_the_document(executor):
    service = make_service(executor)

    document = await service.upload("invoice.pdf", PDF)

    assert document.status is DocumentStatus.QUEUED
    assert len(document.sha256) == 64
    assert (await service.load_file(document.id))[1] == PDF


@pytest.mark.parametrize(
    ("data", "error"),
    [(b"", EmptyFileError), (b"hello", NotAPdfError), (b"%PDF" + b"x" * 200, FileTooLargeError)],
)
async def test_bad_uploads_are_rejected(executor, data, error):
    with pytest.raises(error):
        await make_service(executor).upload("invoice.pdf", data)


async def test_successful_run_completes_the_document(executor):
    service = make_service(executor)
    document = await service.upload("invoice.pdf", PDF)

    await service.process(document.id)

    assert (await service.get(document.id)).status is DocumentStatus.COMPLETED


async def test_expected_failure_is_recorded_with_its_code(executor):
    service = make_service(executor, FakeExtractor(EncryptedPdfError()))
    document = await service.upload("invoice.pdf", PDF)

    await service.process(document.id)

    saved = await service.get(document.id)
    assert saved.status is DocumentStatus.FAILED
    assert saved.error.code is ErrorCode.ENCRYPTED_PDF


async def test_unexpected_crash_is_recorded_without_leaking_details(executor):
    service = make_service(executor, FakeExtractor(RuntimeError("secret internals")))
    document = await service.upload("invoice.pdf", PDF)

    await service.process(document.id)

    saved = await service.get(document.id)
    assert saved.error.code is ErrorCode.INTERNAL_ERROR
    assert "secret" not in saved.error.message


async def test_restart_fails_unfinished_work_only(executor):
    service = make_service(executor)
    finished = await service.upload("done.pdf", PDF)
    await service.process(finished.id)
    stranded = await service.upload("stranded.pdf", PDF)

    assert await service.recover_interrupted() == 1

    assert (await service.get(finished.id)).status is DocumentStatus.COMPLETED
    assert (await service.get(stranded.id)).error.code is ErrorCode.INTERRUPTED


async def test_unknown_document_raises(executor):
    with pytest.raises(DocumentNotFoundError):
        await make_service(executor).get("missing")
