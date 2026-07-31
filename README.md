# agent-workflow

A board-driven, multi-agent development workflow for Claude Code —
works with **Trello** (via MCP) or **GitHub Issues** (via `gh`, no MCP
needed); other trackers are one provider descriptor away.
A meta-agent triages cards into reviewable plans, a human approves by
dragging a card, and an orchestrator executes: isolated git worktree →
(TDD gate: failing specs → adversarial test critic) → worker implements →
two-verdict acceptance audit → auto-merge or human review. Every step
leaves an audit trail on the card.

Synthesized from studied methodologies plus production experience:
[github/spec-kit](https://github.com/github/spec-kit) (constitution,
clarify-before-plan, WHAT/HOW separation),
[obra/superpowers](https://github.com/obra/superpowers) (two-stage review,
evidence-before-claims, TDD iron law),
[garrytan/gstack](https://github.com/garrytan/gstack) (the quote-the-evidence
verification gate and file-anchored project learnings are adapted from its
review/learnings mechanics), and an adversarial-critics TDD process
(refute-framed test critic, mutation-resistance checks).

Extracted from a live project and used in production by its two original
repos (a Rails web app and a Rust/Tauri desktop app) — every mechanism
here was earned by a real failure, and `docs/design-notes.md` records
which one.

## The flow

```
Icebox → Backlog → [/flow-check] → Plan Proposed ─(human drags)→ Ready for AI
                       ↓ questions                                     ↓ [/flow-run]
                  Human Questions                              In Progress
                                                                    ↓
                                        worktree + guardrail hooks + branch
                                                                    ↓
                                     TDD gate (M/L or risky cards): specs-only worker
                                        → test critic (job: REJECT the specs)
                                        → implementation resumes same session
                                                                    ↓
                                     acceptance subagent: 8 checks, severity triage,
                                     two verdicts (spec compliance + code quality),
                                     constitution re-check against the DIFF
                                                                    ↓
                            gaps → retry (≤3 iterations) │ minor → ledger comment
                                                                    ↓
                        auto-merge (confidence/risk/CI gates) → Done │ else → Review
```

Key properties:
- **Humans gate twice**: approving the plan (drag to Ready) and, when
  auto-merge criteria fail, reviewing the PR. Everything else is agents.
- **Constitution**: project non-negotiables live in
  `.claude/constitution.md`; every plan carries a per-article gate and
  the acceptance check re-verifies the diff. See
  `constitution-template.md` and `examples/constitution-rodnik-web.md`.
- **Workers are guardrailed** (not sandboxed): fresh `claude -p` in a
  git worktree; a PreToolUse hook rejects edits outside the plan's file
  manifest and another blocks history rewrites / self-merge. These
  hooks catch a well-meaning worker drifting off-plan — they are NOT a
  security boundary (a plain Bash file write never hits the scope hook,
  and light obfuscation slips the git regexes); the acceptance check
  re-enforces scope post-hoc. See "Threat model" below.
- **Verdicts require evidence**: no "should pass" anywhere in the chain —
  fresh command output or it didn't happen. Acceptance findings must
  quote the motivating line (unquotable → demoted to minor), and every
  finding carries a stable fingerprint that meta tracks across
  iterations: repeats are marked, ledgered minors aren't re-litigated,
  and two identical gap sets in a row block the card early instead of
  burning the last iteration.
- **Project memory compounds**: acceptance and the test critic surface
  non-obvious, file-anchored discoveries into `.claude/learnings.jsonl`
  (meta is the single writer — dedup by key, staleness via anchored
  files); triage reads them when drafting PLANs and workers get the
  relevant ones injected before touching code, so the same pitfall
  isn't rediscovered on card 30.

## Repository layout

