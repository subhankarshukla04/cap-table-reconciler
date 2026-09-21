# Operations Runbook

> SYSTEM_SPEC §8.6 + GAP-02, GAP-04, GAP-38. Backup, disaster recovery,
> retention, incident response, key rotation, audit-log query SLO.
> Written 2026-05-25 for wave-2 release. Updated whenever the production
> stance changes.

---

## 1. Service-level objectives

| Target | Value | Verified by |
|---|---|---|
| RPO (recovery point objective) | ≤ 1 hour | Backup runs hourly; latest restore drill timestamp logged |
| RTO (recovery time objective) | ≤ 4 hours | Quarterly DR rehearsal |
| Audit-log query | ≤ 5 s for 7-year engagement | `tests/test_audit_log_slo.py` benchmark (added W3.3) |
| Memo PDF generation | ≤ 10 s end-to-end on reference env | Manual + load test |
| Engagement create / snapshot upload | ≤ 2 s on reference env | Per-request timing in monitoring |

Reference env per SYSTEM_SPEC §8.3: 4 vCPU, 8 GiB RAM, SSD, Python 3.11+,
≤ 20 ms RTT to data source.

## 2. Backup policy

**What gets backed up:**

- `engagements.db` (Engagement / Snapshot / Resolution / Audit event)
- `sessions.db` (Phase-0 SessionStore — sunset path; still backed up
  while in use)
- `export_limits.db` (rate-limit counters; cosmetic to lose, but kept
  for audit-event continuity)
- `rule_packs/*.json` (versioned in git, so this is belt-and-braces)
- Snapshot blob storage (cap-table source files, side-letter PDFs) once
  the migration off SQLite-only TEXT happens.

**Schedule:**

- Hourly incremental dump of each SQLite DB (sqlite3 `.backup` API to
  avoid hot-page corruption).
- Daily full dump to encrypted off-cluster storage (KMS-managed key).
- Weekly cross-region replication of the last 7 daily fulls.

**Retention:**

- Hourly: keep 24.
- Daily: keep 90.
- Weekly: keep 52 (1 year of off-region history).
- For Big-4-audit-relevant engagements, retain DB-level snapshots for
  **7 years** alongside the audit-log per row's hash chain.

## 3. Disaster recovery — restore drill

The drill runs quarterly. Procedure:

1. Provision a clean machine matching the reference env.
2. Pull the latest daily backup from off-region storage.
3. Restore `engagements.db` and verify schema with `PRAGMA integrity_check`.
4. For three pinned reference engagements, run `EngagementStore.verify_audit_log`.
   All three must return `(True, None)` — the hash chain proves the
   restore is byte-equivalent to the original.
5. Restart the Flask app, run the smoke suite `pytest -k "not slow"`,
   record wall-clock duration. Must be < 4 hours from start of drill.
6. Log the drill outcome to `runbook_log/dr-YYYY-MM-DD.md` with the
   restore timestamps and any deviations.

## 4. Retention and deletion (GAP-02 closure)

**Archived engagement deletion eligibility:**

Engagements in `archived` status for ≥ 90 days are eligible for hard
deletion subject to:

- No outstanding regulatory / litigation hold on the client_id.
- Big-4 retention policy permits deletion (most do at 7 years).
- A partner-signed deletion request is recorded as an `audit_event` of
  type `engagement_hard_delete` BEFORE the DELETE statement runs.

Deletion is cascaded: snapshots, resolutions, audit-events for the
engagement are removed. The audit-log hash chain breaks at the deletion
point — this is correct behaviour; the engagement no longer exists.

**PDPA / GDPR / DPDPA right-of-erasure (GAP-03):**

Per SYSTEM_SPEC §8.13: snapshots are REDACTED in place (sentinel payload),
the audit log is preserved (with a `pii_redacted` audit_event). The
existing partner-only `engagement.pii_redact` permission gates this.

