"""Rule-pack versioning (SYSTEM_SPEC §4.1, §8.15).

A rule pack is a versioned, citation-stamped collection of checklist rules.
Each engagement binds to a specific pack version at open time; the bound pack
+ the engine commit SHA together make checklist runs reproducible years
later.

Architecture:

  - Rule implementations are Python functions in `src/checklist.py`.
  - Each rule registers itself with `@rule(...)` at import time, attaching
    metadata (id, severity, citation, jurisdictions, standards).
  - A `RulePack` (pydantic model) names a version and lists which rule IDs
    are included, with per-pack effective dates.
  - `head_pack()` returns the currently-effective pack (defaults to the
    one shipped in `rule_packs/`).
  - `run_pack(cap_table, pack)` evaluates only the rules in the pack and
    in pack order.
  - `EngagementPackBinding` (pydantic) is the at-bind-time record that
    pins the pack version + engine commit SHA. Stored alongside the
    engagement in the engagement model.

Cross-references:
  - GAP-06 schema evolution: severities are enum-validated.
  - GAP-07 version skew: engine commit SHA captured at bind time.
  - GAP-26 jurisdiction predicate: each rule carries jurisdictions list;
    `run_pack` filters by engagement jurisdiction if supplied.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .models import CapTable


# m1 fix: pack_version must look like a semver tag. Prevents path
# traversal when pack_version is used in a file path.
_PACK_VERSION_RE = "^v\\d+\\.\\d+\\.\\d+(?:-[A-Za-z0-9.\\-]+)?$"


# ---- Rule registry -----------------------------------------------------------


Severity = str  # Literal["blocker", "warning", "info"] — kept as str for json
_VALID_SEVERITIES = ("blocker", "warning", "info")


@dataclass(frozen=True)
class RuleMetadata:
    id: str  # stable G-prefix code, e.g. "G-AD-001"
    severity: Severity
    category: str
    summary: str
    citation: str  # publisher + reference
    jurisdictions: tuple[str, ...] = ()
    standards: tuple[str, ...] = ()
    introduced_in_pack: str = "v2026.1.0"


# Registry: rule_id -> (callable, metadata). Populated by @rule.
_REGISTRY: dict[str, tuple[Callable, RuleMetadata]] = {}


def rule(
    id: str,
    severity: Severity,
    category: str,
    summary: str,
    citation: str,
    jurisdictions: tuple[str, ...] = (),
    standards: tuple[str, ...] = (),
    introduced_in_pack: str = "v2026.1.0",
):
    """Decorator: register a checklist rule with metadata.

    The wrapped function must accept a CapTable and return list[Finding].
    """
    if severity not in _VALID_SEVERITIES:
        raise ValueError(
            f"invalid severity {severity!r}; must be one of {_VALID_SEVERITIES}"
        )

    meta = RuleMetadata(
        id=id,
        severity=severity,
        category=category,
        summary=summary,
        citation=citation,
        jurisdictions=jurisdictions,
        standards=standards,
        introduced_in_pack=introduced_in_pack,
    )

    def decorator(fn: Callable) -> Callable:
        if id in _REGISTRY:
            raise ValueError(f"duplicate rule id {id!r}; already registered")
        _REGISTRY[id] = (fn, meta)
        fn._rule_meta = meta  # type: ignore[attr-defined]
        return fn

    return decorator


def registered_rule_ids() -> list[str]:
    """All currently-registered rule IDs, in registration order."""
    return list(_REGISTRY.keys())


def _assert_no_finding_code_collisions(cap_table) -> Optional[str]:
    """W4-AUDIT m-4: defence-in-depth. The registry refuses duplicate
    rule IDs, but two distinct rules can emit Finding(code=X) with the
    same code. Run every registered rule against the cap table and
    flag any duplicate finding codes (would mean resolving one silently
    resolves both).

    Returns a problem string if a collision is detected; None if clean.
    Production should NOT call this on every request — it's a CI / fuzz
    helper. Exposed publicly for the test suite to enforce.
    """
    from collections import Counter
    codes: list[tuple[str, str]] = []  # (rule_id, finding_code)
    for rid, (fn, _meta) in _REGISTRY.items():
        try:
            findings = fn(cap_table)
        except Exception:
            continue
        for f in findings:
            codes.append((rid, f.code))
    counter = Counter(c for _r, c in codes)
    dupes = [c for c, n in counter.items() if n > 1]
    if dupes:
        # Map back to which rules emitted the dupe
        problem_lines = []
        for dupe in dupes:
            owners = sorted({r for r, c in codes if c == dupe})
            problem_lines.append(f"  finding code {dupe!r} emitted by: {owners}")
        return "\n".join(problem_lines)
    return None


def rule_metadata(rule_id: str) -> Optional[RuleMetadata]:
    entry = _REGISTRY.get(rule_id)
    return entry[1] if entry else None


def _representative_cap_table_for_collision_check():
    """Build a programmatic cap table that exercises enough rule paths to
    catch finding-code collisions at boot (W6.2 + SD-AUD-W6M-1).

    Coverage targets every rule code path that emits per-class or
    per-instrument findings: common + ESOP reserved + ESOP granted, four
    preferred classes spanning every LP variant + every AD variant,
    SAFE outstanding, warrant outstanding, convertible note past
    maturity, side letter, down-round (Series C issued lower than B),
    missing conversion ratio, and a stale option grant.
    """
    from datetime import date
    from .models import (
        CapTable, Company, ShareClass, ShareClassType,
        LiquidationPreference, LPType, AntiDilution, AntiDilutionVariant,
        SAFE, Warrant, ConvertibleNote, SideLetter, ProtectiveProvision,
    )
    return CapTable(
        company=Company(
            name="Probe Co", currency="USD", currency_symbol="$",
            stage="series_c", jurisdiction="delaware",
            valuation_date=date(2026, 1, 1),
        ),
        share_classes=[
            ShareClass(
                name="Common", type=ShareClassType.common,
                shares_outstanding=5_000_000, issue_price=0.001,
                issue_date=date(2020, 1, 1),
            ),
            ShareClass(
                name="ESOP Pool", type=ShareClassType.option_pool_reserved,
                shares_outstanding=500_000,
            ),
            ShareClass(
                name="ESOP Granted", type=ShareClassType.option_pool_granted,
                shares_outstanding=300_000, issue_price=0.50,
                # Stale grant — issued >90 days before valuation_date.
                issue_date=date(2022, 6, 1),
            ),
            ShareClass(
                name="Series A", type=ShareClassType.preferred,
                shares_outstanding=1_000_000, issue_price=1.0,
                issue_date=date(2022, 1, 1), seniority_rank=3,
                liquidation_preference=LiquidationPreference(
                    multiple=1.0, type=LPType.non_participating,
                    amount=1_000_000,
                ),
                anti_dilution=AntiDilution(
                    variant=AntiDilutionVariant.broad_based_weighted_average,
                ),
            ),
            ShareClass(
                name="Series B", type=ShareClassType.preferred,
                shares_outstanding=2_000_000, issue_price=2.0,
                issue_date=date(2023, 1, 1), seniority_rank=2,
                liquidation_preference=LiquidationPreference(
                    multiple=1.0, type=LPType.participating_capped,
                    amount=4_000_000, cap_multiple=3.0,
                ),
                anti_dilution=AntiDilution(
                    variant=AntiDilutionVariant.full_ratchet,
                ),
            ),
            ShareClass(
                # Down-round: Series C priced below Series B.
                name="Series C", type=ShareClassType.preferred,
                shares_outstanding=1_500_000, issue_price=1.50,
                issue_date=date(2025, 1, 1), seniority_rank=1,
                liquidation_preference=LiquidationPreference(
                    multiple=2.0, type=LPType.participating_uncapped,
                    amount=4_500_000,
                ),
                anti_dilution=AntiDilution(
                    variant=AntiDilutionVariant.narrow_based_weighted_average,
                ),
                # Missing conversion_ratio on purpose to fire G-LP-002 family.
            ),
        ],
        side_letters=[
            SideLetter(id="sl-1", title="MFN clause",
                       body="Standard MFN.",
                       unresolved_questions=["Does MFN extend to Series C?"]),
        ],
        safes_outstanding=[
            SAFE(id="safe-1", principal=500_000.0,
                 valuation_cap=10_000_000.0, discount_rate=0.20,
                 issue_date=date(2024, 6, 1)),
        ],
        warrants_outstanding=[
            Warrant(id="war-1", holder="Acme Lender", shares=50_000,
                    share_class="Series B", strike_price=2.0,
                    issue_date=date(2023, 6, 1),
                    # Expired warrant — fires G-WAR-002 family.
                    expiry_date=date(2025, 6, 1)),
        ],
        convertible_notes_outstanding=[
            ConvertibleNote(id="note-1", principal=1_000_000.0,
                            valuation_cap=12_000_000.0,
                            discount_rate=0.20, interest_rate=0.06,
                            issue_date=date(2023, 1, 1),
                            qualified_financing_threshold=5_000_000.0),
        ],
        protective_provisions=[
            ProtectiveProvision(
                name="amend_charter",
                description="Series A approval required to amend charter",
                consent_threshold_pct=66.7,
                consenting_class_names=["Series A"],
            ),
        ],
    )


def _probe_cap_tables() -> list:
    """Multiple probe cap tables covering jurisdictional rule paths the
    default Delaware probe doesn't fire. SD-AUD-W6M-1 hardening."""
    base = _representative_cap_table_for_collision_check()
    # India variant — fires G-IN-* FEMA / CCPS rules.
    india = base.model_copy(update={
        "company": base.company.model_copy(update={
            "jurisdiction": "india", "currency": "INR", "currency_symbol": "₹",
        }),
    })
    # Singapore variant — fires G-SG-* IRAS rules.
    singapore = base.model_copy(update={
        "company": base.company.model_copy(update={
            "jurisdiction": "singapore", "currency": "SGD",
            "currency_symbol": "S$",
        }),
    })
    # US 409A variant — fires G-US-* §409A rules.
    us_409a = base.model_copy(update={
        "company": base.company.model_copy(update={
            "jurisdiction": "delaware", "stage": "series_b",
        }),
    })
    return [base, india, singapore, us_409a]


