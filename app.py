"""
Cap Table Reconciler — Flask app.

Local-first tool for screen-shared demo. Stateless — uploaded files are kept
in an in-memory session dict keyed by a short token, not persisted to disk.
No auth, no users, no DB.

Routes:
  GET  /                     — landing + upload form
  POST /upload               — accept .xlsx, parse, store in session
  GET  /review/<token>       — column mapping + parse warnings + checklist
  GET  /waterfall/<token>    — breakpoints + per-tranche allocation
  GET  /export/<token>.json  — clean structured output as JSON
  GET  /export/<token>.xlsx  — clean structured output as Excel
  GET  /demo/<fixture>       — load a built-in fixture for the demo
  GET  /healthz              — liveness probe
"""

from __future__ import annotations

import io
import json
import secrets
from dataclasses import asdict
from pathlib import Path

from flask import (
    Flask,
    Response,
    abort,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)

from src.audit_memo import build_audit_memo
from src.checklist import run_checklist
from src.diff import diff_cap_tables
from src.formula_workbook import build_formula_workbook
from src.parser import load_from_canonical_json, parse_excel
from src.pdf_intake import parse_pdf_to_side_letter
from src.persistence import SessionStore
from src.waterfall import breakpoint_explanations, chart_payload, compute_waterfall


app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024  # 8 MB upload cap


@app.after_request
def _no_cache(resp):
    resp.headers["Cache-Control"] = "no-store, max-age=0"
    return resp

# SQLite-backed session store. Survives server restart.
_DB_PATH = Path(__file__).parent / "data" / "sessions.db"
SESSIONS: SessionStore = SessionStore(_DB_PATH)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ---- Helpers ----------------------------------------------------------------


def _new_token() -> str:
    return secrets.token_urlsafe(8)


def _store_session(cap_table, parse_report=None, raw_excerpt=None, fixture_id=None) -> str:
    token = _new_token()
    SESSIONS[token] = {
        "cap_table": cap_table,
        "original_cap_table": cap_table,
        "parse_report": parse_report,
        "waterfall": compute_waterfall(cap_table),
        "findings": run_checklist(cap_table),
        "raw_excerpt": raw_excerpt,
        "fixture_id": fixture_id,
        "resolutions": [],
    }
    return token


def _read_xlsx_raw_excerpt(path: Path, max_rows: int = 12) -> dict | None:
    """Read the first N rows of the cap table tab as raw values, for the
    'before/after' panel on the review page. Returns None if the file isn't
    parseable or doesn't have a recognized cap table tab."""
    try:
        from openpyxl import load_workbook
        from src.parser import _detect_cap_table_sheet, _normalize, CAP_TABLE_TAB_NAMES

        wb = load_workbook(path, data_only=True)
        sheet = _detect_cap_table_sheet(wb)
        if sheet is None:
            return None
        ws = wb[sheet]
        rows = []
        for i, row in enumerate(ws.iter_rows(values_only=True)):
            if i >= max_rows:
                break
            rows.append(["" if v is None else str(v) for v in row])
        return {"sheet": sheet, "rows": rows}
    except Exception:
        return None


def _recompute_session(token: str) -> None:
    sess = SESSIONS[token]
    sess["waterfall"] = compute_waterfall(sess["cap_table"])
    sess["findings"] = run_checklist(sess["cap_table"])
    SESSIONS.flush(token)


def _format_money(value: float, symbol: str = "$") -> str:
    if value is None:
        return ""
    if abs(value) >= 1_000_000_000:
        return f"{symbol}{value/1_000_000_000:,.2f}B"
    if abs(value) >= 1_000_000:
        return f"{symbol}{value/1_000_000:,.2f}M"
    if abs(value) >= 1_000:
        return f"{symbol}{value/1_000:,.0f}K"
    return f"{symbol}{value:,.2f}"


@app.template_filter("money")
def money_filter(value, symbol="$"):
    return _format_money(value, symbol)


@app.template_filter("pct")
def pct_filter(value):
    if value is None:
        return ""
    return f"{value:.2f}%"


@app.template_filter("commas")
def commas_filter(value):
    if value is None:
        return ""
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return str(value)


# ---- Routes -----------------------------------------------------------------


@app.get("/")
def index():
    return render_template(
        "index.html",
        fixtures=[
            {"id": "fixture_01_clean", "name": "Solstice Labs (clean baseline)"},
            {"id": "fixture_02_typical_messy", "name": "Pelaut Logistics (typical messy)"},
            {"id": "fixture_03_edge_case", "name": "Bandhan Ventures (SEA edge case)"},
            {"id": "fixture_04_down_round_ratchet", "name": "Surya Foods (down-round + triggered ratchet)"},
            {"id": "fixture_05_delaware_double_cap", "name": "AeroFreight Inc. (Delaware double participating-cap)"},
        ],
    )


@app.post("/upload")
def upload():
    file = request.files.get("file")
    if file is None or file.filename == "":
        return render_template("index.html", error="No file uploaded.")
    if not file.filename.lower().endswith(".xlsx"):
        return render_template("index.html", error="Only .xlsx files are supported.")

    try:
        data = file.read()
        tmp = Path("/tmp") / f"cap_{secrets.token_hex(4)}.xlsx"
        tmp.write_bytes(data)
        try:
            cap_table, report = parse_excel(tmp)
            raw_excerpt = _read_xlsx_raw_excerpt(tmp)
        finally:
            try:
                tmp.unlink()
            except OSError:
                pass
    except Exception as e:
        return render_template("index.html", error=f"Could not parse file: {e}")

    token = _store_session(cap_table, report, raw_excerpt=raw_excerpt)
    return redirect(url_for("review", token=token))


