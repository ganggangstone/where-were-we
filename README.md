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

1. Open the app, click **Create project** (the **＋** in the toolbar), and enter a project name and a GitHub URL or local code folder.
2. Use **Manage code** to add the project's other code. Choose **All code** to see it together. With two or more connections, choose each one's **Server code receiving requests**. Without that choice, matching addresses do not connect different code; when the app shows connection candidates, confirm them with **Connect to this server**.
3. GitHub connections collect their first map automatically. For a local folder, click **Refresh**.

GitHub connections follow the remote default branch. Local folders use committed code. Choose other branches or tags under **Code versions to analyze** when needed. The toolbar version buttons show the **Analyzed** and **Compared** versions by their actual branch or tag names. They compare code, not deployment state.

In **Menu → Settings**, select when the change comparison should start. Settings apply to all projects; **Save and refresh** applies them right away. A specific date and time stays fixed across refreshes until you change it.

The app starts in Korean. Choose **English** in the **Menu** to save your language preference.

## Use your AI agent

Click **Menu → Connect agent** and copy the instructions into Claude Code, Codex or another MCP-compatible agent. It will ask before changing its connection settings.

With the app open, try: **“Show me the upload retry feature in where-were-we.”** Your agent can find and highlight it, and read what you select in the app. Ask it to consult the map before planning or editing to find affected areas and overlapping work.

For a more detailed map or other languages and frameworks, choose **AI analysis**, then the code and the kind of analysis (code analysis, system, screen groups, or change explanations). When **All code** is selected, choose the code first:

1. Copy the request into your connected agent's chat.
2. Let the agent analyze the code and save its results.
3. Click **Check saved results** in the app. After browsing elsewhere, **AI analysis · waiting for result check** reopens the same request.

Reading saved results preserves **Changes** and its comparison baseline. AI analysis uses your agent's account and plan; ordinary refresh does not run AI analysis.

If tools are missing after an update, open **Connection diagnostics**, copy the repair request to your agent, and click **Check current connection** after it reconnects. You may need a new agent session.

## Explore the map

The three toolbar views are **Structure · What it does · Changes**. **What it does** contains **Features · Screen map · Connections & data**. Search works in every view and finds screens, endpoints, programs, data, features, and PR or issue numbers linked to screens.

### Changes

See changed screens and requests, merged PRs and explanations of what changed and why. Choose **Request change explanations**, send the request to your agent, then **Check saved results**. These actions keep your comparison baseline unchanged.

![Changes: fictional Lumen Studio](docs/images/en/changes.png)

### Structure

Programs, queues, shared data, providers, and things that require access to the running system.

![Structure: fictional Lumen Studio](docs/images/en/overview.png)

An AI proposal saved by your agent never replaces the written structure. Choose **AI proposal** to view it separately.

### Screen map and ongoing work

In **What it does → Screen map**, see requests, tests, differences between the analyzed and compared versions, overlapping PRs, branches without PRs, local work folders, and linked issues.

![Screen map and ongoing work: fictional Lumen Studio](docs/images/en/screen-map.png)

### Follow a request

Step through cancellation, provider calls, status changes, and credit release. Background work is distinguished from the request itself.

![Follow a request: fictional Lumen Studio](docs/images/en/request-flow.png)

### Shared data impact

Find screens and workers touching the same data.

![Shared data impact: fictional Lumen Studio](docs/images/en/data-impact.png)

### More views

Each item links to a screenshot of the same fictional project.

- **Features:** in **What it does → Features**, group screens by purpose and follow connections across features. [Screenshot](docs/images/en/features.png)
- **Connections & data:** in **What it does → Connections & data**, focus on one screen or request and see its callers, data, and external services. [Screenshot](docs/images/en/connections.png)
- **Workers and copied code:** inspect background jobs, directly accessed data, copied files that differ from the source branch, and unverified operational details. [Screenshot](docs/images/en/worker.png)
- **Find missing test links:** copy a prompt for an agent to locate tests and register repeatable patterns or individual verified lines. Missing links do not establish that tests are absent. [Screenshot](docs/images/en/tests.png)
- **Connect your agent:** in **Menu → Connect agent**, generate MCP registration instructions for the installed runtime. Ask the agent to show proposed configuration edits and request permission. [Screenshot](docs/images/en/agent-setup.png)
- **Version & updates:** in **Menu → Version & updates**, view the installed version, stable releases, and bilingual notes; install Homebrew updates with **Update now**. [Screenshot](docs/images/en/updates.png)
- **Map gaps:** server requests with no mapped screen ([screenshot](docs/images/en/orphan-requests.png)), requests whose destination cannot be resolved ([screenshot](docs/images/en/unresolved-requests.png)), issues with no screen link ([screenshot](docs/images/en/unlinked-issues.png)), and screens and requests removed since the previous map ([screenshot](docs/images/en/removed-items.png)).
- **Search:** find screens, actions, requests, PRs, and issues from any view. [Screenshot](docs/images/en/search.png)

