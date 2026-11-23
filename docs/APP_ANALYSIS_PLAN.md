# App-initiated analysis — issue #8

Issue: https://github.com/ganggangstone/where-were-we/issues/8

## Outcome and initial execution choice

An explicit app action starts analysis, reports progress, and reads validated saved
results without changing collection history or the selected comparison baseline.
Existing copy-to-MCP requests remain available.

The first automatic executor is an installed Claude Code CLI signed in with a
Claude account. Its account and usage responsibility are shown before execution.
The app does not log in, switch accounts, claim free usage, or store provider keys.
Direct provider API support belongs to issue #10. Additional CLI adapters can use
the same executor interface after their execution and authentication contracts are
verified; MCP registration alone is not an automatic execution capability.

Claude runs in a temporary working directory with built-in tools disabled, a
strict empty MCP configuration, safe mode, and no session persistence. Safe mode
preserves normal authentication; bare mode is unsuitable because it bypasses
subscription OAuth. Organization-managed policy can still apply. Unsupported CLI
versions and authentication modes fail before model execution, with the manual
handoff still available.

Official references checked 2026-10-29:

- https://code.claude.com/docs/en/cli-reference
- https://code.claude.com/docs/en/headless
- https://code.claude.com/docs/en/hooks

## Work breakdown

1. **Run coordinator:** persist run identity and project/repository/branch/language
   scope and explicit task/targets; pin commit, configuration and (only for a
   requested briefing) collected evidence. The first automatic analysis builds
   analysis, system overview and screen groups. It omits embedded route steps and
   program jobs as well as their task queue entries. Detail buttons run only the
   chosen targets and necessary prerequisites; the public manual MCP plan stays
   compatible. Re-plan after each save and retain completed work on failure.
2. **CLI adapter:** discover the executable, check supported options and login,
   supply bounded pinned source and request data via stdin, parse structured
   output, handle authentication/usage limits, timeout and cancellation. Never run
   application code or give the model write access to the map store.
3. **Native/UI integration:** display provider/account and explicit Start, progress,
   Cancel and Retry; poll scoped run status; read stored results on completion;
   recover state after reopening without confusing a different task with the
   selected request. Keep repository-local target IDs when a combined map spans
   repositories. Show saved tasks separately from input calls, encoded bytes and
   processed input units. Package both Python modules and the UI script.
4. **Integration review:** fake executors and temporary repositories cover success,
   invalid evidence, stale sources/configuration, partial progress, cancellation,
   retry and interrupted workers. Check frontend stale-response handling, preserved
   comparison settings, packaging and the existing regression suite.

## State and storage contract

Runs use preparing, running, saving, completed, failed and cancelled states. An
interrupted worker becomes an actionable failed run; retry creates a new pinned
run with the same task and targets. One active run per project prevents overlapping scopes from competing for
saved snapshots. Cancellation affects only a process launched for that run.

The coordinator checks pins before each task and before recording. Existing
analysis, task and briefing recorders remain the authority for evidence and stale
result validation. No refresh is performed to display results. Source prompts,
credentials and raw provider diagnostic output are not persisted in run metadata.
Source and metadata are split into server-identified units with a hard 131,072-byte
cap on each complete encoded prompt. Partial changes send affected source and
necessary prior blobs. The first system overview uses validated map and collected
structure metadata; missing context uses bounded, pinned source or metadata reads.
Within one run, immutable file contents are reused by Git object ID, so repeated
source searches do not read the same blob from Git again. Every export still applies
that commit's tree and path eligibility rules. The first read of each blob and the
in-memory search remain, and the reused contents are released when the run ends.
All units and final relationships must validate before one recorder call per task.
Unrequested details stay absent or retain their existing provenance and freshness;
empty details are not invented to complete the overview. An unchanged overview
requires zero model calls, even when details have never been requested. Inputs
that cannot fit still fail explicitly. App updates wait for active workers.

## Release verification