def _collisions_across_probes(probes: list) -> Optional[str]:
    """Run the collision check over the union of probes. A code emitted
    by two different rule_ids in ANY single probe (or across probes
    where the same rule_id × code pair appears once but a different
    rule_id × same-code pair appears in another probe) is a collision."""
    from collections import defaultdict
    code_to_rule_ids: dict[str, set[str]] = defaultdict(set)
    for ct in probes:
        for rid, (fn, _meta) in _REGISTRY.items():
            try:
                findings = fn(ct)
            except Exception:
                continue
            for f in findings:
                code_to_rule_ids[f.code].add(rid)
    dupes = {c: rids for c, rids in code_to_rule_ids.items() if len(rids) > 1}
    if not dupes:
        return None
    return "\n".join(
        f"  finding code {c!r} emitted by: {sorted(rids)}"
        for c, rids in sorted(dupes.items())
    )


def _static_collisions_in_rule_sources() -> Optional[str]:
    """Scan src/rules_v2026_*.py + src/checklist.py for hard-coded
    `Finding(code="...")` and `code=f"...{var}"` literals. Catches the
    collision class that runtime-probe coverage misses: two rule
    functions with the same hardcoded literal but mutually exclusive
    code paths (the probe never fires both, so the runtime check
    cannot see them).

    Returns a problem string if a static collision is detected. Returns
    None if clean. Caveat: f-string templates collapse to their literal
    prefix/suffix — `f"AD-MISSING-{sc.name}"` registers as
    `AD-MISSING-` template, not as a fully resolved code. Two rules
    emitting the same template prefix flag a probable runtime collision.
    """
    import re
    from pathlib import Path
    from collections import defaultdict
    src_dir = Path(__file__).parent
    targets = list(src_dir.glob("rules_v2026_*.py"))
    chk = src_dir / "checklist.py"
    if chk.exists():
        targets.append(chk)
    # Match Finding(code="..."), Finding(code='...'), and the f-string
    # variant where the literal portion is grabbed (template prefix).
    literal_re = re.compile(
        r'Finding\([^)]*?\bcode\s*=\s*(?:f?["\'])([^"\']+?)(?:["\'])'
    )
    rule_def_re = re.compile(r"@rule\(\s*['\"]([^'\"]+)['\"]")
    code_to_rule_ids: dict[str, set[str]] = defaultdict(set)
    for path in targets:
        src = path.read_text()
        # Track the @rule decorator that owns each function so we map
        # codes back to their owning rule_id.
        positions = [(m.start(), m.group(1)) for m in rule_def_re.finditer(src)]
        for m in literal_re.finditer(src):
            # Find the nearest preceding @rule decorator.
            owner = "unknown"
            for pos, rid in positions:
                if pos < m.start():
                    owner = rid
                else:
                    break
            code_to_rule_ids[m.group(1)].add(owner)
    dupes = {c: rids for c, rids in code_to_rule_ids.items() if len(rids) > 1}
    if not dupes:
        return None
    return "\n".join(
        f"  finding code {c!r} emitted by source files of: {sorted(rids)}"
        for c, rids in sorted(dupes.items())
    )


