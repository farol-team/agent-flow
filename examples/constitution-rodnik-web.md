# Constitution

Non-negotiable engineering articles for this repo. Inspired by spec-kit's
constitution: every PLAN is validated against these articles BEFORE work
starts, and the acceptance check re-validates the actual diff AFTER. An
article violation without a documented justification blocks the card.

Enforcement touchpoints:
1. `/trello-check` (card-eval) — every code PLAN must contain a
   `## Constitution gate` section: one verdict per article
   (`pass` / `n/a` / `violates — <justification>`). A `violates` without
   justification → the plan fails self-check.
2. Worker — the gate section is part of the PLAN contract the worker
   implements under.
3. Acceptance check — re-verifies the DIFF (not the plan's words) against
   each article; violations are Critical gaps.

Amendment procedure: articles are added/changed by PR only, each with a
one-line rationale citing the incident or decision that motivated it.
Articles are numbered and never renumbered — retired articles are marked
`(retired)`, not deleted.

---

## Universal articles (any project using this kit)

### Article I — Test-First
No production code before a failing test that demands it. The RED phase
counts only when the test fails **for the right reason** (the feature is
missing) — not a typo, not a broken setup. Tests are committed separately
and before the implementation. Tests assert BEHAVIOR (what the code should
do), not implementation details (how it happens to do it). A test that
would still pass if the feature body were replaced with `return nil` is
not a test.
Rebuttals to the usual rationalizations: "I'll test after" → tests-after
answer *what does this do*, tests-first answer *what should this do*;
"I already manually tested" → manual runs don't survive the next change;
"keeping the code as reference" → delete it and restart from the test.

### Article II — Evidence Before Claims
No completion claims without fresh verification evidence. "Done", "fixed",
"passing" require the actual command output from THIS session — not memory,
not expectation. Banned as substitutes for evidence: "should work",
"probably", "I'm confident", "seems to", a bare "Great!". A linter passing
is not a build passing; a build passing is not tests passing. When
delegating to a subagent, verify its result independently — never relay
its success report as your own evidence.

### Article III — Simplicity & Anti-Abstraction
Use the framework directly; do not wrap it. No abstraction until the
second concrete use exists. The minimal diff that satisfies the plan wins;
"while I'm here" changes are scope creep (see Article IV). Do not add
error handling, validation, or fallbacks for scenarios that cannot happen.

### Article IV — Scope Discipline
Only the files in the PLAN's `## Files`; `## Out of scope` is inviolable.
If reality contradicts the plan mid-work — BLOCKED, not improvisation.
(Mechanically enforced by the scope-guard hook; this article is why the
hook exists.)

### Article V — Integration-First Testing
Prefer realistic environments where the toolchain supports it: the real
database over mocks, the actual queue adapter over stubs. Mock only at
true process boundaries (external HTTP APIs, paid services, clock).

---

## Project articles (web)

### Article P1 — Tenancy Above All
Every query, index, uniqueness constraint, and background job is scoped by
`company_id`. No cross-tenant reads or writes, ever — including analytics,
digests, and agent-facing APIs (RLS enforces this at the DB layer for the
agent query API; application code must match). New tables carry
`company_id` + `belongs_to :company` from the first migration.

### Article P2 — Incremental Work Only
*(Rationale: 2026-07-14 — a full-snapshot reconciler froze all prod job
processing.)* A recurring or background job must NEVER re-pull an entire
external snapshot or scan a whole large table. Fetch only what changed
since the last run (windowed by `updated_at` / a stored cursor). A
recurring job must complete well within its schedule interval.

### Article P3 — Pipeline Queue Is Sacred
*(Same incident.)* Heavy provider-sync work never runs on a queue the
meeting pipeline shares. New heavy jobs go to `low` (or a dedicated
queue), never `default`-alongside-`pipeline`. When adding a job, state its
queue explicitly in the PLAN.

### Article P4 — Zero CRM Writes
Nothing is written to the external CRM. Internal linking sets the foreign
key directly (`update_columns`) so the link attribute stays nil and the
sync-to-CRM job never fires. Any change that could trigger an outbound
CRM write is `violates` and needs explicit human sign-off on the card.

### Article P5 — Schema Dumps Are Triplets
*(Rationale: `meetings.call_class` was silently clobbered in tests.)* A
new column on a table shared with the queue/cable databases must be
mirrored into all three dumps: `db/schema.rb`, `db/queue_schema.rb`,
`db/cable_schema.rb` — `maintain_test_schema!` clobbers columns that exist
in only one.


---

## Project articles (tauri)

*(Execution target `tauri` — the desktop recorder app, a sibling
Rust/Tauri repo.)*

### Article T1 — Recording Is Sacred
The audio/capture path never blocks and never panics: no synchronous IO,
network calls, or lock contention on the capture thread; heavy work is
handed off through channels. A dropped frame is a bug; a killed recording
is an incident.

### Article T2 — No Panics in Production Paths
No `unwrap()` / `expect()` / `panic!` outside tests and build scripts.
Errors propagate via `Result` and are handled where recovery is possible;
the app degrades (skips a feature), it does not crash mid-meeting.

### Article T3 — Crash-Safe Capture
A crash or power loss may not lose an in-progress recording: capture
state is written incrementally to disk and recoverable on next launch.
Any change to the recording pipeline states in the PLAN how the
in-progress artifact survives interruption.

### Article T4 — Content Stays Local Until Upload
Recordings and transcripts never leave the machine except through the
documented upload path to the backend. No third-party telemetry or crash
reporting that could carry meeting content.