- Automated checks use fake executors; they must not spend real model usage.
- Check a packaged macOS build with an installed supported Claude Code CLI: inspect
  the account notice, explicitly start a synthetic project, observe progress,
  cancel/retry, reopen the app, and see a validated result without moving the
  comparison baseline.
- Check missing CLI, signed-out CLI, unsupported CLI/auth mode, and manual MCP
  fallback. Confirm ordinary refresh never starts paid analysis.
- A real-provider smoke test requires the user to choose the account and explicit
  execution. Passing fake-provider tests alone does not satisfy this final check.

## 큰 저장소의 첫 상세 지도 · 구현 범위와 후속 설계

사용자가 코드에 다시 들어왔을 때 구조, 하는 일, 바뀐 것을 같은 근거에서 따라가게 한다. 분석 속도는 사용자가 근거 있는 첫 기능을 열기까지 걸리는 시간과 선택한 분석 전체가 끝나는 시간으로 나눠 측정한다.

현재 앱의 첫 분석(`full`)과 재검토(`review`)는 큰 저장소에서 고정 커밋의 파일 목록과 크기를 먼저 읽는다. 작은 파일을 여러 폴더에서 선택해 첫 요청을 준비하고, 이미 알려진 근거 경로와 재검토 대상을 우선한다. 같은 커밋의 나머지 적격 소스는 뒤에서 계속 처리한다. 문자열 추가 읽기는 이미 해독한 파일을 재사용하며, 그 밖의 허용 파일은 Git으로 일치 후보를 찾고 후보 원문에서 줄 번호와 전체 일치 개수를 확인한다.

분석 패널은 현재 실행·저장소·작업·커밋이 일치하는 범위에서 확인된 화면·서버 요청·프로그램의 이름과 근거 파일, 줄, 인용문을 열어 준다. 코드가 존재한다는 근거와 AI가 설명한 의미의 정확성은 별개의 검증이다. 개별 근거 미리보기와 최종 지도 저장은 서로 다른 상태다. 작은 입력은 종전의 단일 요청을 사용한다. 가짜 실행기 시험은 AI 응답 시간을 포함하지 않으며, 처음부터 유용한 기능을 찾는 시간은 선택된 파일과 실제 모델 응답에 따라 달라진다.

아래 항목은 설계 목표다. 특히 실행을 넘는 상세 설명 재사용, 임의 프로젝트의 첫 기능 발견 품질과 사용자에게 보이는 전체 대기 시간은 추가 검증 대상이다.

