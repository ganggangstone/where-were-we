# App-initiated analysis — issue #8

Issue: https://github.com/ganggangstone/where-were-we/issues/8

## What 「분석하기」 does

One button analyses the connected repository and draws the result. Its label states the number of AI calls
(`분석하기 · 호출 N회`). The user confirms nothing else. Every answer is saved when it arrives, so the board fills in
while the run goes on.

1. **Local map (no AI).** `structure_index.build` and `analysis_units.catalog` turn the pinned commit into units
   (routes, packages, command families, screens, programs, folders) and import links between them. The board
   (`analysis_run.unit_board`) shows them as soon as they are calculated.
2. **Reading rules (one call per language).** Python, JavaScript/TypeScript, Go and HTML are read by built-in
   readers. A language outside those five that has enough code files (`lang_rules.needed`) and no cached rules gets
   one `lang_rules.obtain` call. The local map is then rebuilt with those rules, which adds declarations,
   import links and route units (route registrations outside test and support files) for that language. If the rules fail, the folder map stays and the board says that the
   language's connections were not read.
3. **Labels and structure (from a summary, not from source).** `analysis_label.summary` builds a compact summary
   of the local map. It holds integer unit refs, kinds, local names, file counts, unit links, up to three
   declaration names (each with an integer evidence ref) and file names per unit, the requests the local map knows
   (each with a request ref), and the project description. Folders are sent once as a
   `[parent, name]` tree. When the summary is at most `analysis_label.BOUND` (64 KB), one call names every unit,
   groups the units and lists programs and their connections. A larger summary is split by top-level folder
   into labeling calls of at most 64 KB each, followed by one structure call over the labeled groups.
4. **Unit explanation (on demand).** A card the user opens can ask for that unit's explanation. This is one call
   over source lines read from that unit (`_quick_overview`), saved in `unit_overviews` or `scope_overviews`.
   On the board a unit 「분석하기」 named shows 「이름·설명 있음」 (state `named`) and counts as done for the run; one with
   this explanation shows 「자세한 설명 있음」 (`saved`). Only units no labeling part covered stay `pending` (설명 없음).

The project-overview call is not part of 「분석하기」. The summary already carries the project description that
the structure index reads from the README.

「분석하기」 is the only app run that names units, groups screens and builds the service structure. The service
structure and screen-group views have no buttons of their own; an empty view says that 「분석하기」 in 「AI 지도」
builds it. The copy-request path for another AI agent (MCP `request_ai_task`) is separate and unchanged.

## Details asked one at a time

Each of these runs only when the user asks for that one thing.

| Detail | Entry point | Calls |
| --- | --- | --- |
| Unit explanation | 「AI 설명 · 호출 1회」 on an opened unit card | one call over bounded lines of that unit (`_quick_overview`) |
| Route explanation | 「AI 설명 (베타)」 on a route in the map (`scope_overview`) | one call over bounded lines of that route (`_quick_overview`) |
| Path-group explanations | 「영역 AI 설명 (베타)」 in the map (`resources`) | one call per pack of route scopes, at most the confirmed `max_calls` |
| Action steps (동작 과정) | 「이 동작의 과정 알아보기」 (`steps`) | at most 3 (`MAX_STEPS_CALLS`), below |
| Program jobs (하는 일) | 「이 프로그램이 하는 일 알아보기」 on a program (`jobs`) | one, below |
| Change explanation | 「변경 설명 만들기」 (`briefing`) | at most 4 (`MAX_BRIEFING_CALLS`), below |

In every detail, local code picks bounded source lines and numbers them; the model cites a line only by its integer
ref, and local code fills file, line and quote (`_quick_overview`, `analysis_run._detail`). A reply that names a ref
it was not given, writes a quote itself or asks for further reads (`needs`) is invalid. Each call that fails or
returns an invalid answer is retried once; when the retry fails too, the run fails and the saved result stays.
Detail results are saved through the same checks as the MCP path (`ai_extract.task_record`, `briefing.record`).

