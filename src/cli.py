"""
Command-line shim — `python -m src.cli reconcile <input.xlsx>`.

Useful for batch processing: parse a cap table, compute the waterfall, dump
the structured outputs (json + static xlsx + live xlsx + audit memo) to a
target directory or zip bundle. No Flask, no SQLite, no UI.

Usage:
  python -m src.cli reconcile <input.xlsx> [--out DIR] [--bundle OUT.zip]
  python -m src.cli demo <fixture_id> [--out DIR]
"""

from __future__ import annotations

import argparse
import io
import json
import sys
import zipfile
from dataclasses import asdict
from pathlib import Path

from .audit_memo import build_audit_memo
from .checklist import run_checklist
from .formula_workbook import build_formula_workbook
from .parser import load_from_canonical_json, parse_excel
from .waterfall import compute_waterfall


def _slug(name: str) -> str:
    return name.replace(" ", "_").replace(".", "").replace("/", "_")


def _build_static_xlsx_bytes(cap_table, waterfall, findings) -> bytes:
    """Minimal static .xlsx (Company / Cap Table / Breakpoints / Tranches / Findings)."""
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "Company"
    co = cap_table.company
    for r in (
        ("Company", co.name),
        ("Currency", co.currency),
        ("Valuation date", str(co.valuation_date or "")),
        ("Total fully diluted shares", cap_table.total_fully_diluted_for_waterfall),
        ("LP total", waterfall.lp_total),
        ("Breakpoints", len(waterfall.breakpoints)),
    ):
        ws.append(list(r))

    ws_ct = wb.create_sheet("Cap Table")
    ws_ct.append(["Class", "Type", "Shares", "PPS", "Issue Date", "Seniority"])
    for sc in cap_table.share_classes:
        ws_ct.append([
            sc.name, sc.type.value, sc.shares_outstanding,
            sc.issue_price or "", str(sc.issue_date or ""),
            sc.seniority_rank if sc.type.value == "preferred" else "",
        ])

    ws_bp = wb.create_sheet("Breakpoints")
    ws_bp.append(["ID", "Value", "Event"])
    for bp in waterfall.breakpoints:
        ws_bp.append([bp.id, bp.value, bp.event])

    ws_t = wb.create_sheet("Tranches")
    classes = [sc.name for sc in cap_table.share_classes if not sc.excluded_from_waterfall]
    ws_t.append(["Tranche", "Range Low", "Range High", "Description"] + classes)
    for tr in waterfall.tranches:
        row = [tr.id, tr.range_low, tr.range_high if tr.range_high is not None else "", tr.description]
        for c in classes:
            row.append(tr.marginal_allocation_pct.get(c, 0.0))
        ws_t.append(row)

    ws_f = wb.create_sheet("Findings")
    ws_f.append(["Code", "Severity", "Summary"])
    for f in findings:
        ws_f.append([f.code, f.severity, f.summary])

    bio = io.BytesIO()
    wb.save(bio)
    return bio.getvalue()


