"""
PDF side-letter intake.

pdfplumber-based text extraction for side-letter and term-sheet PDFs. The
extracted text is attached verbatim to a SideLetter on the cap table; no
auto-extraction of structured fields, no LLM. The analyst remains in
control of which terms are recorded as overrides.

Scope:
  - Text-based PDFs only. Scanned PDFs (image-only) are out of scope.
    A warning is returned if no text is recovered.
  - Heuristic title detection: first non-blank line is treated as the title
    if it's < 120 characters and doesn't end with a period.
  - Heuristic open-question detection: lines starting with "Q:", "Question:",
    or "TODO" (case-insensitive) are appended to unresolved_questions.

Returns a dict suitable for SideLetter.model_validate().
"""

from __future__ import annotations

import re
from io import BytesIO
from pathlib import Path
from typing import Optional

import pdfplumber


_QUESTION_PREFIX = re.compile(r"^\s*(q\d*\.?:|question[:\s]|todo[:\s])", re.IGNORECASE)


# W2.4 OCR fallback configuration.
# A text yield below this threshold triggers the OCR backend (likely a
# scanned/image PDF).
_OCR_FALLBACK_MIN_CHARS = 100


def extract_text(blob_or_path, *, enable_ocr: bool = True) -> tuple[str, list[str]]:
    """Return (full_text, warnings). full_text='' if no text recovered.

    When pdfplumber's text yield is below `_OCR_FALLBACK_MIN_CHARS` and
    `enable_ocr=True`, route the PDF through the registered OCR backend
    (SYSTEM_SPEC §4.3). When confidence < 0.85 the spec banner code is
    appended to warnings.
    """
    warnings: list[str] = []
    src = blob_or_path
    if isinstance(src, (bytes, bytearray)):
        src = BytesIO(src)
    elif isinstance(src, (str, Path)):
        src = str(src)

    pages_text: list[str] = []
    try:
        with pdfplumber.open(src) as pdf:
            if not pdf.pages:
                warnings.append("pdf-no-pages")
                return "", warnings
            for page in pdf.pages:
                t = page.extract_text() or ""
                pages_text.append(t)
    except Exception as e:
        warnings.append(f"pdf-no-text-recovered: pdfplumber failed: {e}")
        return "", warnings

    full = "\n\n".join(p.strip() for p in pages_text if p.strip())
    if len(full.strip()) < _OCR_FALLBACK_MIN_CHARS and enable_ocr:
        # OCR fallback path. B5 fix from CODE_AUDIT_WAVE_2: spill bytes
        # to a tempfile so user-uploaded PDFs (which arrive as bytes via
        # the Flask upload route) hit the OCR backend rather than
        # silently being dropped with the "image PDF" warning.
        import tempfile

        ocr_path: Optional[Path] = None
        spilled = False
        if isinstance(blob_or_path, (str, Path)):
            ocr_path = Path(str(blob_or_path))
        elif isinstance(blob_or_path, (bytes, bytearray)):
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as fh:
                fh.write(bytes(blob_or_path))
                ocr_path = Path(fh.name)
                spilled = True
        if ocr_path is not None:
            from .ocr import LOW_CONFIDENCE_THRESHOLD, select_backend

            backend = select_backend()
            try:
                ocr_result = backend.ocr_pdf(ocr_path)
            finally:
                if spilled:
                    try:
                        ocr_path.unlink()
                    except OSError:
                        pass
            warnings.append(
                f"pdf-ocr-fallback: backend={ocr_result.backend_name}, "
                f"confidence={ocr_result.confidence:.2f}"
            )
            if ocr_result.warnings:
                warnings.extend(ocr_result.warnings)
            if ocr_result.below_confidence_threshold:
                warnings.append(
                    "pdf-ocr-low-confidence: OCR confidence below "
                    f"{LOW_CONFIDENCE_THRESHOLD}. Recommend manual review."
                )
            if ocr_result.text.strip():
                full = ocr_result.text
            elif not full.strip():
                warnings.append("pdf-no-text-recovered")
        elif not full.strip():
            warnings.append("pdf-no-text-recovered: image PDF + non-path/non-bytes input")
    elif not full.strip():
        warnings.append("pdf-no-text-recovered")
    return full, warnings


def parse_pdf_to_side_letter(
    blob_or_path,
    sl_id: str,
    fallback_title: str = "Imported PDF",
) -> dict:
    """Build a SideLetter-shaped dict from a PDF.

    Result schema:
      {
        "id": sl_id,
        "title": <heuristic title>,
        "summary": <first 280 chars>,
        "body": <full text>,
        "unresolved_questions": [<Q-prefixed lines>],
        "_warnings": [<extraction warnings>],
      }
    """
    full_text, warnings = extract_text(blob_or_path)

    title = fallback_title
    summary: Optional[str] = None
    questions: list[str] = []

    if full_text:
        lines = [ln.strip() for ln in full_text.splitlines() if ln.strip()]
        if lines:
            head = lines[0]
            if len(head) < 120 and not head.endswith("."):
                title = head
        # Summary: first ~280 chars of the body, single-spaced
        summary = " ".join(full_text.split())[:280]
        for ln in lines:
            if _QUESTION_PREFIX.match(ln):
                questions.append(ln)

    return {
        "id": sl_id,
        "title": title,
        "summary": summary,
        "body": full_text,
        "unresolved_questions": questions,
        "_warnings": warnings,
    }
