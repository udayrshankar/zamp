from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request, Response, UploadFile, status

from app.api.dependencies import get_document_service
from app.api.schemas import DocumentDetail, DocumentListItem, DocumentPage, UploadAccepted
from app.services.document_service import DocumentService

router = APIRouter(prefix="/api/v1/documents", tags=["Documents"])

Service = Annotated[DocumentService, Depends(get_document_service)]


@router.post("", response_model=UploadAccepted, status_code=status.HTTP_202_ACCEPTED)
async def upload_document(
    file: UploadFile,
    request: Request,
    background_tasks: BackgroundTasks,
    service: Service,
) -> UploadAccepted:
    # One byte over the limit is enough for the service to reject it, and it
    # stops a huge upload being read fully into memory.
    max_bytes = request.app.state.max_upload_bytes
    document = await service.upload(file.filename or "invoice.pdf", await file.read(max_bytes + 1))
    background_tasks.add_task(service.process, document.id)
    return UploadAccepted.model_validate(document)


@router.get("", response_model=DocumentPage)
async def list_documents(
    service: Service,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> DocumentPage:
    documents, total = await service.list(limit, offset)
    return DocumentPage(
        items=[DocumentListItem.model_validate(document) for document in documents],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{document_id}", response_model=DocumentDetail)
async def get_document(document_id: str, service: Service) -> DocumentDetail:
    return DocumentDetail.model_validate(await service.get(document_id))


@router.get("/{document_id}/file")
async def get_document_file(document_id: str, service: Service) -> Response:
    document, data = await service.load_file(document_id)
    return Response(
        content=data,
        media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename*=UTF-8''{quote(document.filename)}"},
    )