@app.get("/demo/<fixture_id>")
def demo(fixture_id: str):
    valid = {
        "fixture_01_clean",
        "fixture_02_typical_messy",
        "fixture_03_edge_case",
        "fixture_04_down_round_ratchet",
        "fixture_05_delaware_double_cap",
    }
    if fixture_id not in valid:
        abort(404)
    fdir = FIXTURES_DIR / fixture_id
    cap_table = load_from_canonical_json(fdir / "cap_table_input.json")

    parse_report = None
    raw_excerpt = None
    xlsx = fdir / "cap_table.xlsx"
    if xlsx.exists():
        try:
            _, parse_report = parse_excel(xlsx)
        except Exception:
            parse_report = None
        raw_excerpt = _read_xlsx_raw_excerpt(xlsx)

    token = _store_session(cap_table, parse_report=parse_report, raw_excerpt=raw_excerpt, fixture_id=fixture_id)
    return redirect(url_for("review", token=token))


@app.get("/review/<token>")
def review(token: str):
    sess = SESSIONS.get(token)
    if sess is None:
        return render_template("session_expired.html", token=token), 404
    return render_template(
        "review.html",
        token=token,
        cap_table=sess["cap_table"],
        parse_report=sess["parse_report"],
        findings=sess["findings"],
        raw_excerpt=sess.get("raw_excerpt"),
        resolutions=sess.get("resolutions", []),
    )


@app.post("/resolve/<token>/safe/<safe_id>")
def resolve_safe(token: str, safe_id: str):
    """Apply an analyst-entered SAFE conversion to the in-memory cap table.

    The analyst supplies the resulting share count and the existing share
    class name to add the converted shares to (typically the most-recent
    preferred class — e.g., 'Series B Preferred'). The SAFE is removed from
    outstanding instruments. The waterfall + findings are recomputed.

    This is in-memory only; the underlying fixture file is not modified.
    """
    sess = SESSIONS.get(token)
    if sess is None:
        return render_template("session_expired.html", token=token), 404
    cap_table = sess["cap_table"]
    safe = next((s for s in cap_table.safes_outstanding if s.id == safe_id), None)
    if safe is None:
        abort(404)

    try:
        added_shares = int(request.form.get("shares", "0").replace(",", ""))
    except ValueError:
        added_shares = 0
    target_class_name = (request.form.get("target_class") or "").strip()
    note_text = (request.form.get("note") or "").strip() or None

    if added_shares <= 0 or not target_class_name:
        return redirect(url_for("review", token=token))

    target = next((sc for sc in cap_table.share_classes if sc.name == target_class_name), None)
    if target is None:
        return redirect(url_for("review", token=token))

    new_classes = []
    for sc in cap_table.share_classes:
        if sc.name == target_class_name:
            new_classes.append(sc.model_copy(update={"shares_outstanding": sc.shares_outstanding + added_shares}))
        else:
            new_classes.append(sc)

    new_safes = [s for s in cap_table.safes_outstanding if s.id != safe_id]
    sess["cap_table"] = cap_table.model_copy(update={"share_classes": new_classes, "safes_outstanding": new_safes})
    sess["resolutions"].append(
        {
            "code": f"SAFE-UNCONVERTED-{safe_id}",
            "summary": (
                f"Resolved: SAFE {safe_id} (principal {safe.principal:,.0f}) "
                f"recorded as {added_shares:,} additional shares of {target_class_name}."
                + (f" Note: {note_text}" if note_text else "")
            ),
        }
    )
    _recompute_session(token)
    return redirect(url_for("review", token=token))


@app.post("/resolve/<token>/anti_dilution/<path:class_name>")
def resolve_anti_dilution(token: str, class_name: str):
    """Set the anti-dilution variant on a preferred class.

    Resolves AD-MISSING-* blockers by recording the variant from charter
    (broad-based-weighted-average / narrow-based-weighted-average / full_ratchet)
    plus an optional source citation.
    """
    sess = SESSIONS.get(token)
    if sess is None:
        return render_template("session_expired.html", token=token), 404
    cap_table = sess["cap_table"]
    target = next((sc for sc in cap_table.share_classes if sc.name == class_name), None)
    if target is None or target.type.value != "preferred":
        abort(404)

    from src.models import AntiDilution, AntiDilutionVariant

    variant_str = (request.form.get("variant") or "").strip()
    citation = (request.form.get("citation") or "").strip() or None
    try:
        variant = AntiDilutionVariant(variant_str)
    except ValueError:
        return redirect(url_for("review", token=token))

    new_ad = AntiDilution(variant=variant, notes=citation)
    new_classes = []
    for sc in cap_table.share_classes:
        if sc.name == class_name:
            new_classes.append(sc.model_copy(update={"anti_dilution": new_ad}))
        else:
            new_classes.append(sc)
    sess["cap_table"] = cap_table.model_copy(update={"share_classes": new_classes})
    sess["resolutions"].append(
        {
            "code": f"AD-MISSING-{class_name}",
            "summary": (
                f"Resolved: {class_name} anti-dilution recorded as "
                f"{variant.value.replace('_', ' ')}."
                + (f" Source: {citation}" if citation else "")
            ),
        }
    )
    _recompute_session(token)
    return redirect(url_for("review", token=token))


