# Agency Structure — Cap Table Reconciler Build

> The independent agency that builds, ships, and audits the cap-table reconciler at Qapita. One human (Subhankar) wearing many hats; one AI collaborator (Claude) as execution partner. This document codifies the roles, decision rights, escalation triggers, communication cadence, and the change-management process for what pops up mid-build that no one anticipated.
>
> The point of writing it down is not bureaucracy. It is so that when something hard happens at 11pm during Phase 2, the protocol exists already and the person under stress does not have to invent it.

---

## 0. Operating principles

Before the roles, four principles that override any role definition below:

1. **One brain, many hats — no hat fights the others.** When the CTO disagrees with the CEO, it is the same human switching frames. The disagreement is real and useful; the decision is the human's, not the hat's. Hats are scaffolding for honest thinking, not for blame.
2. **Plan is a hypothesis. Reality is the data.** The roadmap is what we believe today. When Phase 2 evidence contradicts Phase 3 assumptions, the plan loses, not reality.
3. **Cadence beats ambition.** A weekly review that happens beats a perfect quarterly review that slips. The smaller cadence is the load-bearing discipline.
4. **Refuse comfortably.** Saying "I do not know" or "I will not ship this yet" is a first-class action, not a failure. The whole tool is built on this principle — apply it to the agency too.

---

## 1. The roles

Each role has: a one-line mandate, scope of authority, the failure mode that triggers escalation, and the hat the human wears when in this role.

### 1.1 CEO — Strategic direction and signoff
**Mandate.** Decides what the project is for, what success looks like, when to pivot, when to kill.
**Authority.** Phase definitions, success metrics, decision to internalize at Qapita (Path A vs Path B), decision to ship or hold, relationships with Evelyn / Vamsee / Amit, IP and license posture.
**Failure mode trigger.** When two roles below disagree on a tradeoff that has business consequences (e.g., "ship without rule-pack versioning to hit Month 3 deadline" vs "delay one month to get versioning in"), the CEO breaks the tie.
**Hat.** Long-view, customer-mind, willing to disappoint short-term to protect the relationship.

### 1.2 CTO — Technical architecture and engineering decisions
**Mandate.** Owns the architecture. Says yes or no to dependencies, services, schema changes, language choices, infra targets.
**Authority.** Stack choices (Python/Flask stays, additions vetted), data model evolution, deployment target, third-party integrations (OCR vendor, SSO provider), test framework, CI/CD pipeline.
**Failure mode trigger.** When the planner schedules engineering work the architecture cannot absorb, or when the structural reviewer keeps blocking a pattern the engineer wants to use.
**Hat.** Long-life code, willing to slow down for the right architecture.

### 1.3 Supervisor — Day-to-day execution oversight
**Mandate.** Knows what is being worked on right now, what is blocked, what slipped, what is next. The person who reads the TaskList every morning.
**Authority.** Reorder tasks within a phase, pull people off blocked work onto unblocked work, call check-ins, escalate to CTO or CEO when a task slips beyond budget.
**Failure mode trigger.** A task in_progress for more than 2x its estimated duration without an explanation.
**Hat.** Tactical, present-tense, asks "what is in the way."

### 1.4 Planner — Work breakdown, sequencing, dependencies
**Mandate.** Translates phase goals into a sequenced backlog. Writes the dependency graph. Estimates effort.
**Authority.** Task creation, task ordering, dependency declarations, effort estimates, sprint scoping if sprints are used.
**Failure mode trigger.** When new work arrives mid-phase, the planner re-sequences and surfaces the impact ("this adds 3 days; here is what slides").
**Hat.** Calendar-aware, scope-aware, willing to say "this is out of scope for this phase."

### 1.5 Structural reviewer — Code quality and architectural invariants
**Mandate.** Reviews every PR (or every commit if no PR flow). Enforces the invariants: no LLM in calc pipeline, every finding cites its field, refusal beats fabrication, snapshots immutable, audit log append-only, determinism.
**Authority.** Block any merge that violates an invariant. Require tests for new behaviors. Require deletion of dead code.
**Failure mode trigger.** An invariant is in tension with a deadline; structural escalates to CTO.
**Hat.** Long-term-maintainer-of-this-code. Asks "will this still make sense in 18 months."

### 1.6 QA / Auditor — Independent verification
**Mandate.** Runs the audit at each phase gate. The author of AUDIT_PLAN.md and the executor of it. Crucially, this role operates with the anti-cheating protocol — does not read the builder's tests or fixtures when designing new test scenarios.
**Authority.** Pass or fail a phase. Surface findings. Require fixes before phase advancement.
**Failure mode trigger.** A blocker finding the builder disputes. The dispute goes to the CEO with both sides written down.
**Hat.** Adversarial-but-fair. The auditor's job is to find what is broken, not to defend the builder's feelings.

