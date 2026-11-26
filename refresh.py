#!/usr/bin/env python3
"""저장소 하나의 새로고침. project.py refresh 가 수집 단계 폴더에서 저장소마다 부른다.

사용: refresh.py <저장소 ID> <저장소 경로> [수집 기준 일수=7]
1. git fetch 뒤 origin/dev·main 커밋이 지도의 기준 커밋과 다르면 지도를 다시 뽑는다(extract.py 가 전 지도를 .prev 로 남긴다).
2. collect.py 로 PR·브랜치·이슈를 모으고 AI 가 적은 것의 근거 줄을 대조한다.
3. 설정에서 고른 기준 시각 뒤에 달라진 것을 changes.json 에 한 건으로 남긴다.
"""
import hashlib, json, os, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import mapcore
import project as project_store

PROJECT = sys.argv[1]
HOME = os.path.join(mapcore.ROOT, PROJECT)
REPO = sys.argv[2]
SINCE = sys.argv[3] if len(sys.argv) > 3 else "7"
NOW = datetime.now(timezone.utc)

GITHUB_ORIGIN = project_store.github_origin(REPO)


def run(*a):
    p = subprocess.run(mapcore.python_command(*a), capture_output=True, text=True)
    if p.returncode: sys.exit(p.stderr[-800:])
    return p.stdout


def git(*args):
    result = subprocess.run(["git", "-C", REPO, *args], capture_output=True, text=True)
    if result.returncode:
        if args and args[0]=='fetch' and os.environ.get('WHERE_WERE_WE_GITHUB'):
            sys.exit(str(project_store.github_error(json.loads(os.environ['WHERE_WERE_WE_GITHUB']),'fetch')))
        sys.exit(result.stderr.strip() or "Git command failed")
    return result.stdout.strip()
if 'WHERE_WERE_WE_REMOTE_STATUS' not in os.environ and not GITHUB_ORIGIN:
    os.environ['WHERE_WERE_WE_REMOTE_STATUS']='not_configured'
has_origin=subprocess.run(['git','-C',REPO,'remote','get-url','origin'],capture_output=True).returncode==0
if has_origin and os.environ.get('WHERE_WERE_WE_REMOTE_STATUS')!='unavailable':
    git("fetch", "-q", "origin")
if os.environ.get("WHERE_WERE_WE_MANAGED_CODE")=="1":git("remote", "set-head", "origin", "-a")
PINNED = {role: git("rev-parse", "--verify", ref + "^{commit}") for role,ref in mapcore.configured_refs().items() if ref}
os.environ["WHERE_WERE_WE_COMMITS"] = json.dumps(PINNED)
log, moved = "", {}
extracted = {}
refs = mapcore.configured_refs()
EXTRACTOR = mapcore.extractor_id(HOME)

def extract_basic(commit, destination):
    """Multiple roles and comparisons can point at one immutable tree in this refresh."""
    previous = extracted.get(commit)
    if previous and previous != destination:
        basic = project_store.read(Path(previous))
        if basic and (basic.get('inventory') or {}).get('commit') == commit:
            target = Path(destination)
            old = project_store.read(target)
            if old and old.get('commit') != basic['commit']:
                project_store.atomic(target.with_suffix('.prev.json'),old)
            project_store.atomic(target,{**basic,'ref':refs.get(target.stem,commit)})
            return f'{target.stem}: reused basic map for {commit[:8]}\n'
    output = run(os.path.join(HERE,'extract.py'),REPO,commit,destination)
    extracted[commit] = destination
    return output

