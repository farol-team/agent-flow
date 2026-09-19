# Review coverage and source evidence

The acceptance prompt supplies an immutable review manifest path. This
protocol applies to code and research reviews, for every language/provider.

## Inputs and grouping

`data.items` is the complete Git change inventory. Each item has a stable
`id`, old/new paths, status, diff digest/size, ordered applicable rule IDs,
and either a configured exclusion reason or null. An item with a null new
path is a deletion: inspect the old source and surviving callers. Binary
files and type changes require a suitable inspection, or failed coverage.

`data.groups` assigns every non-excluded item exactly once. Configured group
patterns let related source/tests/contracts share a review pass. Unassigned
items are still grouped; count and diff-byte limits bound each group.
An `oversized` group means one file alone exceeds the preparation budget:
read it in portions or report failure. It is never silently excluded.
Grouping organizes context; it does not remove the final integration review.

`data.rules` contains all matched project rules. Apply ALL rule IDs on an
item, in order, in addition to the universal checks and constitution.
Conflicting rules are a gap to resolve, not permission to ignore one.
The source base is `data.base`, head is `data.head`; both are immutable SHAs.
Do not substitute a newer branch tip while reviewing.

## Coverage output

Add a `review` object to the normal acceptance verdict:

```json
{
  "identity": "the manifest identity",
  "files": [
    {"id": "an item ID", "status": "reviewed", "rules": ["api-contract"],
     "summary": "Checked the changed producer and its callers against the contract."},
    {"id": "another item ID", "status": "failed", "rules": [],
     "summary": "Binary asset could not be inspected with available tools."},
    {"id": "an excluded item ID", "status": "excluded",
     "summary": "exact exclusion reason from the manifest"}
  ],
  "cross_file": {"status": "reviewed", "summary": "Concrete assessment of interactions across the change."},
  "findings": []
}
```

Every inventory ID appears exactly once, no additional IDs. A reviewed or
failed item's `rules` must exactly equal its manifest rule IDs. An exclusion
is permitted only when configured, with the identical reason; the reviewer
cannot add exclusions. `summary` describes what was inspected or why it was
not. Status `reviewed` means inspected, not defect-free: defects still go
into gaps/minor. `cross_file` is mandatory even for one group; for one file,
record the caller/contract check or explain why there is no interaction.

A failed file or cross-file assessment makes coverage incomplete. Empty
gaps plus incomplete coverage is never approval. Budgets/timeouts are failed
coverage, not a reason to quietly reduce the selected set. If a process dies
before returning coverage, its incomplete output cannot produce acceptance.

## Structured source findings

Every verified check-8 finding must also appear in `review.findings`:

```json
{
  "fingerprint": "c8:src/example.ext:missing-check",
  "severity": "important",
  "item_id": "the changed item's ID",
  "side": "new",
  "line_start": 12,
  "line_end": 13,
  "quote": "exact source line 12\nexact source line 13"
}
```

`severity` is critical, important or minor. Keep the same fingerprint in the
matching gaps/minor ledger so findings cannot disappear during aggregation.
`side` is new (head/path) or old (merge-base/old_path), including deletions.
Lines are 1-based, inclusive. Quotes use newline-normalized source lines
without an extra trailing newline. The validator reads the Git blob rather
than the current filesystem, checks bounds and compares the exact text.
Other source-anchored checks may use this shape too. Command failures and
plan-wide findings retain their existing textual evidence contract.
Unverified minor observations keep the UNVERIFIED marker and cannot become
blocking code-quality findings without source evidence.

This verifies source attribution, not the truth of the interpretation.
Preserve contrary evidence, and remove an uncertain finding only after
checking it; document the reasoning in the working audit output. A second
model call is not mandatory for small/clear findings.

## Meta validation and reuse

`review-manifest check` compares the full manifest against freshly computed
inputs and validates coverage, verdict consistency and source quotes.
Exit 0 permits the normal gaps/retry decision; exit 3 is incomplete coverage;
exit 4 is malformed/stale evidence. `review-manifest verify` additionally
requires approval and is mandatory inside `merge-reviewed-pr`.

Identity includes repository, base tip, merge-base, head, exact plan bytes,
tracker configuration and kit/prompt/constitution/context contents. Changing
any of them requires a new acceptance attempt, even with an unchanged branch
name. Store the manifest beside the durable attempts; do not recreate it on
resume or relabel old results. A newer policy cannot approve an old review.

These are audit records from a trusted orchestrator, not signed attestations.
A model can still falsely claim to have inspected a file. The validator
prevents missing/inconsistent accounting; tests and human review remain
necessary to assess the quality of the inspection.