def assert_no_collisions_at_startup(strict: bool = True) -> None:
    """Boot-time guard. Runs collision detection against the union of the
    probe cap tables; raises RuntimeError if any code is emitted by two
    different rules. Call once after all rule modules are imported (e.g.,
    end of app.py).

    SD-AUD-W6M-1: the union of four jurisdictional probes exercises the
    bulk of registered rules (G-IN-*, G-SG-*, G-US-*, generic). Rules
    that never fire on any probe table are inherently un-collidable at
    runtime against this corpus — for those, future static analysis
    over `Finding(code=...)` literals is the durable answer.

    `strict=False` logs instead of raising — useful for dev mode where
    a noisy startup is preferable to a refused boot.
    """
    import logging
    runtime_problem = _collisions_across_probes(_probe_cap_tables())
    static_problem = _static_collisions_in_rule_sources()
    pieces = []
    if runtime_problem is not None:
        pieces.append("Runtime probe collisions:\n" + runtime_problem)
    if static_problem is not None:
        pieces.append("Static source collisions:\n" + static_problem)
    if not pieces:
        return
    msg = (
        "Rule-pack finding-code collision detected at startup (W6.2):\n"
        + "\n\n".join(pieces)
        + "\nTwo rules emit the same Finding.code → resolving one silently "
        "resolves the other. Fix rule_ids before continuing."
    )
    if strict:
        raise RuntimeError(msg)
    logging.getLogger(__name__).error(msg)


