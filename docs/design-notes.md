# Design notes

Why the kit is shaped the way it is. Each section records a mechanism,
the failure mode that motivated it, and the deliberate limits of the
design. Newest first. (The adoption guide lives in the README; the
reference configs are `docs/tracker.example.trello.json` and
`docs/tracker.example.github.json`.)

## Executor selection without a second orchestration protocol

**Problem.** Worker, test-critic and acceptance launches assumed Claude's
flags and JSON envelope. Merely replacing the executable with Codex would
misread its event stream, silently lose limits/hooks, or resume the wrong
provider's session.

**Mechanism.** `run-agent` resolves the configured executor per role and
uses the existing `run-stage` atomic claim. Each attempt records a frozen
request, raw provider logs and one normalized result. Codex requires a
complete successful turn and a matching final-message artifact; commentary
or partial output cannot become approval. Resume names a completed worker
attempt and validates provider, worktree, configuration and session identity.
Critic/acceptance always start fresh. All verdict, manifest and merge gates
remain shared. A common wall-clock deadline stops the provider process group.

**Limit.** Claude hooks and turn budgets are not Codex capabilities. Codex
uses an explicit workspace/read-only sandbox; `max_turns` remains Claude-only.
Permission failures block, never trigger an unrestricted retry. Cost and
turn count absent from Codex output remain unknown; token usage is retained.
This adapter is not a security boundary against hostile tools, credentials
or workers. The common config block is now an explicit upgrade requirement.
See [executor configuration and operational limits](executors.md).

## /flow-refactor: the contour learns to remove

**Problem.** Every command in the flow adds code; nothing ever proposes
removal or boundary repair, so complexity accumulates one merged card at
a time — invisibly, because each card's diff looked fine in isolation.
The stakes are structural, not aesthetic: the harness's own mechanisms
(scoped gates, file manifests, diff-based acceptance) assume correctness
in the target repo is a LOCAL property. Module cycles and cross-boundary
co-change coupling erode exactly that assumption, and a worker whose
context window holds one module is the first casualty.

**Mechanism.** `/flow-refactor` sweeps a target repo with a four-lens
priority (boundary violations → non-local correctness → dead code →
complexity hotspots, constitution articles as an overlay), from cheap
deterministic signals up: configured gates (`lint_cmd`, optional
`arch_cmd`), graph/hygiene tools already present in the repo, git churn
and cross-module co-change pairs, then a bounded LLM pass over the worst
hotspots. Findings need evidence produced in this run — the gstack rule
again. The top ≤5 become card drafts in the `flow-card.md` contract
(Goal/Why/Done when/Out of scope/Stop if/Context), shown in full;
`AskUserQuestion` picks which land in Backlog. From there they ride the
normal contour — a refactor executed outside triage/gates/audit is
exactly the unreviewed change the contour exists to prevent.

**Limit.** It proposes; it never edits, and it never installs tools — a
repo with no analyzers gets git-signals-plus-reading and a higher bar
for proposing. Five cards per sweep is a hard cap: prioritization is the
product, a 30-item dump is noise. A previously declined candidate is not
re-proposed. And a finding that indicts the constitution itself (an
article forces the coupling) is surfaced as a report section for the
human, not laundered into a card.

## Authoring the card: ask at write time, not at triage time

**Problem.** A rough card ("make the recorder not lose audio") is
underspecified in exactly the ways triage detects and cannot fix alone.
The pipeline handles it correctly and expensively: `/flow-check` posts
`[meta] QUESTIONS`, the card moves to `Human Questions`, `/flow-questions`
asks the human one question, the card returns to `Backlog`, `/flow-check`
runs again. Three commands, two full board reloads, and — the real cost —
the human answers hours later, having lost the context that made the
intention obvious when they typed it.

**Mechanism.** `/flow-card <rough intention>` moves that Q&A to the
moment of authoring. It grounds the sentence in the repo first (files
must exist now; matching `learnings.jsonl` pitfalls are read), then
sorts the eight `card-eval.md` gap categories through the same
auto-answer policy triage uses: safe defaults become `[meta] ASSUMED`
comments, and only the genuinely human gaps (`What`, `Why`,
`Dependencies`, split-implying `Size`) reach `AskUserQuestion` — at most
three turns. The card it writes carries a completion contract: `## Goal`,
`## Why`, `## Done when`, `## Out of scope`, `## Stop if`, `## Context`.
No new config keys, no new state — the artifact is an ordinary Backlog
card, and every downstream stage is unchanged. Nothing is written until
the human has read the exact text: the composed card is shown in full and
approved (or revised, repeatedly) before `create_item` runs, because
after creation every wording fix costs a round-trip through the tracker
UI.

