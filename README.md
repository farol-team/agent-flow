# agent-workflow

A Trello-driven, multi-agent development workflow for Claude Code.
A meta-agent triages cards into reviewable plans, a human approves by
dragging a card, and an orchestrator executes: isolated git worktree →
(TDD gate: failing specs → adversarial test critic) → worker implements →
two-verdict acceptance audit → auto-merge or human review. Every step
leaves an audit trail on the card.

Synthesized from three studied methodologies plus production experience:
[github/spec-kit](https://github.com/github/spec-kit) (constitution,
clarify-before-plan, WHAT/HOW separation),
[obra/superpowers](https://github.com/obra/superpowers) (two-stage review,
evidence-before-claims, TDD iron law), and an adversarial-critics TDD
process (refute-framed test critic, mutation-resistance checks).

## The flow

```
Icebox → Backlog → [/trello-check] → Plan Proposed ─(human drags)→ Ready for AI
                       ↓ questions                                     ↓ [/trello-run]
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
- **Workers are sandboxed**: fresh `claude -p` in a git worktree, scope
  limited by a hook-enforced file manifest derived from the plan; no
  force-push/rebase (git hook).
- **Verdicts require evidence**: no "should pass" anywhere in the chain —
  fresh command output or it didn't happen.

## Repository layout

```
kit/                    → copy into your repo's .claude/
  commands/             /trello-check, /trello-run (+ helpers) — the orchestrators
  prompts/              plan format, card triage, worker bodies (iter1/specs/impl/iterN),
                        test-critic, acceptance-check, roles/
  hooks/                scope-guard.sh, git-guard.sh, worker-settings.json
constitution-template.md → seed for your .claude/constitution.md
examples/               a real, incident-driven project constitution
docs/                   deeper docs (adoption guide, design notes)
```

## Requirements

- Claude Code CLI (`claude`) with an API plan that allows spawning
  headless workers (`claude -p`).
- A Trello MCP server configured in the adopting project (the kit calls
  `mcp__trello__*` tools) with API key/token for your board.
- `gh` (authenticated), `git`, `jq`.
- A Trello board with these lists: Icebox, Backlog, Triage in progress,
  Human Questions, Plan Proposed, Ready for AI, In Progress, Review,
  Blocked, Done.

## Canonical source & staying in sync

**This repo is the canonical source of the kit.** Consumers do not edit
kit files in their own repo — they edit HERE (PR to this repo), then pull:

1. Copy `scripts/workflow-kit-sync` into your repo (e.g. `bin/`) once,
   during adoption.
2. Run `bin/workflow-kit-sync` to pull the latest kit. It overwrites
   `.claude/{commands,prompts,hooks}` (deletions propagate), never touches
   project-owned files (`trello.json`, `constitution.md`,
   `project-context.md`, `settings.local.json`, optional
   `prompts/ui-design.md`), and records the kit SHA in
   `.claude/KIT_REVISION`.
3. Review the diff, commit.

Consumers: `rodnik-ai/rodnik-web` (first).

**Contributing (humans AND agents): `main` is PR-only by convention.** The
org plan has no enforced branch protection, so this is a standing rule,
not a technical gate: never push to `main` directly — branch, open a PR
with a rationale, merge after review (self-merge is acceptable for
trivial doc fixes; prompt/behavior changes wait for a human or a second
agent). Direct pushes to `main` are treated as incidents.

## Adoption (human or agent — ~15 minutes)

1. Copy `kit/` into the target repo as `.claude/` (commands/, prompts/,
   hooks/ — keep paths) and `scripts/workflow-kit-sync` as
   `bin/workflow-kit-sync`. `chmod +x .claude/hooks/*.sh bin/workflow-kit-sync`.
2. Create `.claude/constitution.md` from `constitution-template.md`. Keep
   the universal articles; write 3–7 PROJECT articles — each earned by a
   real incident/constraint (see `examples/`).
3. Create `.claude/trello.json` from `docs/trello.example.json`: board id,
   list ids (from the Trello API or MCP), `card_prefix` (e.g. `ACME`),
   `targets` (repo_root + toolchain + test_cmd/lint_cmd per repo),
   `default_target`, `tdd_gate` thresholds, `auto_merge_criteria`.
4. Create the session log file (default `.gilb/session-log.md`, path is
   configurable in trello.json).
5. Write `.claude/project-context.md`: stack, language conventions,
   commit format — workers read it before touching code.
6. Smoke-test: put one small card in Backlog → run `/trello-check` →
   review the PLAN it posts → drag to Ready for AI → run `/trello-run` →
   watch the card land in Done/Review with an audit trail.

### Giving this workflow to an agent (e.g. a Hermes cofounder agent)

Grant the agent read access to this repo and say:

> Adopt the development workflow from <repo-url> in project X: follow
> README "Adoption" steps 1–6. Ask me for: the Trello board to use, the
> card prefix, and the project articles for the constitution (propose a
> draft from the incidents you know). Do not modify kit files themselves —
> configuration lives in trello.json / constitution.md / project-context.md.

The kit is agent-agnostic on the meta side: any agent that can call the
Trello MCP, run `claude -p`, `gh`, and `jq` can act as the orchestrator —
the worker/critic/acceptance chain always runs on Claude Code.

## Tuning

- `tdd_gate` (trello.json): `enabled`, `min_size` (S/M/L), `min_risk` —
  which cards get the specs-first + test-critic path. Below the gate,
  workers still follow inline test-first discipline.
- `auto_merge_criteria`: `min_confidence`, `max_risk`, `require_ci_green`,
  `strategy`. Research cards never auto-merge.
- `worker.model` / `acceptance.model`: per-stage model override (e.g. a
  cheaper model for acceptance).
- `--parallel N` on `/trello-run`: up to 4 cards in flight.

## Known origins

The kit was extracted from a live project (card prefix RDK, earlier GILB);
a few prose examples in prompts still reference those names — they are
illustrative only. Update them if they bother you; they have no effect on
behavior.