## Connection help

- **Collection failed:** use **Change GitHub account** to select a saved login and retry. Each code connection remembers its own account; the previous successful map stays available if a refresh fails.
- **Several repositories use one database:** map their table names under **Manage code → When code folders share the same data**. Equal table names alone do not connect them.
- **A request belongs to another repository:** choose its receiving server under **Server code receiving requests** in **Manage code**.
- **Disconnecting code:** the downloaded code and saved maps remain on your Mac.

## Updates

Open **Menu → Version & updates** and click **Update now** for Homebrew installations. **View update** in the new-version banner only opens this window. The app closes and reopens after installation; saved maps remain in place. Reconnect your agent's MCP afterward.

To update from a terminal:

```sh
brew update && brew upgrade --cask ganggangstone/tap/where-were-we
```

The app can notify you of new versions. Automatic checks can be turned off in **Menu → Version & updates**. For ZIP installations, download the latest ZIP from [Releases](https://github.com/ganggangstone/where-were-we/releases/latest).

**If an update is interrupted**

The updater attempts to restore the previous app after an installation or startup failure. If recovery is interrupted, open the recovery log:

```sh
open -a TextEdit ~/.where-were-we/.app-update.log
```

It shows the backup location and reinstall command. Restore the backup with Finder or follow that command.


## Your data and analysis coverage

- Maps and downloaded code stay under `~/.where-were-we/`. They describe your project; keep them out of public repositories.
- Collection reads code, Git history and GitHub activity. It fetches updates without switching branches or changing your source files.
- AI analysis provides source code to your connected agent. Its data handling follows the agent/provider settings you choose.
- Automatic extraction supports React Router/axios, FastAPI and SQLAlchemy. Use agent analysis for other languages and frameworks. Check the displayed coverage, unresolved areas and source evidence when interpreting results.
- Branch comparisons describe code, not what is deployed or verified in a running system.

## Contributing and license

Report bugs or suggest improvements in [Issues](https://github.com/ganggangstone/where-were-we/issues). Pull requests are welcome; discuss substantial changes before implementation.

The [license](LICENSE) permits personal use, internal business use, and free redistribution under its conditions. Paid products and external paid services are restricted. This is a custom source-available license; third-party components retain their own licenses.

**v0.4.0 release notes**

<!-- release-notes:start -->
### 한국어

- 상단 보기를 구조·하는 일·바뀐 것 세 가지로 정리했습니다. 기능 묶음·화면 지도·연결·데이터는 각 보기 안에서 고릅니다.
- 설정·언어·에이전트 연결·버전·업데이트를 메뉴 하나에 모았습니다.
- 운영·개발 대신 분석 버전과 비교 버전을 실제 브랜치·태그 이름으로 보여 줍니다.
- 분석 요청과 결과 확인 흐름을 단순하게 바꾸고, 일부만 끝난 결과와 진행 상황을 코드 범위마다 정확히 보여 줍니다. 새로고침이 겹쳐도 화면이 엇갈리지 않습니다.
- 코드 링크를 키보드로 찾아 열 수 있고, 누를 수 있는 항목은 누르면 반응합니다.
- 앱이 보여 주는 안내를 한국어와 영어로 모두 제공합니다.

### English

- The toolbar now has three views: Structure, What it does and Changes. Feature groups, screen map and connections/data are chosen inside each view.
- Settings, language, agent connection and version/updates are in one menu.
- Analyzed and compared versions are shown by their actual branch or tag names instead of production/development.
- Requesting analysis and reading its results is simpler; partial results and progress are shown accurately for each code scope, and overlapping refreshes no longer leave the screen inconsistent.
- Code links can be reached and opened from the keyboard, and clickable items respond when pressed.
- Messages shown by the app are available in both Korean and English.
<!-- release-notes:end -->


[All releases](https://github.com/ganggangstone/where-were-we/releases) · [Configuration and implementation](docs/MULTI_REPO_SPEC.md)
