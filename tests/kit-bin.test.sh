#!/usr/bin/env bash
# kit-bin.test.sh — unit tests for kit/bin/* (tier 1.5: free, no LLM).
# These scripts carry the mechanical halves of trello-run's verdict
# parsing and learnings pipeline; this file is their behavioral pin.
#
# Usage: bash tests/kit-bin.test.sh   (exit 0 = all pass)
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BIN="$ROOT/kit/bin"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

FAIL=0; CHECKS=0
pass() { CHECKS=$((CHECKS + 1)); }
fail() { CHECKS=$((CHECKS + 1)); FAIL=$((FAIL + 1)); echo "FAIL: $1" >&2; }

expect_eq() { # desc actual expected
  if [ "$2" = "$3" ]; then pass; else fail "$1: got [$2], want [$3]"; fi
}
expect_exit() { # desc actual expected
  if [ "$2" -eq "$3" ]; then pass; else fail "$1: exit $2, want $3"; fi
}

mk_envelope() { # result-text-file -> envelope path on stdout
  local out="$WORK/env-$RANDOM.json"
  jq -n --rawfile r "$1" \
    '{result: $r, session_id: "sess-1", total_cost_usd: 1.25, num_turns: 7, is_error: false}' > "$out"
  echo "$out"
}

# ── parse-verdict: acceptance ─────────────────────────────────────────────

# 1. Clean single-line verdict with fingerprints.
cat > "$WORK/r1" <<'EOF'
{"gaps":["CRITICAL [c1:src/a.rs:missing-check]: no check","IMPORTANT [c4:-:lint-skipped]: lint"],"gaps_summary":"a; b","minor":["[c8:src/b.rs:naming] naming"],"verdicts":{"spec":"fail","quality":"approved"}}
EOF
ENV="$(mk_envelope "$WORK/r1")"
OUT="$("$BIN/parse-verdict" acceptance "$ENV")"; RC=$?
expect_exit "acceptance clean: exit" "$RC" 0
expect_eq "acceptance clean: gaps count" "$(printf '%s' "$OUT" | jq '.gaps | length')" "2"
expect_eq "acceptance clean: fps parsed" "$(printf '%s' "$OUT" | jq '._fps.parsed')" "3"
expect_eq "acceptance clean: fps total" "$(printf '%s' "$OUT" | jq '._fps.total')" "3"
expect_eq "acceptance clean: fp[0]" "$(printf '%s' "$OUT" | jq -r '._fingerprints.gaps[0]')" "c1:src/a.rs:missing-check"
expect_eq "acceptance clean: cost" "$(printf '%s' "$OUT" | jq '._cost_usd')" "1.25"

# 2. Tolerant: prose around the JSON line; unfingerprinted entry counts in total only.
cat > "$WORK/r2" <<'EOF'
I ran all checks. Here is the verdict:
{"gaps":["IMPORTANT: entry without fingerprint"],"gaps_summary":"x","minor":[]}
Thanks!
EOF
ENV="$(mk_envelope "$WORK/r2")"
OUT="$("$BIN/parse-verdict" acceptance "$ENV")"; RC=$?
expect_exit "acceptance prose: exit" "$RC" 0
expect_eq "acceptance prose: fps" "$(printf '%s' "$OUT" | jq -c '._fps')" '{"parsed":0,"total":1}'
expect_eq "acceptance prose: fp null" "$(printf '%s' "$OUT" | jq '._fingerprints.gaps[0]')" "null"
expect_eq "acceptance prose: verdicts default" "$(printf '%s' "$OUT" | jq -r '.verdicts.spec')" "pass"
expect_eq "acceptance prose: learnings default" "$(printf '%s' "$OUT" | jq -c '.learnings')" "[]"

# 3. BLOCKED result → exit 3 with reason.
printf 'BLOCKED: worktree missing\n' > "$WORK/r3"
ENV="$(mk_envelope "$WORK/r3")"
OUT="$("$BIN/parse-verdict" acceptance "$ENV")"; RC=$?
expect_exit "acceptance blocked: exit" "$RC" 3
expect_eq "acceptance blocked: reason" "$(printf '%s' "$OUT" | jq -r '.blocked')" "worktree missing"

# 4. Unusable: is_error envelope → exit 4.
jq -n '{result: "x", is_error: true}' > "$WORK/env-err.json"
"$BIN/parse-verdict" acceptance "$WORK/env-err.json" >/dev/null 2>&1; RC=$?
expect_exit "acceptance is_error: exit" "$RC" 4

