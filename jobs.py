#!/usr/bin/env python3
"""서버 밖 프로그램이 하는 일. 전체 구조의 상자 하나(code 폴더가 적힌 프로그램)의 코드를 설치된 에이전트(claude -p)에 읽혀,
그 프로그램이 어떤 일을 언제 시작하고 차례로 무엇을 하는지, 그 일을 시작하게 만드는 기록을 서버의 어디서 남기는지 받는다.

사용: jobs.py <프로젝트 이름> <상자 id> [브랜치=origin/dev]
결과: ~/.where-were-we/<프로젝트>/jobs.json 의 nodes[<상자 id>]
에이전트에게는 git show / git grep / git ls-tree / git log 만 허락한다. 근거마다 그 줄(±2)에 그 토막이 있는지 대조한다.
시작 근거가 통과하지 못한 일은 싣지 않는다. 서버 쪽 근거는 그 줄이 든 서버 기능(같은 파일이면 그 함수, 서비스 파일이면 그 파일을 쓰는 서버 기능)에 잇는다.
"""
import json, os, re, subprocess, sys

args = [a for a in sys.argv[1:] if not a.startswith("--")]
PROJECT, NODE = args[0], args[1]
REF = args[2] if len(args) > 2 else "origin/dev"
LINK_ONLY = "--link-only" in sys.argv  # 에이전트를 다시 부르지 않고 서버 기능과의 연결만 다시 계산한다
HOME = os.path.expanduser("~/.where-were-we/" + PROJECT)
m = json.load(open(os.path.join(HOME, "dev.json")))
system = json.load(open(os.path.join(HOME, "system.json")))
node = next(n for n in system["nodes"] if n["id"] == NODE)
REPO = m["repo"]
CODE = node.get("code") or sys.exit(f"{node['name']}: 코드 폴더(code)가 적혀 있지 않다")


def git(*a):
    return subprocess.run(["git", "-C", REPO, *a], capture_output=True, text=True, errors="replace").stdout


norm = lambda t: re.sub(r"\s+", "", t or "")
_src = {}
def check(ev):
    f, ln, q = (ev or {}).get("file"), (ev or {}).get("line"), norm((ev or {}).get("quote"))
    if not f or not isinstance(ln, int) or len(q) < 6:
        return False
    lines = _src.setdefault(f, git("show", f"{REF}:{f}").splitlines())
    return any(q in norm(l) for l in lines[max(0, ln - 3):ln + 2])

# 서버 쪽 근거 줄 → 서버 기능.
# 라우터 파일이면 그 줄 위의 가장 가까운 서버 기능. 서비스 파일이면 그 줄이 든 함수를 본문에서 직접 부르는, 값을 바꾸는(GET 아닌) 서버 기능.
routes = [r for r in m["backend_routes"] if r.get("mounted") and r.get("function")]
def enclosing(lines, ln):
    for k in range(min(ln, len(lines)) - 1, -1, -1):
        mm_ = re.match(r"\s*(?:async\s+)?def\s+(\w+)\s*\(", lines[k])
        if mm_: return mm_.group(1)
    return None
def body_of(file, fn):
    src = git("show", f"{REF}:{file}")
    mm_ = re.search(rf"^(\s*)(?:async\s+)?def\s+{re.escape(fn)}\s*\(", src, re.M)
    if not mm_: return ""
    rest = src[mm_.end():]; end = re.search(rf"^{mm_.group(1)}(?:@|(?:async\s+)?def\s|class\s)", rest, re.M)
    return rest[:end.start()] if end else rest
def routes_of(ev):
    same = sorted((r for r in routes if r["file"] == ev["file"] and r["line"] <= ev["line"]), key=lambda r: r["line"])
    if same:
        return [{"key": same[-1]["file"] + "::" + same[-1]["function"], "exact": True}]
    fn = enclosing(_src.setdefault(ev["file"], git("show", f"{REF}:{ev['file']}").splitlines()), ev["line"])
    if not fn: return []
    mod = os.path.splitext(os.path.basename(ev["file"]))[0]
    def calls_it(r):  # 그 서비스 모듈의 그 함수를 부르는가. 같은 이름의 다른 모듈 함수와 섞지 않는다
        body, imps = body_of(r["file"], r["function"]), imports_of(r["file"])
        direct = [l for l, (mm_, o) in imps.items() if mm_.split(".")[-1] == mod and o == fn]
        alias = [l for l, (mm_, o) in imps.items() if o == mod]
        return any(re.search(rf"(?<![\w.]){re.escape(l)}\s*\(", body) for l in direct) or any(re.search(rf"\b{re.escape(l)}\.{re.escape(fn)}\s*\(", body) for l in alias)
    return [{"key": r["file"] + "::" + r["function"], "exact": False} for r in routes
            if r["method"] != "GET" and ev["file"] in r.get("services", []) and calls_it(r)]
_imps = {}
def imports_of(file):
    """from ..a.b import x as y → {y: ('a.b', 'x')}. 함수 안에서 들여 쓴 import 도 본다 (extract.py 와 같은 규칙)."""
    if file not in _imps:
        src, t = git("show", f"{REF}:{file}"), {}
        found = [(m_.group(1), m_.group(2)) for m_ in re.finditer(r"^[ \t]*from\s+\.*([\w.]*)\s+import\s*\(([^)]*)\)", src, re.M)]
        found += [(m_.group(1), m_.group(2)) for m_ in re.finditer(r"^[ \t]*from\s+\.*([\w.]*)\s+import\s+([^(\s][^\n]*)$", src, re.M)]
        for mod_, names in found:
            for item in names.split("#")[0].replace("\n", " ").split(","):
                p = item.strip().split()
                if p: t[p[-1]] = (mod_, p[0])
        _imps[file] = t
    return _imps[file]