1. **기준과 범위.** 기존 실행 조정기에서 저장소별 Git commit(코드 버전), 설정, 언어, 작업 대상을 고정한다. 로컬 기본 지도와 직전 결과를 먼저 읽고, 이전 버전의 결과에는 그 버전을 표시한다. 전체 파일 목록을 로컬에서 관리하고 허용된 일반 텍스트 파일별로 검토한 범위와 남은 범위를 기록한다. 민감 경로, 심볼릭 링크, 바이너리는 기존 제외 규칙을 적용한다.
2. **첫 결과 선택.** 기본 지도에서 근거를 갖춘 기능을 열 수 있게 한다. 기본 지도가 빈 프로젝트에서는 실행 명령, 모듈의 공개 진입점, 작업 등록 등 탐색 가능한 단서와 그 주변 원문을 작은 단위로 읽는다. 웹 화면·서버 요청 외에도 CLI 명령·라이브러리 기능·백그라운드 작업은 해당 프로그램과 근거를 연결해 표현한다. 이름·README·인용 횟수는 읽는 순서를 정하는 후보 정보다. 지원하지 않는 언어나 폴더 구조, 참조가 적은 모듈도 남은 검토 범위에 포함한다. 동작을 확인하기 어려운 파일은 미확인 사유를 남긴다.
3. **AI가 원문을 읽는 경로.** 사용자가 시작한 분석에만 기존 실행기를 사용한다. 첫 요청에는 선택한 단서, 관련 항목과 근거 줄을 담고, 부족한 정보는 기존 `needs`(특정 파일 범위·문자열·메타데이터 추가 읽기) 계약으로 받는다. 고정 커밋에서 Git의 문자열 검색과 파일 범위 읽기를 사용하고 결과에 기존 경로·내용 검사를 적용한다. 저장소 전체 보강은 우선순위가 낮은 영역까지 이어가며, 작은 요청마다 기존 입력 한도를 지킨다.
4. **부분 결과와 확정 결과.** 실행 도중에는 해당 실행의 별도 임시 저장 영역에만 검증한 항목을 보관한다. 파일·줄·인용문의 일치, 연결 양끝의 존재와 관계의 근거를 확인하고 미확인 해석을 구분한다. UI가 현재 실행과 대상이 일치하는 항목을 ‘분석 중 확인한 기능’으로 열어 준다. 완결된 관계를 검증하기 전의 연결은 보류한다. 취소·실패·대상 변경 시 확정 지도와 비교 기준을 보존한다. 전체 검토 범위가 처리되고 기존 작업별 최종 검사를 통과할 때 기존 저장기를 한 번 호출한다. 완료는 요청한 범위를 처리했다는 뜻이며 결과의 미확인 항목도 계속 표시한다.
5. **새로고침과 재사용.** 파일 내부에서 추출한 사실은 Git blob(파일 내용 식별값)과 추출 규칙 버전을 기준으로 재사용한다. 파일 경로·설정·등록 관계가 의미에 영향을 주는 설명은 저장소·경로·설정·언어와 관련 근거 파일까지 대조한다. 추가·삭제·이동된 파일은 새 연결을 만들거나 기존 연결을 무효로 할 수 있어 해당 관계의 발견 규칙도 다시 검사한다. 영향 범위를 한정할 수 없는 경우 기존 재검토 절차로 돌아간다. 일반 새로고침은 변경·재검토 필요 상태만 갱신하고 AI 실행은 사용자가 시작한다.
6. **도입 판단.** 웹 앱, CLI, 라이브러리, 작업 프로그램, 언어를 인식하지 못한 저장소의 고정 커밋에서 현재 방식과 비교한다. 첫 실행과 변경 후 실행을 나눠 첫 기능을 실제 열 수 있는 시점, 전체 완료 시간, 호출 수·전송량, 사람이 확인한 기능·관계의 누락 및 잘못된 연결을 기록한다. 첫 추출이 비어 있거나 관련 코드가 파일 뒷부분에 있는 사례를 넣는다. 취소·재시도·브랜치 전환 시 부분 지도와 확정 지도가 섞이지 않는지도 확인한다. 자동 회귀 검사는 가짜 실행기를 사용하고 실제 응답을 포함한 시간은 별도 측정값으로 보고한다.

코드 이름 검색과 생성 버튼은 [후속 검색 계획](CODE_SEARCH_PLAN.md)에서 다룬다. 이 설계의 첫 적용 범위는 기존 ‘AI로 자세한 지도 만들기’이다.

## 전체 코드 분석(베타) · 구현 범위와 한계

