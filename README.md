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

Click **＋** to create a project and add a local repository folder. Add related repositories under **Manage repositories**. Use **All repositories** for the service view, or select one repository to narrow it down.

Each repository can use its own development and production refs; leave a role empty when it does not exist. React Router frontends and FastAPI backends can live in separate repositories. The app detects `frontend/src` or `src`, and `backend/app` or `app`; set other source roots in repository settings. For other languages and frameworks, refresh first, select a repository, then choose **Analyze with AI**. Copy the analysis request to your MCP-connected agent. That agent uses its own model to read the selected branch snapshot through MCP and submit a detailed map, including request steps. The app validates and stores the result; it does not launch another model or pay for AI access. Matching source text verifies evidence, not the correctness of AI interpretations. Normal refresh does not call AI; changed code is marked as requiring analysis, and the previous AI map stays available.

Use **API destination repositories** to explicitly identify a frontend's API repository. Matching endpoints are labeled as user-configured connections. Unconfigured or ambiguous matches remain candidates. Equal table names stay separate unless explicitly assigned to shared data. In **Manage repositories → Shared data settings**, add a shared data ID and connect the repository/table pairs. You can edit or remove connections there; collected table names are suggested. Repository collection failures preserve the last successful map and appear beside the repository's commit and last success time.

Existing projects remain available. Open **Manage repositories** to keep the original repository and add others without moving or deleting the old map files.

The app starts in Korean. Choose **English** in the toolbar; the preference is saved locally. Project names, code, and AI explanations stay verbatim.

## Explore the map

### What changed

New and removed screens, requests and navigation, merged PRs, and changed AI evidence.

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

Ask your agent to check `changes` before planning and `impact` before editing. It can use the same map to find affected areas and overlapping work. MCP tools accept a `repository` ID to narrow the scope; test-rule writes require a repository when the project has several.

## Updates

The app checks for new versions when opened, at most once per day. Use **Version & updates** to read release notes, check manually, or turn automatic checks off.

To upgrade, run:

```sh
brew update && brew upgrade --cask ganggangstone/tap/where-were-we
```

For Homebrew installations, click **Update now**. The app checks that the new version is available, closes, installs it through Homebrew, and reopens. Finish collection or AI work before updating. If installation or startup fails, the updater attempts to restore the previous app and shows the error; recovery files are retained if restoration fails. Maps remain in place.

If an update is interrupted by shutdown or force quit, recovery details remain in `~/.where-were-we/.app-update.log` and `.app-update.json`. Open the log with `open -a TextEdit ~/.where-were-we/.app-update.log`. It records the retained app copy and its original destination: copy it back with Finder and choose Replace, or run the recorded Homebrew reinstall command.

The command above is the manual fallback, including for older versions that only offer command copying. A ZIP installation is not managed by the update button. Uninstalling the app preserves your maps.

## Data and limits

- Maps stay in `~/.where-were-we/`. They contain your project's structure; keep them out of public repositories.
- The collector runs `git fetch` and reads local files, git history, GitHub activity, work folders, and available local Claude Code session metadata. It does not check out another branch or modify target repository files.
- Detailed analysis uses the connected MCP agent and its account. `analyze` returns the instructions and schema, `analysis_source` serves the pinned source, and `record_analysis` verifies and saves the result. Grouping, architecture, program jobs and request-step buttons prepare requests for the same connected agent through `request_ai_task` and `record_ai_task`. Copy the request to the agent, then refresh the app after it saves the result. Source processing follows the selected agent/provider settings.
- Automatic code extraction supports React Router/axios, FastAPI, and SQLAlchemy. Explicit AI analysis accepts source code in other languages and frameworks, subject to what the model can establish; it does not guarantee complete coverage. AI provenance, source checks, unresolved areas and changed-commit warnings remain visible. Source roots are configurable per repository.
- `dev` and `main` are code branch comparisons, not a check of what is actually deployed. Programs or runtime facts absent from git remain unverified until someone checks the running system.
- Read/write grouping uses HTTP methods (GET versus other methods). Missing test or navigation links can reflect an unrecognized pattern. AI explanations and candidate matches still need checking; a matching code quote does not establish that an explanation is correct.

## Contributing and license

Report bugs or suggest improvements in [Issues](https://github.com/ganggangstone/where-were-we/issues). Pull requests are welcome; discuss substantial changes before implementation.

The [license](LICENSE) permits personal use, internal business use, and free redistribution under its conditions. Paid products and external paid services are restricted. This is a custom source-available license; third-party components retain their own licenses.

<details>
<summary>v0.2.0 release notes (unreleased)</summary>

<!-- release-notes:start -->
### 한국어

- 한 프로젝트에 여러 레포를 연결하고 전체 또는 레포별 지도를 봅니다.
- 웹·API가 나뉜 레포와 서로 다른 브랜치·소스 폴더를 지원합니다.
- 레포별 수집 상태를 표시하고, 실패·중단 시 마지막 성공 지도를 유지합니다.
- 사용자가 지정한 API 연결과 미확인 후보를 구분합니다. 같은 경로·PR 번호·테이블 이름을 레포별로 구분합니다.
- MCP 조회와 테스트 기록에도 레포 범위를 지정할 수 있습니다. 기존 단일 레포 지도는 보존합니다.
- Homebrew 설치본에서 버튼으로 업데이트하고 앱을 다시 엽니다. 실패 시 이전 앱 복구를 시도합니다.

### English

- Connect multiple repositories to one project and switch between service-wide and repository views.
- Collect split frontend/backend repositories with independent refs and source roots.
- Show collection status per repository and retain the last successful snapshot after failure or interruption.
- Distinguish user-configured API destinations from unverified candidates; keep equal paths, PR numbers, and table names separate.
- Scope MCP queries and test writes by repository while preserving existing single-repository maps.
- Install Homebrew updates from the app and reopen automatically, with recovery of the previous app on failure.
<!-- release-notes:end -->

</details>

Implementation and configuration details: [multi-repository specification](docs/MULTI_REPO_SPEC.md).
