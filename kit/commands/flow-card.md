---
description: Turn a rough intention into a well-specified card in Backlog — interactively, before triage, so /flow-check plans it on the first pass
allowed-tools: Read, Glob, Grep, AskUserQuestion, Edit(.gilb/**), Write(.gilb/**), Bash(date:*), Bash(gh:*), mcp__trello
---

# /flow-card

Role: **card composer**. Invoked manually by the user with a rough
intention as the argument:

```
/flow-card the recorder drops the last second of audio when you stop mid-sentence
```

Grounds that sentence in the repo, resolves the gaps `/flow-check` could
not auto-answer by asking the human *now* (while they still have the
context in their head), and creates one card in `Backlog` carrying a
completion contract: goal, done-when, out-of-scope, stop-if.

Why it exists: without it a rough card costs two triage passes —
`/flow-check` → `[meta] QUESTIONS` → `Human Questions` → `/flow-questions`
→ `Backlog` → `/flow-check` again. The questions are the same either way;
asking them at authoring time is one turn instead of three commands and
two context reloads. `/flow-questions` remains the path for cards that
entered the board some other way.

## Contract (what you must NOT do)

- Do NOT write a PLAN. The card states **WHAT and how we'll know it's
  done**; `/flow-check` decides HOW (approach, files, test commands) and
  the human gates that plan. A card that names the implementation
  pre-empts both.
- Do NOT create more than one card per invocation. If the intention is
  several PRs, see "Too big" below — splitting stays in `/flow-check`.
- Do NOT create anything before the human has read the exact card text
  (step 7). A card the human first sees on the board is a card they now
  have to edit in the tracker UI.
- Do NOT move any card into `Ready for AI` — only the user does that.
- Do NOT run triage (`card-eval.md`), spawn workers, or touch git.
- Do NOT use the `Agent` tool — this is a single interactive session.
- Do NOT ask a question the repo already answers, or one `/flow-check`
  would auto-answer per `card-eval.md` step F. Every avoidable question
  is a turn the human pays for.
- Do NOT comment on cards without the `[meta] ` prefix.

## Sources of truth

- `.claude/tracker.json` — `tracker.provider`, `states.backlog`,
  `states.icebox`, `card_prefix`, `research.marker`, `epic.marker`,
  `repo_label_prefix`, `targets`, `default_target`, `session_log`,
  `learnings`, `comment_prefixes`.
- `.claude/providers/<tracker.provider>.md` — `create_item`,
  `update_title`, `set_labels`, `add_comment`, `list_items`;
  `## Capabilities` (`native_ids` decides the title prefix).
- `.claude/prompts/card-eval.md` — the eight gap categories (step D) and
  the auto-answer policy (step F). This command does not define its own;
  it front-runs those.
- `.claude/constitution.md` — an intention that cannot satisfy an
  applicable article is a question, not something to word around.

## Algorithm

### 1. Bootstrap

Read `tracker.json`, the provider doc, the constitution, and the
learnings file (skip silently if missing). Fetch open cards in
`backlog`, `plan_proposed`, `ready`, `in_progress`, `review` — titles
only — for the duplicate scan in step 3.

With no argument: print the usage line above and stop.

### 2. Ground the intention in the repo

Before asking anything, spend a bounded pass on the target repo
(`repo_label_prefix` label if the intention names one, else
`default_target`): locate the files/modules the intention implicates,
confirm they exist *now*, and note anchors (`path:line`) worth carrying
into the card. Read the matching `learnings.jsonl` entries — a pitfall
whose `files[]` overlap the likely scope belongs in `## Stop if` or
`## Out of scope`, not in a question.

Note the target's `test_cmd` / `lint_cmd` from `tracker.json`, and what
the repo already uses to prove this kind of change (a suite path, a
lint rule, a search that must come back empty). That is what `## Done
when` names in step 6 — the card cannot ask for proof the author never
went looking for.

Detect the card type: research (`research.marker` — deliverable is a doc,
gaps are question / decision-it-informs / boundary) or code. Epics
(`epic.marker`) are out of scope for this command.

Enough context to write a defensible contract, not an exhaustive survey.

### 3. Duplicate scan

If an open card plainly covers this intention, say so with its ref and
stop — do not create a near-duplicate. Offer: comment on the existing
card instead, or re-run with a narrower intention.

### 4. Gap pass

Walk the eight categories from `card-eval.md` step D against the
grounded intention. Sort each gap:

- **Auto-answerable** (all four conditions of step F hold) → take the
  default. It goes into the card body *and* into an `[meta] ASSUMED`
  comment (same format as `card-eval.md` F3) so the human can override
  later exactly as they would after triage.
- **Not auto-answerable** (`What`, `Why`, `Dependencies`, `Size` when it
  implies a split) → ask, step 5.

### 5. Interview — at most 3 `AskUserQuestion` turns

One question per turn, most consequential first (same priority order as
`flow-questions.md` step 3: `What` → `Why` → `Size`-as-split →
`Dependencies` → first remaining). Each question:

- carries ≤1 sentence of repo-grounded context — what the choice lands
  on, quoting a real path;
- offers 3–4 concrete options, each described by its consequence for the
  codebase and for the follow-up work it implies;
- always includes **`Park in Icebox`** as the escape hatch — the honest
  answer when the human doesn't know yet.

After three turns, stop asking. Remaining gaps take documented defaults
(`[meta] ASSUMED`) if the step-F conditions hold, and otherwise become
one `Open question:` bullet in `## Stop if` — `/flow-check` will raise it
as a proper QUESTIONS gap. Three turns is the budget; an interview longer
than that is a card that isn't ready to be written.

**Escapes.** `Park in Icebox` on the decisive gap, or a cancelled
`AskUserQuestion`: the card is destined for `icebox` instead of
`backlog`, carrying whatever contract exists so far and a `[meta] PARKED`
comment naming the undecided gap. Icebox is the human-only holding pen;
nothing triages it. This changes the destination, not the route — still
compose (step 6) and still show the text for approval (step 7). A parked
card is one the human will read months later, so it earns the same
30 seconds of review as any other.

**Too big.** If the intention is clearly several PRs, don't split it
here. Say so, propose the first independently shippable slice, and offer
it as the card being created — the rest is a one-line `icebox` idea,
shown for approval in step 7 alongside the card and created in step 8.
`/flow-check`'s SPLIT path stays the single tested splitter.

### 6. Compose the card

Title: `<one-line imperative>`, prefixed with `research.marker` for a
research card. No `[<card_prefix>-N]` yet — the number is the native id,
which only exists after creation (step 8).

Body:

```
## Goal
<the one observable change, in the user's terms — WHAT, never HOW>

## Why
<the impact or incident that motivates it, 1–2 lines>

## Done when
- <proof, not effort: what an acceptance check can observe. Name an
  existing verification when the repo has one — a suite, a lint rule, a
  search that must return zero hits, a metric over a threshold — WITHOUT
  prescribing the approach that gets there. /flow-check turns these into
  the PLAN's ## Tests.>
- <…>

## Out of scope
- <what this card deliberately does not touch>

## Stop if
- <a condition that invalidates the card: an assumption that turns out
  false, a pitfall from learnings, an open question. Meta or the worker
  escalates instead of improvising — but only for a real impasse that
  survives a retry. A first failing attempt, work that is merely large,
  slow or unclear, and "this would benefit from clarification" are not
  stop conditions.>

## Context
- <path:line / doc / card ref — verified in step 2 to exist now>
```

Self-check before creating — every one is a defect if it fails:

- No placeholders (`TBD`, "appropriate handling", "etc."). An unmade
  decision is either an ASSUMED default or a `Stop if` bullet.
- `## Goal` names an observable change, not an approach or a file list.
- Every `## Done when` bullet is checkable by someone who didn't write
  the card.
- Every `## Context` anchor was actually opened in step 2.
- Research card: `## Out of scope` states "no production code".

### 7. Show the exact text, then create

Print the composed title and body **in full** — the text that will land
on the board, not a paraphrase — and name the choices behind it: what
you took as the finish line, what proves it, what you fenced off, what
you assumed. Flag anything still soft.

Then a final `AskUserQuestion`: `Create it` / `Revise` (fold the edits in
and show the draft again — expect more than one round) / `Discard`. This
turn does not count against the three-question budget in step 5: that
budget is for resolving gaps, this is the approval gesture. Nothing is
written to the tracker before the human has read the exact wording,
because after creation every edit costs a round-trip through the tracker
UI. On `Discard`, print the draft one last time so the work isn't lost,
and create nothing.

If the human wants the card looser than you'd recommend, say what the
trade-off is once, then write their version. Don't relitigate it, and
don't quietly re-tighten the wording on the next draft.

### 8. Create, number, label, log

1. `create_item(states.backlog, title, body, labels)` — or `icebox` per
   the escapes in step 5. Labels: `repo_label_prefix + <target>` when the
   target isn't `default_target`. Never the `ai_generated` label — this
   card is the human's, co-authored.
2. If the provider's `## Capabilities` has `native_ids: no`, read back
   the native id and `update_title` to `[<card_prefix>-<N>] <title>`.
   With `native_ids: yes`, leave the title clean.
3. Post one `[meta] ASSUMED (gap: <category>)` comment per default taken
   (step 4), before anything else on the card.
4. Append to the session log:
   `<ISO UTC ts>  <card-short>  CREATED-INTERACTIVE  | <terse goal> (asked: <N>, assumed: <M>)`

## Output

The contract itself was already shown in step 7 — don't reprint it. Close
with the card ref and URL, the assumed defaults, and one next action:
normally `Run /flow-check to triage <ref>` (or, for a parked card, what
decision would unpark it).

## Failure modes

| Situation | Action |
|---|---|
| No argument given | Print usage, stop. Don't invent an intention. |
| Tracker (MCP/CLI) not responding | Stop. Error to chat. Never fall back to raw REST/curl. |
| `.claude/tracker.json` malformed or missing a key above | Stop. Don't guess field values. |
| Intention names a file that doesn't exist | Don't ask about it — report it and ask whether the file is new or the name is wrong (that's a `What` gap). |
| An open card already covers this | Report the ref, create nothing (step 3). |
| Human picks `Discard`, or cancels the approval prompt | Treat both as discard: print the full draft so the work survives in the transcript, create nothing. |
| Card created but `update_title`/label/comment fails | The card exists — report exactly which follow-up call failed and what to run manually. Never create a second card. |
| Session log missing | Create it from the existing header template; proceed. Log the recovery in chat. |
| Constitution forbids the intention as stated | Surface the article in the interview as the first question — a card that cannot pass the gate is not worth planning. |