def _emit_artifacts(cap_table, waterfall, findings, out_dir: Path | None,
                    bundle: Path | None, slug_override: str | None = None) -> dict[str, Path]:
    slug = slug_override or _slug(cap_table.company.name or "captable")
    json_payload = {
        "company": cap_table.company.model_dump(mode="json"),
        "share_classes": [sc.model_dump(mode="json") for sc in cap_table.share_classes],
        "side_letters": [sl.model_dump(mode="json") for sl in cap_table.side_letters],
        "waterfall": {
            "lp_total": waterfall.lp_total,
            "breakpoints": [{"id": bp.id, "value": bp.value, "event": bp.event} for bp in waterfall.breakpoints],
            "tranches": [
                {"id": t.id, "range_low": t.range_low, "range_high": t.range_high,
                 "description": t.description,
                 "marginal_allocation_pct": t.marginal_allocation_pct}
                for t in waterfall.tranches
            ],
        },
        "findings": [asdict(f) for f in findings],
    }
    json_bytes = json.dumps(json_payload, indent=2, default=str).encode("utf-8")
    static_bytes = _build_static_xlsx_bytes(cap_table, waterfall, findings)
    live_bio = io.BytesIO()
    build_formula_workbook(cap_table, waterfall).save(live_bio)
    memo_md = build_audit_memo(cap_table, waterfall, findings, [])

    artifacts: dict[str, bytes] = {
        f"{slug}_clean.json": json_bytes,
        f"{slug}_static.xlsx": static_bytes,
        f"{slug}_live_formulas.xlsx": live_bio.getvalue(),
        f"audit_memo_{slug}.md": memo_md.encode("utf-8"),
    }

    written: dict[str, Path] = {}
    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)
        for fname, content in artifacts.items():
            target = out_dir / fname
            target.write_bytes(content)
            written[fname] = target
    if bundle:
        bundle.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(bundle, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for fname, content in artifacts.items():
                zf.writestr(fname, content)
        written["bundle"] = bundle
    return written


def cmd_reconcile(args: argparse.Namespace) -> int:
    src = Path(args.input)
    if not src.exists():
        print(f"error: {src} not found", file=sys.stderr)
        return 2
    cap_table, report = parse_excel(src)
    waterfall = compute_waterfall(cap_table)
    findings = run_checklist(cap_table)

    print(f"Parsed {cap_table.company.name}: {len(cap_table.share_classes)} classes, "
          f"{len(waterfall.breakpoints)} breakpoints, {len(findings)} findings.")
    if report.warnings:
        print(f"Parser warnings: {len(report.warnings)}")
        for w in report.warnings:
            print(f"  [{w.code}] {w.message}")
    blockers = [f for f in findings if f.severity == "blocker"]
    if blockers:
        print(f"Blockers: {len(blockers)}")
        for f in blockers:
            print(f"  [{f.code}] {f.summary}")

    out_dir = Path(args.out) if args.out else None
    bundle = Path(args.bundle) if args.bundle else None
    if not out_dir and not bundle:
        out_dir = Path.cwd() / f"reconciled_{_slug(cap_table.company.name)}"
    written = _emit_artifacts(cap_table, waterfall, findings, out_dir, bundle)
    for k, v in written.items():
        print(f"wrote {v}")
    return 0


def cmd_demo(args: argparse.Namespace) -> int:
    fixtures_dir = Path(__file__).parent.parent / "fixtures"
    fdir = fixtures_dir / args.fixture
    if not fdir.exists():
        print(f"error: fixture {args.fixture} not found at {fdir}", file=sys.stderr)
        return 2
    cap_table = load_from_canonical_json(fdir / "cap_table_input.json")
    waterfall = compute_waterfall(cap_table)
    findings = run_checklist(cap_table)
    print(f"Loaded {cap_table.company.name} ({args.fixture}): "
          f"{len(waterfall.breakpoints)} breakpoints.")
    out_dir = Path(args.out) if args.out else (Path.cwd() / f"reconciled_{args.fixture}")
    bundle = Path(args.bundle) if args.bundle else None
    written = _emit_artifacts(cap_table, waterfall, findings, out_dir, bundle)
    for k, v in written.items():
        print(f"wrote {v}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="cap-table-reconciler")
    sub = p.add_subparsers(dest="command", required=True)

    p_rec = sub.add_parser("reconcile", help="Parse + reconcile a cap-table .xlsx")
    p_rec.add_argument("input")
    p_rec.add_argument("--out", help="Output directory (defaults to ./reconciled_<slug>)")
    p_rec.add_argument("--bundle", help="Also produce a single .zip bundle at this path")
    p_rec.set_defaults(func=cmd_reconcile)

    p_demo = sub.add_parser("demo", help="Run a built-in fixture")
    p_demo.add_argument("fixture", choices=[
        "fixture_01_clean", "fixture_02_typical_messy",
        "fixture_03_edge_case", "fixture_04_down_round_ratchet",
        "fixture_05_delaware_double_cap",
    ])
    p_demo.add_argument("--out", help="Output directory")
    p_demo.add_argument("--bundle", help="Also produce a .zip bundle")
    p_demo.set_defaults(func=cmd_demo)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
