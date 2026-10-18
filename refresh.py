#!/usr/bin/env python3
"""새로고침 한 번. 앱의 ↻ 버튼과 에이전트 연결(mcp_server.py)이 같이 쓴다.

사용: refresh.py <프로젝트 이름> [저장소 경로] [수집 기준 일수=7]
1. git fetch 뒤 origin/dev·main 커밋이 지도의 기준 커밋과 다르면 지도를 다시 뽑는다(extract.py 가 전 지도를 .prev 로 남긴다).
2. collect.py 로 PR·브랜치·이슈를 모으고 AI 가 적은 것의 근거 줄을 대조한다.
3. 설정에서 고른 기준 시각 뒤에 달라진 것을 changes.json 에 한 건으로 남긴다.
"""
import json, os, subprocess, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import mapcore

PROJECT = sys.argv[1]
if os.path.exists(os.path.join(mapcore.ROOT, PROJECT, "project.json")):
    import project
    print(project.refresh_project(PROJECT, since=sys.argv[3] if len(sys.argv) > 3 else "7"))
    sys.exit(0)
HOME = os.path.join(mapcore.ROOT, PROJECT)
REPO = sys.argv[2] if len(sys.argv) > 2 else json.load(open(os.path.join(HOME, "dev.json")))["repo"]
SINCE = sys.argv[3] if len(sys.argv) > 3 else "7"
NOW = datetime.now(timezone.utc)


def run(*a):
    p = subprocess.run(mapcore.python_command(*a), capture_output=True, text=True)
    if p.returncode: sys.exit(p.stderr[-800:])
    return p.stdout


def git(*args):
    result = subprocess.run(["git", "-C", REPO, *args], capture_output=True, text=True)
    if result.returncode:sys.exit(result.stderr.strip() or "Git command failed")
    return result.stdout.strip()
git("fetch", "-q", "origin")
PINNED = {role: git("rev-parse", "--verify", ref + "^{commit}") for role,ref in mapcore.configured_refs().items() if ref}
os.environ["WHERE_WERE_WE_COMMITS"] = json.dumps(PINNED)
log, moved = "", {}
for b in ("dev", "main"):
    ref = PINNED.get(b)
    if not ref: continue
    path = os.path.join(HOME, b + ".json")
    cur = json.load(open(path)) if os.path.exists(path) else {}
    have = cur.get("commit")
    now = git("rev-parse", "--short", ref)
    if (cur.get('analysis') or {}).get('source')=='ai':
        # A normal refresh must not spend the user's AI quota or erase an AI map.
        cur['analysis']['observed_commit']=ref
        cur['analysis']['stale']=have not in (now,ref)
        import ai_extract
        ai_extract.refresh_test_links(cur,mapcore.tests_conf(HOME))
        import project as project_store
        project_store.atomic(Path(path),cur)
        log += f"{b}: AI map retained; " + ("AI analysis required\n" if cur['analysis']['stale'] else "current\n")
        continue
    if have != now:
        log += run(os.path.join(HERE, "extract.py"), REPO, ref, path); moved[b] = (have, now)
    elif cur.get("extractor") != mapcore.extractor_id(HOME):  # 테스트 규칙 등 뽑는 방법만 바뀌었으면 같은 커밋을 다시 뽑는다
        log += run(os.path.join(HERE, "extract.py"), REPO, ref, path)
    else:
        log += f"origin/{b} ({now}) 그대로\n"
# --- 설정에서 고른 기준 시각 뒤에 달라진 것 ---
cpath = os.path.join(HOME, "changes.json")
ch = json.load(open(cpath)) if os.path.exists(cpath) else {"entries": []}
since, since_note = mapcore.since_of(REPO, datetime.fromisoformat(ch['last_refresh']) if ch.get('last_refresh') else None, NOW)
days = max(int(SINCE), (NOW-since).days+2)
log += run(os.path.join(HERE, 'collect.py'), REPO, PROJECT, str(days))
entry = {"at": NOW.isoformat(), "since": since.isoformat(), "since_note":since_note, "branches": {}, "prs": [], "ai_stale": {}}

def base_map(branch, commit):
    for name in (branch+'.prev.json', branch+'.base.json'):
        path=os.path.join(HOME,name)
        if os.path.exists(path):
            value=json.loads(Path(path).read_text())
            if value.get('commit') and commit.startswith(value['commit']) and value.get('extractor')==mapcore.extractor_id(HOME) and (value.get('analysis') or {}).get('source')!='ai':return value
    path=os.path.join(HOME,branch+'.base.json')
    run(os.path.join(HERE,'extract.py'),REPO,commit,path)
    return json.loads(Path(path).read_text())

for branch, pinned in PINNED.items():
    cur=mapcore._read(PROJECT,branch) or {}
    base=git('rev-list','-1','--before='+since.isoformat(),pinned)
    if not base or not cur.get('commit') or base==pinned:continue
    if (cur.get('analysis') or {}).get('source')=='ai':
        # Compare like extractors without overwriting the saved AI map or calling AI.
        path=os.path.join(HOME,branch+'.current-basic.json')
        run(os.path.join(HERE,'extract.py'),REPO,pinned,path)
        cur=json.loads(Path(path).read_text())
        log += branch+': structural comparison uses basic collection; AI-only details require agent analysis\n'
    delta=mapcore.diff(mapcore.Map(PROJECT,branch,base_map(branch,base)),mapcore.Map(PROJECT,branch,cur))
    entry['branches'][branch]={'from':base[:8],'to':pinned[:8],'scope':'basic',**delta}
m = mapcore.Map(PROJECT, "dev" if os.path.exists(os.path.join(HOME,"dev.json")) else "main")
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
changed = entry["prs"] or any(v[k] for v in entry["branches"].values() for k in v if k not in ("from", "to", "scope"))
if changed:
    ch["entries"] = ([entry] + ch["entries"])[:30]
ch["last_refresh"] = NOW.isoformat()
ch['last_result']={'at':NOW.isoformat(),'since':since.isoformat(),'since_note':since_note,'changed':bool(changed),'scope':'basic'}
json.dump(ch, open(cpath, "w"), ensure_ascii=False, indent=1)
print(log + (f"달라진 것: PR {len(entry['prs'])}, " + ", ".join(f"{b} {v['from']}→{v['to']}" for b, v in entry["branches"].items()) if changed else f"{since_note} 달라진 것 없음"))
