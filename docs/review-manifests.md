# Review manifests

agent-flow prepares review inputs mechanically and verifies that the audit
accounts for the entire change. The same protocol works for any language,
build system or tracker. No OCR installation, external service or Python
package is required. Python 3.8+ is a runtime prerequisite for the helper.

## Configuration

Add `review` to the consumer's `.claude/tracker.json` when upgrading. Both
tracker examples contain the default block: all changes reviewed, no special
rules, no exclusions, groups of at most 8 files or 120000 diff bytes.
See [the policy example](review-policy.example.json) for optional generic
API/storage rules. Paths and rule text belong to the consumer, never the kit.

- `rules`: ordered `{id, paths, text}` entries. ALL matches apply in order,
  alongside the constitution and universal acceptance checks. No override
  layer can remove universal requirements. IDs must be unique.
- `groups`: ordered `{id, paths}` entries. First match assigns a group hint;
  limits split the group into smaller batches. Related implementation,
  contracts and tests can share a hint. Unmatched files enter default groups.
- `exclude`: ordered `{paths, reason}` entries. First matching entry supplies
  a mandatory explanation; an exclusion is never a reviewer decision. For
  renames, BOTH old and new paths must match, so moving a generated file into
  production cannot retain an old generated-file exclusion accidentally.
- `max_files_per_group`, `max_diff_bytes_per_group`: positive integer limits
  for preparing groups. One oversized file is retained and marked oversized;
  the reviewer must inspect it in portions or report failed coverage. There
  is no automatic truncation or exclusion.

Paths are case-sensitive repository-relative segment globs. `*`, `?` and
character classes match within a segment; `**` matches zero or more segments.
`*.ext` matches only root files, `**/*.ext` also matches nested files. All
matching rules consider both sides of a rename. Unknown keys, duplicate IDs,
absolute/parent-traversing patterns and exclusions without reasons fail.
No policy files are fetched or executed. Rule text is trusted project policy.

## Lifecycle

Before a new acceptance attempt, meta verifies the clean checkout and remote
PR head/base, saves the exact approved PLAN, then creates a manifest outside
the unclaimed stage directory:

```sh
.claude/bin/review-manifest create \
  --repo /path/to/worktree --base origin/main --head FULL_REVIEWED_SHA \
  --plan /path/to/run/plan.md --config /path/to/meta/.claude/tracker.json \
  --kit /path/to/meta/.claude --output /path/to/run/review-iter1.json
```

The helper resolves the base tip and merge-base, freezes HEAD, inventories
all changed items with NUL-delimited Git output, and groups every included
item exactly once. Deleted files, renamed paths, binary/type changes and
unusual names remain visible. It reads Git blobs with literal paths, rather
than following working-tree symlinks. Manifest creation is exclusive: an
existing artifact is never overwritten, including when two creators race.

The manifest identity covers the repository identity, base tip, merge-base,
head, plan bytes, tracker configuration and the kit's command/prompt/hook/bin/
provider contents plus constitution/project-context. Changing any of these
invalidates reuse. The manifest stores absolute local input paths for later
verification, but only hashes config/source identity; it does not copy tokens
from the tracker file or remote URL into its output. With no origin URL, the
local common Git directory identifies the repository, so moving that checkout
invalidates reuse. Conservative invalidation is preferable to false reuse.

The acceptance subagent receives the manifest path and the
[review protocol](../kit/prompts/review-protocol.md) in its prompt. It processes
groups, applies all matched rules, and then performs a final cross-file
assessment. Grouping does not imply separate processes: this version keeps
the existing single acceptance subagent and its universal checks.

Its normal verdict gains a `review` object with the manifest identity, one
coverage row per item, a cross-file assessment and structured source findings.
Coverage status is reviewed, failed or configured-excluded. Reviewed means
inspected, not free of defects. Every row carries an assessment/reason and
acknowledges applicable rule IDs. All check-8 source findings carry an item,
old/new side, line range and exact quote linked to the normal finding ledger.
The helper verifies the quote against the frozen Git blob, including deleted
source. It proves location/text, not the interpretation's correctness.

Meta saves the normalized verdict and calls `review-manifest check` with
`--repo`, `--base`, `--head`, `--manifest` and `--verdict`. Exit 0 means
complete valid coverage (gaps may still require fixes); 3 means incomplete;
4 means invalid/stale evidence. On failure there is no acceptance claim.
`merge-reviewed-pr` requires the manifest and verdict as its final arguments
and calls `review-manifest verify` before/after the CI query. Verify additionally
requires empty gaps and passing spec/quality verdicts. Missing coverage cannot
be bypassed by a green CI check or a manually empty gaps array.

## Limits and validation

Coverage rows are reviewer attestations, not proof that a model understood
every file. Trusted orchestration remains part of the threat model; these
JSON files are not cryptographically signed approvals. Existing tests,
constitution checks and human review still provide independent evidence.
No cross-project replay cache or extra review service is introduced.

Remote base/head are checked near merge, and the server enforces the reviewed
head SHA. GitHub's head-match option does not atomically pin the base; projects
requiring tested merge results should enforce up-to-date checks or a merge
queue in branch policy. This helper does not replace server-side protection.

The offline suites use real temporary repositories/processes and mock only
GitHub transport. They cover missing/duplicate/failed coverage, invented
exclusions/quotes, configuration and input drift, file grouping, renames,
deletions/binaries/unusual paths, and rejection at the actual merge helper.
Run all commands in [CONTRIBUTING](../CONTRIBUTING.md) before upgrading a kit.
