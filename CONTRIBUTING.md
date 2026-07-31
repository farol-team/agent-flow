# Contributing

The prompts and commands in `kit/` ARE the product — treat every line as
shipped code. This file is the practical loop; the standing rules live in
the README ("Canonical source & staying in sync").

## Before every PR

```sh
bash tests/kit-invariants.sh   # static contracts (needs bash + jq)
bash tests/kit-bin.test.sh     # behavioral pins for kit/bin/*
```

CI runs both. Green locally = green in CI; there is no hidden step.

## Rules that surprise people

- **`main` is PR-only by convention** (no paid branch protection on the
  org plan). Self-merge is acceptable for trivial doc fixes;
  prompt/behavior changes wait for a human or a second, independent
  agent's review. Direct pushes to `main` are treated as incidents.
- **Prompt size budgets are enforced** (`tests/kit-invariants.sh`,
  check 7). Growing a prompt past its ceiling must be a conscious diff
  in the test file — every line of every prompt is context spent on
  every card.
- **New config keys go to `kit/config-contract.txt`**, never inline into
  a script — invariants check the example config against it and
  `workflow-kit-sync` checks every consumer's real config.
- **Mechanical logic goes to `kit/bin/`**, not into command prose: if a
  step has one correct answer (parsing, dedup, selection), it belongs in
  a tested script the orchestrator calls. Add behavioral pins to
  `tests/kit-bin.test.sh` in the same PR.
- **A new tracker = one provider descriptor** (`kit/providers/<name>.md`:
  the seven semantic ops, ref resolution, capabilities + degradation
  rules — see trello.md/github.md for the shape) plus an example config
  (`docs/tracker.example.<name>.json`). The parity invariants will tell
  you what's missing. Command files should not need to change.
- **Verdict/PLAN contract changes must touch both sides** — the prompt
  that produces the format and the command/script that consumes it —
  in one PR. The parity checks will fail you otherwise, by design.

## What a good PR body contains

The rationale (what failure mode this closes, with the incident if there
is one), the verification evidence (both suites' counts), and — for
prompt changes — which contract lines moved. See merged PRs #1–#6 for
the expected shape; `docs/design-notes.md` records the reasoning behind
each shipped mechanism (problem → mechanism → deliberate limit) and is
updated in the same PR when a mechanism changes.
