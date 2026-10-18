#!/usr/bin/env python3
"""수집. git 과 GitHub 를 읽어 "어제 이후" 상태를 만든다.

사용: collect.py <저장소 경로> <프로젝트 이름> [기준: 일수 또는 ISO 시각, 기본 7]
결과: ~/.where-were-we/<프로젝트>/status.json
읽기만 한다. 저장소에는 git fetch 외에 아무것도 쓰지 않는다.
"""
import json, os, re, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mapcore
from collections import defaultdict
from datetime import datetime, timedelta, timezone

REPO, PROJECT = sys.argv[1], sys.argv[2]
STALE_DAYS = 14
REFS = mapcore.configured_refs()
PINNED = json.loads(os.environ.get("WHERE_WERE_WE_COMMITS", "{}"))
BASE = PINNED.get("dev") or PINNED.get("main") or REFS.get("dev") or REFS.get("main")
HOME = mapcore.project_home(PROJECT)
NOW = datetime.now(timezone.utc)
_arg = sys.argv[3] if len(sys.argv) > 3 else "7"
SINCE = NOW - timedelta(days=float(_arg)) if _arg.replace(".", "").isdigit() else datetime.fromisoformat(_arg.replace("Z", "+00:00"))


def sh(*args, cwd=REPO):
    result = subprocess.run(args, cwd=cwd, capture_output=True, text=True)
    if result.returncode:sys.exit(result.stderr.strip() or "Collection command failed")
    return result.stdout


def git(*args, cwd=REPO):
    return sh("git", "-c", "core.quotepath=off", *args, cwd=cwd)


def github_json(*args,fields):
    command=["gh",*args,"--json",fields]
    result=subprocess.run(command,cwd=REPO,capture_output=True,text=True)
    if result.returncode:
        if os.environ.get('WHERE_WERE_WE_GITHUB'):
            import project
            sys.exit(str(project.github_error(json.loads(os.environ['WHERE_WERE_WE_GITHUB']),'repository')))
        sys.exit(result.stderr.strip() or 'GitHub collection failed')
    out=result.stdout
    return json.loads(out or "[]")

def gh(*args):
    return github_json(*args,fields="number,title,headRefName,baseRefName,url,author,createdAt,updatedAt,mergedAt,files,closingIssuesReferences,body")