```
kit/                    → copy into your repo's .claude/
  commands/             /flow-check, /flow-run (+ helpers) — the orchestrators
  prompts/              plan format, card triage, worker bodies (iter1/specs/impl/iterN),
                        test-critic, acceptance-check, roles/
  hooks/                scope-guard.sh, git-guard.sh, worker-settings.json
  bin/                  parse-verdict, harvest-learnings, render-learnings —
                        the tested mechanical halves of /flow-run
constitution-template.md → seed for your .claude/constitution.md
examples/               a real, incident-driven project constitution
  providers/            tracker descriptors: trello.md, github.md — how meta
                        performs the semantic ops on each tracker
docs/                   design-notes.md + tracker.example.*.json
tests/                  kit self-checks (static invariants, run in CI)
```

## Requirements

- Claude Code CLI (`claude`) with an API plan that allows spawning
  headless workers (`claude -p`).
- `gh` (authenticated), `git`, `jq`.
- A task tracker, one of:
  - **Trello** — an MCP server exposing `mcp__trello__*` tools, e.g.
    [`@delorenj/mcp-server-trello`](https://github.com/delorenj/mcp-server-trello);
    a board with the ten pipeline lists (Icebox, Backlog, Triage in
    progress, Human Questions, Plan Proposed, Ready for AI, In Progress,
    Review, Blocked, Done).
  - **GitHub Issues** — no MCP: the kit drives `gh` directly; pipeline
    states are `flow:*` labels (one-time setup in
    `kit/providers/github.md`).
  Everything provider-specific lives in `kit/providers/<name>.md` —
  adding a tracker is one descriptor file, not a fork of the commands.

## Threat model (read before adopting)

What the kit defends against, and what it deliberately does not:

- **Defended: honest-mistake drift.** The scope/git hooks, the file
  manifest, the acceptance re-check and the two-verdict audit exist to
  catch a *well-meaning* worker going off-plan. That is the designed
  failure mode, and the layers are redundant on purpose.
- **NOT defended: a malicious card.** Card text, PLAN comments and PR
  bodies are injected into worker/acceptance prompts, and workers run
  with `--permission-mode bypassPermissions` inside the worktree. A card
  authored by an attacker is a prompt injection with shell access.
  **The tracker is a trusted input** — restrict board/repo write access
  to people you'd give a shell.
- **NOT defended: a malicious worker.** `git-guard`/`scope-guard` are
  regex/manifest checks on tool-call arguments, and real bypasses are
  trivial (verified): `scope-guard` matches only the edit tools, so a
  Bash `echo hacked > file` writes anywhere unchecked; `git-guard`
  greps the raw command string, so quote-splitting the flag
  (`git push --for''ce`) walks past it. Treat the hooks as guardrails,
  not containment. If you need containment, run `/flow-run` itself
  inside a VM/container with a repo-scoped token.
- **Blast radius**: a worker holds whatever credentials the worktree
  environment exposes (`gh` token, env vars). Scope the token to the
  target repos; never export unrelated secrets into the meta session
  that spawns workers.

## Canonical source & staying in sync

**This repo is the canonical source of the kit.** Consumers do not edit
kit files in their own repo — they edit HERE (PR to this repo), then pull:

1. Copy `scripts/workflow-kit-sync` into your repo (e.g. `bin/`) once,
   during adoption.
2. Run `bin/workflow-kit-sync` to pull the latest kit. It overwrites
   `.claude/{commands,prompts,hooks,bin,providers}` (deletions propagate), never touches
   project-owned files (`tracker.json`, `constitution.md`,
   `project-context.md`, `settings.local.json`, the committed
   `learnings.jsonl` memory, optional `prompts/ui-design.md`), and
   records the kit SHA in
   `.claude/KIT_REVISION`.
3. Review the diff, commit.

First production consumers: two private repos of the original project (a
Rails web app and a Rust/Tauri desktop app), synced through this exact
mechanism.

**Contributing (humans AND agents): `main` is PR-only by convention.** The
org plan has no enforced branch protection, so this is a standing rule,
not a technical gate: never push to `main` directly — branch, open a PR
with a rationale, merge after review (self-merge is acceptable for
trivial doc fixes; prompt/behavior changes wait for a human or a second
agent). Direct pushes to `main` are treated as incidents.

Before opening a PR, run `bash tests/kit-invariants.sh` (needs only
`bash` + `jq`) — CI runs the same script. It pins the invariants that
break silently: dangling file references, placeholders a prompt body
uses but doesn't declare, verdict-contract keys drifting between a
prompt and the meta code that parses it, invalid JSON artifacts, and
prompt size budgets (raising a budget is allowed, but it's a conscious
diff in the test file, not silent growth).

## Adoption (human or agent — ~15 minutes)

1. Copy `kit/` into the target repo as `.claude/` (commands/, prompts/,
   hooks/, bin/, providers/ — keep paths) and `scripts/workflow-kit-sync` as
   `bin/workflow-kit-sync`.
   `chmod +x .claude/hooks/*.sh .claude/bin/* bin/workflow-kit-sync`.
2. Create `.claude/constitution.md` from `constitution-template.md`. Keep
   the universal articles; write 3–7 PROJECT articles — each earned by a
   real incident/constraint (see `examples/`).
3. Create `.claude/tracker.json` from the example for your tracker
   (`docs/tracker.example.trello.json` / `docs/tracker.example.github.json`):
   provider + board/repo, state ids or labels, `card_prefix` (e.g. `ACME`),
   `targets` (repo_root + toolchain + test_cmd/lint_cmd per repo),
   `default_target`, `tdd_gate` thresholds, `auto_merge_criteria`.
4. Create the session log file (default `.gilb/session-log.md`, path is
   configurable in tracker.json). The learnings file (default
   `.claude/learnings.jsonl`, key `learnings`) is created lazily by meta on
   first harvest — nothing to do here.
5. Write `.claude/project-context.md`: stack, language conventions,
   commit format — workers read it before touching code.
6. Smoke-test: put one small card in Backlog → run `/flow-check` →
   review the PLAN it posts → drag to Ready for AI → run `/flow-run` →
   watch the card land in Done/Review with an audit trail.

### Giving this workflow to an agent (e.g. an autonomous cofounder agent)

Grant the agent read access to this repo and say:

> Adopt the development workflow from <repo-url> in project X: follow
> README "Adoption" steps 1–6. Ask me for: the tracker (Trello board /
> GitHub repo) to use, the
> card prefix, and the project articles for the constitution (propose a
> draft from the incidents you know). Do not modify kit files themselves —
> configuration lives in tracker.json / constitution.md / project-context.md.

The kit is agent-agnostic on the meta side: any agent that can call the
tracker (MCP or `gh`), run `claude -p` and `jq` can act as the orchestrator —
the worker/critic/acceptance chain always runs on Claude Code.

## Tuning

- `tdd_gate` (tracker.json): `enabled`, `min_size` (S/M/L), `min_risk` —
  which cards get the specs-first + test-critic path. Below the gate,
  workers still follow inline test-first discipline.
- `auto_merge_criteria`: `min_confidence`, `max_risk`, `require_ci_green`,
  `strategy`. Research cards never auto-merge.
- `worker.model` / `acceptance.model`: per-stage model override (e.g. a
  cheaper model for acceptance).
- `--parallel N` on `/flow-run`: up to 4 cards in flight.
- `/flow-run --resume <card>`: continue a card whose meta session died
  mid-run — per-card state is journaled to
  `<worker_log_dir>/<card-short>-state.json` at every phase boundary
  (worker spawn, parse, verdict, merge decision).
- `/flow-clean`: the sanctioned worktree cleanup — lists finished-card
  worktrees (card Done + PR merged/closed + clean tree) and removes only
  what the human confirms. `/flow-run` itself never deletes worktrees.

## Known origins

The kit was extracted from a live project (card prefix RDK, earlier
GILB). The example constitution's filename and the default state
directory `.gilb/` (configurable per target in `tracker.json`) still
carry the original names — historical, not functional; they have no
effect on behavior.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) — the short version: run both test
suites before every PR, `main` is PR-only, prompt growth is budgeted, and
mechanical logic belongs in `kit/bin/` with behavioral pins.

## License

[MIT](LICENSE). The methodologies credited above have their own licenses
in their own repos; nothing from them is copied verbatim here — the
mechanisms are re-implementations adapted to this kit's tracker/PLAN
architecture.
