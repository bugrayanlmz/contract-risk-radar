import hashlib
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import StoredFile


class PostgresFileStorage:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def put(self, pdf_bytes: bytes, content_type: str) -> UUID:
        item = StoredFile(
            content=pdf_bytes,
            content_type=content_type,
            size_bytes=len(pdf_bytes),
            sha256=hashlib.sha256(pdf_bytes).hexdigest(),
        )
        self.session.add(item)
        await self.session.flush()
        return item.id

    async def get(self, file_id: UUID) -> bytes:
        content = await self.session.scalar(
            select(StoredFile.content).where(StoredFile.id == file_id)
        )
        if content is None:
            raise FileNotFoundError(str(file_id))
        return content

    async def delete(self, file_id: UUID) -> None:
        await self.session.execute(delete(StoredFile).where(StoredFile.id == file_id))