Cryptographic shredding is an alternative for jurisdictions that require
unrecoverable erasure — encrypt snapshots at rest per-snapshot, delete the
per-snapshot key on redaction request. Architecture for this is deferred
to Phase 3 infra alignment with Vamsee.

## 5. Incident response

**Severity definitions:**

- **SEV-1**: data loss or compromise (any DB write loss, any unauthorized
  data exfiltration, audit-log integrity break).
- **SEV-2**: production unavailable, multi-user impact.
- **SEV-3**: degraded behaviour, single-engagement impact.
- **SEV-4**: cosmetic.

**SEV-1 protocol:**

1. Page the CTO and Risk roles simultaneously.
2. Freeze writes: set the engagement store into read-only mode by
   flipping `app.config["ENGAGEMENT_STORE"] = ReadOnlyEngagementStore(...)`
   (helper to be added when needed — for now, halt the Flask process).
3. Preserve evidence: copy the live DB to `/incident/<date>/` before any
   recovery action.
4. Notify Evelyn within 1 hour of detection; notify any affected client
   per SYSTEM_SPEC §3.5 communication template (template TBD).
5. Run `verify_audit_log` on every active engagement. Any failures are
   logged with their break point.
6. Post-incident: write `incident/<date>.md` within 48 hours covering
   root cause, blast radius, fix, prevention.

**SEV-2 protocol:**

1. Notify the on-call (CTO role).
2. Roll back the most recent deploy if a fresh deploy is correlated.
3. Document and assign a SEV-3 fix to the engineer on the cause.

## 6. Key rotation

**Keys involved:**

- SSO signing keys (managed by Qapita SSO — out of our scope).
- Snapshot encryption keys (if added per §4 cryptographic shredding).
- Backup encryption keys (KMS-managed).
- Engagement-bound rule-pack engine version (git-SHA, immutable).

**Rotation policy:**

- KMS rotation: annual, automated. Old keys retained for the retention
  window (so older backups remain decryptable).
- Snapshot keys (when added): rotated per redaction request only; never
  silently.
- Engine version: not rotated. The git SHA is immutable; engagements
  bind to it at open and the binding never changes.

## 7. Audit-log query SLO

The `audit_event` table is the load-bearing artefact for 7-year-old
re-audits. Query SLO: list the full chain for one engagement in ≤ 5
seconds even at 10k events.

**Index in place:** `ix_audit_engagement_ts ON audit_event(engagement_id, ts)`.

**Verification:** W3.3 will add `tests/test_audit_log_slo.py` that
synthesises 10k events into a single engagement and times
`store.list_audit_events`. The benchmark must complete within 5 seconds
on the reference env. Failure routes to a quarterly index review.

## 8. Monitoring + alerting

**Production dashboards (when deployed):**

- Engagement request rate per route (5xx, 4xx, 2xx).
- Audit-log integrity verification result per engagement (hourly job).
- Export rate-limit counter heatmap per user (alerts on hard-limit
  triggers).
- Storage utilisation per SQLite file + projected days-to-full.
- Memo PDF generation latency p50/p95/p99.

**Alerting:**

- Any audit-log integrity verification failure → SEV-1 page.
- Any hard-limit export trigger → SEV-3 notification to Risk role.
- 5xx rate > 1% for 5 consecutive minutes → SEV-2.
- DB connection count anomaly (we should have ≈ 0 idle since BUG-005
  fix landed) → SEV-3.

## 9. Things still owed to Evelyn / Vamsee

1. Pick the production database (Postgres recommended; current SQLite
   abstraction supports a swap behind `EngagementStore(db_path=...)`).
2. Pick the deployment target (Kubernetes, ECS, Fly.io, etc.).
3. Pick the monitoring stack (Grafana + Prometheus is the obvious default).
4. Confirm the backup destination (S3 + cross-region, GCS, ABS).
5. Confirm the KMS solution (AWS KMS, GCP KMS, HashiCorp Vault).
6. Confirm the SSO endpoint URL + JWT claim mapping (replaces
   `StubSSOProvider`).