**Limit.** Deliberately not a second planner. It never writes an
approach, a file manifest or test commands — the WHAT/HOW split and the
human's plan-approval gate stay where they are. It creates exactly one
card: an intention worth several PRs is narrowed to its first slice with
the rest parked in `Icebox`, because `/flow-check`'s SPLIT path is the
tested splitter and two of those would drift. The three-turn cap means a
card can still reach triage with an open question — that's the intended
overflow, not a failure: it lands as a `## Stop if` bullet and the old
`QUESTIONS` route handles it. And nothing requires the command — a card
typed straight into the board behaves exactly as it did before.

## KIT_REVISION digest: the no-local-edits rule, made checkable

**Problem.** "Consumers do not edit kit files in their own repo — they
edit HERE, then pull" is the rule the whole canonical-source model rests
on, and until now it was prose. The sync overwrites
`.claude/{commands,prompts,hooks,bin,providers}` with `rsync --delete`, so
a local edit to a prompt is erased by the next update *with no diff to
notice it by*: the consumer learns about the edit when the behavior it
bought silently disappears, weeks later, and the fix is re-derived from
memory.

**Mechanism.** Reported by a consumer repo, which had built it locally.
`workflow-kit-sync` now records a second line in `.claude/KIT_REVISION`:
a sha256 over every file in the kit-owned trees — path, contents, and
the exec bit, since a hook that lost `+x` is a silent hole the bytes
alone don't show. `bin/kit-verify` recomputes it and fails the pull
request while the edit still exists, naming the three ways out (upstream
it, move the file out of the kit-owned trees, re-sync deliberately).
`--selftest` tampers with a synthetic kit on every run and asserts both
failures, because a green check that cannot go red says nothing.
`kit-digest`/`kit-verify` live in the consumer's `bin/`, never
`.claude/bin/` — that tree is one the sync wipes, and a check the sync
can delete is not a check.

**Limit.** The digest proves the trees match what the last sync wrote; it
says nothing about whether that revision was any good. It also cannot
sync itself: the three `bin/` scripts are copied once at adoption and
never updated by the sync (they must survive the deletion), so the sync
now diffs them against this repo and says when they've fallen behind —
which is a note, not an update. And it fails open by design: a consumer
whose `KIT_REVISION` predates the digest gets "records a revision but no
digest — re-run the sync", not a broken sync.

## Verification gate: quote the evidence or it's a minor

