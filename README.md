# where-were-we

[English](README.md) · [한국어](README.ko.md)

A local code map for people and AI agents working on a service that keeps changing.

See how programs, screens, server requests, and data connect—and where ongoing GitHub work overlaps. Your agent reads the same map through MCP before planning and editing.

![Explore Lumen Studio from architecture to render cancellation and shared data](docs/images/en/demo.gif)

Screenshots use **Lumen Studio**, a fictional content creation platform. Maps, GitHub activity, AI explanations, and version information are sample data shown in the real UI.

## Install

Apple Silicon Mac, macOS 11 or newer, and [Homebrew](https://brew.sh/) are required. Download the ZIP directly from [Releases](https://github.com/ganggangstone/where-were-we/releases/latest) if preferred.

```sh
brew install --cask ganggangstone/tap/where-were-we
gh auth login
```

Python is included. Homebrew installs git and GitHub CLI. AI analysis, screen grouping, architecture, program jobs and request steps work through any MCP agent that supports tool calls; Claude Code is not required. The MCP server must be able to find git and gh on its PATH.

**This initial build is unsigned and not notarized.** macOS may block its first launch; see Apple's [instructions for opening an app from an unidentified developer](https://support.apple.com/guide/mac-help/open-a-mac-app-from-an-unknown-developer-mh40616/mac).

### Create your first map

Click **＋**, enter a service name, and paste a GitHub repository URL or a code folder on this computer. Names are filled automatically and can be edited. Add the service’s web, server, and worker repositories under **Manage code**; **All code** shows their combined map. A new GitHub connection downloads code to app storage and collects its first map. Existing local folders use **Refresh** after connecting.

GitHub URLs support `https://github.com/owner/repository`, the `.git` form, `git@github.com:owner/repository.git`, and `owner/repository`. The same URL can only be connected once per project. Downloads use local disk space. **Manage code** shows the storage location and remembered account. Disconnecting retains code and maps; reconnecting the same URL reuses the code. If downloading fails, select an available GitHub account and save again. If map collection fails after saving, use **Refresh** to retry.

GitHub connections follow the remote default branch (`origin/HEAD`) on each refresh. Local folder connections analyze committed code on the folder’s currently selected branch (`HEAD`). Under **Code versions to analyze**, choose another branch, tag or commit when needed; the comparison version is optional. Existing version settings are preserved. React Router frontends and FastAPI backends can live in separate repositories. The app detects `frontend/src` or `src`, and `backend/app` or `app`; set other source roots in repository settings. For other languages and frameworks, refresh first, select a repository, then choose **Request code analysis**. Copy the analysis request to your MCP-connected agent. That agent uses its own model to read the selected branch snapshot through MCP and submit a detailed map, including request steps. In the existing request pane, follow **Copy the request → Send it to your agent → Check saved results**. After the agent saves its output, **Check saved results** reads that analysis without collecting PRs or changing **What changed** or its comparison baseline. Copying a request does not start analysis. The pane distinguishes missing, previous, outdated, partially saved and newly saved results. The app validates and stores the result; it does not launch another model or pay for AI access. Matching source text verifies evidence, not the correctness of AI interpretations. Normal refresh does not call AI; changed code is marked as requiring analysis, and the previous AI map stays available. In **Settings**, choose whether to refresh on app open and compare changes since the previous refresh, your last commit in each repository, or a selected time. Refresh after saving to apply the baseline. A selected date and time stays fixed across refreshes until you change it in Settings.

Under **Specify server connections and code locations**, select the receiving server by its display name. Matching endpoints are labeled as user-configured connections. Unconfigured or ambiguous matches remain candidates. Equal table names stay separate unless explicitly assigned to shared data. Under **Manage code → When code folders share the same data**, connect the code folders and table names that use the same database tables. Shared-data identifiers are generated automatically. You can edit or remove connections there; collected table names are suggested. Repository collection failures preserve the last successful map and appear beside the repository's commit and last success time.

For github.com code, the app remembers the GitHub account at connection time (or the first refresh for existing projects). Changing the active account in another task does not change this connection. If collection fails, **Change GitHub account** lets you choose a saved login and retry. Tokens stay in GitHub CLI; only the account name is saved. HTTPS fetch uses that account; SSH fetch uses your configured SSH keys.

Existing projects remain available. Open **Manage code** to keep the original repository and add others without moving or deleting the old map files.

With the app open and MCP connected, ask your agent: “Show me the upload retry feature in where-were-we.” It can find matching targets, open the right project and code version, select and highlight a target, and read back the selection you make in the app. Ask it to clarify when names match more than one target. Navigation and result checks do not refresh change history. The agent can also use the app's configuration, comparison settings, analysis requests and update actions. Preparing an analysis request does not run a model; result submission uses the existing analysis MCP tools. Both the app and MCP server need this version. If a command is still queued or running, its command ID lets the agent check completion without repeating it. After an interruption, inspect the app state before retrying.

The app starts in Korean. Choose **English** in the toolbar; the preference is saved locally. Project names, code, and AI explanations stay verbatim.

## Explore the map

### What changed

New and removed screens, requests and navigation, merged PRs, and changed AI evidence. After a refresh preserves the supporting PR/issue text, choose **Request change explanations**, send the request to your MCP agent, then **Check saved results**. Problem cards explain the reason, before/after behavior, resolution, data impact, recovery, terms and unknowns with source quotes and links. Related PRs can share a card, and one PR can appear on multiple cards; distinct PRs are counted separately. PR evidence includes every base branch of a repository; structure uses the selected map version. Each repository’s exact comparison window is shown. Missing evidence, collection limits, failed collections and previous results stay visible. Merge, deployment and runtime verification are separate states. Requesting, saving and checking explanations do not refresh PRs or move your comparison baseline.

![What changed: fictional Lumen Studio](docs/images/en/changes.png)

### System overview

Programs, queues, shared data, providers, and things that require access to the running system.

![System overview: fictional Lumen Studio](docs/images/en/overview.png)

### Screen map and ongoing work

See requests, tests, dev/main differences, overlapping PRs, branches without PRs, local work folders, and linked issues.

![Screen map and ongoing work: fictional Lumen Studio](docs/images/en/screen-map.png)

### Follow a request

Step through cancellation, provider calls, status changes, and credit release. Background work is distinguished from the request itself.

![Follow a request: fictional Lumen Studio](docs/images/en/request-flow.png)

### Shared data impact

Find screens and workers touching the same data.

![Shared data impact: fictional Lumen Studio](docs/images/en/data-impact.png)

<details>
<summary>More screenshots</summary>

### Features

Group screens by purpose and follow connections across features.

![Features: fictional Lumen Studio](docs/images/en/features.png)

### Trace connections

Focus on one screen or request and see its callers, data, and external services.

![Trace connections: fictional Lumen Studio](docs/images/en/connections.png)

### Workers and copied code

Inspect background jobs, directly accessed data, copied files that differ from the source branch, and unverified operational details.

![Workers and copied code: fictional Lumen Studio](docs/images/en/worker.png)

### Find missing test links

Copy a prompt for an agent to locate tests and register repeatable patterns or individual verified lines. Missing links do not establish that tests are absent.

![Find missing test links: fictional Lumen Studio](docs/images/en/tests.png)

### Connect your agent

Generate MCP registration instructions for the installed runtime. Ask the agent to show proposed configuration edits and request permission.

![Connect your agent: fictional Lumen Studio](docs/images/en/agent-setup.png)

### Versions and updates

View the installed version, stable releases, and bilingual notes; install Homebrew updates with **Update now**.

![Versions and updates: fictional Lumen Studio](docs/images/en/updates.png)

**Server requests with no mapped screen**

![Server requests with no mapped screen](docs/images/en/orphan-requests.png)

**Requests whose destination cannot be resolved**

![Requests whose destination cannot be resolved](docs/images/en/unresolved-requests.png)

**Issues with no screen link**

![Issues with no screen link](docs/images/en/unlinked-issues.png)

**Screens and requests removed since the previous map**

![Screens and requests removed since the previous map](docs/images/en/removed-items.png)

**Search screens, actions, requests, PRs, and issues**

![Search screens, actions, requests, PRs, and issues](docs/images/en/search.png)

</details>

## Agent workflow

Click **Connect agent**, copy the instructions, and give them to Claude Code, Codex, or another MCP client. The agent asks permission before editing configuration.

If tools are missing, choose **Connection diagnostics**, select the feature, and copy the repair request to your agent. After it reconnects and calls the confirmation tool, click **Check current connection**. The app checks its own server separately; a healthy app server alone does not confirm your agent reconnected. Settings are not rewritten automatically.

Ask your agent to check `changes` before planning and `impact` before editing. It can use the same map to find affected areas and overlapping work. MCP tools accept a `repository` ID to narrow the scope; test-rule writes require a repository when the project has several.

## Updates

The app checks for new versions when opened, at most once per day. Use **Version & updates** to read release notes, check manually, or turn automatic checks off.

To upgrade, run:

```sh
brew update && brew upgrade --cask ganggangstone/tap/where-were-we
```

For Homebrew installations, click **Update now**. The app checks that the new version is available, closes, installs it through Homebrew, and reopens. Finish collection or AI work before updating. If installation or startup fails, the updater attempts to restore the previous app and shows the error; recovery files are retained if restoration fails. Maps remain in place.

If an update is interrupted by shutdown or force quit, recovery details remain in `~/.where-were-we/.app-update.log` and `.app-update.json`. Open the log with `open -a TextEdit ~/.where-were-we/.app-update.log`. It records the retained app copy and its original destination: copy it back with Finder and choose Replace, or run the recorded Homebrew reinstall command.

After updating, reconnect where-were-we in your agent. If new tools are still missing, start a new session. **Version & updates → Connection diagnostics** helps check old paths and connections still running older code.

The command above is the manual fallback, including for older versions that only offer command copying. A ZIP installation is not managed by the update button. Uninstalling the app preserves your maps.

## Data and limits

- Maps stay in `~/.where-were-we/`. They contain your project's structure; keep them out of public repositories.
- The collector runs `git fetch` and reads local files, git history, GitHub activity and work folders. It does not check out another branch or modify target repository files.
- Detailed analysis uses the connected MCP agent and its account. `analyze` returns the instructions and schema, `analysis_source` serves the pinned source, and `record_analysis` verifies and saves the result. After recording the detailed map, the same analysis request continues with architecture and program jobs through `request_ai_task` and `record_ai_task`. Architecture analysis saves what each program does alongside the structure. Select a program in the app to read its saved jobs directly; programs without results show an explicit empty state. Grouping and request-step actions also use the connected agent. Copy the request to the agent, then use **Check saved results** after it saves the result. This reads analysis without updating change history. Source processing follows the selected agent/provider settings.
- Automatic code extraction supports React Router/axios, FastAPI, and SQLAlchemy. Explicit AI analysis accepts source code in other languages and frameworks, subject to what the model can establish; it does not guarantee complete coverage. AI provenance, source checks, unresolved areas and changed-commit warnings remain visible. Source roots are configurable per repository. Collection status is separate from analysis scope: unrecognized or unresolved areas remain unverified, and disabled areas are labeled separately. Regression fixtures cover React Router → FastAPI → SQLAlchemy tables, and Vue → Go → tables with supplied AI JSON. These tests verify source checks and map connections; they do not measure a real model’s analysis accuracy.
- `dev` and `main` are code branch comparisons, not a check of what is actually deployed. Programs or runtime facts absent from git remain unverified until someone checks the running system.
- Read/write grouping uses HTTP methods (GET versus other methods). Missing test or navigation links can reflect an unrecognized pattern. AI explanations and candidate matches still need checking; a matching code quote does not establish that an explanation is correct.

## Contributing and license

Report bugs or suggest improvements in [Issues](https://github.com/ganggangstone/where-were-we/issues). Pull requests are welcome; discuss substantial changes before implementation.

The [license](LICENSE) permits personal use, internal business use, and free redistribution under its conditions. Paid products and external paid services are restricted. This is a custom source-available license; third-party components retain their own licenses.

<details>
<summary>v0.3.0 release notes</summary>

<!-- release-notes:start -->
### 한국어

- 코드 연결 화면을 쉬운 표현과 자동 입력으로 정리하고, 수집 성공과 실제 분석 범위를 구분했습니다.
- 코드 연결마다 GitHub 계정을 기억하며 인증 실패 시 해당 연결의 계정을 바꿀 수 있습니다.
- 저장된 분석 결과만 읽어 ‘바뀐 것’과 비교 기준을 유지합니다. 프로그램을 선택하면 저장된 하는 일을 바로 보여 줍니다.
- 바뀐 내용을 문제별로 설명하고 PR·이슈 근거, 전후 동작과 확인하지 못한 부분을 함께 보여 줍니다.
- GitHub 주소로 코드를 연결하면 앱 전용 위치에 내려받고 첫 지도를 수집합니다.
- MCP 에이전트가 실행 앱의 대상을 찾고 선택·강조하며 실제 선택 상태를 읽을 수 있습니다.
- 업데이트 후 연결 진단에서 앱 서버·등록 경로·현재 에이전트 연결을 구분하고, 재연결 여부를 확인합니다.
- 앱이 뒤에 있을 때도 MCP 명령에 응답하도록 보완했습니다.
- 앱 배포 파일에서 개발용 캐시를 제외했습니다.

### English

- Simplified code connection setup with clearer labels and automatic values, and separated collection success from analysis coverage.
- Remember a GitHub account for each code connection and switch that connection’s account after an authentication failure.
- Read saved analysis without changing change history or comparison settings. Select a program to read its saved jobs directly.
- Explain changes by problem, with PR/issue evidence, before-and-after behavior and unresolved questions.
- Connect a GitHub URL to download code into app-managed storage and collect its first map.
- Let MCP agents find, select and highlight targets in the running app and read back the actual selection.
- Diagnose the app server, registered paths and current agent connection separately, and verify reconnection after an update.
- Keep MCP commands responsive when the app window is in the background.
- Exclude development caches from app bundles.
<!-- release-notes:end -->

</details>

<details>
<summary>v0.2.1 release notes</summary>

### 한국어

- 기본 Tauri 아이콘을 where-were-we 전용 로고로 교체했습니다. 연결된 W 모양과 초록색 점으로 코드의 연결 관계와 돌아올 위치를 표현했습니다.

### English

- Replaced the default Tauri icon with a dedicated where-were-we logo. The connected W shape and green dot represent code connections and a place to resume work.

</details>

<details>
<summary>v0.2.0 release notes</summary>

### 한국어

- 한 프로젝트에 여러 레포를 연결하고 전체 또는 레포별 지도를 봅니다.
- 웹·API가 나뉜 레포와 서로 다른 브랜치·소스 폴더를 지원합니다.
- 레포별 수집 상태를 표시하고, 실패·중단 시 마지막 성공 지도를 유지합니다.
- 사용자가 지정한 API 연결과 미확인 후보를 구분합니다. 같은 경로·PR 번호·테이블 이름을 레포별로 구분합니다.
- MCP 조회와 테스트 기록에도 레포 범위를 지정할 수 있습니다. 기존 단일 레포 지도는 보존합니다.
- 설정 화면에서 여러 레포가 함께 쓰는 데이터 연결을 관리합니다.
- 상세 분석·화면 묶음·전체 구조·프로그램 작업·요청 단계를 연결된 MCP 에이전트로 만듭니다. 특정 AI CLI 설치가 필요하지 않습니다.
- 에이전트 세션 수집과 세션 재개 기능을 제거했습니다.
- Homebrew 설치본에서 버튼으로 업데이트하고 앱을 다시 엽니다. 실패 시 이전 앱 복구를 시도합니다.

### English

- Connect multiple repositories to one project and switch between service-wide and repository views.
- Collect split frontend/backend repositories with independent refs and source roots.
- Show collection status per repository and retain the last successful snapshot after failure or interruption.
- Distinguish user-configured API destinations from unverified candidates; keep equal paths, PR numbers, and table names separate.
- Scope MCP queries and test writes by repository while preserving existing single-repository maps.
- Manage shared data mappings across repositories in settings.
- Use your connected MCP agent for detailed maps, grouping, architecture, program jobs and request steps, without a provider-specific AI CLI.
- Remove agent session collection and session-resume controls.
- Install Homebrew updates from the app and reopen automatically, with recovery of the previous app on failure.

</details>

Implementation and configuration details: [multi-repository specification](docs/MULTI_REPO_SPEC.md).
