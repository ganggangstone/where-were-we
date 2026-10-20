# Multiple repositories in one project

Repositories are collected independently, then composed into one project view. A repository that fails to refresh keeps its last successful map, so the others stay usable. Analyzing every checkout in one pass was considered; it would couple refreshes and failure recovery.

## Behavior

Agent session discovery, activity tracking and session resumption are outside the product scope. Git worktrees and uncommitted source changes remain part of repository impact. Legacy session fields are omitted at the shared read boundary; stored snapshots are not rewritten to remove them.

- Create a project with one repository; add related repositories without replacing earlier maps. Register either a GitHub URL or an existing local folder, then choose all repositories or one. URL connections clone code and run their first collection; opening the resulting project does not trigger an extra refresh of existing repositories.
- Each repository has a stable ID, a local Git repository, analyzed/compared refs, and frontend/backend source roots. A role may be absent; two roles may use the same ref. Frontend-only, backend-only and general repositories are valid. Missing configured source directories are reported.
- The automatic parser covers React Router/axios, FastAPI and SQLAlchemy. Other languages and frameworks use explicit AI analysis: `ai_extract.py` accepts results from any connected MCP agent and returns the same map schema.
- Repository names appear on screens, requests, GitHub work and evidence. Original paths are kept separately from internal identifiers, so equal screen paths, file names, PR/issue numbers and table names in different repositories stay distinct. Mobile folding and common-component detection stay local to each repository.
- Automatic cross-repository HTTP matches are candidates. Only an explicitly configured API destination connects matching requests; ambiguous matches stay candidates. Configured connections are labeled as configured, never as proven by code. Tables are separate unless explicitly mapped to a shared data ID.
- Refresh all repositories or one. The last complete successful snapshot survives fetch, extraction, GitHub or publication failures. Each repository shows its last attempt, last success, error and retained commit. A first failure is not an empty success. Refresh, configuration, AI and test writes are serialized with a project lock, and completed repository snapshots are published atomically.
- Changing refs or layout starts a new comparison baseline instead of reporting every old item as deleted. Unregistering a repository keeps its stored snapshots. Existing single-repository files remain readable and are preserved on adoption.
- The UI and MCP read the same composed snapshot. Repository selection uses stable IDs and cannot be overwritten by older asynchronous responses.
- In a multi-repository project, code-map AI actions and test-rule/evidence writes require an explicit repository. Change explanations may cover the whole project or one repository. Test evidence is checked against that repository's recorded commit. Ambiguous MCP targets return choices instead of selecting the first.

## Storage

`project.json` describes the project and its repositories. Each repository keeps its JSON maps in immutable generations; one atomically written state file selects the successful generation and records attempts. Failed or interrupted generations never replace the selected one. Legacy files are referenced in place until a successful new generation exists.

Project-level `briefing.json` keeps change explanations keyed by repository, branch and language, with the evidence each one used. Inputs come from the last successful collection; results submitted after the inputs, settings or code changed are rejected. Preparing, recording and reading explanations do not collect or advance change history.

Atomic publication applies to configured projects. Repository refreshes have independent commit and timestamp boundaries, so a composed view is not a simultaneous snapshot across repositories.

## Modules

`project.py` owns validation, registration, locking, snapshot publication, composition and command dispatch. `mapcore.py` and the Tauri bridge consume its bundle reader instead of implementing their own composition. The composed view uses repository-qualified internal keys and keeps `repository` and `source_*` fields for original paths. A repository filter changes the visible screens and work while keeping their dependency targets.

Refs and layout reach the collectors through an explicit child environment. GitHub failures are errors, not empty lists. User checkouts, branches, worktrees and working files are never modified; collection may run `git fetch`.

`connections.py` parses GitHub URLs and keeps full-history clones without a checkout under `<project>/.code/<URL hash>/repository`. HTTPS, `.git`, SSH notation and owner/repository forms normalize to one HTTPS URL; duplicates and invalid forms are rejected before download. Managed clones were chosen over API-only source reads so Git-based analysis can be reused, at the cost of local disk space and download time. The remembered GitHub account authenticates clone and refresh without changing global login state. A clone is staged before publication, so a failed download preserves the configuration and can be retried. Disconnecting keeps code and maps; reconnecting reuses the code after verifying its URL and ownership marker. Managed storage is excluded from worktree reporting, and its `origin/HEAD` pointer is updated after each fetch.

`app_control.py` provides the live-control MCP tools (`app_state`, `app_targets`, `app_control`, `app_command_result`). A local command bridge was chosen over navigation links and GUI automation so selection works in both directions and covers every action. The macOS app owns a private Unix socket (0700 directory, 0600 socket); there is no HTTP listener. Its mailbox serializes commands, scopes IDs to one app instance and keeps replay tombstones after responses are evicted. Only the UI acknowledges that a command was applied. Queued and running commands are incomplete; a UI reload interrupts unresolved commands, and old instance IDs cannot run in a new app. Closed, not-ready, missing, expired and failed results stay distinct.

