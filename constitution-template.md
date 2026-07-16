# Constitution

Non-negotiable engineering articles for this repo. Every PLAN is validated
against these articles BEFORE work starts (`## Constitution gate` — one
verdict per article: `pass` / `n/a` / `violates — <justification>`), and
the acceptance check re-validates the actual DIFF after.

Enforcement touchpoints:
1. `/trello-check` (card-eval) — every code PLAN must contain a
   `## Constitution gate` section; a `violates` without justification
   fails self-check.
2. Worker — the gate section is part of the PLAN contract.
3. Acceptance check — re-verifies the DIFF against each article;
   violations are Critical gaps.

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
and before the implementation. Tests assert BEHAVIOR, not implementation
details. A test that would still pass if the feature body were replaced
with `return nil` is not a test.

### Article II — Evidence Before Claims
No completion claims without fresh verification evidence. "Done", "fixed",
"passing" require the actual command output from THIS session. Banned as
substitutes: "should work", "probably", "I'm confident", "seems to". When
delegating to a subagent, verify its result independently.

### Article III — Simplicity & Anti-Abstraction
Use the framework directly; do not wrap it. No abstraction until the
second concrete use exists. The minimal diff that satisfies the plan wins.
Do not add error handling for scenarios that cannot happen.

### Article IV — Scope Discipline
Only the files in the PLAN's `## Files`; `## Out of scope` is inviolable.
If reality contradicts the plan mid-work — BLOCKED, not improvisation.

### Article V — Integration-First Testing
Prefer realistic environments: the real database over mocks, the actual
queue adapter over stubs. Mock only at true process boundaries (external
HTTP APIs, paid services, clock).

---

## Project articles

<!-- Populate with YOUR project's non-negotiables. Each article should be
     earned: cite the incident, constraint, or hard decision behind it.
     See examples/constitution-rodnik-web.md for a real, incident-driven
     set (multi-tenancy, job-queue isolation, external-API write bans,
     schema-dump mirroring). Aim for 3-7 articles per section; a
     constitution nobody can hold in their head stops being checked.

     TARGET SCOPING (multi-repo boards): when trello.json defines several
     execution targets, split project articles into per-target sections —
     `## Project articles (<target-name>)`, names matching the `targets`
     keys — plus an optional `## Project articles (all targets)` for
     cross-cutting rules. A card's Constitution gate covers the universal
     articles + its own target's section (+ the all-targets section).
     A constitution with a single unnamed `## Project articles` section
     applies to every target (single-repo default). Prefix article
     numbers per section (P1…, T1…) — numbers are never reused. -->

### Article P1 — <name>
*(Rationale: <incident / decision, one line>.)*
<the rule, stated so a reviewer can check a diff against it>