분석 패널의 「전체 코드 분석」은 고정 커밋의 로컬 구조 색인에서 분석 단위를 AI 없이 계산한다(`analysis_units.py`). 저장된 색인이 없거나(구 저장 프로젝트) 고정 커밋·버전과 다르면 git에서 AI 없이 다시 계산해 `.analysis-cache`에 임시로 저장하며 프로젝트 저장 데이터는 바꾸지 않는다. 보드는 고정 커밋과 설정 지문만으로 열려(전체 파일을 읽는 수집기는 부르지 않는다) 추적 파일·제외 수를 먼저 보이고 단위를 이어서 계산하며, 수집기·색인·신호 검사 결과는 `.analysis-cache`에 커밋·수집 코드 판별값으로 저장한다. 새로고침 없이 「분석 시작」이 주 동작으로 보이고, 새로고침이 필요한 경우(수집된 브랜치가 없음 등)에만 「새로고침하고 단위 계산」을 보인다. 단위 종류는 경로 묶음(route), 화면(screen), 프로그램(program), 패키지(package), CLI, 폴더(folder)이며, 지도·서비스 구성·화면 묶음은 단위가 아니라 마지막에 실행하는 작업으로 같은 보드에 행(map·system·groups)으로 보인다. 추적 파일은 단위 안에 들어가거나 제외 사유(비밀·바이너리·생성·잠금·300KB 초과) 한 곳에 센다. 구조 색인이 읽지 못한 설정·스크립트·색인 한도 밖 파일은 일반 파일로 폴더 단위에 들어간다. 문서·데이터·테스트·외부 코드만 있는 폴더는 `folder:local:*` 로컬 단위(최대 200개 파일, `reading: local`)로 묶여 AI 없이 세고 목록만 보이며, UTF-8 텍스트로 읽히지 않는 파일(컴파일된 카탈로그 등)은 바이너리로 제외한다. 단위 사이의 import 간선은 `links`로 보드가 보여 준다. 전체 분석은 첫 개요·지도·서비스 구성·화면 묶음만 실행하고, 단위 설명은 카드에서 그 단위를 고를 때만 만든다(`intent.only`). 웹 서비스가 아닌 저장소도 같은 흐름을 쓴다.

### 읽음 · 색인 · AI 해석 범위

지도·서비스 구성이 AI에 보내는 원문은 두 방식 중 사용자가 시작 전에 고른다.

- **신호 기반 읽기(기본, `intent.coverage=signal`).** 적격 텍스트 파일 전부를 로컬에서 한 번 읽고(`git cat-file --batch`) 언어와 프레임워크에 묶이지 않는 어휘 규칙으로 검사한다(`source_signals.py`): 동사 옆의 경로 문자열·라우트 등록 어노테이션·Rails식 선언·OpenAPI 경로 키(route), 요청 클라이언트 호출(client), DDL/DML·ORM 필드(store), 접속 문자열·환경 변수로 받는 키·SDK(external), 진입점·CLI·작업자·서버 기동(program), 화면 라우트·이동 호출(screen). 신호 줄이 있는 파일은 그 줄의 앞 2줄·뒤 5줄을 합친 창(window)으로만 보내며 줄은 원래 번호를 그대로 쓴다(근거 인용이 실제 줄을 가리킨다). 한 줄이 1,600자를 넘으면 신호 위치 주변 한 조각만 보낸다(`offset` 포함). 저장된 AI 지도가 인용한 파일은 파일 전체를 함께 보낸다. 그 밖의 파일은 세 층으로 나뉘어 로컬 색인에만 남는다: **신호 없음**(코드·설정이지만 신호 줄이 없음), **문서·데이터**(`.md`·`.rst`·`.csv` 등), **테스트·외부 코드**(`tests`·`fixtures`·`vendor`·`node_modules` 등의 경로). 이 파일들도 AI는 기존 읽기 요청(`needs`: 파일 범위·문자열 검색)으로 언제든 읽을 수 있고, 요청에는 층별 개수를 담은 `coverage` 안내가 들어간다. 보드는 「로컬로 읽고 색인한 파일 · AI가 신호 줄 주변 해석 · 인용해 전체 전송 · 신호 없음 · 문서·데이터 · 테스트·외부 코드」를 따로 세고 전송량과 전체 원문 크기를 함께 보인다. 신호 규칙은 빠뜨림을 줄이는 쪽(재현율)으로 짜여 있어, 인식하지 못하는 신호는 로컬 색인에만 남을 수 있다.
- **모든 텍스트 파일 원문을 AI가 읽기(`coverage=all`).** 신호와 관계없이 이전처럼 모든 적격 파일을 조각으로 보낸다. 호출과 전송량이 가장 크며 시작 전에 이 값의 상한을 따로 보여 준다.

