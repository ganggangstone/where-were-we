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

Python is included. Homebrew installs git and GitHub CLI. [Claude Code](https://code.claude.com/docs/en/overview) must be installed separately for AI actions. The MCP host must be able to find git, gh, and (for AI actions) claude on its PATH.

**This initial build is unsigned and not notarized.** macOS may block its first launch; see Apple's [instructions for opening an app from an unidentified developer](https://support.apple.com/guide/mac-help/open-a-mac-app-from-an-unknown-developer-mh40616/mac).

### Create your first map

There is no project creation form yet. Quit the app first if it is open. Use a local checkout with `origin/dev`, `origin/main`, and the [supported layout](#data-and-limits), including `frontend/src/App.tsx` and `backend/app/main.py`. Run the bundled collector once, then choose the project in the app:

```sh
RUNTIME="/Applications/where-were-we.app/Contents/Resources/runtime"
"$RUNTIME/python/bin/python3" -I -B "$RUNTIME/backend/refresh.py" my-project /path/to/repository
open -a where-were-we
```

Replace `my-project` and `/path/to/repository` with your own values. The path above assumes the app is in `/Applications`. The collector reads both remote branches and GitHub activity; the refresh button subsequently updates the selected project. GitHub authentication must permit reading that repository.

The app starts in Korean. Choose **English** in the toolbar; the preference is saved locally. Interface text and newly requested agent/test prompts follow the selected language. Names, code, and AI explanations from your project stay verbatim.

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

View the installed version, stable releases, and bilingual notes; copy the Homebrew upgrade command.

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

Ask your agent to check `changes` before planning and `impact` before editing. It can use the same map to find affected areas and overlapping work.

## Updates

The app checks for new versions when opened, at most once per day. Use **Version & updates** to read release notes, check manually, or turn automatic checks off.

To upgrade, run:

```sh
brew update && brew upgrade --cask ganggangstone/tap/where-were-we
```

Run the command yourself to install an update. Uninstalling the app preserves your maps.

## Data and limits

- Maps stay in `~/.where-were-we/`. They contain your project's structure; keep them out of public repositories.
- The collector runs `git fetch` and reads local files, git history, GitHub activity, work folders, and available local Claude Code session metadata. It does not check out another branch or modify target repository files.
- Explicitly requested AI actions run your installed `claude -p`. Their input can include source snippets and screen information; processing and transmission follow that client's provider and settings.
- Detailed extraction currently assumes React Router, axios in `frontend/src/api`, FastAPI in `backend/app/routers`, and SQLAlchemy in `backend/app/models`. Other layouts require extractor changes. General structure/PR information is separate from detailed screen extraction.
- `dev` and `main` are code branch comparisons, not a check of what is actually deployed. Programs or runtime facts absent from git remain unverified until someone checks the running system.
- Read/write grouping uses HTTP methods (GET versus other methods). Missing test or navigation links can reflect an unrecognized pattern. AI explanations and candidate matches still need checking; a matching code quote does not establish that an explanation is correct.

## Contributing and license

Report bugs or suggest improvements in [Issues](https://github.com/ganggangstone/where-were-we/issues). Pull requests are welcome; discuss substantial changes before implementation.

The [license](LICENSE) permits personal use, internal business use, and free redistribution under its conditions. Paid products and external paid services are restricted. This is a custom source-available license; third-party components retain their own licenses.

<details>
<summary>v0.1.0 release notes</summary>

<!-- release-notes:start -->
### 한국어

- 서비스의 프로그램·화면·서버 요청·데이터와 연결된 PR·이슈를 지도에서 확인합니다.
- 한국어 기본 화면과 영어 전환을 지원하며 선택한 언어를 저장합니다. 프로젝트 원문은 유지합니다.
- macOS 앱에 Python과 MCP 실행 환경을 포함합니다. git·GitHub CLI와 AI 기능에 필요한 Claude Code는 별도로 필요합니다.
- 앱에서 새 버전과 한영 릴리즈 노트를 확인하고, Homebrew 업데이트 명령을 복사할 수 있습니다.

### English

- Explore programs, screens, server requests, data, and linked pull requests and issues in a local map.
- Start in Korean or switch to English; your language preference is saved and project content stays verbatim.
- The macOS app includes Python and MCP. Git, GitHub CLI, and Claude Code for AI actions remain external requirements.
- Check new versions and Korean/English release notes in the app, then copy the Homebrew upgrade command.
<!-- release-notes:end -->

</details>