# ---- Rule pack model ---------------------------------------------------------


class RulePack(BaseModel):
    """Versioned bundle of rule IDs effective in a date range."""

    model_config = ConfigDict(extra="forbid")

    version: str = Field(pattern=_PACK_VERSION_RE)
    effective_from: date
    effective_to: Optional[date] = None
    jurisdictions: list[str] = Field(default_factory=list)
    standards: list[str] = Field(default_factory=list)
    rule_ids: list[str]
    description: Optional[str] = None

    @field_validator("version")
    @classmethod
    def _no_path_traversal_in_version(cls, v: str) -> str:
        # Defence in depth: regex above already enforces this, but
        # explicit double-check for the path-traversal vector flagged
        # in CODE_AUDIT_WAVE_2 m1.
        if "/" in v or ".." in v or "\0" in v:
            raise ValueError(f"pack version contains forbidden characters: {v!r}")
        return v

    def is_effective_on(self, d: date) -> bool:
        if d < self.effective_from:
            return False
        if self.effective_to is not None and d > self.effective_to:
            return False
        return True


class EngagementPackBinding(BaseModel):
    """The at-bind-time record per engagement (GAP-07)."""

    model_config = ConfigDict(extra="forbid")

    engagement_id: str
    pack_version: str
    engine_version: str  # git commit SHA at bind time
    bound_at: datetime

    @classmethod
    def create(cls, engagement_id: str, pack: RulePack) -> "EngagementPackBinding":
        return cls(
            engagement_id=engagement_id,
            pack_version=pack.version,
            engine_version=current_engine_commit(),
            bound_at=datetime.now(timezone.utc),
        )


