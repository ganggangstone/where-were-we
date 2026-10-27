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

1. Open the app. The **Getting started** guide opens on a new install (reopen it from **Menu → Getting started**).
2. **Ask your AI to connect your service:** copy the one request into the coding AI chat you build the service with (Claude Code, Codex or another MCP-compatible agent). That single request covers the connection, the service's code, the first map and the first AI analysis. Your AI asks before it changes its connection settings, and asks you once to confirm the code to save, the first collection and the first analysis. The analysis runs with your AI's own model, so its pricing and usage limits apply; you can decline it and keep the map. You do not copy a second request.
3. In **Connected code**, check each code's location and whether its map is ready. Use **Edit connected code** to fix a saved service; use **Enter the code location myself** only to enter a service yourself (**＋ Add another service** for a further service).
4. **First analysis** is the last step. It is finished only when every code has a saved AI analysis in the app's language for its current version; a basic map alone is not. When your AI is done, return to the app: it reads the saved results by itself (or click **Read saved results**) and **View the analysis** opens the analyzed structure. If only part was saved, the step says so and **Create a request for the remaining analysis** continues it. If your AI needs a new session for its tools, it stops and tells you; what it already saved is kept.
5. If you connect without the one request, GitHub connections collect their first map when connected, and for a local folder you click **Refresh**. Once newly connected code has its first map, **Detail the map with AI** opens with the first analysis request ready to copy. There is no framework or code-location step: the app finds screens, server requests and data by reading the code, and the analysis reads the actual source at the collected commit.

With two or more code connections, **All code** in the top selector shows every connected code on one map; choosing one code shows only its screens while its configured server links stay. Choose each one's **Server called by this code** in **Add or edit code** if you know it. This only links them on the map; matching addresses alone do not link different code, and when the app shows candidates you can confirm them with **Link on map**.

GitHub connections follow the remote default branch. Local folders use committed code. Choose other branches or tags under **Map version** when needed. The two **Map version** buttons in the toolbar are labelled with the actual branch or tag names. They compare code, not deployment state.

In **Menu → Settings**, select when the change comparison should start. Settings apply to all services; **Save and refresh** applies them right away. With **Since the previous refresh**, the next refresh compares changes since this refresh; a specific date and time stays fixed until you change it. **Refresh when opening a service** also runs when you switch to another service.

The app starts in Korean. Choose **English** in the **Menu** to save your language preference.

## Use your AI agent

Click **Menu → Connect your AI** and copy the instructions into Claude Code, Codex or another MCP-compatible agent. It sets up the connection and adds usage rules to its global instructions, asking before it changes anything.

With the app open, try: **“Show me the upload retry feature in where-were-we.”** Your agent can find and highlight it, and read what you select in the app. Ask it to consult the map before planning or editing to find affected areas and overlapping work.

For a closer look, choose **Detail the map with AI → Request all needed analysis**. One request covers the detailed map, architecture and program jobs, screen groups, action steps, and change explanations. Current saved results are reused.

1. Copy the request.
2. Paste it into your coding AI chat and let it analyze the code and save its results.
3. Return to the app when your AI is done: it reads the saved results by itself (**Check results** reads them on demand). After browsing elsewhere, **Detail the map with AI · waiting for result check** reopens the same request.

Reading saved results preserves **Changes** and its comparison baseline. Your connected AI runs the analysis and its pricing and usage limits apply; ordinary refresh does not run AI analysis.

If tools are missing after an update, open **Connection diagnostics**, copy the repair request to your AI, and click **Check the connection** after it reconnects. You may need a new agent session.

## Explore the map

The three toolbar views are **Structure · What it does · Changes**. **What it does** contains **Features · Screen map · Connections & data**. Search works in every view and finds screens, endpoints, programs, data, features, and PR or issue numbers linked to screens.

### Changes

See changed screens and requests, merged PRs and explanations of what changed and why. Choose **Explain what changed**, paste the request into your AI chat, then return to the app to see the result. These actions keep your comparison baseline unchanged.

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