def link(made):
    links = {}
    for e in made:
        for r in routes_of(e):
            if r["key"] not in links or r["exact"]: links[r["key"]] = r
    return list(links.values())

if LINK_ONLY:
    path = os.path.join(HOME, "jobs.json"); store = json.load(open(path))
    for j in store["nodes"][NODE]["jobs"]: j["routes"] = link(j["made_by"])
    json.dump(store, open(path, "w"), ensure_ascii=False, indent=1)
    js = store["nodes"][NODE]["jobs"]; print(f"{node['name']}: 하는 일 {len(js)}개, 서버 기능과 이어진 일 {sum(1 for j in js if j['routes'])}, 이어진 서버 기능 {sum(len(j['routes']) for j in js)}"); sys.exit(0)

PROMPT = f"""너는 지금 git 저장소 안에 있다. "{node['name']}"({node.get('what', '')})이라는 프로그램이 하는 일을 조사해 JSON 으로 적어라.
이 프로그램의 코드는 {', '.join(CODE)} 에 있다. 이 서비스의 웹 서버 코드는 다른 폴더(예: backend/app)에 있다.
읽는 사람은 코드를 못 읽는다. "화면에서 무엇을 누르면, 서버가 무엇을 남기고, 그걸 보고 이 프로그램이 무엇을 차례로 하는가"를 알고 싶어 한다.

읽는 방법: 작업 폴더의 파일을 직접 열지 말고 반드시 `{REF}` 의 내용을 읽는다.
  git ls-tree -r --name-only {REF} <경로> / git show {REF}:<경로> / git grep -n <패턴> {REF} -- <경로>

적을 것: 이 프로그램이 하는 일(job)마다
- name: 쉬운 한국어 이름(2~5어절), what: 무엇을 하는지 한 문장
- starts_when: 이 일이 언제 시작되는지 한 문장(예: "DB에 상태가 '대기'인 디자인 요청이 있으면")
- trigger: 이 프로그램 코드에서 그 조건을 보는 곳의 근거 1개
- made_by: 그 조건을 만드는 기록을 웹 서버 코드가 남기는 곳의 근거 0~3개(웹 서버 폴더 안의 파일만). 못 찾으면 빈 목록.
- steps: 이 일이 차례로 하는 것 3~7단계. 단계마다 lane("프로그램"=판단·계산, "저장소"=DB·파일 읽기쓰기, "외부"=다른 회사 서비스·다른 프로그램 호출), text(쉬운 한국어 한 문장), 근거.
근거 형식: {{"file": 경로, "line": 줄 번호, "quote": 그 줄에 적힌 글자를 그대로 복사한 토막(8자 이상)}}. 기계가 대조해서 없으면 버린다.
함수명·변수명을 글에 쓰지 않는다. 모르는 것은 지어내지 않는다.

마지막에 JSON 하나만 출력한다:
{{"jobs": [{{"name": "", "what": "", "starts_when": "", "trigger": {{...}}, "made_by": [{{...}}], "steps": [{{"lane": "", "text": "", "file": "", "line": 0, "quote": ""}}]}}]}}"""

print(f"에이전트가 {node['name']}의 코드를 읽는 중… (몇 분 걸린다)", flush=True)
out = subprocess.run(["claude", "-p", "--output-format", "text", "--model", "opus",
                      "--allowedTools", "Bash(git ls-tree:*)", "Bash(git show:*)", "Bash(git grep:*)", "Bash(git log:*)",
                      "--", PROMPT], cwd=REPO, capture_output=True, text=True, timeout=1800)
mm = re.search(r"\{.*\}", out.stdout, re.S)
if not mm:
    sys.exit("에이전트 출력에 JSON이 없다:\n" + out.stdout[-600:] + out.stderr[-400:])
data = json.loads(mm.group(0))

jobs, dropped = [], 0
for j in data.get("jobs", []):
    if not check(j.get("trigger")):
        dropped += 1; continue
    made = [e for e in j.get("made_by", []) if check(e)]
    steps = [s for s in j.get("steps", []) if check(s)]
    for s in steps:
        if s.get("lane") not in ("프로그램", "저장소", "외부"): s["lane"] = "프로그램"
    jobs.append({"name": j.get("name", ""), "what": j.get("what", ""), "starts_when": j.get("starts_when", ""), "trigger": j["trigger"],
                 "made_by": made, "steps": steps, "routes": link(made)})

path = os.path.join(HOME, "jobs.json")
store = json.load(open(path)) if os.path.exists(path) else {"nodes": {}}
store["nodes"][NODE] = {"commit": git("rev-parse", "--short=8", REF).strip(), "jobs": jobs}
json.dump(store, open(path, "w"), ensure_ascii=False, indent=1)
print(f"{node['name']}: 하는 일 {len(jobs)}개 (시작 근거가 안 맞아 버린 것 {dropped}), 서버 기능과 이어진 일 {sum(1 for j in jobs if j['routes'])}")
