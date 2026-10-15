#!/usr/bin/env python3
"""전체 구조. 설치된 에이전트(claude -p)가 저장소를 읽어 "따로 켜지는 프로그램과 그 사이에 오가는 것"을 적는다.

사용: system.py <프로젝트 이름> [저장소 경로] [브랜치=origin/dev] [--force]
결과: ~/.where-were-we/<프로젝트>/system.json
      이미 사람이 적은 system.json 이 있으면 덮지 않고 system.ai.json 에 쓴다(--force 면 덮는다).
에이전트에게는 git show / git grep / git ls-tree / git log 만 허락한다. 저장소에 아무것도 쓰지 못한다.
에이전트가 적은 상자·선마다 파일·줄·원문 토막을 요구하고, 그 줄(±2)에 그 토막이 실제로 있는지 대조한다.
근거가 하나도 통과하지 못한 상자·선은 싣지 않는다.
"""
import json, os, re, subprocess, sys

args = [a for a in sys.argv[1:] if not a.startswith("--")]
FORCE = "--force" in sys.argv
PROJECT = args[0]
HOME = os.path.expanduser("~/.where-were-we/" + PROJECT)
_map = os.path.join(HOME, "dev.json")
REPO = args[1] if len(args) > 1 else json.load(open(_map))["repo"]
REF = args[2] if len(args) > 2 else "origin/dev"


def git(*a):
    return subprocess.run(["git", "-C", REPO, *a], capture_output=True, text=True, errors="replace").stdout


PROMPT = f"""너는 지금 git 저장소 안에 있다. 이 저장소가 만드는 서비스가 "실제로 돌 때 어떤 프로그램들로 이루어져 있고 서로 무엇을 주고받는지"를 조사해 JSON 으로 적어라.
읽는 사람은 코드를 못 읽는다. 서비스를 가장 멀리서 본 그림 한 장을 그리려는 것이다.

읽는 방법: 작업 폴더의 파일을 직접 열지 말고 반드시 `{REF}` 의 내용을 읽는다.
  git ls-tree -r --name-only {REF} [경로]     파일 목록
  git show {REF}:<경로>                        파일 내용
  git grep -n <패턴> {REF} -- <경로>           찾기
먼저 README, 실행·배포 설정(docker-compose, Makefile, Procfile, launchd·systemd 설정, CI), 설정 파일(환경변수를 읽는 곳), 운영 문서를 읽고,
그 다음 코드에서 확인한다: 무엇이 무엇을 부르는가(다른 프로그램의 주소로 요청, DB 연결, 다른 프로그램의 코드를 가져다 씀).

상자로 그릴 것 (nodes):
- 따로 켜지는 프로그램 하나가 상자 하나다(kind "program"). 같은 저장소 안에 있어도 따로 켜지면 따로 그린다. 저장소 단위로 묶지 않는다.
- 데이터베이스·파일 보관소처럼 이 서비스가 직접 띄우는 저장소(kind "store").
- 쓰는 쪽(kind "user"): 사람의 종류(권한이 코드에 있으면 그것), 그리고 이 서비스를 직접 부르는 다른 프로그램.
- 저장소의 커밋이 아니라 복사본으로 도는 코드가 있으면 그것(kind "copy").
- 다른 덩어리와 주고받는 것이 없는 프로그램(백업, 터널 등)은 nodes 가 아니라 others 에 적는다.
- 돈을 내고 쓰는 남의 서비스는 nodes 가 아니라 externals 에 적는다.

모르는 것은 지어내지 않는다. 저장소에서 읽을 수 없는 것은 unknown 에 적는다:
  needs "ops" = 운영 서버에 접속해야만 알 수 있음, "read" = 다른 저장소 등 여기서 읽지 못함.

근거: nodes·externals·links·others 의 항목마다 ev 를 1개 이상 붙인다. {{"file": 경로, "line": 줄 번호, "quote": 그 줄에 적힌 글자를 그대로 복사한 토막(8자 이상)}}.
quote 는 반드시 그 줄에 실제로 있는 글자여야 한다. 나중에 기계가 대조해서 없으면 그 항목을 버린다. 줄 번호는 `git grep -n` 이나 `git show ... | cat -n` 으로 확인한다.

글: name 은 짧은 한국어 이름(2~4어절). what 과 label 은 쉬운 한국어 한 문장. 함수명·변수명을 쓰지 않는다. 제품·회사 이름은 그대로 쓴다.

마지막에 JSON 하나만 출력한다. 형식:
{{
 "nodes": [{{"id": "영문 소문자", "name": "", "kind": "user|program|store|copy", "what": "",
            "origin": "repo|other|copy|none",   (program·store·copy 만. repo=이 저장소, other=다른 저장소, copy=복사본을 끼워 씀, none=저장소가 없음)
            "origin_text": "코드가 어디에 있는지 한 줄",
            "code": ["이 프로그램의 코드가 있는 폴더"],  (이 저장소에 코드가 있는 program 마다. 서버 본체도 적는다. 다른 프로그램 폴더와 겹치지 않게 가장 좁게)
            "uses": ["externals 의 id"], "unknown": [{{"text": "", "needs": "ops|read"}}], "ev": [...]}}],
 "externals": [{{"id": "", "name": "", "what": "", "ev": [...]}}],
 "links": [{{"from": "node id", "to": "node id", "label": "무엇을 주고받는지", "style": "" 또는 "copy"(부르는 것이 아니라 코드·설정을 같이 쓰는 사이), "sure": "code"(코드에서 확인) 또는 "doc"(문서로만 확인), "ev": [...]}}],
 "others": [{{"name": "", "what": "", "ev": [...]}}],
 "unknown": [{{"text": "", "needs": "ops|read"}}]
}}"""

