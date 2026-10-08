from io import BytesIO

import pytest
from pypdf import PdfReader, PdfWriter

from app.analysis.evidence import normalize_text, verify_quote
from app.analysis.pdf import AnalysisError, extract_pdf, validate_pdf
from app.config import Settings


@pytest.mark.parametrize(
    "quote,text",
    [
        ('"Rent" is due.', "“Rent”\u00a0is\n due."),
        ("termination", "termi-\nnation"),
        ("refundable", "refund‐\r\n  able"),
        ("USD 1000", "USD\t1000"),
        ("ABC", "ＡＢＣ"),
    ],
)
def test_exact_normalized_evidence(quote, text):
    assert verify_quote(quote, text)


@pytest.mark.parametrize(
    "quote", ["", " ", "rent is due", "Rent ... due.", "Rent is owed.", "Rent is due", "Rent due."]
)
def test_rejects_changed_or_missing_quote(quote):
    # A contiguous substring is allowed, but punctuation must not be invented or removed internally.
    if quote == "Rent is due":
        assert verify_quote(quote, "Rent is due.")
    else:
        assert not verify_quote(quote, "Rent is due.")


def test_normalization_preserves_punctuation_and_same_line_hyphen():
    assert normalize_text("non-refundable; USD 10.00") == "non-refundable; USD 10.00"
    assert not verify_quote("nonrefundable", "non-refundable")


def test_pdf_limits_and_scanned(pdf_bytes, scanned_pdf):
    text, warnings = extract_pdf(pdf_bytes, Settings())
    assert "USD 1800.00" in text and not warnings
    with pytest.raises(AnalysisError, match="no readable text layer"):
        extract_pdf(scanned_pdf, Settings())
    with pytest.raises(AnalysisError, match="10 MiB"):
        validate_pdf(pdf_bytes, Settings(max_upload_bytes=10))
    with pytest.raises(AnalysisError, match="too much text"):
        extract_pdf(pdf_bytes, Settings(max_text_chars=10))
    with pytest.raises(AnalysisError, match="valid PDF"):
        validate_pdf(b"not a PDF", Settings())


def test_encryption_and_page_limit(pdf_bytes):
    writer = PdfWriter()
    writer.append(PdfReader(BytesIO(pdf_bytes)))
    writer.encrypt("password")
    stream = BytesIO()
    writer.write(stream)
    with pytest.raises(AnalysisError, match="Password-protected"):
        validate_pdf(stream.getvalue(), Settings())
    writer = PdfWriter()
    for _ in range(31):
        writer.add_blank_page(width=612, height=792)
    stream = BytesIO()
    writer.write(stream)
    with pytest.raises(AnalysisError, match="1 to 30"):
        validate_pdf(stream.getvalue(), Settings())
