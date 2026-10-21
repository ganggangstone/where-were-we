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

1. 앱을 여세요. 처음 설치하면 **시작 안내**가 열립니다(**메뉴 → 시작 안내**에서 다시 열 수 있습니다).
2. **작업하던 AI에게 연결을 맡기세요:** 안내를 복사해 서비스를 만들 때 쓰던 AI 채팅(Claude Code·Codex 등 MCP를 지원하는 에이전트)에 붙여 넣으세요. AI가 허락을 받고 연결을 설정한 뒤, 서비스의 코드를 찾아 저장하기 전에 확인을 요청합니다.
3. **연결한 코드**에서 코드마다 위치와 지도 준비 여부를 확인하세요. 저장된 서비스를 고치려면 **연결한 코드 수정**을, 새 서비스를 직접 입력할 때만 **직접 연결하기**(또는 상단 **＋**)를 쓰세요.
4. GitHub 주소를 연결하면 첫 지도를 가져옵니다. 기존 폴더를 연결했다면 **새로고침**을 누르세요.

코드가 둘 이상이고 서로 요청을 주고받는다면 **코드 연결**에서 각 코드의 **이 코드가 요청을 보내는 서버**를 고를 수 있습니다. 지도에서 관계를 잇는 설정일 뿐이며, 주소가 같다는 이유만으로 서로 다른 코드를 잇지 않습니다. 앱이 연결 후보를 보여 주면 확인한 뒤 **지도에 연결**을 누를 수 있습니다.

GitHub 연결은 원격 기본 브랜치를, 기존 폴더는 커밋된 코드를 읽습니다. 다른 브랜치나 태그를 보려면 **지도에 표시할 버전**에서 선택하세요. 상단 **지도에 표시할 버전** 버튼 두 개에는 실제 브랜치·태그 이름이 적혀 있습니다. 코드 존재 여부를 비교할 뿐 배포 상태를 뜻하지 않습니다.

**메뉴 → 설정**에서 언제부터 바뀐 내용을 볼지 정할 수 있습니다. 설정은 모든 서비스에 적용되며, **저장하고 새로고침**으로 바로 반영할 수 있습니다. **지난 새로고침 이후**를 고르면 다음 새로고침은 이번 새로고침 시각 이후부터 비교하고, 날짜·시각을 직접 지정하면 설정을 바꾸기 전까지 시작점이 유지됩니다. **서비스를 열 때 새로고침**은 다른 서비스로 바꿀 때도 실행됩니다.

앱은 한국어로 시작합니다. **메뉴**에서 **English**로 바꾸면 언어 선택을 저장합니다.

## AI 에이전트와 함께 쓰기

**메뉴 → AI 연결**을 누르고 안내를 Claude Code·Codex 등 MCP를 지원하는 에이전트에 전달하세요. AI 연결을 설정하고 공통 지시 파일에 사용 규칙을 추가하며, 바꾸기 전에 확인을 요청합니다.

앱을 열고 **“업로드 재시도 기능이 지도에서 어디인지 보여 줘”**라고 말해 보세요. 에이전트가 대상을 찾아 강조하고, 앱에서 직접 선택한 대상도 읽습니다. 계획하거나 수정하기 전에 지도를 확인해 영향받는 곳과 겹치는 작업을 살펴보도록 요청할 수 있습니다.

더 자세한 지도나 다른 언어·프레임워크의 분석이 필요하면 **AI에게 알아보기**를 누르고 분석할 코드와 요청을 고르세요(**화면과 서버 코드 자세히 보기**는 서비스 구성과 프로그램별 하는 일도 함께 정리합니다. 그 밖에 **서비스 구성 보기**·**화면을 기능별로 정리하기**·**무엇이 바뀌었는지 알아보기**). **모든 코드**를 보고 있으면 먼저 분석할 코드를 고릅니다.

1. 요청을 복사하세요.
2. 작업하던 AI 채팅에 붙여 넣고, AI가 코드를 분석해 결과를 저장할 때까지 기다리세요.
3. 앱에서 **결과 확인**을 누르세요. 다른 화면을 보다가 돌아올 때는 **AI에게 알아보기 · 결과 확인 대기** 버튼으로 같은 요청을 다시 엽니다.

저장된 결과를 읽어도 **바뀐 것**과 비교 기준은 유지됩니다. 분석은 연결한 AI가 하며, 사용하는 AI의 요금·사용 한도가 적용됩니다. 일반 새로고침은 AI 분석을 실행하지 않습니다.

업데이트 뒤 도구가 보이지 않으면 **연결 진단**에서 수정 요청을 복사해 AI에게 보내세요. 다시 연결한 뒤 **연결됐는지 확인**을 누르세요. 에이전트의 새 세션이 필요할 수도 있습니다.

## 지도 둘러보기

상단의 세 보기 **구조 · 하는 일 · 바뀐 것**으로 서비스를 살펴봅니다. **하는 일** 안에서 **기능 묶음 · 화면 지도 · 연결·데이터**를 고릅니다. 상단 검색은 어느 보기에서든 화면·서버 기능·프로그램·데이터·기능과 화면에 이어진 PR·이슈 번호를 찾습니다.

### 바뀐 것

