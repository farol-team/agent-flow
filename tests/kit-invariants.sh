#!/usr/bin/env bash
# kit-invariants.sh — free, static self-checks for the kit (tier 1).
#
# The kit's prompts and commands are the product; this script treats them
# as build artifacts and pins the invariants that break silently: dangling
# file references, undeclared placeholders, unparseable JSON, drift between
# a verdict contract and the meta code that parses it, and unbounded prompt
# growth. No network, no LLM calls, no repo mutations — safe on every PR.
#
# Behavioral (tier 2) checks — spawning a real `claude -p` on a smoke card —
# are intentionally NOT here; they cost money and belong behind an opt-in
# flag when they land.
#
# Usage: bash tests/kit-invariants.sh   (exit 0 = all invariants hold)
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

FAIL=0
CHECKS=0

pass() { CHECKS=$((CHECKS + 1)); }
fail() {
  CHECKS=$((CHECKS + 1)); FAIL=$((FAIL + 1))
  echo "FAIL: $1" >&2
}

command -v jq >/dev/null 2>&1 || { echo "FAIL: jq is required (it is already a kit requirement)" >&2; exit 1; }

# ── 1. Shell scripts: syntax + executable bit ─────────────────────────────

for f in kit/hooks/*.sh kit/bin/* scripts/workflow-kit-sync; do
  [ -f "$f" ] || continue
  if bash -n "$f" 2>/dev/null; then pass; else fail "$f: bash syntax error (bash -n)"; fi
  if [ -x "$f" ]; then pass; else fail "$f: not executable (chmod +x, adoption step depends on it)"; fi
done

# ── 2. JSON artifacts parse ───────────────────────────────────────────────

for f in kit/hooks/worker-settings.json docs/tracker.example.trello.json docs/tracker.example.github.json; do
  if jq empty "$f" 2>/dev/null; then pass; else fail "$f: invalid JSON"; fi
done

# ── 3. Config contract: keys the commands read exist in the example ───────
# flow-run/flow-check read these top-level keys; a consumer copying the
# example must get every one of them. The list lives in
# kit/config-contract.txt — shared with scripts/workflow-kit-sync, which
# validates the consumer's REAL config after every sync. Extend the list
# THERE when a command grows a new config dependency.

if [ -s kit/config-contract.txt ]; then pass; else fail "kit/config-contract.txt: missing or empty (source of the config contract)"; fi
REQUIRED_CONFIG_KEYS="$(grep -vE '^[[:space:]]*(#|$)' kit/config-contract.txt || true)"
for ex in docs/tracker.example.trello.json docs/tracker.example.github.json; do
  for key in $REQUIRED_CONFIG_KEYS; do
    if jq -e --arg k "$key" 'has($k)' "$ex" >/dev/null 2>&1; then
      pass
    else
      fail "$ex: missing top-level key '$key' (a kit command reads it)"
    fi
  done
done

# ── 3b. Tracker provider parity ───────────────────────────────────────────
# flow-run hard-requires the provider doc at bootstrap; every provider doc
# must define every semantic op the commands invoke, plus the two sections
# meta reads (ref resolution, capabilities). A provider missing an op is a
# runtime dead-end the prompts cannot detect.

SEMANTIC_OPS="list_items read_item create_item move_state add_comment set_labels checklist archive_item update_title"
PROVIDERS="$(ls kit/providers/*.md 2>/dev/null || true)"
if [ -n "$PROVIDERS" ]; then pass; else fail "kit/providers/: no provider docs found"; fi
for p in $PROVIDERS; do
  for op in $SEMANTIC_OPS; do
    if grep -q "${op}(" "$p"; then pass; else fail "$p: semantic op '$op' not defined"; fi
  done
  for section in "Ref resolution" "Capabilities"; do
    if grep -q "^## $section" "$p"; then pass; else fail "$p: missing '## $section' section"; fi
  done
done
# Every provider named by an example config ships a doc.
for ex in docs/tracker.example.*.json; do
  prov="$(jq -r '.tracker.provider' "$ex" 2>/dev/null)"
  if [ -f "kit/providers/$prov.md" ]; then pass; else fail "$ex: provider '$prov' has no kit/providers/$prov.md"; fi
done

# ── 4. File references resolve ────────────────────────────────────────────
# Any `.claude/{prompts,commands,hooks}/<file>` mentioned anywhere in the kit
# or README must exist in kit/ — a renamed prompt with a stale reference is
# exactly the failure mode meta cannot detect at runtime.
# Whitelist: ui-design.md is documented as optional and project-owned.

REF_WHITELIST="prompts/ui-design.md"

REFS=$(grep -rhoE '\.claude/(prompts|commands|hooks|providers)/[A-Za-z0-9._/-]+\.(md|sh|json|txt)' kit README.md 2>/dev/null | sort -u)
for ref in $REFS; do
  rel="${ref#.claude/}"
  case " $REF_WHITELIST " in *" $rel "*) pass; continue ;; esac
  if [ -f "kit/$rel" ]; then pass; else fail "dangling reference: $ref (no kit/$rel)"; fi
done

# ── 4b. Kit bin references resolve ────────────────────────────────────────
# flow-run hard-requires `.claude/bin/<name>` at bootstrap (like role
# files); the scripts are extensionless so check 4's regex can't see them.
# A renamed script would pass every other check and stop every consumer.

BINREFS=$(grep -rhoE '\.claude/bin/[a-z0-9-]+' kit README.md 2>/dev/null | sort -u)
for ref in $BINREFS; do
  rel="${ref#.claude/bin/}"
  if [ -f "kit/bin/$rel" ]; then pass; else fail "dangling bin reference: $ref (no kit/bin/$rel)"; fi
done

# ── 5. Placeholder discipline in prompt bodies ────────────────────────────
# Meta substitutes a fixed vocabulary of placeholders. If a prompt BODY uses
# one of them, the file's header MUST declare it in its Placeholders section —
# an undeclared one reaches the model as literal "<learnings>" text.
# One-directional by design: declared-but-unused is legal (e.g. <branch>
# declared for context), used-but-undeclared is the bug.

KNOWN_PLACEHOLDERS="card-url pr_url worktree-path branch base PLAN-comment prior-findings learnings iter MAX_ITER gaps-list critic-findings"

for f in kit/prompts/*.md; do
  grep -q '^Placeholders' "$f" || continue   # roles/ and non-template files
  header=$(sed -n '1,/^---$/p' "$f")
  body=$(sed -n '/^---$/,$p' "$f")
  for ph in $KNOWN_PLACEHOLDERS; do
    if printf '%s' "$body" | grep -q "<$ph>"; then
      if printf '%s' "$header" | grep -q "<$ph>"; then
        pass
      else
        fail "$f: body uses <$ph> but the Placeholders section does not declare it"
      fi
    fi
  done
done

# ── 6. Verdict-contract parity ────────────────────────────────────────────
# flow-run parses these keys out of subagent verdicts; the prompt that
# produces the verdict must mention every one, and vice versa is pinned by
# the contract lines themselves. Catches one side of the contract moving.

for key in gaps gaps_summary minor verdicts learnings; do
  if grep -q "\"$key\"" kit/prompts/acceptance-check.md; then pass; else
    fail "acceptance-check.md: verdict key \"$key\" (parsed by flow-run) missing from the output contract"
  fi
done
for key in verdict findings summary learnings; do
  if grep -q "\"$key\"" kit/prompts/test-critic.md; then pass; else
    fail "test-critic.md: verdict key \"$key\" (parsed by flow-run) missing from the output contract"
  fi
done

# The orchestrator must reference every key it is documented to parse.
for key in gaps gaps_summary minor verdicts learnings; do
  if grep -q "\`$key" kit/commands/flow-run.md || grep -q "\"$key\"" kit/commands/flow-run.md || grep -qE "(^|[^a-z_])${key}\[?\]?" kit/commands/flow-run.md; then
    pass
  else
    fail "flow-run.md: never mentions verdict key '$key' it is supposed to parse"
  fi
done

# ── 7. Prompt size budgets ────────────────────────────────────────────────
# Every line of every prompt is context spent on every card. Ceilings are
# ~30% above current size — raising one is allowed, but must be a conscious
# diff in this file, not silent growth.

check_budget() { # file max
  local n
  n=$(wc -l < "$1" | tr -d ' ')
  if [ "$n" -le "$2" ]; then pass; else fail "$1: $n lines exceeds budget $2 (raise the budget consciously or trim)"; fi
}

check_budget kit/commands/flow-run.md        1100
check_budget kit/commands/flow-check.md       300
check_budget kit/commands/flow-questions.md   300
check_budget kit/commands/flow-normalize.md   150
check_budget kit/commands/flow-clean.md       110
check_budget kit/prompts/acceptance-check.md    470
check_budget kit/prompts/card-eval.md           430
check_budget kit/prompts/plan-format.md         320
check_budget kit/prompts/test-critic.md         130
check_budget kit/prompts/worker-iter1.md        150
check_budget kit/prompts/worker-iterN.md        140
check_budget kit/prompts/worker-specs.md        110
check_budget kit/prompts/worker-impl.md          60
check_budget kit/prompts/worker-research.md     130

# ── 8. Hook JSON output shape ─────────────────────────────────────────────
# scope-guard blocks via exit 2 + stderr; any JSON it emits on stdout must
# parse (Claude Code consumes it). Extract single-line JSON echoes and check.

for f in kit/hooks/*.sh; do
  jsons=$(grep -oE "echo '\{[^']*\}'" "$f" | sed -e "s/^echo '//" -e "s/'$//")
  [ -z "$jsons" ] && continue
  while IFS= read -r j; do
    if printf '%s' "$j" | jq empty 2>/dev/null; then pass; else fail "$f: emits invalid JSON: $j"; fi
  done <<< "$jsons"
done

# ── Summary ───────────────────────────────────────────────────────────────

echo ""
echo "kit-invariants: $((CHECKS - FAIL))/$CHECKS checks passed"
[ "$FAIL" -eq 0 ] || { echo "kit-invariants: $FAIL FAILED" >&2; exit 1; }