`ui/control.js` derives stable target identities from screens, requests, programs, data, jobs, connections and feature-group members, independent of display order. SHA-256 revisions cover the displayed map, analysis and configuration; selections name the project, repository, branch, target and revision, and stale revisions or missing targets return errors. Commands reuse the UI and native paths. Preparing an analysis request returns `prepared=true, executed=false`; starting an update returns `started=true, completed=false`. Reading results keeps the comparison history. No chat history is collected.

`connection.py` diagnoses the MCP connection after updates. Guided diagnosis with a copyable repair request was chosen over having the app write each client's configuration, which would mean maintaining a writer per client format. The app probes only its own interpreter and server, compares the child's identity with the expected source fingerprint, and never executes supplied registration arguments. A separate expiring challenge is confirmed through the agent's actual MCP connection with `confirm_connection`; `server_info` exposes the startup fingerprint and tool registry. A healthy probe or a copied repair request does not prove the client reconnected. The app reads and writes no client configuration; from optional registration evidence it stores only command and script paths, not environment or argument values. Backend source files and packaging share one allowlist (`BACKEND_FILES`).

`scripts/prepare-runtime.py` packages an explicit backend allowlist and copies only the runtime UI files into the generated `src-tauri/frontend` directory before Tauri embeds them; build helpers and local caches stay out. Embedded assets are Brotli-compressed, so release checks decompress them instead of scanning the raw binary.

## Connected-agent analysis

The UI prepares a copyable request for the user's connected MCP agent. MCP `analyze` returns instructions, schema and arguments; `analysis_source` supplies commit-pinned source so the client needs no local file access; `record_analysis` validates and publishes the submitted JSON. No AI provider is launched by the app. Repository, role, language, commit and configuration fingerprint scope each exchange, and submissions for a changed commit or configuration are rejected.

Screen groups, system structure, program jobs and request steps use `request_ai_task` and `record_ai_task` the same way. The UI buttons and the `group.py`, `system.py`, `jobs.py` and `steps.py` commands only prepare requests. Submitted output is validated against its pinned source and stored input snapshot. Each branch map stores its own `task_outputs`. A manually written system is kept, and an AI proposal is stored separately as `system.ai`. System nodes, links and external services require source evidence; unknown facts use the `{text, needs}` format. Job triggers must belong to the selected program's code; producer-route links remain AI interpretations.

AI items require tracked files, exact source lines and literal quotes, and malformed output cannot replace the selected generation. These checks establish where text came from, not that the interpretation is correct or complete. Unknown areas and AI origin are shown in the UI and MCP. Ordinary refresh keeps AI maps, marks changed commits as needing analysis, and never calls AI. Test rules and recorded evidence use one deterministic matcher for static and AI maps.

## App updates

Homebrew installations update from the UI. The app validates its managed path and the available version before closing. A copy of the native executable outside the app holds an inherited OS lock, waits for the parent to exit, backs up the complete app, runs the cask upgrade, verifies the installed version and starts the new app. Only the expected app path and version can acknowledge startup. A failed installation or startup triggers recovery; partial backups never replace the original. A restored app whose Homebrew receipt is newer uses reinstall on retry. Collection and AI actions in the updating app cannot overlap the update.

Backups live under the app data directory, outside the helper's temporary staging. Before replacement, the log and state files record the backup location, original destination and a shell-quoted reinstall command. A successful update or rollback removes that backup; an interrupted or failed recovery keeps it. ZIP and source builds update manually.

## UI layout

The toolbar has three views: **Structure**, **What it does** (feature groups, screen map, connections and data) and **Changes**. Internal view names (`sys`, `feat`, `map`, `focus`, `changes`) and app-control `navigate` values are unchanged. The internal `dev`/`main` keys hold the configured analyzed and compared refs and never imply deployment state. Search uses the same target list as app control (`controlTargets`) and opens results through the same function as agent selection. All AI requests start from one **AI analysis** pane; a saved `system.ai` proposal is shown separately from the written system.

## Advanced configuration

The app edits repository paths, refs, source roots, API targets and shared-table mappings. No target database is queried or changed. The same configuration is available through `project.json` or `project.py configure`. For example, this fragment connects two table identities:

```json
{"shared_data":[{"id":"workspace","members":[{"repository":"api","table":"settings"},{"repository":"worker","table":"settings"}]}]}
```

Use existing repository IDs in the members. Pass the complete project configuration to `project.py configure PROJECT` on standard input; the fragment alone does not replace a complete configuration. Shared identities are user assertions, not proof of a shared database.

## Not covered by tests

Real company repositories, production systems, end-to-end sessions in individual MCP clients and real AI model calls are not tested; AI tests use synthetic agent-submitted JSON. The macOS app is ad-hoc signed without Developer ID signing or notarization, so Gatekeeper approval at an installed path is not verified.