# 5. Unusable: no verdict-shaped line → exit 4.
printf 'I did some work but forgot the contract.\n' > "$WORK/r5"
ENV="$(mk_envelope "$WORK/r5")"
"$BIN/parse-verdict" acceptance "$ENV" >/dev/null 2>&1; RC=$?
expect_exit "acceptance no-json: exit" "$RC" 4

# 5a. Fingerprint alignment: unfingerprinted STRING entry yields null in
# place (regression: jq capture on a non-matching string emits an empty
# stream, which silently dropped the entry and misaligned the arrays).
cat > "$WORK/r5a" <<'EOF'
{"gaps":["IMPORTANT: unfingerprinted first","CRITICAL [c1:a:b]: second"],"gaps_summary":"x","minor":[]}
EOF
ENV="$(mk_envelope "$WORK/r5a")"
OUT="$("$BIN/parse-verdict" acceptance "$ENV")"
expect_eq "fps align: length matches gaps" "$(printf '%s' "$OUT" | jq '._fingerprints.gaps | length')" "2"
expect_eq "fps align: first is null" "$(printf '%s' "$OUT" | jq '._fingerprints.gaps[0]')" "null"
expect_eq "fps align: second attributed correctly" "$(printf '%s' "$OUT" | jq -r '._fingerprints.gaps[1]')" "c1:a:b"

# 5b. Type garbage → exit 4 crash path (not exit 5, not exit 0).
printf '{"gaps":"whoops-not-array","gaps_summary":"x"}\n' > "$WORK/r5b"
ENV="$(mk_envelope "$WORK/r5b")"
"$BIN/parse-verdict" acceptance "$ENV" >/dev/null 2>&1; RC=$?
expect_exit "acceptance gaps-not-array: exit" "$RC" 4
printf '{"gaps":[{"not":"a string"}],"gaps_summary":"x"}\n' > "$WORK/r5c"
ENV="$(mk_envelope "$WORK/r5c")"
"$BIN/parse-verdict" acceptance "$ENV" >/dev/null 2>&1; RC=$?
expect_exit "acceptance non-string gap entry: exit" "$RC" 4

# 5d. Last-verdict-wins is a PINNED trade-off: an echoed example after the
# real verdict wins (the prompts' one-line-final-response rule is the guard).
cat > "$WORK/r5d" <<'EOF'
{"gaps":["CRITICAL [c1:a:b]: real gap"],"gaps_summary":"real","minor":[]}
{"gaps":[],"gaps_summary":"","minor":[]}
EOF
ENV="$(mk_envelope "$WORK/r5d")"
OUT="$("$BIN/parse-verdict" acceptance "$ENV")"
expect_eq "last-verdict-wins pinned" "$(printf '%s' "$OUT" | jq '.gaps | length')" "0"

# 5e. Multi-line BLOCKED: reason is the first line only.
printf 'BLOCKED: could not run checks\n{"gaps":[],"gaps_summary":"","minor":[]}\n' > "$WORK/r5e"
ENV="$(mk_envelope "$WORK/r5e")"
OUT="$("$BIN/parse-verdict" acceptance "$ENV")"; RC=$?
expect_exit "blocked multiline: exit" "$RC" 3
expect_eq "blocked multiline: first line only" "$(printf '%s' "$OUT" | jq -r '.blocked')" "could not run checks"

# ── parse-verdict: critic ─────────────────────────────────────────────────

cat > "$WORK/r6" <<'EOF'
{"verdict":"rejected","findings":["spec passes against a stub"],"summary":"stub-passable","learnings":[{"type":"pitfall","key":"stub-trap","insight":"x","confidence":8,"files":["spec/a_spec.rb"]}]}
EOF
ENV="$(mk_envelope "$WORK/r6")"
OUT="$("$BIN/parse-verdict" critic "$ENV")"; RC=$?
expect_exit "critic: exit" "$RC" 0
expect_eq "critic: verdict" "$(printf '%s' "$OUT" | jq -r '.verdict')" "rejected"
expect_eq "critic: learnings kept" "$(printf '%s' "$OUT" | jq '.learnings | length')" "1"