7. Sign-off on the 90-day-archived deletion eligibility window.

Until those are picked, the wave-2 production-readiness story is
"library-complete with documented stubs." Wave 3 builds further capability
on top of this; full production cutover requires the seven items above.

## 10. Wave-6 hardening checklist (production deploy)

Closes the deferred items the stitched audit flagged for pre-prod
cutover. Apply before any internet-facing deploy.

### 10.1 Required environment variables

| Var | Purpose | Required mode | Failure mode if unset |
|---|---|---|---|
| `SESSION_SECRET_KEY` | Signs the cookie-auth session token. Hex/utf-8 string >= 32 bytes. | non-TESTING | `attach_login_blueprint` raises `RuntimeError`; app refuses to boot |
| `QAPITA_ALLOW_DEV_PACK` | Allows loading the `v0.0.0-dev` rule pack. | dev only | Engagement create refuses bound pack |
| `QAPITA_ENGINE_COMMIT` | Build-time git SHA injected into engagements. | OCI deploys | `current_engine_commit()` returns `"unversioned"` and pollutes the engagement table |

### 10.2 CSRF (W6.1)

- All cookie-authenticated POST routes require a CSRF token in
  `X-CSRF-Token` header OR `csrf_token` form field that matches the
  `qapita_csrf` cookie issued at login.
- Bearer-authenticated POSTs are exempt (explicit credential, not ambient).
- HTMX forms in `templates/engagement/*` already include the hidden input;
  custom client integrations MUST send the header.
- Logout clears both `qapita_session` and `qapita_csrf` cookies.

### 10.3 Bearer revocation (W6.4)

- `POST /logout` with `Authorization: Bearer <tok>` adds SHA-256(tok) to
  the deny list (`data/token_deny.db`).
- `_require_user` consults the deny list before identity resolution; a
  revoked token authenticates as nobody (falls through to the cookie path
  or 401).
- Run `TokenDenyList.prune_older_than(...)` periodically (cron) using the
  SSO provider's max token lifetime as the cutoff. Without pruning the
  table grows monotonically; correctness is unaffected but disk grows.

### 10.4 Startup checks (W6.2)

- App boot calls `assert_no_collisions_at_startup(strict=True)` outside
  TESTING — refuses to start if any two registered rules emit the same
  `Finding.code`.
- The check runs against a programmatic representative cap table; no
  fixture-file dependency.

### 10.5 Behind-the-proxy cookie config (deferred wave-5 m-3)

If the prod container terminates TLS at an upstream reverse proxy (NGINX,
Caddy, Cloud Load Balancer), the cookie's `secure=True` flag still fires
correctly only when Flask trusts `X-Forwarded-Proto`. Wire `ProxyFix`:

```python
from werkzeug.middleware.proxy_fix import ProxyFix
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_for=1)
```

OR set `app.config["TESTING"] = False` *and* run TLS termination
in-process. Otherwise the browser will refuse to attach the session cookie
to plaintext requests and every login appears to "succeed" with no session.

### 10.6 Cross-wave integration test surface (W6.3)

`tests/test_wave6_integration.py` drives one engagement through every
wave's surface end-to-end (login → upload → resolve → transition →
memo → bundle → whatif). Run as part of pre-deploy gating; the suite
catches seam regressions the unit tests miss by construction.

### 10.7 Production smoke tests

After deploy, exercise the deny-list path:

```bash
# 1. Issue a token via SSO, then logout, then verify revocation.
TOK=$(curl -sX POST /login -d 'token=...' | jq -r .token)
curl -H "Authorization: Bearer $TOK" /engagement/   # expect 200
curl -X POST -H "Authorization: Bearer $TOK" /logout
curl -H "Authorization: Bearer $TOK" /engagement/   # expect 401
```

And the CSRF path:

```bash
# Cookie session POST without the matching CSRF cookie/header → 403.
curl -X POST -b "qapita_session=<sid>" /engagement/   # expect 403
```
