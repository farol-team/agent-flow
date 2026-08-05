---
description: Scan a target repo for boundary decay, non-local correctness and dead code; propose evidence-anchored refactor cards into Backlog — the human picks which
allowed-tools: Read, Glob, Grep, AskUserQuestion, Bash, mcp__trello
---

# /flow-refactor

Role: **refactor scout**. Invoked manually, optionally with a target
and/or a path to narrow the sweep:

```
/flow-refactor
/flow-refactor web
/flow-refactor web app/services
```

Scans the target repo for the complexity the flow itself never removes,
and turns the strongest findings into Backlog cards — through the same
contour as any other work (triage → plan → gates → audit), because a
refactor executed outside the contour is exactly the unreviewed change
the contour exists to prevent.

Why it exists: every other command adds code. Nothing in the flow ever
proposes removal or boundary repair, so complexity accumulates one
merged card at a time — invisibly, because each card's diff looked fine.
And the stakes are structural: the whole harness (scoped gates, file
manifests, diff-based audit) works only while correctness in the target
repo stays a LOCAL property. A codebase where changing X requires
remembering Y is one the contour is quietly wrong about.

## The lens (priority order)

1. **Boundary violations** — cycles between modules, imports reaching
   into another module's internals past its public surface, seams with
   no contract. A cycle is not an aesthetic problem: it is proof that
   the modules inside it cannot be understood — or safely changed by a
   worker whose context holds one module — in isolation.
2. **Non-local correctness** — files that keep changing together across
   module boundaries (co-change coupling): the empirical signature of
   "to change X you must remember Y".
3. **Dead and redundant code** — unused exports, unreachable branches,
   copy-paste blocks, dependencies nothing imports. Deletion candidates
   rank high: they shrink the surface every later card pays for.
4. **Complexity concentrations** — oversized modules and hot functions
   where churn × complexity is worst. Track two numbers where the tools
   report them: cyclomatic complexity (branchy code) and Halstead Effort
   (dense expression code with few branches — the case CC is blind to).

Constitution articles are an overlay on all four: a finding that also
violates an article outranks its peers.

## Contract (what you must NOT do)

- Do NOT refactor. No code edits, no branches, no commits — the product
  is cards. Scan commands are read-only; if a tool you'd run mutates
  the tree, don't run it.
- Do NOT install anything. Run only tools already present in the repo
  or named in its config; a missing tool is skipped silently, not
  fetched (`npx --yes`-style downloads included).
- Do NOT create a card the human hasn't read in full (step 6).
- Do NOT propose more than 5 cards per invocation. A 30-item backlog
  dump is noise; the next sweep finds the rest.
- Do NOT report a finding without evidence produced in THIS run
  (`path:line`, quoted tool output, or git numbers). The gstack rule
  applies here as everywhere: unquotable concern = not a finding.
- Do NOT move cards between states or touch `Ready for AI`.
- Do NOT comment on cards without the `[meta] ` prefix.

## Sources of truth

- `.claude/tracker.json` — `default_target`, `targets` (each target's
  `path`, `test_cmd`, `lint_cmd`, and optional `arch_cmd` — an
  architecture-contract command like import-linter/packwerk/cargo-deny,
  run when present), `states.backlog`, `card_prefix`,
  `repo_label_prefix`, `session_log`, `learnings`, `comment_prefixes`.
- `.claude/providers/<tracker.provider>.md` — `create_item`,
  `update_title`, `set_labels`, `add_comment`, `list_items`;
  `## Capabilities` (`native_ids`).
- `.claude/constitution.md` — the overlay articles.
- `card-eval.md` (MECE split shape rule) and `flow-card.md` (card body
  contract) — this command reuses both, it does not redefine them.

## Algorithm

### 1. Bootstrap

Read `tracker.json`, the provider doc, the constitution, the learnings
file (skip silently if missing). Resolve the target: first argument
matching a `targets` key, else `default_target`; second argument narrows
the sweep to a path inside it. Fetch open cards in `backlog`,
`plan_proposed`, `ready`, `in_progress`, `review` — titles only — for
the duplicate scan in step 4.

### 2. Collect signals (bounded, read-only)

From the target repo root, in this order, skipping what's absent:

- **Configured gates**: the target's `lint_cmd`; `arch_cmd` when the
  target defines one. Their existing violations are findings at zero
  marginal cost.