### 1.7 Risk and compliance — Security, audit-log integrity, regulatory
**Mandate.** Owns the production-gate concerns: SOC 2 posture, data residency, PDPA/DPDPA/GDPR compliance, audit-log tamper-evidence, key rotation, retention.
**Authority.** Block any feature that violates a compliance constraint. Require legal review before any data leaves a defined boundary. Veto third-party services that fail diligence.
**Failure mode trigger.** A regulator question or a Big 4 auditor pushback that touches data integrity.
**Hat.** Pessimistic-by-design. Assumes the worst actor and the worst circumstance.

### 1.8 Documentation steward — Keeps docs in sync with reality
**Mandate.** When code changes, the relevant doc changes in the same commit. The SYSTEM_SPEC, the README, the CURRENT_STATE inventory, the runbooks.
**Authority.** Block a PR that ships behavior change without doc change. Schedule the weekly doc-drift review.
**Failure mode trigger.** Doc and code disagree (caught by audit drift checks).
**Hat.** Future-self-friendly. Writes for the person debugging at 2am six months from now.

---

## 2. Decision rights matrix

When the question is X, the answer comes from role Y. If two roles could answer, the table says who has the tie-break.

| Question | Primary decider | Override path |
|---|---|---|
| "Should we add this feature to Phase N?" | Planner (yes/no for scope), CEO (override if strategic) | CEO can pull anything into any phase; planner re-sequences |
| "Should we use library X / service Y?" | CTO | CEO can override only on commercial grounds (vendor relationship, cost) |
| "Should we ship this PR?" | Structural reviewer | CTO can override after written rebuttal |
| "Is Phase N done?" | QA / Auditor | CEO + CTO co-sign at phase gate |
| "Is this finding a blocker or a major?" | QA / Auditor proposes, CTO accepts or escalates to CEO | CEO has final |
| "Should this engagement use the tool?" | Subhankar-as-analyst (not in this role list — that is engagement work, not tool work) | Evelyn |
| "Should we change the spec mid-phase?" | CEO, advised by CTO and QA | If touching invariants, requires CTO + QA both yes |
| "Should we deploy to production?" | CTO greenlights infra, Risk greenlights security, CEO greenlights timing | Three yeses required |
| "Should we accept this audit finding's rebuttal?" | CEO arbitrates with both sides written | Written record kept |
| "Should we sunset / archive a feature?" | CEO | Documentation steward writes the death note |

---

## 3. Escalation triggers

A trigger is a condition that requires a role to stop working and surface the issue. Not a suggestion. A discipline.

### 3.1 Within a phase
- **Slippage.** A task exceeds 2x its planned duration → supervisor surfaces to planner. If the cause is technical, planner pulls in CTO. If strategic, planner pulls in CEO.
- **Invariant tension.** A planned implementation cannot satisfy a cross-cutting invariant → structural escalates to CTO. CTO either redesigns or seeks CEO override (CEO + QA must both sign off on any invariant relaxation).
- **Audit finding blocked work.** A blocker finding from QA blocks merge → builder fixes or writes rebuttal within 48h; CEO arbitrates if dispute persists.
- **Scope creep.** A new ask arrives mid-phase that adds >2 days work → planner declines for current phase, logs to change log, schedules for next phase. Only CEO can override.

### 3.2 Cross-phase
- **Phase gate fail.** QA's audit shows blockers → phase does not advance. Builder cycle continues until blockers clear. CEO sets a hard re-audit date.
- **Strategic shift.** New information from Qapita (Evelyn changes her mind on Path A vs B, Vamsee declines the stack proposal, a competitor ships something material) → CEO calls a strategic review within 7 days. Roadmap may be revised.
- **External pressure.** Big 4 auditor surfaces a real concern about a feature in production → Risk + CTO + CEO emergency meeting within 24h. May trigger production rollback.

### 3.3 Emergencies (always wakeup-level)
- Data leak, security breach, unauthorized access.
- Audit log tampering detected.
- A real client's cap-table data lost or corrupted.
- Public statement about Qapita that exposes the tool.

---

## 4. Communication patterns

### 4.1 Routine cadence