**Problem.** LLM reviewers produce plausible-but-wrong findings
("field X does not exist" when it's generated by a Rails `has_many`),
and each false gap burns a full worker iteration — the worker "fixes"
a non-problem, sometimes breaking real code to satisfy the reviewer.

**Mechanism.** A finding may enter `gaps` only with verbatim quoted
evidence produced in this run: the diff/source lines or the failing
command output. Unquotable findings are demoted to `minor` with an
`UNVERIFIED:` prefix — recorded, never iterated on. Framework-generated
symbols require quoting the generating construct, not "I grepped and
didn't find it". The test critic has the same rule (`NIT:` findings
can't justify rejection).

**Limit.** The gate is prompt-enforced; a determined model can quote
irrelevant evidence. The fingerprint history (below) is the second
layer: a gap that keeps reappearing without progress blocks the card
early, capping the damage of any single bad finding at one iteration.

## Finding fingerprints + no-progress escalation

**Problem.** Across iterations the acceptance check re-words old
findings into "new" ones, re-litigates ledgered minors, and lets a
non-converging worker burn all three iterations on an identical gap set.

**Mechanism.** Every finding carries `<check>:<file>:<slug>` (no line
numbers — lines shift; the defect keeps its fingerprint). Meta tracks
fingerprints across iterations (`open`/`fixed`/`ledgered`), renders the
history back into the next acceptance prompt (ledgered minors must not
be re-raised without new evidence; open findings must reuse the same
fingerprint), marks `REPEAT` gaps in card comments, and blocks the card
when two consecutive iterations produce identical gap sets.

**Limit.** Fail-open everywhere: an entry without a parseable
fingerprint still counts as a gap, it just leaves history tracking.
That's deliberate (format drift must not corrupt verdicts), but it means
the machinery silently degrades — hence the `Fingerprints: N/M` counter
surfaced in iteration comments.

## Project learnings: file-anchored cross-card memory

**Problem.** The same non-obvious pitfall (a factory trap, a queue
convention, a toolchain quirk) is rediscovered by a fresh worker on
card 30 because worker sessions share nothing.

**Mechanism.** Acceptance (≤2) and the test critic (≤1) may emit
`learnings` in their verdicts — genuine, non-obvious, anchored to ≥1
repo file. Meta is the single writer: it validates, dedups by `key`
(replace only on strictly higher confidence), and appends to the
learnings file. Triage reads it when drafting PLANs; workers get the ≤5
most relevant entries (file/dir overlap with the PLAN's `## Files`, or
key-vs-title match) injected before touching code. Staleness = every
anchored file gone from `git ls-files`. The file is committed —
`/flow-run` Phase 4 publishes each card's harvest as a
`chore(learnings)` commit, because uncommitted memory is host-local
and dies with the machine.

**Limit.** Selection is a grep-class filter, not semantic search — a
false positive costs the worker one read; a false negative loses nothing
that wasn't already lost. Learnings never extend the plan: a learning
that contradicts it → `BLOCKED`, not improvisation.

## Kit self-checks: the prompts are build artifacts

**Problem.** The kit's product is markdown executed by a model. Its
regressions don't fail a compiler — a renamed prompt, an undeclared
placeholder reaching the model as literal text, a verdict key parsed by
the orchestrator but dropped from the prompt's output contract: all
break silently at runtime, possibly weeks later.

**Mechanism.** `tests/kit-invariants.sh` (tier 1, free, every PR): shell
syntax + exec bits, JSON validity, the config contract, references and
prompt budgets. Behavioral scripts are covered by `kit-bin.test.sh`;
`review-gates.test.py` adds offline git, process and GitHub-transport fixtures.
## Review gate repair: decisions, commits and interrupted attempts

**Problem.** An empty gaps array could approve a contradictory spec/quality
verdict; CI absence counted as success; acceptance was not tied to the PR
commit later merged. A dead meta could replay a finished worker because its
journal still said spawn. TDD recovery could change a plan and mark it Ready
without renewed human approval. Finally, the sync script advertised commit
pinning while passing a SHA to clone's branch option.

**Mechanism.** Acceptance now requires both explicit, consistent verdicts;
multiple candidate objects fail closed. `verify-pr-head` checks a clean
tracked checkout, branch, base and remote SHA before and after acceptance.
`merge-reviewed-pr` rechecks that recorded SHA, requires non-empty passing
CI unless explicitly disabled, and uses GitHub's `--match-head-commit`.
Queued merges are not Done. Branch cleanup is separate.

Every executor invocation uses `run-stage` with a persisted, unique attempt
directory and an atomic mkdir claim. Result logs and the terminal exit code
survive meta failure. `stage-status` returns start, wait, consume or inspect;
an ambiguous/dead wrapper is NOT permission to repeat external side effects.
No new spawn/merge is allowed when journal persistence fails. An amended
PLAN returns to Plan Proposed; the old worktree stays available. On resume,
old acceptance output retains its original reviewed SHA and approved plan.

Full commit IDs use fetch plus detached checkout before any consumer files
are changed; branch/tag installs remain supported. KIT_REVISION stores the
full commit. Tests use real temporary git repositories and processes, with
only GitHub transport replaced by an offline fixture.

**Deliberate limits.** The LLM still orchestrates the protocol; these helpers
are mandatory instructions, not a sandbox against a malicious orchestrator.
A crashed wrapper with possibly living descendants requires reconciliation,
not automatic exactly-once recovery. Atomic rename protects against partial
process writes, not guaranteed durability across power loss without fsync.
CI is conservatively all reported checks, including optional checks: skipped
checks send the card to Review. This is stricter than branch protection.
Renewed approvals and actual end-to-end Claude behavior still need a live
smoke card. Old two-key acceptance outputs and pre-attempt journals require
new verification/reconciliation rather than being silently grandfathered in.

## Deterministic review inventory and immutable evidence

**Problem.** A coherent acceptance paragraph does not establish that all
changed files were inspected. File grouping and policy selection can lose
files, a model can quote a nonexistent line, and a valid verdict can outlive
its plan, base or review rules.

**Mechanism.** `review-manifest` (Python standard library) creates a complete
Git-derived inventory, additive path-rule assignments and bounded related-file
groups. The acceptance contract accounts for every item and requires a final
cross-file check. Only consumer configuration may exclude files, with reasons.
Structured source findings must agree with the ledger and frozen Git blobs.
A content identity binds the complete manifest to plan/config/kit and Git
inputs. The merge helper independently rejects incomplete or stale evidence.
All choices are generic consumer configuration, with no project-specific code.

**Origin.** The separation of deterministic preparation from model reasoning
is informed by Alibaba Open Code Review's inventory, input identity, grouping
and rule selection. This is an independent implementation without copied
source. See [the assessment](open-code-review-assessment.md) for primary links
and [the public protocol](review-manifests.md) for configuration and migration.

**Limits.** Coverage is an attestation, not proof of review depth. Grouping
organizes one acceptance session; independent per-group reviewers are not
required here. Source matching verifies a quote, not its inference. Missing
coverage fails closed; explicit exclusions remain visible in the denominator.

## Temporary storage for Codex audits

**Problem.** OIS's first Codex test critic could not create fixture files under
`/tmp`: blanket read-only execution failed before behavioral assertions.

**Mechanism.** Each audit receives a unique private temporary directory and an
explicit profile granting writes only there. Source and Git metadata remain
read-only; shell network remains disabled. Standard temp/cache environment
variables point to the scratch directory, whose identity is frozen in the
durable request. Worker policy and fresh audit sessions are unchanged.

**Limits.** Checks that require source writes or network still fail closed.
Scratch artifacts remain for inspection and require later cleanup. This fixes
test fixture creation, not every project's build or service prerequisites.