저장된 지도를 패치할 수 있으면(바뀐 파일과 저장 항목이 인용한 파일만 읽는 방식) 두 선택이 같다.

전체 분석의 호출 상한은 첫 개요 + 지도·구성 + 재시도 여유(`1 + (개요+지도 호출)//8`)의 합이다. 단위를 고르는 실행(`intent.only`: 1~24개의 `{repository,target}`)의 상한은 묶음 수 + 재시도 여유(묶음의 절반)이고, 이 실행은 자기만의 호출 한도를 가진다(설명이 없는 로컬 단위도 고르면 만든다). 경로 묶음은 4개씩, 나머지 단위는 표본 바이트(단위당 첫 4개 파일의 24줄 + 단위 필드)를 기준으로 108KB 또는 24개까지 한 번에 보내며, 상한과 실행이 같은 묶음 규칙을 쓴다. 한 호출에 묶인 단위들은 지시문과 답 형식을 호출마다 한 번만 싣고, 소스 줄은 `[ref, 줄 번호, 본문]` 압축 형태로 보낸다(경로 묶음은 이전 형태 그대로). 요청이 128KB를 넘으면 실제 크기를 재서 뒤로 미룬다. 한 번 실패한 단위는 정확히 `UNIT_ATTEMPTS`(2)번만 묻는다. 문자열 목록(전체 파일 경로 등)은 항목마다가 아니라 16KB 단위의 쪽으로 나눠 보낸다. 서비스 구성 작업에는 신호 기반 읽기에서 코드·설정 파일 경로만 나열하고 문서·데이터·테스트·바이너리는 폴더별 개수(`other_files`)로 알리며, 그 파일들은 `needs`로 읽거나 검색할 수 있다(`coverage=all`은 모든 경로를 그대로 나열한다).

### 첫 화면과 로컬 신호 수집

- 「전체 코드 분석」 보드는 고정 커밋과 파일 수(`units_quick`), 단위 목록(`units`)을 먼저 보인다. `units`는 신호 검사를 기다리지 않는다: 저장된 신호 결과가 없으면 `signals: "pending"`과 상한의 안전한 위쪽 값만 담고, 화면은 호출 상한·읽기 범위 선택 대신 「로컬 신호 수집 중」을 보이며 「분석 시작」을 잠근다.
- 신호 검사는 별도 요청(`status --view signals`)이 같은 시각에 시작한다. 이 요청은 실행 잠금 밖에서 `.analysis-cache`만 채우며(AI 호출 없음), 끝나면 화면이 `units`를 다시 읽어 정확한 호출 상한과 읽기 범위 선택을 보인다. 저장된 지도를 패치할 수 있으면 신호 검사가 필요 없어 바로 `ready`다.
- 큰 커밋의 신호 검사는 최대 6개의 별도 인터프리터가 파일을 나눠 읽는다(정규식 작업이 GIL을 잡으므로 스레드는 도움이 안 된다). 결과는 직렬 검사와 같고, 작업자를 시작할 수 없으면 이 프로세스에서 직렬로 한다.

