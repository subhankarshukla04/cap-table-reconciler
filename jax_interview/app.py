"""SEA-India ESOP Cross-Border Compliance Atlas — Flask app.

Demo workflow tool. Stateless, no DB, no auth, no session.

Routes:
  GET  /                     — landing + input form
  POST /resolve              — accept Query inputs, render verdict (HTMX swap)
  GET  /verdict/<scenario>   — load a built-in demo fixture (Praxis/Pelaut/Solstice)
  GET  /sources              — show every rule in the loaded corpus
  GET  /healthz              — liveness probe
"""

from __future__ import annotations

import io
import json
from datetime import date
from pathlib import Path

from flask import Flask, Response, abort, render_template, request, send_file

from src.batch import (
    BatchError,
    batch_to_xlsx,
    parse_csv,
    run_batch,
    sample_csv,
)
from src.corpus import Corpus
from src.engine import resolve
from src.export import verdict_to_xlsx
from src.pdf import verdict_to_pdf
from src.models import Event, Jurisdiction, Query, TaxStatus

app = Flask(__name__)
CORPUS: Corpus = Corpus.load()

FIXTURES_DIR = Path(__file__).parent / "tests" / "fixtures"


# ---- Helpers ---------------------------------------------------------------


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _parse_float(value: str | None) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _parse_int(value: str | None) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _query_from_form(form) -> Query:
    return Query(
        parent_jurisdiction=Jurisdiction(form.get("parent_jurisdiction", "SG")),
        employee_jurisdiction=Jurisdiction(form.get("employee_jurisdiction", "IN")),
        event=Event(form.get("event", "exercise")),
        tax_status=TaxStatus(form.get("tax_status", "resident")),
        grant_date=_parse_date(form.get("grant_date")),
        vesting_date=_parse_date(form.get("vesting_date")),
        event_date=_parse_date(form.get("event_date")),
        fmv_at_event=_parse_float(form.get("fmv_at_event")),
        exercise_price=_parse_float(form.get("exercise_price")),
        options_in_event=_parse_int(form.get("options_in_event")),
    )


# ---- Routes ----------------------------------------------------------------


@app.get("/")
def index():
    return render_template(
        "index.html",
        jurisdictions=[j.value for j in Jurisdiction],
        events=[e.value for e in Event],
        tax_statuses=[s.value for s in TaxStatus],
        corpus_size=len(CORPUS),
    )


@app.post("/resolve")
def do_resolve():
    query = _query_from_form(request.form)
    verdict = resolve(query, CORPUS)
    return render_template("verdict.html", verdict=verdict)


@app.get("/verdict/<scenario>")
def verdict_scenario(scenario: str):
    path = FIXTURES_DIR / f"{scenario}.json"
    if not path.exists():
        abort(404, description=f"Unknown fixture: {scenario}")
    raw = json.loads(path.read_text())
    query = Query.model_validate(raw)
    verdict = resolve(query, CORPUS)
    return render_template("verdict.html", verdict=verdict)


@app.post("/export/xlsx")
def export_xlsx():
    query = _query_from_form(request.form)
    verdict = resolve(query, CORPUS)
    payload = verdict_to_xlsx(verdict)
    filename = (
        f"verdict-{query.parent_jurisdiction.value}-{query.employee_jurisdiction.value}"
        f"-{query.event.value}.xlsx"
    )
    return send_file(
        io.BytesIO(payload),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=filename,
    )


@app.get("/export/xlsx/<scenario>")
def export_xlsx_scenario(scenario: str):
    path = FIXTURES_DIR / f"{scenario}.json"
    if not path.exists():
        abort(404)
    raw = json.loads(path.read_text())
    raw = {k: v for k, v in raw.items() if not k.startswith("_")}
    query = Query.model_validate(raw)
    verdict = resolve(query, CORPUS)
    payload = verdict_to_xlsx(verdict)
    return send_file(
        io.BytesIO(payload),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=f"verdict-{scenario}.xlsx",
    )


@app.get("/pdf/<scenario>")
def pdf_scenario(scenario: str):
    path = FIXTURES_DIR / f"{scenario}.json"
    if not path.exists():
        abort(404)
    raw = json.loads(path.read_text())
    raw = {k: v for k, v in raw.items() if not k.startswith("_")}
    query = Query.model_validate(raw)
    verdict = resolve(query, CORPUS)
    payload = verdict_to_pdf(verdict)
    return send_file(
        io.BytesIO(payload),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"esop-atlas-memo-{scenario}.pdf",
    )


@app.post("/pdf")
def pdf_resolve():
    query = _query_from_form(request.form)
    verdict = resolve(query, CORPUS)
    payload = verdict_to_pdf(verdict)
    filename = (
        f"esop-atlas-memo-{query.parent_jurisdiction.value}-{query.employee_jurisdiction.value}"
        f"-{query.event.value}.pdf"
    )
    return send_file(
        io.BytesIO(payload),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=filename,
    )


@app.get("/print/<scenario>")
def print_scenario(scenario: str):
    """Print-friendly verdict view. Use Cmd+P → Save as PDF."""
    path = FIXTURES_DIR / f"{scenario}.json"
    if not path.exists():
        abort(404)
    raw = json.loads(path.read_text())
    raw = {k: v for k, v in raw.items() if not k.startswith("_")}
    query = Query.model_validate(raw)
    verdict = resolve(query, CORPUS)
    return render_template("print.html", verdict=verdict)


@app.get("/sources")
def sources():
    return render_template("sources.html", rules=CORPUS.all_rules)


@app.get("/batch")
def batch_form():
    return render_template("batch.html", corpus_size=len(CORPUS))


@app.post("/batch/run")
def batch_run():
    upload = request.files.get("csv")
    if upload is None or upload.filename == "":
        return render_template(
            "batch.html",
            corpus_size=len(CORPUS),
            error="No file uploaded. Choose a CSV with the columns listed below.",
        )
    try:
        text = upload.stream.read().decode("utf-8-sig")
    except UnicodeDecodeError:
        return render_template(
            "batch.html",
            corpus_size=len(CORPUS),
            error="File could not be read as UTF-8 text.",
        )

    try:
        parsed = parse_csv(io.StringIO(text))
    except BatchError as e:
        return render_template("batch.html", corpus_size=len(CORPUS), error=str(e))

    results = run_batch(parsed, CORPUS)
    payload = batch_to_xlsx(results)
    return send_file(
        io.BytesIO(payload),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=f"esop-atlas-batch-{date.today().isoformat()}.xlsx",
    )


@app.get("/batch/sample")
def batch_sample():
    return Response(
        sample_csv(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=esop-atlas-batch-template.csv"},
    )


@app.get("/healthz")
def healthz():
    jurisdictions = sorted({r.taxing_jurisdiction.value for r in CORPUS.all_rules})
    by_jur: dict[str, int] = {}
    for r in CORPUS.all_rules:
        by_jur[r.taxing_jurisdiction.value] = by_jur.get(r.taxing_jurisdiction.value, 0) + 1
    return {
        "status": "ok",
        "corpus_size": len(CORPUS),
        "jurisdictions": jurisdictions,
        "rules_by_jurisdiction": by_jur,
        "fixtures": sorted(p.stem for p in FIXTURES_DIR.glob("*.json")),
        "version": "0.2.0",
    }


@app.errorhandler(404)
def not_found(e):
    return render_template("error.html", code=404, message=str(getattr(e, "description", "Not found"))), 404


@app.errorhandler(500)
def server_error(e):
    return render_template("error.html", code=500, message="Internal server error — check the server log."), 500


if __name__ == "__main__":
    app.run(debug=True, port=5151)
