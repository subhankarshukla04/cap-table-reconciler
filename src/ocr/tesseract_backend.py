"""Tesseract OCR backend (W2.4 / SYSTEM_SPEC §8.5).

Lazy availability check: returns False if either the `tesseract` binary
or the `pytesseract` python package is missing, so the rest of the
codebase can call `select_backend()` without crashing.

Confidence normalisation: Tesseract emits per-token confidence on a 0-100
scale via image_to_data. We average across the page and divide by 100 to
land on the [0, 1] scale the spec requires.

PDF handling: Tesseract operates on images, not PDFs directly. We use
`pdf2image` to rasterise pages, then OCR each, then concatenate. If
pdf2image is also missing, we degrade further to "available but cannot
process PDFs" (returns confidence=0 with a specific warning).
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Optional

from . import OCRBackend, OCRResult


def _have_tesseract_binary() -> bool:
    return shutil.which("tesseract") is not None


def _have_pytesseract() -> bool:
    try:
        import pytesseract  # noqa: F401
        return True
    except ImportError:
        return False


def _have_pdf2image() -> bool:
    try:
        import pdf2image  # noqa: F401
        return True
    except ImportError:
        return False


class TesseractBackend(OCRBackend):
    name = "tesseract"

    def is_available(self) -> bool:
        return _have_tesseract_binary() and _have_pytesseract()

    def ocr_pdf(self, path: Path) -> OCRResult:
        if not self.is_available():
            return OCRResult(
                text="",
                confidence=0.0,
                backend_name=self.name,
                warnings=("tesseract-unavailable: binary or pytesseract missing.",),
            )
        if not _have_pdf2image():
            return OCRResult(
                text="",
                confidence=0.0,
                backend_name=self.name,
                warnings=(
                    "pdf2image-missing: install pdf2image (pip install pdf2image) "
                    "and poppler (brew install poppler) to OCR PDFs.",
                ),
            )
        import pdf2image
        import pytesseract

        images = pdf2image.convert_from_path(str(path), dpi=300)
        all_text: list[str] = []
        all_confidences: list[float] = []
        for img in images:
            data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
            page_text_parts: list[str] = []
            for word, conf in zip(data["text"], data["conf"]):
                if not word or not word.strip():
                    continue
                page_text_parts.append(word)
                try:
                    c = float(conf)
                    if c >= 0:
                        all_confidences.append(c / 100.0)
                except (TypeError, ValueError):
                    pass
            all_text.append(" ".join(page_text_parts))
        avg_conf = (sum(all_confidences) / len(all_confidences)) if all_confidences else 0.0
        full_text = "\n\n".join(all_text)
        return OCRResult(
            text=full_text,
            confidence=avg_conf,
            backend_name=self.name,
            warnings=(),
        )