- 시작 전에 AI 호출 상한(재시도 여유 포함, 지도·구성 추정 포함), 전송 대상, 구독 한도, 시간 상한을 보이고, 사용자가 누른 뒤에만 `intent.task=full`과 `max_calls`로 시작한다. 상한을 넘는 계산은 준비 단계에서 거부하고, 실행 중에도 확인한 상한을 넘는 호출은 보내지 않는다(`call_limit`, 저장한 결과는 그대로 두고 이어서 분석).
- 이어서 분석하면(같은 코드의 끝나지 않은 전체 분석) 처음 확인한 호출 상한이 그대로 적용되고 앞선 실행의 호출 수를 센다(`budget`). 상한을 다 쓰면 `call_limit`으로 멈추며 새 상한을 확인해야(`renew`) 새로 시작한다. 지도·서비스 구성에서 이미 검증한 입력 조각은 새 요청에서도 다시 보내지 않고, 최종 병합이 실패하면 그 조각을 지우고 같은 상한 안에서 다시 묻는다.
- 첫 개요를 먼저 저장하고, 고른 단위는 하나씩 검증해 저장한다. 한 단위가 두 번 검증에 실패하면 그 단위만 「검증 실패」로 남기고 나머지를 계속한다. 근거로 읽을 줄이 없는 단위는 「건너뜀」이다.
- 지도·서비스 구성·화면 묶음은 기존 기록기 계약(검증을 마친 결과 하나를 한 번에 저장)을 유지한다. 입력 조각(batch)별로 근거를 검증한 부분 결과는 실행 기록의 `partial_results`에 따로 보관하고, 「부분 저장」으로 근거와 함께 보여 준다. 저장된 지도·구성·묶음에는 모든 입력 조각을 덮은 뒤에만 반영하며, 취소·실패·상한 도달 때 기존 결과는 그대로다. 이어서 분석하면 이미 끝낸 입력 조각은 다시 보내지 않는다. 한 번의 호출로 끝나는 작업은 입력 조각이 하나라 부분 결과가 없다.
- 입력 조각 결과는 `_combine`으로 합친다. 같은 화면 경로나 같은 서버 기능(메서드·경로·파일·함수)을 조각마다 달리 적었으면 첫 값을 유지하고 다른 쪽은 `unknown`에 적는다(마운트 근거로 먼저 적은 파일이 달라도 같은 기능이며 경로는 마운트가 반영된 전체 경로다). 서비스 구성의 노드·외부 서비스는 대소문자와 `-`·`_`를 무시한 ID가 같으면 한 항목으로 합치고 첫 표기를 남기며, 그 ID를 가리키는 링크 끝과 `uses`도 남긴 표기로 바꾼다. 식별자가 실제로 충돌하는 값만 실패로 둔다. 모델의 읽기 요청이 잘못돼도(범위 밖 줄 범위, 없는 메타데이터 경로, 추적 소스가 아닌 파일, 16개 초과·형식 오류) 실행을 끝내지 않고 범위를 보정하거나 읽지 못했다고 답한다. 비밀 파일·절대 경로·`..`은 계속 거부한다. 읽기 횟수(지도 `MAX_READ_ROUNDS` 32회, 전체 분석의 서비스 구성 `SYSTEM_READ_ROUNDS` 8회)를 다 쓴 조각은 확인된 결과만 남기고 못 읽은 범위를 `unknown`에 적는다. 지도 재확인 대상 중 어느 조각도 판정하지 못한 항목은 저장된 근거 주변 소스를 한 번 더 보내 판정하고, 같은 등록의 마운트 근거만 달라진 후속 항목은 `replaces`로 잇는다. 서비스 구성 작업은 전체 분석(신호 읽기)에서 저장된 지도를 이름·경로·함수·표만 담은 압축형으로 보내고, 저장된 구조 이후 바뀐 파일이 `SYSTEM_DELTA_FILES`(64)개를 넘으면 바뀐 파일을 전부 읽는 증분 경로 대신 압축 목록 경로로 전체를 읽는다. 구조 결과에서 정의되지 않은 링크 끝·외부 서비스 참조는 버리고 `unknown`에 적으며, 구조 인용은 줄 번호가 틀려도 인용문이 공급된 한 줄과 정확히 하나 일치하면 번호를 바로잡고 한 번의 보정 재시도를 준다.
- 지도·구성이 끝난 뒤 새로 알게 된 화면·프로그램 단위는 목록에만 더하고 호출하지 않는다. 구조 작업에는 첫 개요와 저장된 단위 설명 중 지금 커밋에서 다시 검증한 인용(`verified_units`, 64KB까지)을 함께 보내, 같은 줄을 다시 읽지 않고 인용할 수 있다.
- 전체 분석이 끝나면(완료·실패·취소) 그 실행의 보드는 그 시점에 다시 연 보드와 같은 값으로 봉인되어(`final_board`) 합계(`retired` 포함)·행 순서·`links`가 같다. 다시 연 보드는 지금의 지도·구성에서 단위를 다시 계산하므로 실행 중의 목록과 다를 수 있다. 같은 커밋이어도 저장된 단위 설명의 단위 ID·파일 수·구성 파일 지문이 지금 단위와 다르면 「오래됨」이고, 새 실행도 그 설명을 저장된 것으로 세지 않는다. 지금 구조에 없는 이전 단위의 설명은 기록에만 남으며 `retired`(저장소별 목록, `totals.retired`)로 따로 알려 주고 단위 수에 넣지 않는다.
- 저장된 구성에 ID 표기만 다른 중복 노드가 남아 있으면 `analysis_run.py repair-structure <프로젝트>`가 합칠 수 있는 것만 찾는다(`--apply`가 있을 때만 쓴다). 합치는 조건은 ID 철자(대소문자·`-`·`_` 무시)가 같고, 종류가 같고, 코드 폴더가 서로 어긋나지 않고, 이름이 같거나 줄·인용까지 같은 근거가 있는 경우다. 서로 어긋나는 쌍이나 연결 고리가 끊긴 묶음은 그대로 두고 보고한다. 합친 뒤에도 근거·`uses`·코드 폴더·링크가 남고(다른 값은 `unknown`), 손으로 쓴 구성(`system.hand.json`)과 다른 저장 결과는 바뀌지 않는다. 적용하면 원본을 `<branch>.json.before-structure-repair-<시각>`으로 남기고 전후 개수·합친 항목·보류 항목을 `structure-repair-<시각>.json`에 적는다. 분석이 실행 중이면 적용하지 않는다. AI를 부르지 않는다.
- 취소·중단 뒤에는 저장한 단위를 유지하고, 다시 시도하면 저장되지 않은 지도·구성 입력만 요청한다. 코드가 바뀌면 단위가 인용한 파일과 모델 입력(연결·앵커 줄)이 그대로인 단위만 재사용하고 나머지는 「오래됨」으로 보인다. 단위가 저장 목록보다 크면 변경이 하나라도 있을 때 다시 분석한다. 모든 단위 결과는 기존 인용 검증을 거친다.
- 기존 첫 개요·경로 묶음 결과의 버전과 저장 형식은 바꾸지 않는다.

