# Open Code Review: what agent-flow should adopt

Assessment date: 2026-09-19. Source review of Alibaba's public main branch
through GitHub/raw source pages; no local build, paid review run, or benchmark
reproduction. These recommendations are an architectural assessment, not a
claim that OCR detects all defects or that its advertised savings hold here.
No Alibaba source code was copied into the fixes.

## Recommendation

Keep agent-flow responsible for task approval, implementation, tests and
merge decisions. Borrow OCR's explicit accounting of what was reviewed,
immutable input identity and path-specific rules. Evaluate OCR as an optional
additional reviewer before making it a required dependency or merge gate.
An empty list of OCR comments must never substitute for acceptance evidence.

## Mechanisms worth adopting

1. **A coverage manifest per review.** OCR's agent records selected work,
   completion/reuse/failure and runtime provenance, and freezes a final
   manifest. Its implementation excludes deleted files from the selected
   review denominator. For agent-flow, generate the complete change inventory
   mechanically, including deletions/renames, and require a reviewed status or
   an explicit exclusion reason for every item. A timeout, exhausted budget
   or failed subtask should yield an incomplete review, even if findings are
   empty. This is the highest-value follow-up to the current gate repairs.
   [Agent implementation](https://github.com/alibaba/open-code-review/blob/main/internal/agent/agent.go).

2. **Immutable review identity.** OCR resolves moving refs before starting a
   run and identifies inputs using source, rule configuration and repository
   hashes. agent-flow's current repair binds acceptance/merge to the reviewed
   SHA and retains the approved plan identity. A future cache should also
   include the base SHA, kit/prompt version and applicable rules; changing any
   of these must invalidate reuse. Never reuse a verdict merely because the
   branch name is unchanged.
   [Input identity](https://github.com/alibaba/open-code-review/blob/main/internal/agent/identity.go).

3. **Rules selected by file path, with provenance.** OCR resolves glob rules
   through custom/project/global/system layers and can retain the matched
   pattern and source. In OIS, separate rules for `mobile/**` (offline state,
   navigation, accessibility), `tools/**` (date semantics, idempotency,
   partial imports), and publication/storage code (validated manifests,
   last-good state, atomic publication) would be more focused than sending
   the whole constitution on every file. Keep universal project constraints
   mandatory: OCR's user rules replace system rules by default unless merge
   is requested, which is not the policy we want for constitution articles.
   [Rule resolver](https://github.com/alibaba/open-code-review/blob/main/internal/config/rules/system_rules.go),
   [rule provenance grouping](https://github.com/alibaba/open-code-review/blob/main/internal/delegate/rulegroup.go).

4. **Bounded grouping without lost files.** OCR can ask a model to group
   changed files, but code removes duplicate/invalid assignments, creates
   groups for unassigned files and limits group size/token consumption.
   Small changes avoid a grouping model call. For larger OIS changes, review
   importer + schema + tests together and mobile consumers together, then
   retain a final cross-module review. Deterministic coverage is the useful
   guarantee; the semantic grouping itself is still a model decision.
   [Grouping implementation](https://github.com/alibaba/open-code-review/blob/main/internal/agent/grouping.go).

5. **Structured evidence and selective second-pass review.** OCR represents
   comments with path, existing code, category and severity, and tests an
   optional filter that removes identified incorrect comments while retaining
   originals if the filtering call fails. agent-flow already asks for quoted
   evidence and tracks fingerprints. A useful next step is structured finding
   objects validated against the frozen diff, followed by a second look at
   uncertain findings. Preserve the original finding and removal reason in
   the audit trail. Do not add a second model call to every clean small card.
   [Comment parsing](https://github.com/alibaba/open-code-review/blob/main/internal/tool/code_comment.go),
   [filter tests](https://github.com/alibaba/open-code-review/blob/main/internal/agent/coverage_test.go).

## What not to adopt automatically

- Do not replace test execution, plan compliance or human approval with OCR.
- Do not infer approval from comment count, an empty result, or CLI success
  without complete coverage and matching input identity.
- Do not treat precision or token claims as measured gains for OIS. The
  authors report a precision/recall trade-off; evaluate actual project PRs.
  [Published benchmark description](https://github.com/alibaba/open-code-review#benchmark).
- Do not copy the Go runtime and bundled rules wholesale into a shell/prompt
  kit. Prefer an optional version-pinned CLI adapter or independently written
  small mechanisms; preserve upstream licensing if code is later reused.

## Suggested pilot

After agent-flow's fixes are reviewed and a live smoke card succeeds, compare
its acceptance with OCR on 10-20 completed OIS changes. Label true defects,
false positives and known missed defects; record coverage, latency and cost.
Start with advisory output and the existing human merge gate. OCR offers a
JSON output mode and a delegation mode that prepares selection/rules without
its own LLM call, so the pilot need not change task orchestration.
[CLI usage and delegation](https://github.com/alibaba/open-code-review#quick-start).

This assessment proposes a follow-up; it does not install OCR or claim that
coverage manifests/rule routing have been implemented by the gate repair.
