from app.domain.models import ErrorCode


class DomainError(Exception):
    """Base class for every failure the application expects and can explain."""


class ExtractionError(DomainError):
    """A failure while reading a PDF. `code` is stable and shown to clients."""

    code: ErrorCode = ErrorCode.INTERNAL_ERROR
    message: str = "The document could not be processed."

    def __init__(self, message: str | None = None) -> None:
        self.message = message or self.message
        super().__init__(self.message)


class EncryptedPdfError(ExtractionError):
    code = ErrorCode.ENCRYPTED_PDF
    message = "The PDF is password-protected."


class CorruptPdfError(ExtractionError):
    code = ErrorCode.CORRUPT_PDF
    message = "The PDF is corrupt or could not be parsed."


class TooManyPagesError(ExtractionError):
    code = ErrorCode.TOO_MANY_PAGES
    message = "The PDF has more pages than the allowed limit."


class PageReadError(ExtractionError):
    """A single page could not be read. The rest of the document can continue."""

    code = ErrorCode.PAGE_READ_FAILED
    message = "The page could not be read."


class NothingToParseError(PageReadError):
    """The page was deliberately kept away from the parsing model."""


class UploadRejectedError(DomainError):
    """The upload was refused before any processing started."""


class EmptyFileError(UploadRejectedError):
    pass


class FileTooLargeError(UploadRejectedError):
    pass


class NotAPdfError(UploadRejectedError):
    pass


class DocumentNotFoundError(DomainError):
    pass


class PurchaseOrderNotFoundError(DomainError):
    pass


class DuplicatePurchaseOrderError(DomainError):
    pass


class LlmError(DomainError):
    """The LLM failed or gave an unusable answer. Callers fall back to a person."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class RunNotFoundError(DomainError):
    pass


class RunNotAwaitingPoError(DomainError):
    pass


class RunInProgressError(DomainError):
    pass


class UnknownPoNumberError(DomainError):
    pass