한계: 단위 설명은 단위당 최대 4파일·파일당 24줄 표본이다. 지도·구성의 호출 수는 읽을 코드 크기로 추정한 값이라 실제와 다를 수 있고, 상한이 먼저 닿으면 부분 결과만 남는다. 신호 규칙이 알아보지 못하는 모양의 코드는 AI가 `needs`로 요청하기 전까지 로컬 색인에만 있다. 실제 AI의 지도 품질(신호 창만 보고도 같은 결과가 나오는지)은 가짜 실행기로 확인하지 못했다.

### 측정 (가짜 실행기, 실제 AI 호출 없음)

저장된 지도가 없는 처음 분석(전체 코드 분석, 모든 단위 + 지도·구성)을 가짜 실행기로 끝까지 돌린 값이다. 처음 = 95edd56(모든 텍스트 파일 원문을 지도에 보냄), 이후 = 신호 기반 읽기(기본)와 `coverage=all`. 같은 시험에서 신호 기반 읽기만 먼저 넣었을 때(55b8748)는 사본 391 / 295, django 172 / 136, cargo 66 / 47이었다. 상한 = 시작 전에 보드가 보이는 호출 상한, 호출 = 실제 호출 수, 가짜 실행기 시간은 AI 대기 시간을 뺀 로컬 처리 시간이다.

