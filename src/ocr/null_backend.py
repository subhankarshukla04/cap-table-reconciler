"""Null OCR backend: signals "OCR not available" without crashing.

Used in dev environments without Tesseract installed. The pipeline
records a warning and the analyst falls back to manual transcription
of the side letter.
"""

from __future__ import annotations

from pathlib import Path

from . import OCRBackend, OCRResult


class NullBackend(OCRBackend):
    name = "null"

    def is_available(self) -> bool:
        # Always available — but flagged as unhelpful by zero confidence.
        return True

    def ocr_pdf(self, path: Path) -> OCRResult:
        return OCRResult(
            text="",
            confidence=0.0,
            backend_name=self.name,
            warnings=(
                "ocr-backend-unavailable: no OCR backend installed. "
                "Install tesseract (brew install tesseract) and the "
                "pytesseract python package to enable image-PDF parsing.",
            ),
        )