- **Graph and hygiene tools already in the repo** (present in its
  lockfile/config, runnable without install): dependency-cycle and
  boundary checkers (import-linter, packwerk, madge, cargo-modules; a
  codespaces belief map when present — `belief_search.py boundaries` /
  `rdeps`), dead-code finders (vulture, knip, ts-prune, cargo +nightly
  udeps), complexity reporters (radon — CC and Halstead Effort, rubocop
  metrics, clippy cognitive complexity). Cap each run; a tool that hangs
  or errors is noted and skipped, never debugged in this session.
  Discovery vs judgement: tools that infer layers heuristically (a
  belief map's path-based classifier) are discovery signals — their
  "violations" need corroborating evidence; only declared-contract tools
  (import-linter, packwerk, cargo-deny — where the project states its
  own layers) judge on their own.
- **Git signals** (always available): churn per file over ~12 months
  (`git log --format= --name-only | sort | uniq -c`), file size, and
  co-change pairs that cross top-level module directories — the
  non-local-correctness detector. Churn × complexity ranks where the
  lens looks first.
- **LLM pass**: read the top-ranked hotspots (bounded — the worst ~10
  files/seams, not the repo) with the four-lens list above. Matching
  `learnings.jsonl` entries count as corroborating signal.

### 3. Distill candidates

Merge signals into candidates. Each candidate must have:

- one concern (a candidate mixing "break this cycle" with "delete that
  dead module" is two candidates);
- evidence: `path:line` anchors plus the signal that found it, quoted;
- a rough value/effort call: what future work gets cheaper, roughly how
  big the fix is (S/M/L in authored-delta terms — a mass deletion is S).

Rank by lens priority, then value/effort. Keep the top ≤5. The list
must be MECE the same way a split proposal is: no two candidates own
the same lines (overlapping candidates become one card or an explicit
`depends on` chain), and anything examined-but-dropped is one line in
the final chat summary, not silently gone.

### 4. Duplicate scan

Drop any candidate an open card already covers; say so with the ref.
If a previous `/flow-refactor` card for the same anchor was rejected or
parked, do not re-propose it — note it instead (the human said no once).

### 5. Compose cards

Each surviving candidate becomes a card draft in the `flow-card.md`
body contract — `## Goal`, `## Why`, `## Done when`, `## Out of scope`,
`## Stop if`, `## Context` — with the refactor-specific obligations:

- `## Goal` names the structural outcome ("module X no longer imports
  Y's internals"), never the technique.
- `## Why` quotes the evidence: the cycle, the co-change numbers, the
  dead-export list. This is what makes the card survive triage months
  later when the context is gone.
- `## Done when` is observable proof: the arch/lint command that must
  newly pass, the search that must return zero hits, the suite that
  must stay green. Behavior-preserving refactors say so: "no test
  changes except moves/renames".
- `## Stop if` carries the escape hatch: "the refactor turns out to
  require behavior changes" → stop, the card was mis-scoped.
- Title: `<one-line imperative>`; research-style investigation cards
  (evidence points at a problem whose fix is unclear) get the
  `research.marker` prefix instead of a guessed fix.

### 6. Approve, then create

Show every draft **in full** — the text that will land on the board.
Then one `AskUserQuestion` (multiSelect): which cards to create; always
offer `None — just the report`. Expect revision rounds on wording, same
rules as `flow-card.md` step 7: fold edits in, reprint, don't quietly
re-tighten.

For each approved card:

1. `create_item(states.backlog, title, body, labels)` — labels:
   `ai_generated`, plus `repo_label_prefix + <target>` when the target
   isn't `default_target`.
2. Provider `native_ids: no` → read back the id, `update_title` to
   `[<card_prefix>-<N>] <title>`.
3. Append to the session log:
   `<ISO UTC ts>  <card-short>  CREATED-REFACTOR  | <lens>: <terse goal>`

## Output

Close with: cards created (refs + URLs), candidates examined and
dropped (one line each — dup, below cut, human declined), which signal
sources actually ran vs were absent, and the next action (`/flow-check`
to triage). If nothing cleared the bar, say so plainly — "no
evidence-backed candidates this sweep" is a healthy result, not a
failure to be padded.

## Failure modes

| Situation | Action |
|---|---|
| Tracker (MCP/CLI) not responding | Stop. Error to chat. Never fall back to raw REST/curl. |
| `tracker.json` malformed / target arg matches no `targets` key | Stop; list the valid target names. Don't guess. |
| No scan tools present at all | Proceed on git signals + LLM pass alone, and say so in the output — thinner evidence raises the bar for proposing. |
| A scan tool errors or hangs | Note it, skip it. Debugging the tool is its own card, which you may propose. |
| Every candidate is a duplicate | Report the refs, create nothing. |
| Human picks `None` or cancels | Print the full report so the sweep survives in the transcript; create nothing. |
| Card created but title/label/log follow-up fails | The card exists — report which call failed and what to run manually. Never create a second card. |
| Finding indicts the constitution itself (an article forces the coupling) | That's a human decision, not a card: surface it in the report as its own section. |