| Cadence | Format | Owner | Purpose |
|---|---|---|---|
| **Daily** | 5-min self-check at start of work session | Supervisor | What is in progress, what is blocked, one thing I will finish today |
| **Weekly** | 30-min phase progress review, Friday | Supervisor + Planner | Status of every in-flight task, slippage report, new risks |
| **Bi-weekly** | 60-min architecture review | CTO + Structural | What was built, what was decided, what is now technical debt |
| **Per phase** | Phase-gate audit (per VERIFICATION_MATRIX §5.2) | QA + CEO + CTO sign | The formal sign-off |
| **Monthly** | 60-min strategic review | CEO | Are we still building the right thing? Is Qapita's situation what we assumed? Does the plan need to shift? |
| **Quarterly** | Full doc-drift audit | Documentation + QA | Confirm SPEC ↔ code ↔ tests ↔ README all still aligned |

### 4.2 Artifacts that get produced at each cadence

| Cadence | Artifact | Where it lives |
|---|---|---|
| Daily | TaskList updates (in_progress / completed) | Task system |
| Weekly | One-paragraph status note appended to a `WEEKLY_LOG.md` | Repo root |
| Bi-weekly | Architecture decision record (ADR) for each significant decision | `docs/decisions/ADR-NNN-*.md` |
| Per phase | Audit PDF + companion XLSX + sign-off page | `audits/phase-N-YYYYMMDD/` |
| Monthly | Strategic-review note | `notes_private/strategic-YYYY-MM.md` |
| Quarterly | Doc-drift report | `audits/doc-drift-YYYYQN.md` |

The artifacts are evidence the cadence happened. Skipping the artifact is skipping the cadence.

### 4.3 Asynchronous communication

Most work is solo. The "communication" is between hats, not between people. Practical patterns:

- **Decision log.** When the CEO hat makes a strategic call, write a one-line entry in `DECISIONS.md` with date, decision, why, who-disagreed (if anyone). Becomes the record when "wait, why did we do it that way?" comes up 6 months later.
- **TODO marker convention.** `# TODO[role]: text` in code. `# TODO[structural]: this duplicates the auth check in `app.py:512`, refactor pre-merge.` Searchable, attributable.
- **Pre-mortem habit.** Before any non-trivial change, write a 5-line "what could go wrong" note. Lives in the PR description or in the commit body. Forces the structural and risk hats to engage before the code is written.

---

## 5. Change management — when something pops up mid-build

The user said this explicitly: leave room for new things, occasional check-ins, consistent improvising. Here is the protocol.

### 5.1 What counts as "something popping up"

- A real bug found during development (not in the audit) that affects in-flight work.
- A new requirement from Evelyn (most common: "while you're in there, can you also…").
- A new constraint from Vamsee or Risk (new SSO policy, new data-residency rule).
- A new fact about Qapita's stack or workflow that invalidates an assumption.
- A regulatory change (RBI / SEBI / IRAS / SEC issues a new circular touching cap-table reporting).
- A competitor announcement that changes the strategic frame.
- Something Subhankar learns while reading or thinking that materially shifts the plan.

### 5.2 The triage protocol — 4 questions, in order

1. **Is it urgent (regulatory / security / client-facing data integrity)?** If yes → emergency protocol §3.3. If no → continue.
2. **Does it affect the current phase, a future phase, or no phase?**
   - Current phase → planner evaluates impact, supervisor may re-sequence.
   - Future phase → log to `BACKLOG.md` with phase tag.
   - No phase / not relevant → log to `BACKLOG.md` under "deferred / out of scope" with rationale.
3. **Can the current phase still meet its definition-of-done without addressing it?** If yes → defer. If no → re-scope or extend phase.
4. **Does any cross-cutting invariant change?** If yes → CEO + CTO + QA review. Spec amendment may be needed. Trigger §3.2 escalation.

### 5.3 The "improvise" license

The user wants room to improvise. Concretely:

