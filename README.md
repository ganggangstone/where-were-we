# where-were-we

[English](README.md) · [한국어](README.ko.md)

Explore your codebase with visual architecture maps, change tracking, and impact analysis. Available as a local desktop app and MCP server for AI agents.

Connect several repositories to one project to explore their screens, server requests, programs and shared data. Your AI agent can read the same map and highlight what you are discussing in the app.

![Explore Lumen Studio from architecture to render cancellation and shared data](docs/images/en/demo.gif)

Screenshots show the real app with fictional **Lumen Studio** data.

## Install

Requires an Apple Silicon Mac and macOS 11 or later.

```sh
brew install --cask ganggangstone/tap/where-were-we
gh auth login
```

[Homebrew](https://brew.sh/) installs the required Git and GitHub CLI. You can also download the app from [Releases](https://github.com/ganggangstone/where-were-we/releases/latest); ZIP installations need Git and GitHub CLI installed separately.

The app does not have Apple Developer ID signing or notarization. If macOS blocks its first launch, follow Apple's [instructions for opening an app from an unidentified developer](https://support.apple.com/guide/mac-help/open-a-mac-app-from-an-unknown-developer-mh40616/mac).

## Get started

1. Open the app, click **＋**, and enter a project name and a GitHub URL or local code folder.
2. Use **Manage code** to add the project's other repositories. Choose **All code** to see them together.
3. GitHub connections collect their first map automatically. For a local folder, click **Refresh**.

GitHub connections follow the remote default branch. Local folders use committed code. Choose other branches or tags under **Code versions to analyze** when needed.

In **Settings**, select when the change comparison should start. A specific date and time stays fixed across refreshes until you change it.

The app starts in Korean. Choose **English** in the toolbar to save your language preference.

## Use your AI agent

Click **Connect agent** and copy the instructions into Claude Code, Codex or another MCP-compatible agent. It will ask before changing its connection settings.

With the app open, try: **“Show me the upload retry feature in where-were-we.”** Your agent can find and highlight it, and read what you select in the app. Ask it to consult the map before planning or editing to find affected areas and overlapping work.

For a more detailed map or other languages and frameworks, select a repository and choose **Request code analysis**:

1. Copy the request into your connected agent's chat.
2. Let the agent analyze the code and save its results.
3. Click **Check saved results** in the app.

Reading saved results preserves **What changed** and its comparison baseline. AI analysis uses your agent's account and plan; ordinary refresh does not run AI analysis.

If tools are missing after an update, open **Connection diagnostics**, copy the repair request to your agent, and click **Check current connection** after it reconnects. You may need a new agent session.

## Explore the map

### What changed

See changed screens and requests, merged PRs and explanations of what changed and why. Choose **Request change explanations**, send the request to your agent, then **Check saved results**. These actions keep your comparison baseline unchanged.

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

## Connection help

- **Collection failed:** use **Change GitHub account** to select a saved login and retry. Each code connection remembers its own account; the previous successful map stays available if a refresh fails.
- **Several repositories use one database:** map their table names under **Manage code → When code folders share the same data**. Equal table names alone do not connect them.
- **A request belongs to another repository:** choose its receiving server under **Specify server connections and code locations**.
- **Disconnecting code:** the downloaded code and saved maps remain on your Mac.

## Updates

Open **Version & updates** and click **Update now** for Homebrew installations. The app closes and reopens after installation; saved maps remain in place. Reconnect your agent's MCP afterward.

To update from a terminal:

```sh
brew update && brew upgrade --cask ganggangstone/tap/where-were-we
```

The app can notify you of new versions. Automatic checks can be turned off in **Version & updates**. For ZIP installations, download the latest ZIP from [Releases](https://github.com/ganggangstone/where-were-we/releases/latest).

<details>
<summary>If an update is interrupted</summary>

The updater attempts to restore the previous app after an installation or startup failure. If recovery is interrupted, open the recovery log:

```sh
open -a TextEdit ~/.where-were-we/.app-update.log
```

It shows the backup location and reinstall command. Restore the backup with Finder or follow that command.

</details>

## Your data and analysis coverage

- Maps and downloaded code stay under `~/.where-were-we/`. They describe your project; keep them out of public repositories.
- Collection reads code, Git history and GitHub activity. It fetches updates without switching branches or changing your source files.
- AI analysis provides source code to your connected agent. Its data handling follows the agent/provider settings you choose.
- Automatic extraction supports React Router/axios, FastAPI and SQLAlchemy. Use agent analysis for other languages and frameworks. Check the displayed coverage, unresolved areas and source evidence when interpreting results.
- Branch comparisons describe code, not what is deployed or verified in a running system.

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

[All releases](https://github.com/ganggangstone/where-were-we/releases) · [Configuration and implementation](docs/MULTI_REPO_SPEC.md)
