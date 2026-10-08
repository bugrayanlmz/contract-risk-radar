from functools import lru_cache

import procrastinate
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import Document


@lru_cache
def get_queue() -> procrastinate.App:
    return procrastinate.App(
        connector=procrastinate.PsycopgConnector(conninfo=get_settings().queue_conninfo),
        import_paths=["app.jobs.tasks"],
    )


async def enqueue_document(session: AsyncSession, document: Document) -> int:
    await session.flush()
    connection = await session.connection()
    raw = await connection.get_raw_connection()
    return (
        await get_queue()
        .configure_task(
            name="analyze_document",
            allow_unknown=True,
            queue="analysis",
            connection=raw.driver_connection,
            lock=f"document:{document.id}",
            queueing_lock=f"document:{document.id}",
        )
        .defer_async(document_id=str(document.id), run_id=str(document.run_id))
    )