# ---- Engine version helper ---------------------------------------------------


_ENGINE_COMMIT_CACHE: Optional[str] = None


def current_engine_commit() -> str:
    """Return the engine's current git commit SHA (short).

    Lookup order (W8.3 — closes wave-5 m-4):
      1. `QAPITA_ENGINE_COMMIT` env var (set by the OCI image build).
      2. `git rev-parse --short=12 HEAD` (dev path).
      3. Literal "unversioned" (last-resort fallback).

    Cached at module level so engagement-create doesn't fork+exec git on
    every call (also closes wave-5 m-12 indirectly).
    """
    global _ENGINE_COMMIT_CACHE
    import os
    env_commit = os.environ.get("QAPITA_ENGINE_COMMIT", "").strip()
    # SD-AUD-W8-m2: bust cache when the env var differs from what we
    # cached. Hot-reload paths (dotenv loaded after first call, CLI
    # commands that import the engine before reading config) get the
    # current env value instead of a stale "unversioned".
    if env_commit and _ENGINE_COMMIT_CACHE != env_commit[:12]:
        _ENGINE_COMMIT_CACHE = None
    if _ENGINE_COMMIT_CACHE is not None:
        return _ENGINE_COMMIT_CACHE
    if env_commit:
        _ENGINE_COMMIT_CACHE = env_commit[:12]
        return _ENGINE_COMMIT_CACHE
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--short=12", "HEAD"],
            cwd=Path(__file__).parent.parent,
            capture_output=True,
            text=True,
            timeout=2,
        )
        if proc.returncode == 0:
            _ENGINE_COMMIT_CACHE = proc.stdout.strip()
            return _ENGINE_COMMIT_CACHE
    except (FileNotFoundError, subprocess.SubprocessError):
        pass
    _ENGINE_COMMIT_CACHE = "unversioned"
    return _ENGINE_COMMIT_CACHE


# ---- Persistence -------------------------------------------------------------


_PACKS_DIR = Path(__file__).parent.parent / "rule_packs"


def load_pack_from_file(path: Path | str) -> RulePack:
    return RulePack.model_validate_json(Path(path).read_text())


def save_pack_to_file(pack: RulePack, path: Path | str) -> None:
    Path(path).write_text(pack.model_dump_json(indent=2))


def list_available_packs() -> list[RulePack]:
    if not _PACKS_DIR.exists():
        return []
    out = []
    for f in sorted(_PACKS_DIR.glob("*.json")):
        try:
            out.append(load_pack_from_file(f))
        except Exception:
            continue
    return out


def load_engagement_bound_pack(pack_version: str) -> RulePack:
    """Load the specific pack version an engagement was bound to.

    Used by the memo / subsequent-events / bundle code paths so they
    honour SPEC §4.1 binding (the bound pack is sticky for the
    engagement's lifetime). Raises FileNotFoundError if the pack file
    is missing on disk. M-7 / system audit: refuses to fall back to
    v0.0.0-dev unless QAPITA_ALLOW_DEV_PACK=1.
    """
    import os
    import re
    # W4-AUDIT m-5: defence-in-depth semver validation. pack_version
    # flows from head_pack().version today, but any future code path
    # that ingests the version from an untrusted source would let path
    # traversal escape via "../../etc/passwd.json".
    if not re.match(_PACK_VERSION_RE, pack_version):
        raise ValueError(
            f"pack_version {pack_version!r} does not match the semver "
            f"pattern {_PACK_VERSION_RE}"
        )
    if pack_version == "v0.0.0-dev" and os.environ.get("QAPITA_ALLOW_DEV_PACK") != "1":
        raise ValueError(
            "Engagement is bound to v0.0.0-dev (in-memory dev fallback). "
            "Production must bind to a persisted pack. Set "
            "QAPITA_ALLOW_DEV_PACK=1 only in development environments."
        )
    candidate = _PACKS_DIR / f"{pack_version}.json"
    if not candidate.exists():
        raise FileNotFoundError(
            f"Engagement-bound rule pack {pack_version} not found at "
            f"{candidate}. Did the pack file get pruned?"
        )
    return load_pack_from_file(candidate)


