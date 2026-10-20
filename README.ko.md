# where-were-we

[English](README.md) · [한국어](README.ko.md)

서비스가 어떻게 이어지는지, 무엇이 바뀌었는지 보고 하던 일을 이어갑니다.

한 프로젝트에 여러 저장소를 연결해 화면·서버 요청·프로그램·공유 데이터를 함께 봅니다. AI 에이전트도 같은 지도를 읽고, 대화 중인 기능을 앱에서 찾아 표시할 수 있습니다.

![전체 구조에서 렌더 취소와 공유 데이터까지 따라가는 Lumen Studio 데모](docs/images/ko/demo.gif)

실제 앱에 가상 서비스 **Lumen Studio**의 데이터를 넣어 촬영했습니다.

## 설치

Apple Silicon Mac과 macOS 11 이상이 필요합니다.

```sh
brew install --cask ganggangstone/tap/where-were-we
gh auth login
```

[Homebrew](https://brew.sh/)가 필요한 Git과 GitHub CLI를 함께 설치합니다. [릴리즈](https://github.com/ganggangstone/where-were-we/releases/latest)에서 ZIP을 직접 받을 수도 있습니다. ZIP 설치에는 Git과 GitHub CLI가 별도로 필요합니다.

앱은 Apple의 개발자 서명·공증을 받지 않았습니다. macOS가 첫 실행을 막으면 Apple의 [확인되지 않은 개발자의 앱 열기 안내](https://support.apple.com/ko-kr/guide/mac-help/mh40616/mac)를 참고하세요.

## 시작하기

1. 앱에서 **프로젝트 만들기**(상단 **＋**)를 누르고 프로젝트 이름과 GitHub 주소 또는 이 컴퓨터의 코드 폴더를 입력하세요.
2. **코드 연결**에서 같은 프로젝트의 다른 코드를 추가하세요. **모든 코드**를 선택하면 함께 볼 수 있습니다. 코드가 둘 이상이면 각 코드의 **요청을 받는 서버 코드**를 고르세요. 고르지 않으면 주소가 같아도 서로 다른 코드를 잇지 않으며, 앱이 연결 후보를 보여 주면 확인한 뒤 **이 서버로 연결**을 누를 수 있습니다.
3. GitHub 주소를 연결하면 첫 지도를 자동으로 가져옵니다. 기존 폴더를 연결했다면 **새로고침**을 누르세요.

GitHub 연결은 원격 기본 브랜치를, 기존 폴더는 커밋된 코드를 읽습니다. 다른 브랜치나 태그를 보려면 **분석할 코드 버전**에서 선택하세요. 상단 버전 버튼은 **분석 버전**과 **비교 버전**을 실제 브랜치·태그 이름으로 보여 줍니다. 코드 존재 여부를 비교할 뿐 배포 상태를 뜻하지 않습니다.

**메뉴 → 설정**에서 언제부터 바뀐 내용을 볼지 정할 수 있습니다. 설정은 모든 프로젝트에 적용되며, **저장하고 새로고침**으로 바로 반영할 수 있습니다. 날짜·시각을 직접 지정하면 설정을 바꾸기 전까지 새로고침해도 기준이 유지됩니다.

앱은 한국어로 시작합니다. **메뉴**에서 **English**로 바꾸면 언어 선택을 저장합니다.

## AI 에이전트와 함께 쓰기

**메뉴 → 에이전트 연결**을 누르고 안내를 Claude Code·Codex 등 MCP를 지원하는 에이전트에 전달하세요. 에이전트가 연결 설정을 바꾸기 전에 허락을 구합니다.

앱을 열고 **“업로드 재시도 기능이 지도에서 어디인지 보여 줘”**라고 말해 보세요. 에이전트가 대상을 찾아 강조하고, 앱에서 직접 선택한 대상도 읽습니다. 계획하거나 수정하기 전에 지도를 확인해 영향받는 곳과 겹치는 작업을 살펴보도록 요청할 수 있습니다.

더 자세한 지도나 다른 언어·프레임워크의 분석이 필요하면 **AI 분석**을 누르고 분석할 코드와 종류(코드 분석·전체 구조·화면 묶음·변경 설명)를 고르세요. **모든 코드**를 보고 있으면 먼저 분석할 코드를 고릅니다.

1. 요청을 복사해 연결된 에이전트 채팅에 전달하세요.
2. 에이전트가 코드를 분석하고 결과를 저장할 때까지 기다리세요.
3. 앱에서 **저장된 결과 확인**을 누르세요. 다른 화면을 보다가 돌아올 때는 **AI 분석 · 결과 확인 대기** 버튼으로 같은 요청을 다시 엽니다.

저장된 결과를 읽어도 **바뀐 것**과 비교 기준은 유지됩니다. AI 분석은 사용하는 에이전트의 계정·요금제를 따릅니다. 일반 새로고침은 AI 분석을 실행하지 않습니다.

업데이트 뒤 도구가 보이지 않으면 **연결 진단**에서 수정 요청을 복사해 에이전트에 전달하세요. 재연결 후 **현재 연결 확인**을 누르세요. 에이전트의 새 세션이 필요할 수도 있습니다.

## 지도 둘러보기

상단의 세 보기 **구조 · 하는 일 · 바뀐 것**으로 서비스를 살펴봅니다. **하는 일** 안에서 **기능 묶음 · 화면 지도 · 연결·데이터**를 고릅니다. 상단 검색은 어느 보기에서든 화면·서버 기능·프로그램·데이터·기능과 화면에 이어진 PR·이슈 번호를 찾습니다.

### 바뀐 것

바뀐 화면·요청·병합 PR과 바꾼 이유를 봅니다. **변경 설명 요청**을 에이전트에 전달하고 **저장된 결과 확인**을 누르세요. 설명을 요청하거나 결과를 읽어도 비교 기준은 유지됩니다.

![바뀐 것: 가상 Lumen Studio](docs/images/ko/changes.png)

### 구조

프로그램·대기열·공유 데이터·외부 서비스와 실제 실행 환경에서 확인할 내용을 봅니다.

![구조: 가상 Lumen Studio](docs/images/ko/overview.png)

에이전트가 저장한 AI 제안은 직접 작성한 구조를 바꾸지 않습니다. **AI 제안**을 눌러 따로 볼 수 있습니다.

### 화면 지도와 진행 중인 작업

**하는 일 → 화면 지도**에서 서버 요청·테스트·분석 버전과 비교 버전의 차이, 겹치는 PR·PR 없는 브랜치·작업 폴더·연결된 이슈를 봅니다.

![화면 지도와 진행 중인 작업: 가상 Lumen Studio](docs/images/ko/screen-map.png)

### 요청 뒤의 순서

취소 요청·외부 호출·상태 변경·크레딧 반환을 따라갑니다. 이어지는 작업기의 일도 따로 표시합니다.

![요청 뒤의 순서: 가상 Lumen Studio](docs/images/ko/request-flow.png)

### 공유 데이터의 영향

같은 데이터를 쓰는 화면과 작업기를 찾습니다.

![공유 데이터의 영향: 가상 Lumen Studio](docs/images/ko/data-impact.png)

### 그 밖의 화면

항목마다 같은 가상 프로젝트의 화면 이미지를 링크했습니다.

- **기능 묶음:** **하는 일 → 기능 묶음**에서 화면을 하는 일로 묶고 기능 사이의 연결을 따라갑니다. [화면 보기](docs/images/ko/features.png)
- **연결·데이터:** **하는 일 → 연결·데이터**에서 화면이나 요청 하나를 가운데 두고 부르는 곳·데이터·외부 서비스를 봅니다. [화면 보기](docs/images/ko/connections.png)
- **작업기와 코드 사본:** 백그라운드 작업·직접 쓰는 데이터·원본 브랜치와 다른 코드 사본·운영 환경의 미확인 내용을 봅니다. [화면 보기](docs/images/ko/worker.png)
- **테스트 연결 찾기:** 에이전트가 테스트를 찾아 반복되는 규칙이나 개별 근거 줄을 등록하도록 안내를 복사합니다. 연결하지 못했다는 것이 테스트가 없다는 뜻은 아닙니다. [화면 보기](docs/images/ko/tests.png)
- **에이전트 연결:** **메뉴 → 에이전트 연결**에서 설치된 실행 환경에 맞는 MCP 연결 안내를 만듭니다. 에이전트가 설정 변경 내용을 먼저 보여 주고 허락을 받도록 안내합니다. [화면 보기](docs/images/ko/agent-setup.png)
- **버전·업데이트:** **메뉴 → 버전·업데이트**에서 설치 버전·최신 정식 릴리즈·한영 노트를 확인하고 **지금 업데이트**로 Homebrew 업데이트를 설치합니다. [화면 보기](docs/images/ko/updates.png)
- **지도의 빈틈:** 화면과 연결되지 않은 서버 기능([화면 보기](docs/images/ko/orphan-requests.png)), 받는 곳을 못 찾은 요청([화면 보기](docs/images/ko/unresolved-requests.png)), 화면과 연결되지 않은 이슈([화면 보기](docs/images/ko/unlinked-issues.png)), 지난 지도에서 사라진 화면과 요청([화면 보기](docs/images/ko/removed-items.png))을 봅니다.
- **검색:** 어느 보기에서든 화면·버튼·요청·PR·이슈를 찾습니다. [화면 보기](docs/images/ko/search.png)

## 코드 연결 도움말

- **수집에 실패했을 때:** **GitHub 계정 바꾸기**에서 로그인된 계정을 선택하고 다시 시도하세요. 코드 연결마다 계정을 기억하며, 새로고침에 실패해도 마지막 성공 지도는 유지됩니다.
- **여러 저장소가 같은 데이터베이스를 쓸 때:** **코드 연결 → 여러 코드가 같은 데이터를 사용할 때**에서 테이블을 연결하세요. 이름이 같은 테이블을 자동으로 합치지는 않습니다.
- **다른 코드의 서버로 요청할 때:** **코드 연결**의 **요청을 받는 서버 코드**에서 선택하세요.
- **연결을 해제할 때:** 내려받은 코드와 저장된 지도는 Mac에 남습니다.

## 업데이트

Homebrew로 설치했다면 **메뉴 → 버전·업데이트 → 지금 업데이트**를 누르세요. 새 버전 알림의 **업데이트 보기**는 이 창을 열 뿐 바로 설치하지 않습니다. 설치 뒤 앱이 다시 열리고, 저장된 지도는 유지됩니다. 업데이트가 끝나면 에이전트의 MCP도 재연결하세요.

터미널에서 업데이트하려면 다음 명령을 실행하세요.

```sh
brew update && brew upgrade --cask ganggangstone/tap/where-were-we
```

새 버전 알림은 **메뉴 → 버전·업데이트**에서 끌 수 있습니다. ZIP으로 설치했다면 [릴리즈](https://github.com/ganggangstone/where-were-we/releases/latest)에서 최신 ZIP을 받으세요.

**업데이트가 중단됐을 때**

설치나 실행에 실패하면 이전 앱 복구를 시도합니다. 복구도 중단됐다면 아래 명령으로 복구 안내를 여세요.

```sh
open -a TextEdit ~/.where-were-we/.app-update.log
```

보관한 앱의 위치와 재설치 명령이 적혀 있습니다. Finder로 앱을 복원하거나 안내된 명령을 실행하세요.


## 데이터와 분석 범위

- 지도와 내려받은 코드는 `~/.where-were-we/`에 저장합니다. 프로젝트 정보가 들어 있으므로 공개 저장소에 넣지 마세요.
- 수집은 코드·Git 이력·GitHub 작업을 읽습니다. 원격 변경을 가져오지만 작업 중인 브랜치를 바꾸거나 소스 파일을 수정하지 않습니다.
- AI 분석 때는 연결한 에이전트에 소스 코드를 제공합니다. 데이터 처리는 선택한 에이전트·제공자의 설정을 따릅니다.
- 자동 수집은 React Router/axios·FastAPI·SQLAlchemy를 지원합니다. 다른 언어·프레임워크는 에이전트에 분석을 요청하세요. 표시된 분석 범위·미확인 항목·원문 근거를 함께 확인하세요.
- 브랜치 비교는 코드의 차이를 보여 줍니다. 실제 배포 상태나 실행 환경을 확인한 결과는 아닙니다.

## 기여와 라이선스

버그·개선 제안은 [이슈](https://github.com/ganggangstone/where-were-we/issues)로 보내 주세요. PR도 환영합니다. 큰 변경은 구현 전에 범위를 논의해 주세요.

[라이선스](LICENSE)는 조건에 따라 개인·회사 내부 사용과 무료 재배포를 허용하며, 유료 제품·외부 유료 서비스를 제한합니다. 별도의 소스 공개 라이선스이며, 제삼자 구성 요소에는 각각의 라이선스가 적용됩니다.

**v0.3.0 릴리즈 노트**

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


[전체 릴리즈](https://github.com/ganggangstone/where-were-we/releases) · [설정과 구현 상세](docs/MULTI_REPO_SPEC.md)
