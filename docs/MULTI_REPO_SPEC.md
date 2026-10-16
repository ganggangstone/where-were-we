# Multiple repositories in one project

Status: implemented and verified locally for 0.2.0; not released. Decision: collect repositories independently, then compose one project view (A). This keeps successful repositories usable when another repository is unavailable. A single analysis of every checkout was considered; it couples refreshes and failure recovery.

## User behavior

- Create a project with one repository; add related repositories without replacing earlier maps. Use the app to register repositories and choose all repositories or one repository.
- Each repository has a stable ID, a local checkout, development/production refs, and frontend/backend source roots. A role may be absent; two roles may intentionally use the same ref. Frontend-only, backend-only and general repositories are valid. Unsupported frameworks remain unsupported; missing configured roots are reported.
- Show repository names on screens, requests, GitHub work and evidence. Preserve original paths separately from internal identifiers. Equal screen paths, function/file names, PR/issue numbers, and table names in different repositories remain distinct. Mobile folding and common-component detection remain local to each repository.
- Automatic cross-repository HTTP matches are candidates. Only an explicitly configured API destination can connect matching mounted requests; ambiguous matches stay candidates. Mark configured connections as configured, never as code-proven. Tables are separate unless explicitly mapped to a shared data ID.
- Refresh all repositories or one. Preserve the last complete successful snapshot on fetch, extraction, GitHub, or publication failure. Show last attempt, last success, error and retained commit per repository. A first failure is not an empty success. Serialize refresh/configuration/AI/test writes with a project lock. Publish completed repository snapshots atomically.
- Changing refs/layout starts a new comparison baseline rather than reporting all old items as deleted. Unregistering a repository keeps its stored snapshots. Existing single-repository files remain readable and are preserved on adoption.
- UI and MCP read the same composed snapshot. Repository selection has stable IDs and cannot be overwritten by older asynchronous responses. Cross-repository dependencies remain visible with their source repository.
- AI actions and test-rule/evidence writes require an explicit repository in a multi-repository project. Existing single-repository calls keep working. Test evidence is checked against that repository's recorded commit. Ambiguous MCP targets return choices rather than silently selecting the first.

## Storage and implementation

`project.json` describes the project and its repositories. Each repository retains the current JSON formats in its own immutable generation. A single atomic repository-state file selects successful generations and reports attempts. Failed or interrupted generations never replace the selected successful generation. Legacy files are referenced in place until a successful new generation exists.

`project.py` owns validation, registration, locking, snapshot publication, composition and command dispatch. `mapcore.py` and the Tauri bridge consume its bundle reader; they do not implement separate composition rules. The composed compatibility view uses repository-qualified internal keys and retains `repository` and `source_*` fields for original paths. It also includes repository metadata and HTTP candidate/configuration provenance. A filter changes the visible source screens/work while retaining their dependency targets.

Refs and layout are passed to the existing collectors through an explicit child environment. GitHub failures are errors, not empty lists. Source readers accept absent application halves. No target checkout, branch, worktree or working file is changed; collection may run `git fetch`.

The packaged backend allowlist must include `project.py`. Python source/layout/test rules participate in extraction invalidation. The UI offers project/repository setup, repository selection, status and qualified evidence links in Korean and English. MCP tools accept an optional repository scope and share the UI's results.

## Completion evidence

| Condition | Required check | Result |
|---|---|---|
| Four repositories, frontend/backend separation | Synthetic collection and composed requests | Passed: actual isolated collectors with four synthetic repositories; separated frontend/API request composition |
| Duplicate paths, tables, PR/issue numbers | Independent IDs and scoped queries | Passed: duplicate screen/file/PR/table keys, mobile paths, repository-scoped MCP lookup |
| Cross-repository calls | Configured unique target, unconfigured candidate, ambiguous target | Passed: only a unique configured target connects; other matches remain candidates |
| Per-repository refs/layout | Actual collector execution with synthetic git/GitHub responses | Passed: custom refs/roots, pinned commit reads, main-only and general repositories |
| Failure and interruption | Last success preserved; first failure exposed; lock contention | Passed: fetch/GitHub/publication failure, interrupted attempt, serialized settings/actions/test writes |
| Legacy and configuration changes | Original files preserved; ref change baseline reset | Passed: adoption and unregister retain files; configuration fingerprint resets the comparison baseline |
| UI/MCP scope and writes | Same read bundle; selection race; explicit write target | Passed: MCP scoped lookup/rules/evidence; browser repository selection, late-response protection and API-repository step dispatch |
| Installed runtime | Rebuilt bundle includes source; relocated MCP multi-repo read | Passed: all 10 bundled backend files match source; relocated runtime performs actual MCP reads with four synthetic repositories |

Validation uses 20 multi-repository regression tests, 10 packaging tests (including the built runtime), five Rust tests, the design-token checker, and browser checks for projects, language and updates. The collector integration executes the actual Python collectors with temporary synthetic git/GitHub responses. Browser checks mock the native bridge; the relocated-runtime check uses the real MCP protocol. A mutation restoring the former mobile-key collision makes its regression test fail.

Real company repositories, production systems, private project maps, live AI generation, and complete native-window interaction were not tested. The ARM macOS app was built locally as 0.2.0 without signing or notarization. The published release, Homebrew cask and installed app remain 0.1.0. Existing release files were not replaced.

Atomic publication applies to configured projects. Legacy files remain readable; adopt them into a configured project to use the new per-repository transactions. Repository refreshes have independent commit/timestamp boundaries, so a composed view is not a simultaneous snapshot across repositories.

## Advanced configuration

The app edits repository paths, refs, source roots and API targets. Shared-table mappings are configured through `project.json` or `project.py configure`; they do not have a dedicated UI editor. For example, this fragment explicitly connects the two table identities:

```json
{"shared_data":[{"id":"workspace","members":[{"repository":"api","table":"settings"},{"repository":"worker","table":"settings"}]}]}
```

Use existing repository IDs in the members. Pass the complete project configuration to `project.py configure PROJECT` on standard input; the fragment alone does not replace a complete configuration. Shared identities are user assertions, not proof of a shared database.