def head_pack(on_date: Optional[date] = None) -> RulePack:
    """Return the rule pack effective on the given date (default: today).

    If no pack is effective, returns a synthesized pack containing every
    registered rule — the in-process default for development. In production,
    every engagement must explicitly bind to a persisted pack.
    """
    on_date = on_date or datetime.now(timezone.utc).date()
    packs = list_available_packs()
    effective = [p for p in packs if p.is_effective_on(on_date)]
    if effective:
        # Pick the latest effective_from
        return max(effective, key=lambda p: p.effective_from)
    # No persisted pack — fall back to in-memory registry as a "dev pack."
    return RulePack(
        version="v0.0.0-dev",
        effective_from=on_date,
        rule_ids=registered_rule_ids(),
        description="In-memory fallback. Persist a rule_packs/*.json before production use.",
    )


# ---- Execution ---------------------------------------------------------------


def run_pack(
    cap_table: CapTable,
    pack: Optional[RulePack] = None,
    engagement_jurisdiction: Optional[str] = None,
):
    """Run a rule pack against a cap table.

    Args:
      cap_table: the parsed cap table to check.
      pack: a specific pack to run. None = head pack.
      engagement_jurisdiction: if set, filters rules to those tagged for
        the given jurisdiction or untagged (universal) rules.

    Returns: list[Finding] sorted by severity then code.
    """
    from .checklist import Finding  # avoid circular import at module top

    if pack is None:
        pack = head_pack()

    findings: list[Finding] = []
    for rid in pack.rule_ids:
        entry = _REGISTRY.get(rid)
        if entry is None:
            # Rule referenced by pack but not registered in engine. Surface
            # as a meta-finding so the auditor sees the skew.
            findings.append(
                Finding(
                    code=f"META-RULE-MISSING-{rid}",
                    severity="blocker",
                    category="engine_pack_skew",
                    summary=(
                        f"Rule {rid} referenced by pack {pack.version} but not "
                        f"registered in the current engine."
                    ),
                    fields_referenced=(),
                )
            )
            continue
        fn, meta = entry
        # Jurisdiction filter (GAP-26)
        if engagement_jurisdiction and meta.jurisdictions:
            jset = {j.upper() for j in meta.jurisdictions}
            if engagement_jurisdiction.upper() not in jset:
                continue
        findings.extend(fn(cap_table))

    severity_order = {"blocker": 0, "warning": 1, "info": 2}
    findings.sort(key=lambda f: (severity_order.get(f.severity, 99), f.code))
    return findings


def finding_provenance_map(
    cap_table,
    pack: Optional[RulePack] = None,
    engagement_jurisdiction: Optional[str] = None,
) -> dict:
    """W9.1: returns `{finding.code: {"rule_id": ..., "citation": ...,
    "pack_version": ...}}` by re-running the pack and recording which
    rule emitted each code. The PDF memo + bundle use this to surface
    "why" next to each finding.

    The map is built deterministically: same cap_table + pack → same
    map. If two rules collide on a code (which the W6.2 startup guard
    refuses), the later rule's metadata wins.
    """
    if pack is None:
        pack = head_pack()
    out = {}
    for rid in pack.rule_ids:
        entry = _REGISTRY.get(rid)
        if entry is None:
            continue
        fn, meta = entry
        if engagement_jurisdiction and meta.jurisdictions:
            jset = {j.upper() for j in meta.jurisdictions}
            if engagement_jurisdiction.upper() not in jset:
                continue
        try:
            for f in fn(cap_table):
                out[f.code] = {
                    "rule_id": rid,
                    "citation": meta.citation,
                    "pack_version": pack.version,
                }
        except Exception:
            continue
    return out
