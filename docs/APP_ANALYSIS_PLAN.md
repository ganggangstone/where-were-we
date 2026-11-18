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