# 6c. Critic type garbage → exit 4, never a value that reads as approved.
printf '{"verdict":7,"findings":"oops"}\n' > "$WORK/r6c"
ENV="$(mk_envelope "$WORK/r6c")"
"$BIN/parse-verdict" critic "$ENV" >/dev/null 2>&1; RC=$?
expect_exit "critic garbage types: exit" "$RC" 4

# ── harvest-learnings ─────────────────────────────────────────────────────

LF="$WORK/learnings.jsonl"

# 6. New valid entry appended with date+card; invalid (no files) dropped; max respected.
cat > "$WORK/v1" <<'EOF'
{"learnings":[
 {"type":"pitfall","key":"default-queue","insight":"jobs must declare queue","confidence":8,"files":["app/jobs/a.rb"]},
 {"type":"pitfall","key":"invalid-entry","insight":"no files","confidence":9,"files":[]},
 {"type":"pattern","key":"over-max","insight":"third entry","confidence":9,"files":["x.rb"]}]}
EOF
jq -c . "$WORK/v1" | "$BIN/harvest-learnings" "$LF" CARD1234 2 >/dev/null
expect_eq "harvest: one valid within max" "$(wc -l < "$LF" | tr -d ' ')" "1"
expect_eq "harvest: card stamped" "$(jq -r '.card' "$LF")" "CARD1234"
expect_eq "harvest: date stamped" "$(jq -r '.date | length' "$LF")" "10"

# 7. Same key, lower/equal confidence → skipped; higher → replaced.
echo '{"learnings":[{"type":"pitfall","key":"default-queue","insight":"weaker","confidence":5,"files":["a.rb"]}]}' \
  | "$BIN/harvest-learnings" "$LF" CARD5678 2 >/dev/null
expect_eq "harvest: lower conf skipped" "$(jq -r 'select(.key=="default-queue") | .confidence' "$LF")" "8"
echo '{"learnings":[{"type":"pitfall","key":"default-queue","insight":"stronger","confidence":9,"files":["a.rb"]}]}' \
  | "$BIN/harvest-learnings" "$LF" CARD9999 2 >/dev/null
expect_eq "harvest: higher conf replaced" "$(jq -r 'select(.key=="default-queue") | .confidence' "$LF")" "9"
expect_eq "harvest: still one line per key" "$(wc -l < "$LF" | tr -d ' ')" "1"

# 8. Bad type rejected.
echo '{"learnings":[{"type":"vibe","key":"bad-type","insight":"x","confidence":5,"files":["a.rb"]}]}' \
  | "$BIN/harvest-learnings" "$LF" C 2 >/dev/null
expect_eq "harvest: bad type dropped" "$(grep -c bad-type "$LF" || true)" "0"

# 8b. Corrupt line in the file: preserved untouched; replace still
# deduplicates the valid line (committed file → merge-conflict debris is real).
LFC="$WORK/corrupt.jsonl"
printf '{"date":"2026-07-01","card":"A","type":"pitfall","key":"good-key","insight":"old","confidence":5,"files":["a.rb"]}\nNOT JSON AT ALL\n' > "$LFC"
echo '{"learnings":[{"type":"pitfall","key":"good-key","insight":"new","confidence":9,"files":["a.rb"]}]}' \
  | "$BIN/harvest-learnings" "$LFC" C 2 >/dev/null
expect_eq "harvest corrupt: corrupt line preserved" "$(grep -c 'NOT JSON AT ALL' "$LFC")" "1"
expect_eq "harvest corrupt: exactly one good-key line" "$(grep -c 'good-key' "$LFC")" "1"
expect_eq "harvest corrupt: replaced confidence" "$(grep 'good-key' "$LFC" | jq -r '.confidence')" "9"

# 8c. Key with JSON-escaped characters still dedups (raw-vs-escaped mismatch).
LFQ="$WORK/quoted.jsonl"; : > "$LFQ"
echo '{"learnings":[{"type":"pitfall","key":"a\"b","insight":"x","confidence":5,"files":["a.rb"]}]}' | "$BIN/harvest-learnings" "$LFQ" C 2 >/dev/null
echo '{"learnings":[{"type":"pitfall","key":"a\"b","insight":"x","confidence":4,"files":["a.rb"]}]}' | "$BIN/harvest-learnings" "$LFQ" C 2 >/dev/null
expect_eq "harvest quoted key: single line" "$(wc -l < "$LFQ" | tr -d ' ')" "1"