- Any role may **propose a deviation from the plan** in writing (1 paragraph) at any time. The proposal is logged.
- The proposal must answer three questions: (a) what is the deviation, (b) what triggered it, (c) what changes downstream.
- If the deviation is local (within one role's authority), that role decides and logs.
- If the deviation crosses roles, the most-senior affected role decides (CEO breaks any tie).
- Deviations are reviewed at the next monthly strategic review. A pattern of similar deviations means the plan was wrong; the plan gets revised.

The improv license is bounded by the invariants. No improv ever introduces an LLM in the calc pipeline, mutates a snapshot, or skips an audit gate.

### 5.4 The "kill switch"

CEO has the explicit authority to pause the build at any phase for any duration. The kill switch is for: "I am no longer confident this is the right thing." It is not a failure — it is a feature of the agency.

When the kill switch fires:
- All in-flight work is committed in its current state.
- A `PAUSE_NOTE.md` is written: why, what state we are in, what would need to be true to resume.
- The TaskList is frozen with everything marked as paused.
- Resumption requires a written restart note answering the questions in the pause note.

The kill switch has been used zero times by definition right now. The point of naming it is to make using it psychologically possible.

---

## 6. The build-time discipline checklist

Every coding session (every time the human sits down to build), the supervisor hat runs this checklist before opening a file:

1. Read `WEEKLY_LOG.md` for last week's status note. Two minutes.
2. Read `BACKLOG.md` for anything urgent that came in async. One minute.
3. Read the TaskList. Confirm which task is currently in_progress and that the description still matches what is being worked on. One minute.
4. Open the relevant ADR if one exists for this area. Two minutes.
5. Confirm tests pass on the current branch before starting new work. One minute (or however long pytest takes).
6. Write a one-line intention: "Today I will finish X." Sets the supervisor's exit condition for the session.

Total: ~10 minutes. Skippable on a "I am pasting a typo fix" session. Mandatory on anything else.

---

## 7. The build-time anti-pattern list

Things the supervisor hat watches for and stops:

- **Drift from the in_progress task** without updating the task. ("I started fixing Y but ended up refactoring Z.") Either update the task or stop and restart.
- **Long-running work without a commit.** > 90 minutes of work without committing is a smell. Either commit or write down why not.
- **Coding without a failing test.** When the goal is fixing a bug or adding behavior, the test comes first (or the case for "test impossible here" is written down).
- **Reading files outside the in_progress task's scope** unless explicitly for understanding. The supervisor flags rabbit holes.
- **Adding new dependencies during a phase without CTO sign-off.** Even small ones. Adds blast radius without thought.
- **Editing the spec at the same time as the code that implements it.** Spec changes are documentation-steward concerns and require a separate commit with a stated reason.

---

## 8. The audit-time anti-pattern list

Things the QA / auditor hat watches for and stops (in addition to the cheating watch-list in `VERIFICATION_MATRIX.md §4`):

- **Builder argues with a finding before fully understanding it.** Rebuttal requires understanding first.
- **A test added "to make the audit happy" without being added to the regression suite.** Tests are tests forever, not audit decorations.
- **A finding "fixed" by a behavior change that introduces a new behavior nobody tested.** The fix gets its own test.
- **Spec amended to remove a refusal that the auditor caught violating.** This is the §4.1 hard cheat from VERIFICATION_MATRIX; immediate fail.

---

## 9. The check-in calendar (year 1, post-Aug-2026)

This is the calendar the agency commits to before build starts. Items in italics are auditor-led, not builder-led.

| Date | Event | Owner | Output |
|---|---|---|---|
| Aug 1, 2026 | Day 1 at Qapita | All roles | First TaskList for Phase 1 |
| Aug 8 | Week 1 review | Supervisor | First WEEKLY_LOG entry |
| Aug 30 | Phase 1 audit (Day-30 pitch) | *QA* | Audit PDF, Path A/B decision |
| Sep 15 | Phase 2 kickoff (assumes Path A) | CEO | Phase 2 task plan |
| Sep 30 | Monthly strategic review | CEO | Strategic note |
| Oct 15 | Phase 2 mid-phase smoke audit | *QA* | Smoke audit report |
| Oct 30 | Monthly strategic review | CEO | Strategic note |
| Nov 15 | Phase 2 full audit | *QA + Big 4 sample* | Phase 2 sign-off |
| Nov 30 | Phase 3 kickoff | CEO | Phase 3 task plan |
| Dec 15 | Phase 3 mini-audit + Q4 doc-drift audit | *QA + Documentation* | Mini audit + doc-drift report |
| Dec 31 | NOC internship ends. Year-end strategic review. | CEO | Year-end note, continuation plan |
| (post-NOC) | Phase 3 full audit | *QA + Big 4 partner* | Phase 3 sign-off |
| (post-NOC) | Phase 4 quarterly audits | *External Big 4 named partner* | Quarterly sign-offs |

This calendar is a hypothesis. The monthly strategic review revises it.

---

## 10. The agency's covenant with itself

Three commitments the agency makes to itself and re-reads at the start of each phase:

1. **We do not lie to ourselves.** Audits surface real findings. Findings are addressed or rebutted with written reasoning. Hiding is the hardest cheat to detect and the worst one to allow.
2. **We ship by Saying No.** Every "yes" to a feature is a "no" to ten other things. The refusal list (`SYSTEM_SPEC.md §7`) is the soul of the product. Adding to it is hard. Removing from it is harder.
3. **We protect the relationship before we protect the code.** The point is Evelyn's team using the tool, not the tool being beautiful. If a feature would alienate the team, it loses. If a polish makes adoption easier, it wins even if it adds technical debt.

That is the structure. The roles are scaffolding. The cadence is discipline. The improv license is honest. The kill switch is real. Build begins when the build-ready signoff says it does, not before.
