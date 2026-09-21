"""OCR backend abstraction tests (W2.4 / SYSTEM_SPEC §4.3, §8.5)."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from src.ocr import (
    LOW_CONFIDENCE_THRESHOLD,
    NullBackend,
    OCRResult,
    TesseractBackend,
    select_backend,
)


def test_null_backend_is_always_available():
    assert NullBackend().is_available() is True


def test_null_backend_emits_unavailable_warning():
    r = NullBackend().ocr_pdf(Path("/nonexistent.pdf"))
    assert r.text == ""
    assert r.confidence == 0.0
    assert any("ocr-backend-unavailable" in w for w in r.warnings)
    assert r.below_confidence_threshold


def test_tesseract_backend_availability_matches_environment():
    """If tesseract binary AND pytesseract are both present, available;
    otherwise not. Either way the call must not crash."""
    available = TesseractBackend().is_available()
    assert isinstance(available, bool)


def test_select_backend_returns_some_backend():
    backend = select_backend()
    assert backend is not None
    # If tesseract is installed locally, the picker prefers it. If not,
    # falls through to Null. Either is a valid environment.
    assert backend.name in ("tesseract", "null")


def test_low_confidence_threshold_constant():
    assert LOW_CONFIDENCE_THRESHOLD == 0.85
    r = OCRResult(text="hello", confidence=0.80, backend_name="x")
    assert r.below_confidence_threshold
    r2 = OCRResult(text="hello", confidence=0.86, backend_name="x")
    assert not r2.below_confidence_threshold


# ---- pdf_intake fallback wiring ------------------------------------------


def test_pdf_intake_extract_text_routes_image_pdf_to_ocr():
    """Build a deliberately-image-only PDF surrogate (an empty PDF) and
    verify pdf_intake calls the OCR backend and surfaces its warnings."""
    from io import BytesIO

    # Smallest possible "PDF-like" path-input. We use a real but content-less
    # PDF generated via reportlab if available; otherwise skip with a clear
    # explanation. Falling back to an empty file path triggers
    # pdfplumber to fail, which is a different code path.
    try:
        from reportlab.pdfgen import canvas  # type: ignore
    except ImportError:
        pytest.skip("reportlab not available; skipping image-PDF surrogate test")

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as fh:
        p = Path(fh.name)
    try:
        c = canvas.Canvas(str(p))
        c.showPage()  # blank page, no text content
        c.save()
        from src.pdf_intake import extract_text
        full, warnings = extract_text(p)
        # On systems without Tesseract: NullBackend triggers, warnings
        # include pdf-ocr-fallback + ocr-backend-unavailable.
        assert any("pdf-ocr-fallback" in w for w in warnings) or full
    finally:
        p.unlink(missing_ok=True)