# ── render-learnings ──────────────────────────────────────────────────────

# Fixture repo: render runs from the target repo root (staleness = git ls-files).
REPO="$WORK/repo"; mkdir -p "$REPO/app/jobs" "$REPO/lib"
git -C "$REPO" init -q
touch "$REPO/app/jobs/a.rb" "$REPO/lib/util.rb"
git -C "$REPO" add -A >/dev/null 2>&1
git -C "$REPO" -c user.email=t@t -c user.name=t commit -qm init

LF2="$WORK/l2.jsonl"
cat > "$LF2" <<'EOF'
{"date":"2026-07-01","card":"A","type":"pitfall","key":"queue-choice","insight":"exact file match","confidence":8,"files":["app/jobs/a.rb"]}
{"date":"2026-07-01","card":"B","type":"pattern","key":"dir-match","insight":"same dir","confidence":6,"files":["app/jobs/other.rb","lib/util.rb"]}
{"date":"2026-07-01","card":"C","type":"tool","key":"stale-entry","insight":"gone","confidence":9,"files":["removed/file.rb"]}
{"date":"2026-07-01","card":"D","type":"tool","key":"title-match-keyword","insight":"via title","confidence":4,"files":["lib/util.rb"]}
{"date":"2026-07-01","card":"E","type":"tool","key":"no-match","insight":"irrelevant","confidence":9,"files":["lib/util.rb"]}
EOF
printf 'app/jobs/a.rb\n' > "$WORK/plan-files"
OUT="$(cd "$REPO" && "$BIN/render-learnings" "$LF2" "$WORK/plan-files" "Fix the keyword handling in importer" 2> "$WORK/render-err")"
expect_eq "render: exact-file entry included" "$(printf '%s\n' "$OUT" | grep -c 'queue-choice')" "1"
expect_eq "render: same-dir entry included" "$(printf '%s\n' "$OUT" | grep -c 'dir-match')" "1"
expect_eq "render: title-keyword entry included" "$(printf '%s\n' "$OUT" | grep -c 'title-match-keyword')" "1"
expect_eq "render: irrelevant excluded" "$(printf '%s\n' "$OUT" | grep -c 'no-match' || true)" "0"
expect_eq "render: stale excluded" "$(printf '%s\n' "$OUT" | grep -c 'stale-entry' || true)" "0"
expect_eq "render: stale surfaced on stderr" "$(grep -c 'stale: stale-entry' "$WORK/render-err")" "1"
expect_eq "render: sorted by confidence" "$(printf '%s\n' "$OUT" | head -1 | grep -c 'queue-choice')" "1"

# 9. Empty/missing learnings file → literal none.
OUT="$(cd "$REPO" && "$BIN/render-learnings" "$WORK/does-not-exist" "$WORK/plan-files" "title")"
expect_eq "render: missing file -> none" "$OUT" "none"

# 10. Cap at 5: six matching entries → 5 rendered.
LF3="$WORK/l3.jsonl"; : > "$LF3"
for i in 1 2 3 4 5 6; do
  printf '{"date":"2026-07-01","card":"X","type":"tool","key":"entry-%s","insight":"i","confidence":%s,"files":["app/jobs/a.rb"]}\n' "$i" "$i" >> "$LF3"
done
OUT="$(cd "$REPO" && "$BIN/render-learnings" "$LF3" "$WORK/plan-files" "t" 2>/dev/null)"
expect_eq "render: capped at 5" "$(printf '%s\n' "$OUT" | grep -c '^\[')" "5"
expect_eq "render: lowest-confidence dropped" "$(printf '%s\n' "$OUT" | grep -c 'entry-1' || true)" "0"

# 11. Outside a git repo staleness fails OPEN — memory survives, not `none`.
NOREPO="$WORK/norepo"; mkdir -p "$NOREPO"
OUT="$(cd "$NOREPO" && "$BIN/render-learnings" "$LF2" "$WORK/plan-files" "t" 2>/dev/null)"
expect_eq "render no-git: staleness skipped, matches survive" "$(printf '%s\n' "$OUT" | grep -c 'queue-choice')" "1"

# ── Summary ───────────────────────────────────────────────────────────────

echo ""
echo "kit-bin: $((CHECKS - FAIL))/$CHECKS checks passed"
[ "$FAIL" -eq 0 ] || { echo "kit-bin: $FAIL FAILED" >&2; exit 1; }
