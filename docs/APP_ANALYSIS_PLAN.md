# App-initiated analysis — issue #8

Issue: https://github.com/ganggangstone/where-were-we/issues/8

## Outcome and initial execution choice

An explicit app action starts analysis, reports progress, and reads validated saved
results without changing collection history or the selected comparison baseline.
Existing copy-to-MCP requests remain available.

The first automatic executor is an installed Claude Code CLI signed in with a
Claude account. Its account and usage responsibility are shown before execution.
The app does not log in, switch accounts, claim free usage, or store provider keys.
Direct provider API support belongs to issue #10. Additional CLI adapters can use
the same executor interface after their execution and authentication contracts are
verified; MCP registration alone is not an automatic execution capability.

Claude runs in a temporary working directory with built-in tools disabled, a
strict empty MCP configuration, safe mode, and no session persistence. Safe mode
preserves normal authentication; bare mode is unsuitable because it bypasses
subscription OAuth. Organization-managed policy can still apply. Unsupported CLI
versions and authentication modes fail before model execution, with the manual
handoff still available.

Official references checked 2026-10-29:

- https://code.claude.com/docs/en/cli-reference
- https://code.claude.com/docs/en/headless
- https://code.claude.com/docs/en/hooks

## Work breakdown

1. **Run coordinator:** persist run identity and project/repository/branch/language
   scope and explicit task/targets; pin commit, configuration and (only for a
   requested briefing) collected evidence. The first automatic analysis builds
   analysis, system overview and screen groups. It omits embedded route steps and
   program jobs as well as their task queue entries. Detail buttons run only the
   chosen targets and necessary prerequisites; the public manual MCP plan stays
   compatible. Re-plan after each save and retain completed work on failure.
2. **CLI adapter:** discover the executable, check supported options and login,
   supply bounded pinned source and request data via stdin, parse structured
   output, handle authentication/usage limits, timeout and cancellation. Never run
   application code or give the model write access to the map store.
3. **Native/UI integration:** display provider/account and explicit Start, progress,
   Cancel and Retry; poll scoped run status; read stored results on completion;
   recover state after reopening without confusing a different task with the
   selected request. Keep repository-local target IDs when a combined map spans
   repositories. Show saved tasks separately from input calls, encoded bytes and
   processed input units. Package both Python modules and the UI script.
4. **Integration review:** fake executors and temporary repositories cover success,
   invalid evidence, stale sources/configuration, partial progress, cancellation,
   retry and interrupted workers. Check frontend stale-response handling, preserved
   comparison settings, packaging and the existing regression suite.

## State and storage contract

Runs use preparing, running, saving, completed, failed and cancelled states. An
interrupted worker becomes an actionable failed run; retry creates a new pinned
run with the same task and targets. One active run per project prevents overlapping scopes from competing for
saved snapshots. Cancellation affects only a process launched for that run.

The coordinator checks pins before each task and before recording. Existing
analysis, task and briefing recorders remain the authority for evidence and stale
result validation. No refresh is performed to display results. Source prompts,
credentials and raw provider diagnostic output are not persisted in run metadata.
Source and metadata are split into server-identified units with a hard 131,072-byte
cap on each complete encoded prompt. Partial changes send affected source and
necessary prior blobs. The first system overview uses validated map and collected
structure metadata; missing context uses bounded, pinned source or metadata reads.
All units and final relationships must validate before one recorder call per task.
Unrequested details stay absent or retain their existing provenance and freshness;
empty details are not invented to complete the overview. An unchanged overview
requires zero model calls, even when details have never been requested. Inputs
that cannot fit still fail explicitly. App updates wait for active workers.

## Release verification

- Automated checks use fake executors; they must not spend real model usage.
- Check a packaged macOS build with an installed supported Claude Code CLI: inspect
  the account notice, explicitly start a synthetic project, observe progress,
  cancel/retry, reopen the app, and see a validated result without moving the
  comparison baseline.
- Check missing CLI, signed-out CLI, unsupported CLI/auth mode, and manual MCP
  fallback. Confirm ordinary refresh never starts paid analysis.
- A real-provider smoke test requires the user to choose the account and explicit
  execution. Passing fake-provider tests alone does not satisfy this final check.
