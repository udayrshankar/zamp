from bson import ObjectId
from gridfs.asynchronous import AsyncGridFSBucket
from gridfs.errors import NoFile
from pymongo.asynchronous.database import AsyncDatabase

BUCKET = "invoice_files"


class GridFsStorage:
    def __init__(self, database: AsyncDatabase) -> None:
        self._bucket = AsyncGridFSBucket(database, bucket_name=BUCKET)

    async def save(self, filename: str, data: bytes) -> str:
        file_id = await self._bucket.upload_from_stream(filename, data)
        return str(file_id)

    async def load(self, file_id: str) -> bytes:
        stream = await self._bucket.open_download_stream(ObjectId(file_id))
        return await stream.read()

    async def delete(self, file_id: str) -> None:
        try:
            await self._bucket.delete(ObjectId(file_id))
        except NoFile:
            pass