print(f"에이전트가 {REPO} 의 {REF} 를 읽는 중… (몇 분 걸린다)", flush=True)
out = subprocess.run(["claude", "-p", "--output-format", "text", "--model", "opus",
                      "--allowedTools", "Bash(git ls-tree:*)", "Bash(git show:*)", "Bash(git grep:*)", "Bash(git log:*)",
                      "--", PROMPT], cwd=REPO, capture_output=True, text=True, timeout=1800)
mm = re.search(r"\{.*\}", out.stdout, re.S)
if not mm:
    sys.exit("에이전트 출력에 JSON이 없다:\n" + out.stdout[-600:] + out.stderr[-400:])
data = json.loads(mm.group(0))

# --- 근거 대조: 그 줄(±2)에 그 토막이 있는가 ---
norm = lambda t: re.sub(r"\s+", "", t or "")
_src = {}
def check(ev):
    f, ln, q = ev.get("file"), ev.get("line"), norm(ev.get("quote"))
    if not f or not isinstance(ln, int) or len(q) < 6:
        return False
    lines = _src.setdefault(f, git("show", f"{REF}:{f}").splitlines())
    return any(q in norm(l) for l in lines[max(0, ln - 3):ln + 2])

stats = {"kept": 0, "dropped": []}
def keep(items, what):
    good = []
    for it in items or []:
        evs = [dict(e, ok=True) for e in it.get("ev", []) if check(e)]
        if evs:
            it["ev"] = evs; good.append(it); stats["kept"] += 1
        else:
            stats["dropped"].append(f"{what}: {it.get('name') or it.get('label') or it.get('id')}")
    return good

nodes = keep(data.get("nodes"), "상자")
ids = {n["id"] for n in nodes}
externals = keep(data.get("externals"), "바깥 서비스")
ext_ids = {x["id"] for x in externals}
links = [l for l in keep(data.get("links"), "선") if l.get("from") in ids and l.get("to") in ids and l["from"] != l["to"]]
for n in nodes:
    n["kind"] = n.get("kind") if n.get("kind") in ("user", "program", "store", "copy") else "program"
    n["uses"] = [u for u in n.get("uses", []) if u in ext_ids]
    if n["kind"] == "user":
        n.pop("origin", None)
    elif n.get("origin") not in ("repo", "other", "copy", "none"):
        n["origin"] = "repo"

# --- 자리: 쓰는 쪽은 1열, 나머지는 쓰는 쪽에서 선을 몇 번 건너야 닿는지로 2~3열. 바깥 서비스는 화면이 4열에 따로 놓는다 ---
depth = {n["id"]: 0 for n in nodes if n["kind"] == "user"}
front = list(depth)
while front:
    nxt = []
    for a in front:
        for l in links:
            b = l["to"] if l["from"] == a else l["from"] if l["to"] == a else None
            if b and b not in depth:
                depth[b] = depth[a] + 1; nxt.append(b)
    front = nxt
rows = {}
for n in nodes:
    col = 1 if n["kind"] == "user" else min(max(depth.get(n["id"], 2), 1), 2) + 1
    rows[col] = rows.get(col, 0) + 1
    n["col"], n["row"] = col, rows[col]

system = {"source": "ai", "written": "에이전트가 저장소를 읽어 적음", "commit": git("rev-parse", "--short=8", REF).strip(), "checked": git("rev-parse", "--short=8", REF).strip(),
          "nodes": nodes, "externals": externals, "links": links, "others": keep(data.get("others"), "그림 밖"), "unknown": data.get("unknown", [])}
os.makedirs(HOME, exist_ok=True)
path = os.path.join(HOME, "system.json")
if os.path.exists(path) and json.load(open(path)).get("source") != "ai" and not FORCE:
    path = os.path.join(HOME, "system.ai.json")
json.dump(system, open(path, "w"), ensure_ascii=False, indent=1)
print(f"{os.path.basename(path)}: 상자 {len(nodes)}, 선 {len(links)}, 바깥 서비스 {len(externals)}, 그림 밖 {len(system['others'])}, 모르는 것 {len(system['unknown'])}")
print(f"근거 대조 통과 {stats['kept']}, 버린 것 {len(stats['dropped'])}" + ("".join("\n  - " + d for d in stats["dropped"])))