| 저장소 | 처음(모든 원문) 상한/호출/전송 | 신호 기반 상한/호출/전송 | all 상한/호출 |
|---|---|---|---|
| cobra (Go CLI) | 19 / 19 / 1.3MB | 6 / 4 / 0.1MB | 18 / 18 |
| express (JS) | 38 / 27 / 1.2MB | 9 / 6 / 0.2MB | 23 / 17 |
| click (Python CLI) | 48 / 38 / 2.3MB | 8 / 7 / 0.3MB | 36 / 30 |
| bubbletea (Go TUI) | 43 / 31 / 1.0MB | 10 / 8 / 0.2MB | 20 / 16 |
| fastapi 템플릿 | 38 / 30 / 1.7MB | 15 / 12 / 0.5MB | 32 / 26 |
| vue core (TS) | 137 / 107 / 8.9MB | 7 / 6 / 0.3MB | 129 / 102 |
| github cli (Go) | 419 / 314 / 21.7MB | 43 / 31 / 2.8MB | 299 / 235 |
| cargo (Rust) | 506 / 383 / 23.8MB | 45 / 33 / 1.9MB | 335 / 264 |
| redis (C) | 557 / 434 / 35.0MB | 25 / 19 / 1.3MB | 491 / 390 |
| rails (Ruby) | 839 / 640 / 41.9MB | 72 / 55 / 3.3MB | 584 / 466 |
| django (Python) | 1,460 / 1,081 / 60.6MB | 137 / 109 / 5.1MB | 863 / 686 |
| 기존 프로젝트 사본(122MB 원문) | 1,990 / 1,606 / 124.4MB | 280 / 195 / 15.3MB | 1,684 / 1,382 |

화면 지연(기존 프로젝트 사본, 모든 캐시를 비운 첫 열기): 고정 커밋·파일 수 0.12초, 단위 목록 4.1초(저장된 구조 색인이 없는 구 저장 프로젝트라 색인을 git에서 다시 계산하는 시간이며 저장된 색인이 있으면 약 0.3초), 호출 상한과 읽기 범위 선택은 목록과 동시에 시작한 로컬 신호 검사(2.2초, 이전에는 목록에 직렬로 6초가 더해졌다)가 끝난 뒤 표시된다. 같은 커밋을 다시 열면 0.3초다. django는 목록 1.3초·신호 0.4초, cargo는 목록 0.2초·신호 0.3초다. 남은 호출의 대부분은 폴더 단위 설명이다(기존 프로젝트 사본 195회 중 단위 묶음 131 · 지도 52 · 서비스 구성 11 · 첫 개요 1; 단위 1,337개 중 1,203개가 폴더 단위이고 단위당 표본이 평균 약 8.5KB라 지금의 표본 크기에서는 약 130회가 바닥이다).

### 이전 버전과의 비교

- 첫 공개판(v0.1.0): 지도를 AI 없이 정규식 추출기(`extract.py`)로 만들었다. 호출은 0이었지만 해당 형태의 프론트엔드 레이아웃이 아니면 결과가 비거나 실패했다. 비웹·다른 언어 저장소는 지원하지 못했다.
- v0.2.0~v0.8.0: 연결된 MCP 에이전트가 `analysis_source`로 파일을 200줄씩 읽어 `record_analysis`로 제출하는 방식이다. 읽기와 호출 수는 그 에이전트가 정하므로 기록이 없어 실제 호출 수·시간은 근거가 없다.
- v0.9.0: 앱이 AI 실행기를 직접 돌렸고 고정 커밋의 원문 전체를 한 번의 요청에 담았다(`MAX_SOURCE_BYTES` 1.5MB·`MAX_FILES` 3,000). 한도를 넘는 저장소는 `source_too_large`로 거절하고 범위를 좁히라고 했다. 호출은 적었지만 이 한도를 넘는 저장소(위 표의 모든 큰 저장소)는 시작조차 못 했다. 한도 안의 작은 저장소에서 실제 속도는 측정 기록이 없다.
- v0.10.0 이후: 한도를 없애는 대신 128KB 요청으로 나눠 모든 텍스트 파일 원문을 지도에 보냈고, 호출 수가 저장소 크기에 비례해 늘었다(위 「이전」 열). 이번 변경이 이 부분을 신호 기반으로 줄인다.