- **Steps.** Per route: the handler file from the handler's declaration (about 120 lines) and around the
  registration line, then the screen code that sends the request, then the route's service files and the files the
  handler file imports, each up to 60 lines around their source signals. The screen code is the map's call sites of
  the route (`callers` in the route input, `ai_extract.task_input`): the selected screen's first, at most
  `MAX_CALLERS` (3), each `CALLER_LINES` (12) lines on either side of the call. When a call site of the selected
  screen sits in a function the screen's own files use (the map's `via` file of that screen's api function), the route
  input also lists `uses`: lines in those files that name the function as a whole word, skipping import lines, at
  most `MAX_USES` (3) per route, each `USE_LINES` (8) lines on either side. Names shorter than `MIN_USE_NAME` (4)
  are not searched, and a target of route keys has no selected screen and no uses. A screen whose routes are all
  missing is asked with the screen as its target, so its uses are known. At most `ROUTE_BYTES` (16 KB) per route and
  `DETAIL_BYTES` (96 KB) per call, in at most `MAX_STEPS_CALLS` (3) calls. Routes that do not fit, and routes an
  answer leaves out, are saved with `steps: []` and an `unknown` text saying their steps are not established.
  The model writes 「화면」 (screen) steps only from the caller and use lines: what sets off the request and what
  the screen does with the answer come from the use lines, and what the user does is stated only when a shown line
  shows it; otherwise the step says only that the screen sends the request. A screen step citing any other file is
  invalid in the app run and is dropped on the MCP path; with no callers there are no screen steps. The step picture
  opens with a screen step the app adds only when the saved steps do not start with one.
- **Jobs.** Up to `MAX_JOB_FILES` (8) files in the program's code folders, ranked by source signals (entry points,
  schedulers, workers first), each up to 160 lines around its signals and `DETAIL_BYTES / 8`. The known routes go
  along as metadata. The saved `unknown` says how many of the program's files were read (「프로그램 파일 M개 중 N개만
  읽었다.」).
- **Briefing.** The collected change evidence, with each PR or issue body cut to `BRIEF_BODY_CHARS` (3000) and the
  structure evidence to `BRIEF_STRUCTURE_CHARS` (8000); a cut source is marked `truncated`. PRs are packed with
  their linked issues into groups of at most `DETAIL_BYTES`; each call covers every PR of its group, and the cards
  are joined. When more than `MAX_BRIEFING_CALLS` groups would be needed, the run fails with `source_too_large`
  before any call, so no PR is left out silently.

## Call count

Before the start, `analysis_run._full_plan` counts the calls. The count is fixed by the summary alone:

- rules: one per language that needs rules
- labeling: one per summary part whose input hash is not already saved
- structure: one when the summary is split and the structure of those labels is not already saved

The board and `prepare()` use the same count. A call that fails is retried once. If the retry also fails, that
part is recorded in `gaps` as having no AI interpretation and the run continues. The local map always stays,
and a gap does not fail the run. Pressing 「분석하기」 again redoes only the parts that are missing or whose input
changed. When nothing changed, it makes no call.

When reading rules are needed, every labeling part is counted, because the rules change the summary.
The unit partition is fixed when the run is prepared, so the announced count still holds after the rules arrive.
After the rules, the parts are cut again from the new summary when it splits into the announced number of parts,
so a later press with nothing changed finds the same keys. Otherwise the units the rules add (route units of that
language) join the last labeling part.

## What the AI may claim

- Labels may cite only the unit, evidence and request refs the summary listed. Anything else is dropped and counted
  (`dropped`). For an evidence ref, local code fills the file, line and literal line text of the pinned commit.
- A link's evidence is found locally (`origin: local_link`): up to three lines where a code file of one program imports
  a file of the other or sends a request the other serves, one per source file, most-connected files first. Only the
  link's own direction counts; a link the local map shows the other way is kept as given. Without such a line, and for
  every program, the declarations the model cited are kept (`origin: cited`) and the screen titles them 「관련 코드」,
  because they only show code inside that area.
- Screens and routes come only from local calculation. The AI names and groups them but never adds one.
- No source line is sent for labels, so names and descriptions are an interpretation of the structure and are not
  checked against code. The board says this. Unit explanations are made from read source lines and are checked against them.

## Saved shapes

- Run record (`.analysis-runs/<id>.json`): `announced`, `input_stats.by_kind`, `labels[repository]` =
  `{commit, parts: {input hash: {units: {unit id: {name, what}}, groups, programs, links, requests, dropped}},
  structure: {key, programs, links, dropped}}`, `gaps`.
- Map screen (project bundle): `groups` `{groups: [{name, description, screens: [path]}], names, request_names}`
  (`request_names` keyed `file::function`)
  and `system` (or `system.ai` beside a locally built one) `{nodes, links, externals, others}`. Both are marked
  `basis: structure_summary`. Programs saved this way never become units of the catalog that produced them.

## Limits

- The structure index reads at most `MAX_FILES` and `MAX_BYTES` (`structure_index.py`). Above those it indexes a
  bounded sample. The board's reading range shows `색인 한도 도달`. Files outside the sample still belong to
  folder units, but they have no declarations or links.
- Old run records are read only for saved unit explanations and labels. Fields they hold from earlier formats
  are ignored.

## Tests

`tests/test_analysis_units.py` (`FullRun`) runs the whole flow with fake executors on a temporary data root.
`tests/measure_full_analysis.py` measures local-map time, calls by kind and bytes on local repositories with a
fake executor.
