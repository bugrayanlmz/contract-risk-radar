from io import BytesIO

from pypdf import PdfReader

from app.config import Settings


class AnalysisError(Exception):
    def __init__(self, code: str, message: str, retryable: bool = False):
        super().__init__(message)
        self.code, self.message, self.retryable = code, message, retryable


def validate_pdf(content: bytes, settings: Settings) -> PdfReader:
    if not content or len(content) > settings.max_upload_bytes:
        raise AnalysisError("UPLOAD_SIZE", "Upload a PDF no larger than 10 MiB.")
    if not content.startswith(b"%PDF-"):
        raise AnalysisError("INVALID_PDF", "The uploaded file is not a valid PDF.")
    try:
        reader = PdfReader(BytesIO(content), strict=True)
        if reader.is_encrypted:
            raise AnalysisError("ENCRYPTED_PDF", "Password-protected PDFs are not supported.")
        if not 1 <= len(reader.pages) <= settings.max_pdf_pages:
            raise AnalysisError("PAGE_LIMIT", "Upload a PDF with 1 to 30 pages.")
        return reader
    except AnalysisError:
        raise
    except Exception as exc:
        raise AnalysisError(
            "INVALID_PDF", "This PDF could not be read. Upload a valid PDF."
        ) from exc


def extract_pdf(content: bytes, settings: Settings) -> tuple[str, list[str]]:
    reader = validate_pdf(content, settings)
    try:
        pages = [page.extract_text() or "" for page in reader.pages]
    except Exception as exc:
        raise AnalysisError(
            "TEXT_EXTRACTION", "Text could not be extracted from this PDF."
        ) from exc
    if not any(page.strip() for page in pages):
        raise AnalysisError(
            "NO_TEXT_LAYER",
            "This PDF has no readable text layer. Upload a text-based PDF; OCR is not supported.",
        )
    missing = [str(i + 1) for i, text in enumerate(pages) if not text.strip()]
    warnings = (
        [f"Pages {', '.join(missing)} contain no readable text; analysis may be incomplete."]
        if missing
        else []
    )
    text = "\n".join(pages)
    if len(text) > settings.max_text_chars:
        raise AnalysisError(
            "TEXT_LIMIT",
            "This PDF contains too much text. Upload a shorter contract (80,000 characters maximum).",
        )
    return text, warnings