- **Features:** in **What it does → Features**, group screens by purpose and follow connections across features. Choosing a feature shows its screens, server requests, and linked open work, PRs merged in the last 7 days, branches, work folders, and issues; **Copy feature** copies them for your AI. **Show on the screen map** keeps the whole map and highlights that feature's screens; when you pick a screen, or open a request or data in **Connections & data**, its details show how it relates to the feature, with **‹ Feature overview** and **Clear feature**. Beyond the first eight requests, the rest open from **more**. [Screenshot](docs/images/en/features.png)
- **Connections & data:** in **What it does → Connections & data**, focus on one screen or request and see its callers, data, and external services. [Screenshot](docs/images/en/connections.png)
- **Workers and copied code:** inspect background jobs, directly accessed data, copied files that differ from the source branch, and unverified operational details. [Screenshot](docs/images/en/worker.png)
- **Find missing test links:** **Ask your AI to find tests** copies a request for your AI to locate tests and register repeatable patterns or individual verified lines; it may refresh to check them. Missing links do not establish that tests are absent. [Screenshot](docs/images/en/tests.png)
- **Connect your AI:** in **Menu → Connect your AI**, generate MCP registration instructions for the installed runtime. Ask the agent to show proposed configuration edits and request permission. [Screenshot](docs/images/en/agent-setup.png)
- **Version & updates:** in **Menu → Version & updates**, view the installed version, stable releases, and bilingual notes; install Homebrew updates with **Update now**. [Screenshot](docs/images/en/updates.png)
- **Map gaps:** server requests with no mapped screen ([screenshot](docs/images/en/orphan-requests.png)), requests whose destination cannot be resolved ([screenshot](docs/images/en/unresolved-requests.png)), issues with no screen link ([screenshot](docs/images/en/unlinked-issues.png)), and screens and requests removed since the previous map ([screenshot](docs/images/en/removed-items.png)).
- **Search:** find screens, features, programs, data, PRs and issues from any view once a service has a map. [Screenshot](docs/images/en/search.png)

## Connection help

- **Collection failed:** use **Change GitHub account** to select a saved login and retry. Each code connection remembers its own account; the previous successful map stays available if a refresh fails.
- **Several repositories use one database:** map their table names under **Add or edit code → When repositories share a database**. Equal table names alone do not connect them.
- **A request belongs to another repository:** choose it under **Server called by this code** in **Add or edit code**.
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

**v0.7.0 release notes**

<!-- release-notes:start -->
### 한국어

- 요청 하나로 연결, 서비스 코드 확인, 첫 지도, 첫 AI 분석까지 이어지고, 시작 안내의 마지막 단계는 모든 코드의 첫 분석 저장입니다.
- AI가 끝난 뒤 앱으로 돌아오면 저장된 결과를 스스로 읽고, 일부만 저장됐으면 남은 분석 요청을 이어서 만듭니다.
- 기능을 고르면 지도 전체는 그대로 두고 그 기능의 화면만 강조하며, 고른 화면과 서버 기능의 상세에 그 기능과의 관계를 보여 줍니다.
- 코드가 둘 이상이면 **모든 코드**로 전체를 한 지도에서 보고, 코드 하나를 고르면 그 화면만 보면서 서버 연결은 유지합니다.
- 화면 이름을 **AI로 자세한 지도 만들기**, **코드 추가·수정**처럼 하는 일에 맞게 바꿨습니다.

### English

- One request now carries a connection through the service's code, the first map and the first AI analysis; the last start step is saving the first analysis for every code.
- When your AI is done, returning to the app reads the saved results by itself, and a partly saved analysis continues with a request for the remaining part.
- Choosing a feature keeps the whole map and highlights that feature's screens, and a picked screen or request shows how it relates to the feature.
- With several codes, **All code** shows everything on one map; choosing one code shows only its screens while server links stay.
- Screens are renamed to match what they do, such as **Detail the map with AI** and **Add or edit code**.
<!-- release-notes:end -->


[All releases](https://github.com/ganggangstone/where-were-we/releases) · [Configuration and implementation](docs/MULTI_REPO_SPEC.md)