@app.post("/resolve/<token>/warrant/<warrant_id>")
def resolve_warrant(token: str, warrant_id: str):
    """Resolve a warrant blocker: either add the underlying shares to a class
    or document an explicit exclusion policy.
    """
    sess = SESSIONS.get(token)
    if sess is None:
        return render_template("session_expired.html", token=token), 404
    cap_table = sess["cap_table"]
    warrant = next((w for w in cap_table.warrants_outstanding if w.id == warrant_id), None)
    if warrant is None:
        abort(404)

    action = (request.form.get("action") or "").strip()
    note = (request.form.get("note") or "").strip() or None

    if action == "add_as_shares":
        target_class_name = (request.form.get("target_class") or "").strip()
        try:
            shares = int((request.form.get("shares") or str(warrant.shares)).replace(",", ""))
        except ValueError:
            shares = warrant.shares
        target = next((sc for sc in cap_table.share_classes if sc.name == target_class_name), None)
        if target is None or shares <= 0:
            return redirect(url_for("review", token=token))
        new_classes = []
        for sc in cap_table.share_classes:
            if sc.name == target_class_name:
                new_classes.append(sc.model_copy(update={"shares_outstanding": sc.shares_outstanding + shares}))
            else:
                new_classes.append(sc)
        new_warrants = [w for w in cap_table.warrants_outstanding if w.id != warrant_id]
        sess["cap_table"] = cap_table.model_copy(
            update={"share_classes": new_classes, "warrants_outstanding": new_warrants}
        )
        summary = (
            f"Resolved: warrant {warrant_id} ({warrant.holder}) recorded as "
            f"{shares:,} additional shares of {target_class_name}."
        )
    elif action == "document_exclusion":
        new_warrants = [w for w in cap_table.warrants_outstanding if w.id != warrant_id]
        sess["cap_table"] = cap_table.model_copy(update={"warrants_outstanding": new_warrants})
        summary = (
            f"Resolved: warrant {warrant_id} ({warrant.holder}) documented as "
            f"excluded from fully-diluted share count."
        )
    else:
        return redirect(url_for("review", token=token))

    sess["resolutions"].append(
        {
            "code": f"WARRANT-{warrant_id}",
            "summary": summary + (f" Note: {note}" if note else ""),
        }
    )
    _recompute_session(token)
    return redirect(url_for("review", token=token))


@app.post("/resolve/<token>/side_letter/<sl_id>")
def resolve_side_letter(token: str, sl_id: str):
    """Mark side-letter scope questions as adjudicated, capturing the analyst's
    answer for each open question. Clears unresolved_questions on the side
    letter so the SIDE-LETTER-SCOPE finding clears.
    """
    sess = SESSIONS.get(token)
    if sess is None:
        return render_template("session_expired.html", token=token), 404
    cap_table = sess["cap_table"]
    sl = next((s for s in cap_table.side_letters if s.id == sl_id), None)
    if sl is None:
        abort(404)

    resolutions_text = (request.form.get("resolutions_text") or "").strip()
    if not resolutions_text:
        return redirect(url_for("review", token=token))

    new_sls = []
    for s in cap_table.side_letters:
        if s.id == sl_id:
            existing_body = s.body or ""
            new_body = (existing_body + "\n\nAnalyst-recorded resolutions:\n" + resolutions_text).strip()
            new_sls.append(s.model_copy(update={"body": new_body, "unresolved_questions": []}))
        else:
            new_sls.append(s)
    sess["cap_table"] = cap_table.model_copy(update={"side_letters": new_sls})
    sess["resolutions"].append(
        {
            "code": f"SIDE-LETTER-SCOPE-{sl_id}",
            "summary": (
                f"Resolved: side letter {sl_id} ('{sl.title}') scope questions "
                f"adjudicated and recorded in body."
            ),
        }
    )
    _recompute_session(token)
    return redirect(url_for("review", token=token))


@app.post("/resolve/<token>/pool/<path:pool_name>")
def resolve_pool(token: str, pool_name: str):
    """Resolve a stale-option-pool warning: either document the gap in the
    audit memo (no data mutation) or refresh the grant date to reflect a
    post-round grant tranche.
    """
    sess = SESSIONS.get(token)
    if sess is None:
        return render_template("session_expired.html", token=token), 404
    cap_table = sess["cap_table"]
    pool = next((sc for sc in cap_table.share_classes if sc.name == pool_name), None)
    if pool is None or pool.type.value != "option_pool_granted":
        abort(404)

    action = (request.form.get("action") or "").strip()
    note = (request.form.get("note") or "").strip() or None

    if action == "documented_in_memo":
        summary = (
            f"Resolved: option pool {pool_name} stale-grant gap documented in "
            f"audit memo. No share count adjustment."
        )
        # No mutation — this is a documentation-only resolution.
        # We mark it resolved by recording the resolution entry; the underlying
        # finding will continue to fire until grant date is refreshed. To clear
        # the warning, append a note to the pool's note field so the rule still
        # fires but the analyst record shows it's been adjudicated.
    elif action == "update_grant_date":
        from datetime import date as _date

        new_date_str = (request.form.get("new_date") or "").strip()
        try:
            new_date = _date.fromisoformat(new_date_str)
        except ValueError:
            return redirect(url_for("review", token=token))
        new_classes = []
        for sc in cap_table.share_classes:
            if sc.name == pool_name:
                new_classes.append(sc.model_copy(update={"issue_date": new_date}))
            else:
                new_classes.append(sc)
        sess["cap_table"] = cap_table.model_copy(update={"share_classes": new_classes})
        summary = (
            f"Resolved: option pool {pool_name} most-recent grant date updated "
            f"to {new_date.isoformat()}."
        )
    else:
        return redirect(url_for("review", token=token))

    sess["resolutions"].append(
        {
            "code": f"POOL-STALE-{pool_name}",
            "summary": summary + (f" Note: {note}" if note else ""),
        }
    )
    _recompute_session(token)
    return redirect(url_for("review", token=token))