for b in ("dev", "main"):
    ref = PINNED.get(b)
    if not ref: continue
    path = os.path.join(HOME, b + ".json")
    cur = json.load(open(path)) if os.path.exists(path) else {}
    have = cur.get("commit")
    now = git("rev-parse", "--short", ref)
    if (cur.get('analysis') or {}).get('source')=='ai':
        # A normal refresh must not spend the user's AI quota or erase an AI map.
        import ai_extract
        if ai_extract.carry_unchanged(cur,REPO,ref):have=ref  # identical tree: every saved input is proven unchanged
        if (cur.get('inventory') or {}).get('commit') != ref or 'paths' not in cur['inventory']:
            cur['inventory'] = mapcore.tree_inventory(mapcore.git_tree_entries(REPO, ref), ref)
        import structure_index
        if structure_index.outdated(cur.get('structure_index'), REPO, ref):
            cur['structure_index'] = structure_index.build(REPO, ref)
        cur['analysis']['observed_commit']=ref
        cur['analysis']['stale']=have not in (now,ref)
        ai_extract.refresh_test_links(cur,mapcore.tests_conf(HOME))
        project_store.atomic(Path(path),cur)
        log += f"{b}: AI map retained; " + ("AI analysis required\n" if cur['analysis']['stale'] else "current\n")
        continue
    if have != now:
        log += extract_basic(ref,path); moved[b] = (have, now)
    elif cur.get("extractor") != EXTRACTOR:  # 테스트 규칙 등 뽑는 방법만 바뀌었으면 같은 커밋을 다시 뽑는다
        log += extract_basic(ref,path)
    elif cur.get('structure_index') and __import__('structure_index').outdated(cur['structure_index'], REPO, ref):  # 새로 저장한 읽기 규칙(lang_rules)도 같은 커밋을 다시 읽게 한다
        log += extract_basic(ref,path)
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
            if value.get('commit') and commit.startswith(value['commit']) and value.get('extractor')==EXTRACTOR and (value.get('analysis') or {}).get('source')!='ai':return value
    path=os.path.join(HOME,branch+'.base.json')
    extract_basic(commit,path)
    return json.loads(Path(path).read_text())

BUNDLE=project_store.read_bundle(PROJECT,briefings=False)  # the comparison loop writes only .base/.current-basic files, outside the bundle
bases={}
comparison_keys={}
previous_result=ch.get('last_result') or {}
for branch, pinned in PINNED.items():
    cur=mapcore._read(PROJECT,branch) or {}
    base=git('rev-list','-1','--before='+since.isoformat(),pinned)
    bases[branch]=base or None
    if not base or not cur.get('commit') or base==pinned:continue
    # Local groups and flow names affect the human-readable diff independently
    # of the Git commits. Use the same effective branch details as mapcore.Map.
    details=project_store.branch_bundle({branch:cur,**{k:project_store.read(Path(HOME)/(k+'.json')) for k in ('groups','flows')}},branch)
    inputs=[os.path.realpath(REPO),base,pinned,EXTRACTOR,details.get('groups'),details.get('flows')]
    key=hashlib.sha256(json.dumps(inputs,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    comparison_keys[branch]=key
    previous_delta=(previous_result.get('evidence') or {}).get('structure',{}).get(branch)
    if previous_delta is not None and (previous_result.get('comparison_keys') or {}).get(branch)==key:
        entry['branches'][branch]=previous_delta
        continue
    if (cur.get('analysis') or {}).get('source')=='ai':
        # Compare like extractors without overwriting the saved AI map or calling AI.
        path=os.path.join(HOME,branch+'.current-basic.json')
        extract_basic(pinned,path)
        cur=json.loads(Path(path).read_text())
        log += branch+': structural comparison uses basic collection; AI-only details require agent analysis\n'
    delta=mapcore.diff(mapcore.Map(PROJECT,branch,base_map(branch,base),bundle=BUNDLE),mapcore.Map(PROJECT,branch,cur,bundle=BUNDLE))
    entry['branches'][branch]={'from':base[:8],'to':pinned[:8],'scope':'basic',**delta}
m = mapcore.Map(PROJECT, "dev" if os.path.exists(os.path.join(HOME,"dev.json")) else "main", bundle=BUNDLE)
def place(p):  # 화면에 안 걸리는 PR 의 자리
    fs = p["files"]
    if p.get("common_files"): return ["여러 화면에 똑같이 들어 있는 부품"]
    if any(f.startswith("frontend/src/") and ".test." not in f for f in fs): return ["앱 전체에 걸친 화면 부품"]
    if fs and all(f.endswith(".md") or f.startswith(("docs/", "artifacts/")) for f in fs): return ["문서"]
    if any(f.startswith((".github/", "Makefile", "docker")) for f in fs): return ["배포·CI"]
    return []
for p in m.status.get("merged_prs", []):
    if not p.get("merged_at") or not since < datetime.fromisoformat(p["merged_at"].replace("Z", "+00:00")) <= NOW: continue
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
import briefing
ch['last_result']={'at':NOW.isoformat(),'since':since.isoformat(),'since_note':since_note,'changed':bool(changed),'scope':'basic','evidence':briefing.freeze(m.status,entry,PINNED,bases),'comparison_keys':comparison_keys}
json.dump(ch, open(cpath, "w"), ensure_ascii=False, indent=1)
print(log + (f"달라진 것: PR {len(entry['prs'])}, " + ", ".join(f"{b} {v['from']}→{v['to']}" for b, v in entry["branches"].items()) if changed else f"{since_note} 달라진 것 없음"))
