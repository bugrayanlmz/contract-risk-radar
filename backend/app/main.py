from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.analysis.pdf import AnalysisError
from app.api import auth, documents
from app.config import get_settings
from app.db import session_factory
from app.jobs.app import get_queue
from app.schemas.responses import ApiError, CapabilitiesResponse


@asynccontextmanager
async def lifespan(app):
    await get_queue().open_async()
    yield
    await get_queue().close_async()


app = FastAPI(
    title="Contract Risk Radar",
    version="0.1.0",
    description="English and German residential rental contract demo. Not legal advice.",
    lifespan=lifespan,
    responses={code: {"model": ApiError} for code in (400, 401, 403, 404, 409, 422, 500)},
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(get_settings().origins),
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


def error_response(code, message, status):
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status)


@app.middleware("http")
async def origin_guard(request: Request, call_next):
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        if request.headers.get("origin", "").rstrip("/") not in get_settings().origins:
            return error_response(
                "INVALID_ORIGIN", "Requests must originate from the configured application.", 403
            )
    try:
        response = await call_next(request)
    except Exception:
        return error_response(
            "INTERNAL_ERROR", "The request could not be completed. Please try again.", 500
        )
    response.headers["X-Content-Type-Options"] = "nosniff"
    if request.url.path.startswith("/api"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(HTTPException)
async def http_error(request, exc):
    detail = (
        exc.detail
        if isinstance(exc.detail, dict)
        else {"code": "REQUEST_ERROR", "message": str(exc.detail)}
    )
    return error_response(detail["code"], detail["message"], exc.status_code)


@app.exception_handler(RequestValidationError)
async def validation_error(request, exc):
    locations = ", ".join(".".join(str(part) for part in error["loc"]) for error in exc.errors())
    return error_response("VALIDATION_ERROR", f"Invalid or missing input: {locations}.", 422)


@app.exception_handler(AnalysisError)
async def analysis_error(request, exc):
    return error_response(exc.code, exc.message, 422)


@app.get("/api/health", operation_id="health")
async def health():
    async with session_factory()() as session:
        await session.execute(text("SELECT 1"))
    return {"status": "ok"}


@app.get("/api/capabilities", response_model=CapabilitiesResponse, operation_id="getCapabilities")
async def capabilities():
    return CapabilitiesResponse(
        supported_languages=["english", "german"],
        real_documents_allowed=get_settings().real_documents_allowed,
    )


app.include_router(auth.router, prefix="/api")
app.include_router(documents.router, prefix="/api")
