"""Tests for PDF side-letter intake."""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from src.pdf_intake import extract_text, parse_pdf_to_side_letter


def _build_text_pdf(text: str) -> bytes:
    """Generate a minimal text PDF for tests using reportlab if available, else
    a hand-rolled minimal PDF. Falls back gracefully."""
    try:
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import letter
    except ImportError:
        pytest.skip("reportlab not available — install for PDF intake tests")
    bio = io.BytesIO()
    c = canvas.Canvas(bio, pagesize=letter)
    y = 750
    for line in text.split("\n"):
        c.drawString(50, y, line)
        y -= 14
    c.save()
    return bio.getvalue()


def test_extract_text_from_simple_pdf():
    pdf = _build_text_pdf("Hello World\nSecond line")
    text, warnings = extract_text(pdf)
    assert "Hello World" in text
    assert "Second line" in text
    assert warnings == []


def test_extract_returns_warning_on_empty_pdf():
    # A 0-byte input — pdfplumber will fail
    text, warnings = extract_text(b"")
    assert text == ""
    assert warnings  # at least one warning


def test_parse_pdf_extracts_title_and_body():
    pdf = _build_text_pdf(
        "MFN Side Letter — Series B\n"
        "This letter grants Most Favored Nation rights to Investor X.\n"
        "Scope: applies to subsequent priced rounds at higher PPS only.\n"
        "Q1: does this MFN survive an IPO?\n"
        "Q2: is the trigger automatic or election-based?\n"
    )
    sl = parse_pdf_to_side_letter(pdf, sl_id="SL-PDF-01")
    assert sl["id"] == "SL-PDF-01"
    assert sl["title"] == "MFN Side Letter — Series B"
    assert "Most Favored Nation" in sl["body"]
    assert sl["summary"]
    assert len(sl["unresolved_questions"]) == 2
    assert any("MFN survive an IPO" in q for q in sl["unresolved_questions"])


def test_parse_pdf_with_scan_only_returns_warning():
    """A trivially-malformed PDF should not crash and should emit a warning."""
    sl = parse_pdf_to_side_letter(b"not a real pdf", sl_id="SL-PDF-01")
    assert sl["body"] == ""
    assert sl["_warnings"]


def test_upload_side_letter_route(tmp_path):
    """End-to-end: POST a PDF to /upload_side_letter/<token> and verify it
    appears as a side letter on the cap table + clears no findings."""
    from app import app, SESSIONS

    SESSIONS.clear()
    app.config["TESTING"] = True
    with app.test_client() as c:
        r = c.get("/demo/fixture_01_clean", follow_redirects=False)
        token = r.headers["Location"].split("/")[-1]
        before_count = len(SESSIONS[token]["cap_table"].side_letters)

        pdf_bytes = _build_text_pdf("Test Side Letter\nGrants pro-rata right.")
        r2 = c.post(
            f"/upload_side_letter/{token}",
            data={"pdf": (io.BytesIO(pdf_bytes), "test_letter.pdf")},
            content_type="multipart/form-data",
        )
        assert r2.status_code == 302
        sess = SESSIONS[token]
        after = sess["cap_table"].side_letters
        assert len(after) == before_count + 1
        assert any("pro-rata right" in (sl.body or "") for sl in after)
        assert any(r["code"].startswith("SL-PDF-") for r in sess["resolutions"])
    SESSIONS.clear()


def test_upload_rejects_non_pdf():
    from app import app, SESSIONS

    SESSIONS.clear()
    app.config["TESTING"] = True
    with app.test_client() as c:
        r = c.get("/demo/fixture_01_clean", follow_redirects=False)
        token = r.headers["Location"].split("/")[-1]
        r2 = c.post(
            f"/upload_side_letter/{token}",
            data={"pdf": (io.BytesIO(b"not pdf"), "test.txt")},
            content_type="multipart/form-data",
        )
        # Redirects without changing state
        assert r2.status_code == 302
        sess = SESSIONS[token]
        assert not any(r["code"].startswith("SL-PDF-") for r in sess["resolutions"])
    SESSIONS.clear()
