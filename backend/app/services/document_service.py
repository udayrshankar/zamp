import asyncio
import hashlib
import logging
from concurrent.futures import Executor

from app.domain.errors import (
    DocumentNotFoundError,
    EmptyFileError,
    ExtractionError,
    FileTooLargeError,
    NotAPdfError,
)
from app.domain.models import Document, DocumentError, ErrorCode
from app.domain.ports import DocumentRepository, FileStorage, TextExtractor

logger = logging.getLogger(__name__)

PDF_SIGNATURE = b"%PDF"
# The PDF spec lets the signature sit a little way into the file.
SIGNATURE_SEARCH_BYTES = 1024


class DocumentService:
    """Owns a document's lifecycle: accepted, processed, then completed or failed."""

    def __init__(
        self,
        repository: DocumentRepository,
        storage: FileStorage,
        extractor: TextExtractor,
        executor: Executor,
        max_upload_bytes: int,
    ) -> None:
        self._repository = repository
        self._storage = storage
        self._extractor = extractor
        self._executor = executor
        self._max_upload_bytes = max_upload_bytes
        # Without this, every waiting upload would claim to be "processing".
        self._turn = asyncio.Lock()

    async def upload(self, filename: str, data: bytes) -> Document:
        self._validate(data)
        file_id = await self._storage.save(filename, data)
        document = Document(
            filename=filename,
            sha256=hashlib.sha256(data).hexdigest(),
            size_bytes=len(data),
            file_id=file_id,
        )
        await self._repository.insert(document)
        return document

    async def process(self, document_id: str) -> None:
        async with self._turn:
            await self._repository.mark_processing(document_id)
            try:
                document = await self.get(document_id)
                data = await self._storage.load(document.file_id)
                result = await asyncio.get_running_loop().run_in_executor(
                    self._executor, self._extractor.run, data
                )
            except ExtractionError as error:
                await self._repository.mark_failed(
                    document_id, DocumentError(code=error.code, message=error.message)
                )
            except Exception:
                logger.exception("Extraction crashed for document %s", document_id)
                await self._repository.mark_failed(
                    document_id,
                    DocumentError(
                        code=ErrorCode.INTERNAL_ERROR,
                        message="Something went wrong while processing this document.",
                    ),
                )
            else:
                await self._repository.save_result(document_id, result)

    async def recover_interrupted(self) -> int:
        """Work runs in this process, so anything unfinished at startup is lost."""
        return await self._repository.fail_unfinished(
            DocumentError(
                code=ErrorCode.INTERRUPTED,
                message="Processing stopped because the server restarted. Please upload again.",
            )
        )

    async def get(self, document_id: str) -> Document:
        document = await self._repository.get(document_id)
        if document is None:
            raise DocumentNotFoundError("Document not found.")
        return document

    async def list(self, limit: int, offset: int) -> tuple[list[Document], int]:
        return await self._repository.list(limit, offset)

    async def load_file(self, document_id: str) -> tuple[Document, bytes]:
        document = await self.get(document_id)
        return document, await self._storage.load(document.file_id)

    async def delete(self, document_id: str) -> None:
        document = await self._repository.get(document_id)
        if document is None:
            return
        await self._repository.delete(document_id)
        await self._storage.delete(document.file_id)

    def _validate(self, data: bytes) -> None:
        if not data:
            raise EmptyFileError("The file is empty.")
        if len(data) > self._max_upload_bytes:
            limit_mb = self._max_upload_bytes // (1024 * 1024)
            raise FileTooLargeError(f"The file is larger than the {limit_mb} MB limit.")
        if PDF_SIGNATURE not in data[:SIGNATURE_SEARCH_BYTES]:
            raise NotAPdfError("The file is not a PDF.")