바뀐 화면·요청·병합 PR과 바꾼 이유를 봅니다. **무엇이 바뀌었는지 알아보기**로 만든 요청을 AI 채팅에 붙여 넣고 **결과 확인**을 누르세요. 설명을 요청하거나 결과를 읽어도 비교 기준은 유지됩니다.

![바뀐 것: 가상 Lumen Studio](docs/images/ko/changes.png)

### 구조

프로그램·대기열·공유 데이터·외부 서비스와 실제 실행 환경에서 확인할 내용을 봅니다.

![구조: 가상 Lumen Studio](docs/images/ko/overview.png)

에이전트가 저장한 AI 제안은 직접 작성한 구조를 바꾸지 않습니다. **AI 제안**을 눌러 따로 볼 수 있습니다.

### 화면 지도와 진행 중인 작업

**하는 일 → 화면 지도**에서 서버 요청·테스트·두 버전의 차이, 겹치는 PR·PR 없는 브랜치·작업 폴더·연결된 이슈를 봅니다.

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
- **테스트 연결 찾기:** **AI에게 테스트 찾기 요청**으로 AI가 테스트를 찾아 반복되는 규칙이나 개별 근거 줄을 등록하도록 요청을 복사합니다. 확인하려고 새로고침할 수 있습니다. 연결하지 못했다는 것이 테스트가 없다는 뜻은 아닙니다. [화면 보기](docs/images/ko/tests.png)
- **AI 연결:** **메뉴 → AI 연결**에서 설치된 실행 환경에 맞는 MCP 연결 안내를 만듭니다. 에이전트가 설정 변경 내용을 먼저 보여 주고 허락을 받도록 안내합니다. [화면 보기](docs/images/ko/agent-setup.png)
- **버전·업데이트:** **메뉴 → 버전·업데이트**에서 설치 버전·최신 정식 릴리즈·한영 노트를 확인하고 **지금 업데이트**로 Homebrew 업데이트를 설치합니다. [화면 보기](docs/images/ko/updates.png)
- **지도의 빈틈:** 화면과 연결되지 않은 서버 기능([화면 보기](docs/images/ko/orphan-requests.png)), 받는 곳을 못 찾은 요청([화면 보기](docs/images/ko/unresolved-requests.png)), 화면과 연결되지 않은 이슈([화면 보기](docs/images/ko/unlinked-issues.png)), 지난 지도에서 사라진 화면과 요청([화면 보기](docs/images/ko/removed-items.png))을 봅니다.
- **검색:** 지도가 있는 서비스라면 어느 보기에서든 화면·기능·프로그램·데이터·PR·이슈를 찾습니다. [화면 보기](docs/images/ko/search.png)

## 코드 연결 도움말

- **수집에 실패했을 때:** **GitHub 계정 바꾸기**에서 로그인된 계정을 선택하고 다시 시도하세요. 코드 연결마다 계정을 기억하며, 새로고침에 실패해도 마지막 성공 지도는 유지됩니다.
- **여러 저장소가 같은 데이터베이스를 쓸 때:** **코드 연결 → 같은 데이터베이스를 함께 쓸 때**에서 테이블을 연결하세요. 이름이 같은 테이블을 자동으로 합치지는 않습니다.
- **다른 코드의 서버로 요청할 때:** **코드 연결**의 **이 코드가 요청을 보내는 서버**에서 선택하세요.
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

**v0.5.0 릴리즈 노트**

### 한국어

- 처음 안내에서 작업하던 AI에게 서비스 연결을 맡기고, 연결한 코드와 첫 지도를 확인할 수 있습니다.
- 서비스·AI·연결한 코드로 표현을 통일하고, 중복 설명은 상세로 옮겼습니다.
- 분석 요청 복사와 결과 확인을 단계별로 안내합니다. 결과 확인은 바뀐 것의 비교 시작점을 바꾸지 않습니다.
- 변경 설명에서 문제와 바뀐 점을 먼저 보여 주고, 미확인 항목과 두 비교 기간을 구별합니다.
- 기존 서비스의 코드 연결을 바로 수정하고, 코드마다 위치·지도 준비 상태를 확인할 수 있습니다.
- 오류 원인에 맞는 다음 행동을 안내하며, 오류 원문과 복구 위치는 펼쳐 보고 복사할 수 있습니다.
- 한국어·영어 화면의 글자·버튼·메뉴 스타일을 정리하고, 작은 창에서도 시작 안내를 사용할 수 있도록 다듬었습니다.

### English

- Use the getting-started guide to ask your coding AI to connect a service, review its connected code and open the first map.
- Consistent service, AI and connected-code labels replace mixed terminology; repeated explanations move into details.
- Copy analysis requests and check results in clear steps. Checking results preserves the Changes comparison start.
- Change explanations lead with the problem and what changed, with separate unknown items and comparison periods.
- Edit an existing service's code connections and check each location and map readiness.
- Errors explain the next action for their cause, while original messages and recovery locations remain available to open and copy.
- Korean and English typography, buttons and menus are more consistent, and the getting-started guide fits smaller windows.


[전체 릴리즈](https://github.com/ganggangstone/where-were-we/releases) · [설정과 구현 상세](docs/MULTI_REPO_SPEC.md)
