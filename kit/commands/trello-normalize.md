---
description: Add [<prefix>-<idShort>] prefix to every card on the board that lacks it
allowed-tools: Read, mcp__trello
---

# /trello-normalize

Role: **title-normalizer**. Standalone utility command. Scans all cards on
the board (every column except `Icebox`, including archived if reachable)
and adds the `[<card_prefix>-<idShort>]` prefix to any card whose title
doesn't have it. `Icebox` is the human-only holding pen for raw ideas and
is deliberately skipped — ideas get a prefix only once promoted to
`Backlog`.

Use when:
- You just bulk-created several cards in Trello UI and want their numbers
  visible before triggering /trello-check.
- A card in a column other than `Backlog` (e.g. `Plan Proposed`, `Review`,
  `Done`) somehow lost its prefix or was created there directly.
- Onboarding an existing board (first-time setup) — applies prefix to
  every legacy card.

`/trello-check` performs the same normalization for Backlog cards as part
of its Phase 2. This command is a superset for the columns it doesn't
touch.

## Contract (what you must NOT do)

- Do NOT modify card title content beyond adding the prefix.
- Do NOT comment on cards.
- Do NOT move cards between columns.
- Do NOT touch cards that are already correctly prefixed.
- Do NOT touch cards in `Icebox` (list ID `lists.icebox`).
- Do NOT touch epic trackers (title contains `epic.marker`, default `[epic]`) — they stay outside the `[<prefix>-N]` numbering.
- Do NOT trigger triage logic (`card-eval.md`). This is rename-only.

## Sources of truth

- `.claude/trello.json` → `board.id`, `card_prefix`, `lists.icebox`, `epic.marker`.

## Algorithm

1. Read `.claude/trello.json`. Extract `board.id`, `card_prefix` (default
   `"ACME"`), and `lists.icebox`.
2. Via MCP `trello`, fetch all cards on the board:
   ```
   GET /boards/<board-id>/cards/all?fields=name,idShort,closed,idList
   ```
   Use `/cards/all` (not `/cards`) so archived cards are included; they may
   become unarchived later and should already carry the prefix. `idList` is
   needed to skip the `Icebox` column.
3. For each card, in ascending `idShort` order:
   - If the card's `idList` equals `lists.icebox` → skip (raw idea, not yet
     promoted).
   - If the card's title contains `epic.marker` (default `[epic]`) → skip
     (epic tracker, stays outside the numbering scheme).
   - Compose expected prefix: `[<card_prefix>-<idShort>] ` (with trailing space).
   - If the card's current title already starts with `[<card_prefix>-<idShort>] `
     → skip.
   - If the card's title starts with `[<card_prefix>-<other_number>] ` (i.e.
     it was prefixed but the number doesn't match its current idShort — should
     never happen, but defend) → report to chat as a warning and skip.
   - Otherwise → rename to `[<card_prefix>-<idShort>] <current title>`.
4. Summary to chat:
   ```
   Normalized N cards (already correct: M, skipped due to mismatch: K).
   ```

## Output

Single line per renamed card showing old → new title (terse). No comments
posted to cards, no session-log entries (normalization is a noop in workflow
terms).

## Failure modes

| Situation | Action |
|---|---|
| MCP `trello` not responding | Stop. Error to chat. No partial state — renames are individual API calls; whatever succeeded stays. |
| Rename API call fails for one card (rate limit, permissions) | Log to chat, continue with next card. |
| `.claude/trello.json` malformed or missing `card_prefix` | Stop. Don't guess. |
| Card has a title that starts with `[<prefix>-<wrong_number>]` | Warn, skip. Investigate manually — Trello does not change `idShort`, so this means a human or another tool tampered with the prefix. |
