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


def extract_text(blob_or_path) -> tuple[str, list[str]]:
    """Return (full_text, warnings). full_text='' if no text recovered."""
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
                warnings.append("PDF has no pages.")
                return "", warnings
            for page in pdf.pages:
                t = page.extract_text() or ""
                pages_text.append(t)
    except Exception as e:
        warnings.append(f"pdfplumber failed: {e}")
        return "", warnings

    full = "\n\n".join(p.strip() for p in pages_text if p.strip())
    if not full.strip():
        warnings.append(
            "No text recovered. The PDF may be scanned (image-only). "
            "Side-letter intake supports text PDFs only — re-export from the "
            "source application as a text PDF, or transcribe manually."
        )
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
