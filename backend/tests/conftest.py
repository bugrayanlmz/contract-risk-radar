import os
from io import BytesIO
from pathlib import Path

import httpx
import pytest
from reportlab.pdfgen.canvas import Canvas
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db import get_session
from app.main import app
from app.models import Base


@pytest.fixture
def pdf_bytes():
    return (Path(__file__).resolve().parents[2] / "samples/renewal-trap.pdf").read_bytes()


@pytest.fixture
def scanned_pdf():
    stream = BytesIO()
    canvas = Canvas(stream)
    canvas.rect(10, 10, 20, 20, fill=True)
    canvas.showPage()
    canvas.save()
    return stream.getvalue()


@pytest.fixture
async def factory(request):
    url = os.environ.get("TEST_DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    if "postgres" in request.keywords and not url.startswith("postgresql"):
        pytest.skip("Set TEST_DATABASE_URL for PostgreSQL integration tests.")
    if url.startswith("postgresql") and not (make_url(url).database or "").endswith("_test"):
        raise RuntimeError("TEST_DATABASE_URL must name a disposable database ending in _test.")
    engine = create_async_engine(url)
    async with engine.begin() as connection:
        if url.startswith("postgresql"):
            # Only delete this app's data in the explicitly disposable test database.
            await connection.execute(
                text(
                    "TRUNCATE important_dates, ai_findings, clauses, analysis_results, documents, stored_files, users CASCADE"
                )
            )
        else:
            await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.fixture
async def client(factory):
    async def session_override():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_session] = session_override
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://localhost:5173",
        headers={"Origin": "http://localhost:5173"},
    ) as client:
        yield client
    app.dependency_overrides.clear()
