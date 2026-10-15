#!/usr/bin/env python3
"""새로고침 한 번. 앱의 ↻ 버튼과 에이전트 연결(mcp_server.py)이 같이 쓴다.

사용: refresh.py <프로젝트 이름> [저장소 경로] [수집 기준 일수=7]
1. git fetch 뒤 origin/dev·main 커밋이 지도의 기준 커밋과 다르면 지도를 다시 뽑는다(extract.py 가 전 지도를 .prev 로 남긴다).
2. collect.py 로 PR·브랜치·이슈·세션을 모으고 AI 가 적은 것의 근거 줄을 대조한다.
3. 지난 새로고침 뒤에 달라진 것을 changes.json 에 한 건으로 남긴다(달라진 것이 없으면 남기지 않는다).
"""
import json, os, subprocess, sys
from datetime import datetime, timedelta, timezone
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import mapcore

PROJECT = sys.argv[1]
HOME = os.path.join(mapcore.ROOT, PROJECT)
REPO = sys.argv[2] if len(sys.argv) > 2 else json.load(open(os.path.join(HOME, "dev.json")))["repo"]
SINCE = sys.argv[3] if len(sys.argv) > 3 else "7"
NOW = datetime.now(timezone.utc)


def run(*a):
    p = subprocess.run([sys.executable, *a], capture_output=True, text=True)
    if p.returncode: sys.exit(p.stderr[-800:])
    return p.stdout


git = lambda *a: subprocess.run(["git", "-C", REPO, *a], capture_output=True, text=True).stdout.strip()
git("fetch", "-q", "origin")
log, moved = "", {}
for b in ("dev", "main"):
    path = os.path.join(HOME, b + ".json")
    cur = json.load(open(path)) if os.path.exists(path) else {}
    have = cur.get("commit")
    now = git("rev-parse", "--short", f"origin/{b}")
    if have != now:
        log += run(os.path.join(HERE, "extract.py"), REPO, f"origin/{b}", path); moved[b] = (have, now)
    elif cur.get("extractor") != mapcore.extractor_id(HOME):  # 테스트 규칙 등 뽑는 방법만 바뀌었으면 같은 커밋을 다시 뽑는다
        log += run(os.path.join(HERE, "extract.py"), REPO, f"origin/{b}", path)
    else:
        log += f"origin/{b} ({now}) 그대로\n"
log += run(os.path.join(HERE, "collect.py"), REPO, PROJECT, SINCE)

# --- 지난 새로고침 뒤에 달라진 것 ---
cpath = os.path.join(HOME, "changes.json")
ch = json.load(open(cpath)) if os.path.exists(cpath) else {"entries": []}
since = datetime.fromisoformat(ch["last_refresh"]) if ch.get("last_refresh") else NOW - timedelta(days=1)
entry = {"at": NOW.isoformat(), "since": since.isoformat(), "branches": {}, "prs": [], "ai_stale": {}}
for b, (old, new) in moved.items():
    prev = os.path.join(HOME, b + ".prev.json")
    if old and os.path.exists(prev):
        pm, cm = json.load(open(prev)), json.load(open(os.path.join(HOME, b + ".json")))
        if pm.get("extractor") != cm.get("extractor"):  # 뽑는 방법이 바뀌었으면 전 커밋을 지금 방법으로 다시 뽑아 비교한다
            run(os.path.join(HERE, "extract.py"), REPO, pm["commit"], prev)
        d = mapcore.diff(mapcore.Map(PROJECT, b, json.load(open(prev))), mapcore.Map(PROJECT, b))
        entry["branches"][b] = {"from": old, "to": new, **d}
m = mapcore.Map(PROJECT, "dev")
def place(p):  # 화면에 안 걸리는 PR 의 자리
    fs = p["files"]
    if p.get("common_files"): return ["여러 화면에 똑같이 들어 있는 부품"]
    if any(f.startswith("frontend/src/") and ".test." not in f for f in fs): return ["앱 전체에 걸친 화면 부품"]
    if fs and all(f.endswith(".md") or f.startswith(("docs/", "artifacts/")) for f in fs): return ["문서"]
    if any(f.startswith((".github/", "Makefile", "docker")) for f in fs): return ["배포·CI"]
    return []
for p in m.status.get("merged_prs", []):
    if not p.get("merged_at") or datetime.fromisoformat(p["merged_at"].replace("Z", "+00:00")) <= since: continue
    owners = sorted({o["name"] for f in p["files"] if (o := m.owner_of(f)) and o.get("kind") == "program" and not f.startswith("frontend/")})
    entry["prs"].append({"number": p["number"], "title": p["title"], "url": p["url"], "base": p["base"], "merged_at": p["merged_at"], "author": p.get("author"),
                         "kinds": mapcore.pr_kind(p["files"]), "screens": p["screens"], "groups": sorted({g for s in p["screens"] if (g := m.group_of(s))}) or place(p),
                         "programs": owners, "files": len(p["files"]), "issues": sorted({i["number"] for i in p.get("issues", [])} | set(p.get("refs", [])))})
def stale(obj):
    n = 0
    if isinstance(obj, dict):
        n += obj.get("ok") is False
        for v in obj.values(): n += stale(v)
    elif isinstance(obj, list):
        for v in obj: n += stale(v)
    return n
for name in ("system", "jobs"):
    if (d := mapcore._read(PROJECT, name)) and (k := stale(d)): entry["ai_stale"][name] = k
changed = entry["prs"] or any(v[k] for v in entry["branches"].values() for k in v if k not in ("from", "to"))
if changed:
    ch["entries"] = ([entry] + ch["entries"])[:30]
ch["last_refresh"] = NOW.isoformat()
json.dump(ch, open(cpath, "w"), ensure_ascii=False, indent=1)
print(log + (f"달라진 것: PR {len(entry['prs'])}, " + ", ".join(f"{b} {v['from']}→{v['to']}" for b, v in entry["branches"].items()) if changed else "지난 새로고침 뒤 달라진 것 없음"))