@app.post("/upload_side_letter/<token>")
def upload_side_letter(token: str):
    """Accept a PDF and append it as a SideLetter to the cap table.

    Text-PDFs only. Scanned PDFs return a warning and are still attached as
    empty body — the analyst can edit through the side-letter resolve form
    or re-upload a re-OCR'd version.
    """
    sess = SESSIONS.get(token)
    if sess is None:
        return render_template("session_expired.html", token=token), 404
    file = request.files.get("pdf")
    if file is None or file.filename == "":
        return redirect(url_for("review", token=token))
    if not file.filename.lower().endswith(".pdf"):
        return redirect(url_for("review", token=token))

    blob = file.read()
    cap_table = sess["cap_table"]
    existing_ids = {sl.id for sl in cap_table.side_letters}
    seq = 1
    while f"SL-PDF-{seq:02d}" in existing_ids:
        seq += 1
    sl_data = parse_pdf_to_side_letter(
        blob,
        sl_id=f"SL-PDF-{seq:02d}",
        fallback_title=file.filename,
    )
    warnings = sl_data.pop("_warnings", [])

    from src.models import SideLetter

    new_sl = SideLetter.model_validate(sl_data)
    new_letters = list(cap_table.side_letters) + [new_sl]
    sess["cap_table"] = cap_table.model_copy(update={"side_letters": new_letters})
    summary_msg = (
        f"Imported PDF '{file.filename}' as side letter {new_sl.id} "
        f"({len(sl_data.get('body') or '')} chars)."
    )
    if warnings:
        summary_msg += f" Warnings: {' | '.join(warnings)}"
    sess["resolutions"].append({"code": new_sl.id, "summary": summary_msg})
    _recompute_session(token)
    return redirect(url_for("review", token=token))


@app.get("/waterfall/<token>")
def waterfall(token: str):
    sess = SESSIONS.get(token)
    if sess is None:
        return render_template("session_expired.html", token=token), 404
    chart = chart_payload(sess["cap_table"], sess["waterfall"])
    explanations = breakpoint_explanations(sess["cap_table"], sess["waterfall"])
    return render_template(
        "waterfall.html",
        token=token,
        cap_table=sess["cap_table"],
        waterfall=sess["waterfall"],
        chart=chart,
        chart_json=json.dumps(chart),
        explanations=explanations,
    )


@app.post("/whatif/<token>")
def whatif(token: str):
    """In-browser sensitivity slider. Recomputes the waterfall against an
    overridden cap table without persisting. Returns an HTML fragment for
    HTMX to swap into the waterfall page.

    Form fields:
      shares_<class_name>   — override share count
      lp_mult_<class_name>  — override LP multiple (preferred only)
    """
    sess = SESSIONS.get(token)
    if sess is None:
        return Response("Session expired.", status=404)
    cap_table = sess["cap_table"]
    baseline = sess["waterfall"]

    new_classes = []
    changed: list[str] = []
    for sc in cap_table.share_classes:
        upd: dict = {}
        new_shares = sc.shares_outstanding
        sh_raw = (request.form.get(f"shares_{sc.name}") or "").replace(",", "").strip()
        if sh_raw:
            try:
                sh = int(float(sh_raw))
                if sh >= 0 and sh != sc.shares_outstanding:
                    upd["shares_outstanding"] = sh
                    new_shares = sh
                    changed.append(f"{sc.name} shares: {sc.shares_outstanding:,} → {sh:,}")
            except ValueError:
                pass
        if sc.type.value == "preferred" and sc.liquidation_preference is not None:
            old_lp = sc.liquidation_preference
            new_mult = old_lp.multiple
            mu_raw = (request.form.get(f"lp_mult_{sc.name}") or "").strip()
            if mu_raw:
                try:
                    mu = float(mu_raw)
                    if mu > 0 and abs(mu - old_lp.multiple) > 1e-9:
                        new_mult = mu
                        changed.append(f"{sc.name} LP mult: {old_lp.multiple}× → {mu}×")
                except ValueError:
                    pass
            shares_ratio = (new_shares / sc.shares_outstanding) if sc.shares_outstanding else 1.0
            mult_ratio = new_mult / old_lp.multiple if old_lp.multiple else 1.0
            if abs(shares_ratio * mult_ratio - 1.0) > 1e-9:
                upd["liquidation_preference"] = old_lp.model_copy(update={
                    "multiple": new_mult,
                    "amount": old_lp.amount * shares_ratio * mult_ratio,
                })
        new_classes.append(sc.model_copy(update=upd) if upd else sc)

    scenario_ct = cap_table.model_copy(update={"share_classes": new_classes})
    scenario_wf = compute_waterfall(scenario_ct)
    scenario_chart = chart_payload(scenario_ct, scenario_wf)

    return render_template(
        "_whatif_panel.html",
        cap_table=cap_table,
        baseline=baseline,
        scenario=scenario_wf,
        changed=changed,
        scenario_chart_json=json.dumps(scenario_chart),
    )


