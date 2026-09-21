"""OCR backend abstraction (W2.4 / SYSTEM_SPEC §4.3, §8.5).

Pipeline:
  1. pdfplumber tries to extract text.
  2. If text yield is below threshold (short or low page coverage), the
     pdf is routed to an OCRBackend.
  3. OCRBackend returns text + a confidence score normalised to [0, 1].
  4. Confidence < 0.85 surfaces a UI banner: "OCR confidence low,
     recommend manual review."

This file is the public surface. Concrete backends live in:
  - tesseract_backend.py — local Tesseract via pytesseract
  - null_backend.py      — no-op stub recording a "ocr unavailable" warning

The OCRBackend factory at the bottom of this module picks the best
backend available at import time. Tests can inject a specific backend.
"""

from __future__ import annotations

import shutil
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


# Per SYSTEM_SPEC §8.5: confidence threshold below which the UI surfaces the
# "low confidence, manual review recommended" banner.
LOW_CONFIDENCE_THRESHOLD = 0.85


@dataclass(frozen=True)
class OCRResult:
    text: str
    confidence: float  # normalized to [0, 1]
    backend_name: str
    warnings: tuple[str, ...] = ()

    @property
    def below_confidence_threshold(self) -> bool:
        return self.confidence < LOW_CONFIDENCE_THRESHOLD


class OCRBackend(ABC):
    name: str

    @abstractmethod
    def is_available(self) -> bool:
        ...

    @abstractmethod
    def ocr_pdf(self, path: Path) -> OCRResult:
        ...


from .null_backend import NullBackend  # noqa: E402
from .tesseract_backend import TesseractBackend  # noqa: E402


def select_backend() -> OCRBackend:
    """Return the best backend that reports itself available.

    Order: Tesseract → Null. Adding Google Document AI would mean adding
    its check before Tesseract.
    """
    for cls in (TesseractBackend, NullBackend):
        backend = cls()
        if backend.is_available():
            return backend
    return NullBackend()  # safety net


__all__ = [
    "LOW_CONFIDENCE_THRESHOLD",
    "NullBackend",
    "OCRBackend",
    "OCRResult",
    "TesseractBackend",
    "select_backend",
]