def iso(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")) if s else None


# 파일 → 화면. dev 와 main 지도의 합집합.
file_screens = defaultdict(set)
for b in ("dev", "main"):
    p = os.path.join(HOME, f"{b}.json")
    if os.path.exists(p):
        for f, scr in json.load(open(p)).get("file_screens", {}).items():
            file_screens[f].update(scr)


# 화면의 1/3 넘게 닿는 파일은 공통 파일이다. 어느 화면의 변경이라고 말할 수 없으니 따로 센다.
TOTAL_SCREENS = len({s for v in file_screens.values() for s in v}) or 1
COMMON = {f for f, v in file_screens.items() if len(v) > TOTAL_SCREENS / 3}

def screens_of(files):
    s = set()
    for f in files:
        if f not in COMMON:
            s.update(file_screens.get(f, ()))
    return sorted(s)


def common_of(files):
    return sorted(f for f in files if f in COMMON)


if not PINNED: git("fetch", "-q", "origin")

# --- PR ---
def pr_row(pr):
    files = [f["path"] for f in pr.get("files") or []]
    return {"number": pr["number"], "title": pr["title"], "body":pr.get("body", ""), "url": pr["url"], "branch": pr["headRefName"], "base": pr["baseRefName"],
            "author": (pr.get("author") or {}).get("login"), "created_at": pr["createdAt"], "updated_at": pr["updatedAt"], "merged_at": pr.get("mergedAt"),
            "files": files, "screens": screens_of(files), "common_files": common_of(files),
            "issues": [{"number": i["number"], "title": i.get("title"), "url":i.get("url")} for i in pr.get("closingIssuesReferences") or []],
            "refs": sorted({int(n) for n in re.findall(r"(?<![\w/])#(\d+)\b", (pr.get("title") or "") + " " + (pr.get("body") or ""))})}

merged_input = gh("pr", "list", "--state", "merged", "--limit", "200", "--search", f"merged:>={SINCE.date().isoformat()}")
merged = [pr_row(p) for p in merged_input if SINCE <= iso(p["mergedAt"]) <= NOW]
open_input=gh("pr", "list", "--state", "open", "--limit", "100")
open_prs = [pr_row(p) for p in open_input]
for p in open_prs:
    p["stale"] = (NOW - iso(p["updated_at"])).days >= STALE_DAYS

# --- 원격 브랜치 ---
branches = []
pr_branches = {p["branch"] for p in open_prs}
for line in git("for-each-ref", "--sort=-committerdate", "--format=%(refname:short)\t%(committerdate:iso-strict)\t%(authorname)", "refs/remotes/origin").splitlines():
    ref, date, author = line.split("\t")
    name = ref[len("origin/"):]
    if ref in REFS.values() or name in ("HEAD", ""):
        continue
    ahead = git("rev-list", "--count", f"{BASE}..{ref}").strip()
    files = git("diff", "--name-only", f"{BASE}...{ref}").split()
    age = (NOW - iso(date)).days
    branches.append({"name": name, "last_commit_at": date, "author": author, "age_days": age, "ahead_of_dev": int(ahead or 0),
                     "files": files, "screens": screens_of(files), "has_open_pr": name in pr_branches, "stale": age >= STALE_DAYS})

# --- 이 맥의 작업 폴더와 커밋하지 않은 변경 ---
worktrees = []
cur = {}
# App storage has no checkout and is not a user work folder.
for line in ([] if os.environ.get("WHERE_WERE_WE_MANAGED_CODE")=="1" else git("worktree", "list", "--porcelain").splitlines()) + [""]:
    if not line:
        if cur.get("path") and not cur.get("bare"):
            files = [l[3:] for l in git("status", "--porcelain", cwd=cur["path"]).splitlines()]
            worktrees.append({"path": cur["path"], "branch": cur.get("branch", "").replace("refs/heads/", ""), "uncommitted": files, "screens": screens_of(files)})
        cur = {}
    elif line.startswith("worktree "):
        cur["path"] = line[9:]
    elif line.startswith("branch "):
        cur["branch"] = line[7:]
    elif line == "bare":
        cur["bare"] = True

# --- 겹침: 같은 파일을 열린 PR·앞선 브랜치·작업 폴더가 동시에 건드림 ---
owners = defaultdict(set)
for p in open_prs:
    for f in p["files"]: owners[f].add(f"PR #{p['number']}")
for b in branches:
    if b["ahead_of_dev"] and not b["stale"] and not b["has_open_pr"]:
        for f in b["files"]: owners[f].add(f"브랜치 {b['name']}")
for w in worktrees:
    for f in w["uncommitted"]: owners[f].add(f"폴더 {os.path.basename(w['path'])}")
# 같은 두 작업이 겹치는 파일을 묶어 한 줄로. 파일마다 한 줄이면 clone 브랜치 둘이 수백 줄을 만든다.
pairs = defaultdict(list)
for f, o in owners.items():
    if len(o) >= 2:
        pairs[tuple(sorted(o))].append(f)
overlaps = [{"owners": list(k), "files": sorted(v), "screens": screens_of(v)} for k, v in sorted(pairs.items(), key=lambda kv: -len(kv[1]))]

# Evidence may legitimately refer to a deleted source file.
_source_files = set(git("ls-tree", "-r", "--name-only", BASE).splitlines())
def source_at(file):
    return git("show", BASE + ":" + file) if file in _source_files else ""

# --- 전체 구조(system.json)의 근거 줄이 지금 코드에 그대로 있는지 대조 ---
sys_path = os.path.join(HOME, "system.json")
if os.path.exists(sys_path):
    system = json.load(open(sys_path)); cache = {}; n = miss = 0
    def walk(x):
        if isinstance(x, dict):
            yield x
            for v in x.values(): yield from walk(v)
        elif isinstance(x, list):
            for v in x: yield from walk(v)
    jpath = os.path.join(HOME, "jobs.json"); jobs = json.load(open(jpath)) if os.path.exists(jpath) else None
    norm = lambda t: "".join((t or "").split())
    for ev in [*walk(system), *(walk(jobs) if jobs else [])]:
        if "quote" not in ev or ev.get("repo") or not isinstance(ev.get("line"), int): continue  # 다른 저장소의 근거는 대조하지 않는다
        lines = cache.setdefault(ev["file"], source_at(ev["file"]).splitlines())
        ev["ok"] = any(norm(ev["quote"]) in norm(l) for l in lines[max(0, ev["line"] - 3):ev["line"] + 2])
        n += 1; miss += not ev["ok"]
    if jobs: json.dump(jobs, open(jpath, "w"), ensure_ascii=False, indent=1)
    # 서버 말고 DB를 직접 쓰는 프로그램(code 경로가 적힌 상자)이 닿는 테이블. 그 파일들과, 거기서 가져다 쓰는 서버 services 모듈 한 단계에서 모델 이름을 찾는다.
    import re
    models = json.load(open(os.path.join(HOME, "dev.json" if REFS.get("dev") else "main.json"))).get("models", {})
    for node in system["nodes"]:
        if not node.get("code"): continue
        files = [f for c in node["code"] for f in git("ls-tree", "-r", "--name-only", BASE, c).splitlines() if f.endswith(".py")]
        text = "\n".join(source_at(f) for f in files)
        mods = set(re.findall(r"backend\.app\.services\.(\w+)", text))
        for m in re.finditer(r"from backend\.app\.services import ([\w, ]+)", text): mods |= {x.split()[0] for x in m.group(1).split(",") if x.strip()}
        backend_root = json.loads(os.environ.get('WHERE_WERE_WE_LAYOUT', '{}')).get('backend') or ('app' if 'app/main.py' in _source_files else 'backend/app')
        text += "\n".join(source_at(f"{backend_root}/services/{m}.py") for m in sorted(mods))
        node["tables"] = sorted({t for c, t in models.items() if re.search(rf"\b{c}\b", text)})
        print(f"{node['name']}: 파일 {len(files)}개 + services {len(mods)}개에서 테이블 {len(node['tables'])}개")
    # 사본: 다른 저장소에 기록된 사본 브랜치마다, 그 안에 든 이 저장소 파일이 이 저장소의 판과 같은지. 다르면 두 판이 함께 도는 것이다.
    for node in system["nodes"]:
        sn = node.get("snapshots")
        if not sn: continue
        names = [b["name"] for b in json.loads(sh("gh", "api", f"repos/{sn['repo']}/branches?per_page=100") or "[]") if b["name"].startswith(sn["prefix"])]
        node["copies"] = []
        for b in names:
            ref = next((r for k, r in sn.get("against", {}).items() if k in b), BASE)
            tree = json.loads(sh("gh", "api", f"repos/{sn['repo']}/git/trees/{b}?recursive=1") or "{}").get("tree", [])
            files = []
            for t in tree:
                if t["type"] != "blob" or "/" not in t["path"]: continue  # 맨 위 README 같은 것은 같은 이름이라도 다른 파일이다
                lookup = subprocess.run(["git", "-C", REPO, "rev-parse", "-q", "--verify", f"{ref}:{t['path']}"],capture_output=True,text=True)
                if lookup.returncode not in (0,1):sys.exit(lookup.stderr)
                mine = lookup.stdout.strip() if lookup.returncode == 0 else ""
                if mine: files.append({"path": t["path"], "same": mine == t["sha"]})
            node["copies"].append({"branch": b, "against": ref, "files": files})
        print(f"{node['name']}: 사본 {len(names)}개, 이 저장소 파일과 다른 판 " + ", ".join(f"{c['branch']} {sum(not f['same'] for f in c['files'])}/{len(c['files'])}" for c in node["copies"]))
    system["checked"] = git("rev-parse", "--short=8", BASE).strip()
    json.dump(system, open(sys_path, "w"), ensure_ascii=False, indent=1)
    print(f"AI가 적은 것(전체 구조·하는 일)의 근거 {n}줄 대조, 달라진 것 {miss}")

# --- 이슈(R7): 열린 이슈를 화면에 잇는다. PR 이 그 이슈 번호를 적었으면 확정, 이슈 글에 화면 주소·서버 주소·파일 이름이 나오면 후보 ---
dev_map = json.load(open(os.path.join(HOME, "dev.json" if REFS.get("dev") else "main.json"))) if os.path.exists(os.path.join(HOME, "dev.json" if REFS.get("dev") else "main.json")) else {"screens": [], "api_functions": [], "backend_routes": []}
fn_ix = {(f["file"], f["name"]): f for f in dev_map["api_functions"]}
route_screens = defaultdict(set)
for sc in dev_map["screens"]:
    for ref in sc.get("api_functions", []):
        for c in fn_ix.get((ref["file"], ref["name"]), {}).get("calls", []):
            for b in c["backend"]:
                route_screens[(b["file"], b["line"])].add(sc["path"])
def pattern(path, var):
    lits = [p for p in path.split("/") if p and not re.fullmatch(var, p)]
    if len(lits) < 2: return None  # 고정 글자 조각이 둘 이상인 주소만. "/projects/:id" 같은 것은 너무 흔하다
    return re.compile("".join("/" + ("[^/\\s]+" if re.fullmatch(var, p) else re.escape(p)) for p in path.split("/") if p) + r"(?![\w-])")
needles = []  # (정규식, 화면들, 무엇으로 맞았나)
for sc in dev_map["screens"]:
    if not sc.get("redirect") and (pt := pattern(sc["path"], r":\w+")): needles.append((pt, {sc["path"]}, sc["path"]))
for r in dev_map["backend_routes"]:
    if (scr := route_screens.get((r["file"], r["line"]))) and (pt := pattern(r["path"], r"\{\}")): needles.append((pt, scr, r["method"] + " " + r["path"]))
for f, scr in file_screens.items():
    base = os.path.basename(f)
    if len(base) >= 12 and f not in COMMON: needles.append((re.compile(r"(?<![\w.])" + re.escape(base) + r"\b"), set(scr), base))
by_issue = defaultdict(list)
for p in open_prs + merged:
    for n in {i["number"] for i in p["issues"]} | set(p["refs"]):
        by_issue[n].append(p)
issues = []
issue_input=github_json("issue","list","--state","open","--limit","300",fields="number,title,body,url")
for i in issue_input:
    prs = [p for p in by_issue.get(i["number"], []) if p["number"] != i["number"]]
    if prs:
        scr, via, hits = sorted({s for p in prs for s in p["screens"]}), "pr", [f"PR #{p['number']}" for p in prs]
    else:
        text = (i.get("title") or "") + "\n" + (i.get("body") or "")
        found = [(s, w) for rx, s, w in needles if rx.search(text)]
        scr, via, hits = sorted({x for s, _ in found for x in s}), "text" if found else None, sorted({w for _, w in found})
    issues.append({"number": i["number"], "title": i["title"], "body":i.get("body", ""), "state":"OPEN", "url": i["url"], "via": via, "hits": hits[:6], "screens": scr})
print(f"열린 이슈 {len(issues)}: PR로 이어짐 {sum(i['via'] == 'pr' for i in issues)}, 글로 후보 {sum(i['via'] == 'text' for i in issues)}, 연결 안 됨 {sum(i['via'] is None for i in issues)}")

linked_issues=[]
known_urls={i['url'] for i in issues}
for pr in merged:
    for issue in pr['issues']:
        url=issue.get('url')
        if not url or url in known_urls or not re.fullmatch(r'https://github\.com/[^/\s]+/[^/\s]+/issues/[0-9]+',url):continue
        known_urls.add(url)
        try:linked_issues.append(github_json('issue','view',url,fields='number,title,body,url,state'))
        except SystemExit:linked_issues.append({**issue,'body':'','unavailable':True})
collection={key:{'limit':limit,'count':len(rows),'possibly_truncated':len(rows)>=limit}
            for key,limit,rows in [('merged_prs',200,merged_input),('open_prs',100,open_input),('issues',300,issue_input)]}
collection['pr_files']={'limit':100,'possibly_truncated':any(len(p.get('files',[]))>=100 for p in merged_input)}
collection['linked_issues']={'unavailable':sum(bool(i.get('unavailable')) for i in linked_issues)}
out = {"generated_at": NOW.isoformat(), "since": SINCE.isoformat(), "stale_days": STALE_DAYS,
       "merged_prs": merged, "open_prs": open_prs, "issues": issues, "linked_issues":linked_issues, "collection":collection, "branches": branches, "worktrees": worktrees, "overlaps": overlaps}
os.makedirs(HOME, exist_ok=True)
json.dump(out, open(os.path.join(HOME, "status.json"), "w"), ensure_ascii=False, indent=1)
print(f"{SINCE.date()} 이후 병합 PR {len(merged)}, 열린 PR {len(open_prs)} (멈춤 {sum(p['stale'] for p in open_prs)}), "
      f"원격 브랜치 {len(branches)} (멈춤 {sum(b['stale'] for b in branches)}), 작업 폴더 {len(worktrees)}, 겹치는 파일 {len(overlaps)}")