@app.get("/export/<token>.xlsx")
def export_xlsx(token: str):
    sess = SESSIONS.get(token)
    if sess is None:
        return render_template("session_expired.html", token=token), 404
    return _build_clean_xlsx(sess, token)


def _build_clean_xlsx_bytes(sess: dict) -> bytes:
    """Generate the static clean .xlsx and return raw bytes."""
    bio = io.BytesIO()
    _build_clean_workbook(sess).save(bio)
    return bio.getvalue()


def _build_clean_xlsx(sess: dict, token: str):
    """Generate a clean structured-output .xlsx for the analyst to hand off."""
    bio = io.BytesIO()
    _build_clean_workbook(sess).save(bio)
    bio.seek(0)
    return send_file(
        bio,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=f"cap_table_clean_{token}.xlsx",
    )


def _build_clean_workbook(sess: dict):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

    cap_table = sess["cap_table"]
    waterfall_result = sess["waterfall"]
    findings = sess["findings"]

    wb = Workbook()
    thin = Side(border_style="thin", color="E5E7EB")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    header_fill = PatternFill(start_color="1F2937", end_color="1F2937", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF")

    # Company tab
    ws = wb.active
    ws.title = "Company"
    rows = [
        ("Company", cap_table.company.name),
        ("Jurisdiction", cap_table.company.jurisdiction or ""),
        ("Sector", cap_table.company.sector or ""),
        ("Stage", cap_table.company.stage or ""),
        ("Valuation date", str(cap_table.company.valuation_date or "")),
        ("Currency", cap_table.company.currency),
        ("Total fully diluted shares", cap_table.total_fully_diluted_for_waterfall),
        ("LP total", waterfall_result.lp_total),
        ("Breakpoints", len(waterfall_result.breakpoints)),
        ("Tranches", len(waterfall_result.tranches)),
        ("Findings (blockers)", sum(1 for f in findings if f.severity == "blocker")),
        ("Findings (warnings)", sum(1 for f in findings if f.severity == "warning")),
        ("Findings (info)", sum(1 for f in findings if f.severity == "info")),
    ]
    for r in rows:
        ws.append(list(r))
    for row in ws.iter_rows(min_row=1, max_row=ws.max_row, max_col=1):
        for cell in row:
            cell.font = Font(bold=True)
    ws.column_dimensions["A"].width = 28
    ws.column_dimensions["B"].width = 40

    # Cap Table tab
    ws_ct = wb.create_sheet("Cap Table (clean)")
    ws_ct.append([
        "Class",
        "Type",
        "Shares",
        "Issue Price",
        "Issue Date",
        "Seniority",
        "LP Multiple",
        "LP Type",
        "LP Amount",
        "Cap Multiple",
        "Anti-Dilution",
        "Conversion Ratio",
        "Voting Differential",
    ])
    for cell in ws_ct[1]:
        cell.fill = header_fill
        cell.font = header_font
    for sc in cap_table.share_classes:
        lp = sc.liquidation_preference
        ad = sc.anti_dilution
        ws_ct.append([
            sc.name,
            sc.type.value,
            sc.shares_outstanding,
            sc.issue_price,
            str(sc.issue_date) if sc.issue_date else "",
            sc.seniority_rank if sc.type.value == "preferred" else "",
            lp.multiple if lp else "",
            lp.type.value if lp else "",
            lp.amount if lp else "",
            lp.cap_multiple if lp and lp.cap_multiple else "",
            ad.variant.value if ad and ad.variant else "",
            sc.conversion_ratio if sc.conversion_ratio else "",
            sc.voting_differential or "",
        ])
    for col, w in zip("ABCDEFGHIJKLM", [26, 18, 14, 14, 14, 12, 12, 22, 18, 14, 28, 14, 40]):
        ws_ct.column_dimensions[col].width = w
    for row in ws_ct.iter_rows(min_row=1, max_row=ws_ct.max_row, max_col=ws_ct.max_column):
        for cell in row:
            cell.border = border
            if cell.row > 1 and cell.column == 3:
                cell.number_format = "#,##0"
            if cell.row > 1 and cell.column in (4, 9):
                cell.number_format = f"{cap_table.company.currency_symbol}#,##0.00"

    # Breakpoints tab
    ws_bp = wb.create_sheet("Breakpoints")
    ws_bp.append(["ID", "Value", "Event"])
    for cell in ws_bp[1]:
        cell.fill = header_fill
        cell.font = header_font
    for bp in waterfall_result.breakpoints:
        ws_bp.append([bp.id, bp.value, bp.event])
    ws_bp.column_dimensions["A"].width = 8
    ws_bp.column_dimensions["B"].width = 18
    ws_bp.column_dimensions["C"].width = 50
    for row in ws_bp.iter_rows(min_row=1, max_row=ws_bp.max_row, max_col=3):
        for cell in row:
            cell.border = border
            if cell.row > 1 and cell.column == 2:
                cell.number_format = f"{cap_table.company.currency_symbol}#,##0"

    # Tranches tab
    ws_t = wb.create_sheet("Tranches")
    class_names = [sc.name for sc in cap_table.share_classes if not sc.excluded_from_waterfall]
    ws_t.append(["Tranche", "Range Low", "Range High", "Description"] + class_names)
    for cell in ws_t[1]:
        cell.fill = header_fill
        cell.font = header_font
    for tr in waterfall_result.tranches:
        row = [tr.id, tr.range_low, (tr.range_high if tr.range_high is not None else ""), tr.description]
        for name in class_names:
            row.append(tr.marginal_allocation_pct.get(name, 0.0))
        ws_t.append(row)
    ws_t.column_dimensions["A"].width = 8
    ws_t.column_dimensions["B"].width = 16
    ws_t.column_dimensions["C"].width = 16
    ws_t.column_dimensions["D"].width = 50
    for i, _ in enumerate(class_names):
        ws_t.column_dimensions[chr(ord("E") + i)].width = 14
    for row in ws_t.iter_rows(min_row=1, max_row=ws_t.max_row, max_col=ws_t.max_column):
        for cell in row:
            cell.border = border
            if cell.row > 1 and cell.column in (2, 3):
                cell.number_format = f"{cap_table.company.currency_symbol}#,##0"
            if cell.row > 1 and cell.column >= 5:
                cell.number_format = "0.00\"%\""

    # Findings tab
    ws_f = wb.create_sheet("Findings")
    ws_f.append(["Code", "Severity", "Category", "Summary", "Detail"])
    for cell in ws_f[1]:
        cell.fill = header_fill
        cell.font = header_font
    for f in findings:
        ws_f.append([f.code, f.severity, f.category, f.summary, f.detail or ""])
    ws_f.column_dimensions["A"].width = 24
    ws_f.column_dimensions["B"].width = 12
    ws_f.column_dimensions["C"].width = 28
    ws_f.column_dimensions["D"].width = 60
    ws_f.column_dimensions["E"].width = 80
    for row in ws_f.iter_rows(min_row=1, max_row=ws_f.max_row, max_col=5):
        for cell in row:
            cell.border = border
            cell.alignment = Alignment(wrap_text=True, vertical="top")

    # Convertibles tab — SAFEs, warrants, and convertible notes outstanding.
    ws_cv = wb.create_sheet("Convertibles")
    ws_cv.append(["ID", "Type", "Holder", "Principal", "Valuation Cap", "Discount %",
                  "Strike Price", "Shares", "Share Class", "Issue Date", "Expiry Date", "Notes"])
    for cell in ws_cv[1]:
        cell.fill = header_fill
        cell.font = header_font
    for s in cap_table.safes_outstanding:
        ws_cv.append([
            s.id, "SAFE", "", s.principal, s.valuation_cap or "",
            s.discount_rate if s.discount_rate is not None else "",
            "", "", "", str(s.issue_date) if s.issue_date else "", "", s.notes or "",
        ])
    for w in cap_table.warrants_outstanding:
        ws_cv.append([
            w.id, "Warrant", w.holder, "", "", "",
            w.strike_price, w.shares, w.share_class,
            str(w.issue_date) if w.issue_date else "",
            str(w.expiry_date) if w.expiry_date else "",
            w.notes or "",
        ])
    for n in cap_table.convertible_notes_outstanding:
        ws_cv.append([
            n.id, "Convertible Note", "", n.principal, n.valuation_cap or "",
            n.discount_rate if n.discount_rate is not None else "",
            "", "", "", str(n.issue_date) if n.issue_date else "", "", n.notes or "",
        ])
    for col, w_ in zip("ABCDEFGHIJKL", [22, 18, 30, 14, 16, 12, 14, 12, 18, 14, 14, 50]):
        ws_cv.column_dimensions[col].width = w_
    sym = cap_table.company.currency_symbol
    for row in ws_cv.iter_rows(min_row=1, max_row=ws_cv.max_row, max_col=ws_cv.max_column):
        for cell in row:
            cell.border = border
            if cell.row > 1 and cell.column in (4, 5, 7):
                cell.number_format = f"{sym}#,##0.00"
            if cell.row > 1 and cell.column == 8:
                cell.number_format = "#,##0"
            if cell.row > 1 and cell.column == 6 and isinstance(cell.value, (int, float)):
                cell.number_format = "0.00%"

    # Side Letters tab
    ws_sl = wb.create_sheet("Side Letters")
    ws_sl.append(["ID", "Title", "Summary", "Body"])
    for cell in ws_sl[1]:
        cell.fill = header_fill
        cell.font = header_font
    for sl in cap_table.side_letters:
        ws_sl.append([sl.id, sl.title, sl.summary or "", sl.body or ""])
    for col, w_ in zip("ABCD", [16, 40, 60, 80]):
        ws_sl.column_dimensions[col].width = w_
    for row in ws_sl.iter_rows(min_row=1, max_row=ws_sl.max_row, max_col=4):
        for cell in row:
            cell.border = border
            cell.alignment = Alignment(wrap_text=True, vertical="top")

    return wb


@app.get("/export/<token>_live.xlsx")
def export_live_xlsx(token: str):
    """Live formula workbook — breakpoints, allocations, and chart driven by
    formulas referencing editable input cells. Edit Inputs.D, watch the chart
    update natively in Excel.
    """
    sess = SESSIONS.get(token)
    if sess is None:
        return render_template("session_expired.html", token=token), 404
    wb = build_formula_workbook(sess["cap_table"], sess["waterfall"])
    bio = io.BytesIO()
    wb.save(bio)
    bio.seek(0)
    company_slug = (sess["cap_table"].company.name or "captable").replace(" ", "_").replace(".", "")
    return send_file(
        bio,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=f"{company_slug}_live_{token}.xlsx",
    )


@app.get("/export/<token>.json")
def export_json(token: str):
    sess = SESSIONS.get(token)
    if sess is None:
        return render_template("session_expired.html", token=token), 404
    payload = {
        "company": sess["cap_table"].company.model_dump(mode="json"),
        "share_classes": [sc.model_dump(mode="json") for sc in sess["cap_table"].share_classes],
        "side_letters": [sl.model_dump(mode="json") for sl in sess["cap_table"].side_letters],
        "safes_outstanding": [s.model_dump(mode="json") for s in sess["cap_table"].safes_outstanding],
        "warrants_outstanding": [w.model_dump(mode="json") for w in sess["cap_table"].warrants_outstanding],
        "convertible_notes_outstanding": [n.model_dump(mode="json") for n in sess["cap_table"].convertible_notes_outstanding],
        "waterfall": {
            "lp_total": sess["waterfall"].lp_total,
            "total_fully_diluted_shares": sess["waterfall"].total_fully_diluted_shares,
            "breakpoints": [
                {"id": bp.id, "value": bp.value, "event": bp.event}
                for bp in sess["waterfall"].breakpoints
            ],
            "tranches": [
                {
                    "id": t.id,
                    "range_low": t.range_low,
                    "range_high": t.range_high,
                    "description": t.description,
                    "common_pool_shares": t.common_pool_shares,
                    "marginal_allocation_pct": t.marginal_allocation_pct,
                }
                for t in sess["waterfall"].tranches
            ],
            "conversion_thresholds": sess["waterfall"].conversion_thresholds,
            "cap_reach_thresholds": sess["waterfall"].cap_reach_thresholds,
            "pure_conversion_thresholds": sess["waterfall"].pure_conversion_thresholds,
        },
        "findings": [asdict(f) for f in sess["findings"]],
    }
    return Response(
        json.dumps(payload, indent=2, default=str),
        mimetype="application/json",
        headers={"Content-Disposition": f'attachment; filename="cap_table_{token}.json"'},
    )


@app.get("/export/<token>.zip")
def export_bundle_zip(token: str):
    """One-click bundle: json + static xlsx + live xlsx + audit memo.

    The handoff artifact: drop this onto the next reviewer's desk and they
    have the structured data, the live-edit workbook, and the memo skeleton
    in one file.
    """
    sess = SESSIONS.get(token)
    if sess is None:
        return render_template("session_expired.html", token=token), 404

    import zipfile

    cap_table = sess["cap_table"]
    waterfall = sess["waterfall"]
    findings = sess["findings"]
    resolutions = sess.get("resolutions", [])

    # JSON payload
    json_payload = {
        "company": cap_table.company.model_dump(mode="json"),
        "share_classes": [sc.model_dump(mode="json") for sc in cap_table.share_classes],
        "side_letters": [sl.model_dump(mode="json") for sl in cap_table.side_letters],
        "safes_outstanding": [s.model_dump(mode="json") for s in cap_table.safes_outstanding],
        "warrants_outstanding": [w.model_dump(mode="json") for w in cap_table.warrants_outstanding],
        "convertible_notes_outstanding": [n.model_dump(mode="json") for n in cap_table.convertible_notes_outstanding],
        "waterfall": {
            "lp_total": waterfall.lp_total,
            "total_fully_diluted_shares": waterfall.total_fully_diluted_shares,
            "breakpoints": [
                {"id": bp.id, "value": bp.value, "event": bp.event}
                for bp in waterfall.breakpoints
            ],
            "tranches": [
                {
                    "id": t.id,
                    "range_low": t.range_low,
                    "range_high": t.range_high,
                    "description": t.description,
                    "common_pool_shares": t.common_pool_shares,
                    "marginal_allocation_pct": t.marginal_allocation_pct,
                }
                for t in waterfall.tranches
            ],
        },
        "findings": [asdict(f) for f in findings],
        "resolutions": resolutions,
    }
    json_bytes = json.dumps(json_payload, indent=2, default=str).encode("utf-8")

    # Static xlsx
    wb_static_bytes = _build_clean_xlsx_bytes(sess)

    # Live workbook
    wb_live = build_formula_workbook(cap_table, waterfall)
    live_bio = io.BytesIO()
    wb_live.save(live_bio)

    # Audit memo
    memo_md = build_audit_memo(cap_table, waterfall, findings, resolutions)

    company_slug = (cap_table.company.name or "captable").replace(" ", "_").replace(".", "")
    bundle_bio = io.BytesIO()
    with zipfile.ZipFile(bundle_bio, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"{company_slug}_clean.json", json_bytes)
        zf.writestr(f"{company_slug}_static.xlsx", wb_static_bytes)
        zf.writestr(f"{company_slug}_live_formulas.xlsx", live_bio.getvalue())
        zf.writestr(f"audit_memo_{company_slug}.md", memo_md)
    bundle_bio.seek(0)
    return send_file(
        bundle_bio,
        mimetype="application/zip",
        as_attachment=True,
        download_name=f"{company_slug}_bundle_{token}.zip",
    )


@app.get("/export/<token>.md")
def export_audit_memo(token: str):
    """Audit memo skeleton — Markdown with structured facts pre-filled and
    explicit [ANALYST: ...] placeholders for judgment sections."""
    sess = SESSIONS.get(token)
    if sess is None:
        return render_template("session_expired.html", token=token), 404
    md = build_audit_memo(
        sess["cap_table"],
        sess["waterfall"],
        sess["findings"],
        sess.get("resolutions", []),
    )
    company_slug = (sess["cap_table"].company.name or "captable").replace(" ", "_").replace(".", "")
    return Response(
        md,
        mimetype="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="audit_memo_{company_slug}_{token}.md"'},
    )


@app.get("/compare/<token>")
def compare(token: str):
    """Before vs after resolution: side-by-side cap-table + waterfall delta.

    Snapshots the cap table at session creation; compares against the current
    in-memory state after analyst resolutions. Surfaces material economic
    impact of every resolution (LP total delta, BP-by-BP delta, share-count
    delta per class).
    """
    sess = SESSIONS.get(token)
    if sess is None:
        return render_template("session_expired.html", token=token), 404
    original = sess.get("original_cap_table") or sess["cap_table"]
    current = sess["cap_table"]
    original_wf = compute_waterfall(original)
    current_wf = sess["waterfall"]

    original_classes = {sc.name: sc for sc in original.share_classes}
    current_classes = {sc.name: sc for sc in current.share_classes}
    class_rows: list[dict] = []
    for name in dict.fromkeys(list(original_classes) + list(current_classes)):
        o = original_classes.get(name)
        c = current_classes.get(name)
        o_sh = o.shares_outstanding if o else 0
        c_sh = c.shares_outstanding if c else 0
        o_lp = (o.liquidation_preference.amount if o and o.liquidation_preference else 0)
        c_lp = (c.liquidation_preference.amount if c and c.liquidation_preference else 0)
        if o_sh == c_sh and o_lp == c_lp and bool(o) == bool(c):
            continue  # unchanged
        class_rows.append({
            "name": name,
            "original_shares": o_sh,
            "current_shares": c_sh,
            "delta_shares": c_sh - o_sh,
            "original_lp": o_lp,
            "current_lp": c_lp,
            "delta_lp": c_lp - o_lp,
            "added": o is None,
            "removed": c is None,
        })

    original_bp_by_id = {bp.id: bp for bp in original_wf.breakpoints}
    bp_rows: list[dict] = []
    for bp in current_wf.breakpoints:
        o_bp = original_bp_by_id.get(bp.id)
        bp_rows.append({
            "id": bp.id,
            "current_value": bp.value,
            "current_event": bp.event,
            "original_value": (o_bp.value if o_bp else None),
            "delta": (bp.value - o_bp.value) if o_bp else None,
            "is_new": o_bp is None,
        })
    current_ids = {bp.id for bp in current_wf.breakpoints}
    for bp in original_wf.breakpoints:
        if bp.id not in current_ids:
            bp_rows.append({
                "id": bp.id,
                "original_value": bp.value,
                "current_value": None,
                "current_event": bp.event,
                "delta": None,
                "is_removed": True,
            })

    return render_template(
        "compare.html",
        token=token,
        cap_table=current,
        original=original,
        original_wf=original_wf,
        current_wf=current_wf,
        class_rows=class_rows,
        bp_rows=bp_rows,
        resolutions=sess.get("resolutions", []),
    )


@app.get("/sessions")
def sessions_index():
    """List every persisted session with quick links to resume or delete."""
    items = SESSIONS.list_sessions()
    return render_template("sessions.html", sessions=items)


@app.post("/sessions/<token>/delete")
def sessions_delete(token: str):
    SESSIONS.delete(token)
    return redirect(url_for("sessions_index"))


@app.get("/diff")
def diff_index():
    return render_template("diff.html", diff=None, error=None)


@app.post("/diff")
def diff_run():
    """Two .xlsx uploads: 'left' (prior snapshot) and 'right' (current).

    Both are parsed and diffed; the resulting structured diff renders inline.
    """
    left_file = request.files.get("left")
    right_file = request.files.get("right")
    if not left_file or not right_file or not left_file.filename or not right_file.filename:
        return render_template("diff.html", diff=None, error="Both files are required.")
    for f in (left_file, right_file):
        if not f.filename.lower().endswith(".xlsx"):
            return render_template("diff.html", diff=None, error="Only .xlsx supported.")

    try:
        l_path = Path("/tmp") / f"diff_l_{secrets.token_hex(4)}.xlsx"
        r_path = Path("/tmp") / f"diff_r_{secrets.token_hex(4)}.xlsx"
        l_path.write_bytes(left_file.read())
        r_path.write_bytes(right_file.read())
        try:
            left_ct, _ = parse_excel(l_path)
            right_ct, _ = parse_excel(r_path)
        finally:
            for p in (l_path, r_path):
                try:
                    p.unlink()
                except OSError:
                    pass
    except Exception as e:
        return render_template("diff.html", diff=None, error=f"Parse failed: {e}")

    diff = diff_cap_tables(left_ct, right_ct)
    return render_template("diff.html", diff=diff, error=None)


@app.get("/healthz")
def healthz():
    return {"status": "ok", "active_sessions": len(SESSIONS)}


if __name__ == "__main__":
    app.config["TEMPLATES_AUTO_RELOAD"] = True
    app.jinja_env.auto_reload = True
    app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0  # no static-file caching in dev

    _root = Path(__file__).parent
    extra_files = [
        str(p) for p in (
            *_root.glob("templates/**/*.html"),
            *_root.glob("static/**/*.css"),
            *_root.glob("static/**/*.js"),
        )
    ]

    app.run(debug=True, port=5050, use_reloader=True, extra_files=extra_files)
