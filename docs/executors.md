# Claude and Codex executors

The orchestrator and executor are separate choices. Any meta-agent able to
follow the command Markdown and use the tracker/shell can coordinate a run.
`kit/bin/run-agent` launches its worker, test-critic and acceptance processes
using Claude Code or Codex. The kit still installs under `.claude/`; choosing
Codex does not rename or duplicate prompts, policy or review gates.

## Configure

Add the required top-level `executor` block to existing `tracker.json` before
syncing this revision. Both tracker examples include:

```json
{
  "executor": {
    "default": "claude",
    "timeout_seconds": 1800,
    "codex_sandbox": "workspace-write"
  }
}
```

Set `default` to `codex` for a Codex-only pipeline. Optional `worker.executor`
and `acceptance.executor` override it independently. The test critic follows
acceptance; specs, implementation, retries and research follow worker.
`worker.model` and `acceptance.model` refer to the chosen CLI's model names;
empty means that CLI's default. Explicit example for a mixed pipeline:

```json
{
  "executor": {"default": "codex", "timeout_seconds": 1800},
  "worker": {"model": "", "max_turns": 100, "resume_sessions": true},
  "acceptance": {"executor": "claude", "model": "", "max_turns": 50}
}
```

Only the selected CLIs need to be installed and authenticated. Before moving
cards or launching work, run `.claude/bin/run-agent check --config
.claude/tracker.json`. It validates options/CLI presence and returns the
configuration fingerprint. It does not prove authentication or model access;
provider failures are preserved as failed attempts. CLI contracts were checked
against Codex 0.155.1 and Claude Code 2.1.266; incompatible flags fail closed.

## Capabilities and limits

| Capability | Claude | Codex |
|---|---|---|
| Launch | `claude -p`, JSON result | `codex exec --json`, JSONL plus final-message file |
| Worker permissions | Existing `bypassPermissions` and project hooks | Explicit `workspace-write` by default; approvals `never` |
| Audit permissions | Edit/Write/MultiEdit/NotebookEdit disabled | Read-only source + isolated writable temp; approvals `never` |
| Turn budget | Stage `max_turns` | Unsupported; not silently translated |
| Wall-clock deadline | `executor.timeout_seconds` | Same |
| Resume | Exact recorded session ID | Exact recorded thread ID; never `--last` |
| Cost | Provider-reported USD if available | Unknown (`null`); token usage retained |

Claude's hooks are guardrails, not containment. Codex does not execute those
hooks; its sandbox is not a PLAN file manifest or a ban on particular Git
operations. Acceptance still checks scope and reviewed source identity.
Filesystem permissions do not prevent all external mutations via inherited
MCP tools or credentials. Use trusted tasks and appropriately scoped accounts.

Codex workspace sandbox/network policies can prevent dependency installation,
Git metadata writes, pushing or opening a PR. A permission failure is Blocked;
the adapter never retries with broader access. Where the owner has deliberately
provided an isolated environment, `executor.codex_sandbox: "danger-full-access"`
is an explicit worker-only option. Audited source stays read-only even then. Audits
whose mandatory checks cannot run with their permissions must report a blocker
or failed coverage; pre-existing worker output is not permission to skip them.
Codex audits use an explicit permission profile: filesystem read access, write
access only to a newly created per-attempt temporary directory, and no shell
network access. `TMPDIR`, `TMP`, `TEMP`, `XDG_CACHE_HOME` and npm's cache point
there so tests can create fixtures without changing the audited checkout or
Git metadata. The absolute directory is frozen in `request.json` as
`audit_temp`, remains available for inspection, and may be removed after the
attempt is terminal. Profiles replace inherited permission grants. Unsupported
profile configuration fails closed; there is no unrestricted fallback.
No Claude-specific `max_turns` guarantee is claimed for Codex.

## Results, recovery and review

`run-agent run` takes absolute worktree, prompt-file and attempt paths, a
tracker config and role (`worker`, `critic`, `acceptance`). Pass the bootstrap
`--config-sha256` to reject config drift before starting a new attempt.
`run-stage` owns the single-launch claim; a duplicate returns 73 regardless of
whether the earlier launch completed. Consult `stage-status`: consume a
completed result, wait for a live process, or inspect incomplete evidence.

The attempt stores `request.json` (including the exact rendered prompt),
`provider.stdout`, `provider.stderr.log`, normalized `result.json`, and the
existing owner/exit records. Codex also writes `provider-final.txt`. Requests
and raw logs may contain private project context; keep runtime directories
private and outside tracked source. Prompts travel on stdin, without shell
interpolation. A timeout terminates the provider process group and records
exit 124; a crash with incomplete evidence never authorizes replay.

The normalized envelope preserves `result`, `session_id`, `is_error`,
`total_cost_usd`, `num_turns` plus `executor`, `usage` and `request_sha256`.
Codex turn events are not Claude agent turns: `num_turns` remains null. Sum
only known USD amounts and report unpriced runs separately. Invalid/partial
streams, provider errors, final-message mismatch and changed session IDs
cannot become successful results.

`--resume-from <completed-worker-attempt>` binds continuation to its provider,
worktree, exact config and successful normalized result. Auditors cannot
resume. Preserve the worker attempt separately from the critic attempt. With
`worker.resume_sessions: false`, start fresh and always supply the approved
plan/phase rules. TDD phase B requires critic approval in either mode.
Expired provider sessions may use the protocol's one fresh-context retry only
after a terminal recorded exit; configuration/identity drift requires inspection.

The existing `parse-verdict`, complete manifest/source-evidence validation,
SHA pinning and final merge revalidation are unchanged requirements. The
adapter does not itself approve a plan, certify review quality or authorize merge.

## Using Codex as the orchestrator

Ask Codex explicitly, for example: “Read `.claude/commands/flow-run.md` and
execute its protocol for issue #42, using `.claude/tracker.json`; treat the
invocation arguments as `#42`.” Ready/plan-approval prerequisites still apply.

For persistent discovery, put a short reference in your project-owned
`AGENTS.md` pointing to `.claude/project-context.md`, `.claude/constitution.md`
and the command files. Do not overwrite an existing AGENTS.md or copy the kit
into a second location. Native Codex skills are an optional entry point, not
required for executor selection; this change does not install slash commands.

Official references: [Codex non-interactive execution](https://learn.chatgpt.com/docs/non-interactive-mode),
[Codex project instructions](https://learn.chatgpt.com/docs/agent-configuration/agents-md).
