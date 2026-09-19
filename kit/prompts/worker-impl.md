# Worker prompt template — iteration 1, phase B (implementation)

Sent after the test critic APPROVES phase A. The executor can resume the
phase-A worker or start fresh; this prompt always includes the full plan.
Exhausted spec revisions never authorize implementation.

Placeholders: `<card-url>`, `<branch>`, `<base>`, `<PLAN-comment>`,
`<critic-findings>` (the critic's non-blocking findings, or `none`).

---

Phase A approved. This is **phase B: implement** for card <card-url>.

# Approved plan

<PLAN-comment>

Test-critic findings to keep in mind (non-blocking): <critic-findings>

1. Implement the plan strictly as written — production files from
   `## Files` only; `## Out of scope` is inviolable. Do NOT weaken,
   delete, or rewrite the approved specs to make them pass; if a spec
   turns out to be wrong, that is a BLOCKED reason, not an edit.
2. Make the approved specs pass. Then run EVERY command from the plan's
   `## Tests` (including the scoped lint/format gates) — all must pass
   with fresh output (Article II).
3. Commit per the engineering role's conventions, push:

       git push -u origin <branch>

4. Open the PR via `gh` targeting `<base>`, body per `worker-iter1.md`
   step 6 (first line `Card: <card-url>`; sections `## What`,
   `## Why`, `## Test plan` with the actual commands you ran).
5. Final response: `PR_URL=<url>` — or `BLOCKED: <reason>` per the
   worker-iter1 rules (same conditions, plus "an approved spec is
   unimplementable as specified").
