#!/usr/bin/env python3
"""where-were-we 를 에이전트에 잇는 MCP 서버 (stdio). 지도 파일을 읽어 짧은 글로 답한다. 저장소에는 아무것도 쓰지 않는다.

에이전트 설정 예:
  Claude Code:  claude mcp add --scope user where-were-we -- <이 저장소>/.venv/bin/python <이 저장소>/mcp_server.py
  Codex:        ~/.codex/config.toml 에 [mcp_servers.where-were-we] command = "<…>/.venv/bin/python", args = ["<…>/mcp_server.py"]
"""
import json, os, subprocess, sys
from datetime import datetime
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import mapcore
from mcp.server import MCPServer

INSTRUCTIONS = """이 서버는 대상 서비스의 구조 지도(화면, 서버 기능, 저장소, 서버 밖 프로그램, 열린 작업)를 알려 준다. 지도는 git 에서 계산하고, AI 가 적은 부분은 근거 줄을 대조한 것만 담는다.
- 하루 작업이나 계획을 시작할 때 changes 로 지난 새로고침 뒤에 구조가 어떻게 달라졌는지 본다. 오래됐으면 refresh 를 먼저 부른다.
- 무엇을 고치기 전에 impact 에 파일 경로·화면 주소·저장소 이름·서버 주소를 넣어, 닿는 화면·서버 기능·저장소·서버 밖 프로그램·지금 같은 곳에서 작업 중인 PR·브랜치·이슈를 확인하고 계획에 반영한다.
- 서비스 전체가 낯설면 overview 를 먼저 본다.
답에 "후보", "추정", "확인 못 한 것"이 붙은 것은 사실로 옮기지 않고 그대로 전한다."""

app = MCPServer("where-were-we", instructions=INSTRUCTIONS)


def pick(project):
    ps = mapcore.projects()
    if project: return project if project in ps else None
    return ps[0] if len(ps) == 1 else None


def need(project):
    p = pick(project)
    if not p: raise ValueError(f"project 를 지정해야 한다. 있는 것: {', '.join(mapcore.projects()) or '없음'}")
    return p


def ago(iso):
    try: d = datetime.now(datetime.fromisoformat(iso).tzinfo) - datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except Exception: return ""
    h = d.total_seconds() / 3600
    return f"{int(h * 60)}분 전" if h < 1 else f"{int(h)}시간 전" if h < 48 else f"{int(h / 24)}일 전"


@app.tool(description="지도가 있는 프로젝트 목록과 각 지도의 기준 커밋·마지막 새로고침 시각.")
def projects() -> str:
    out = []
    for p in mapcore.projects():
        m = mapcore.Map(p); ch = mapcore._read(p, "changes") or {}
        out.append(f"- {p}: 개발 {m.m.get('commit', '?')[:8]}, 마지막 새로고침 {ago(ch['last_refresh']) if ch.get('last_refresh') else '기록 없음'}, 저장소 {m.m.get('repo', '?')}")
    return "\n".join(out) or "지도가 없다."


@app.tool(description="서비스 전체: 따로 켜지는 프로그램과 그 사이의 선, 바깥 서비스, 기능 묶음, 확인 못 한 것.")
def overview(project: str = "") -> str:
    m = mapcore.Map(need(project)); y = m.system or {}
    L = [f"# {m.project} (개발 브랜치 {m.m.get('commit', '?')[:8]})", "", "## 프로그램"]
    for n in y.get("nodes", []):
        L.append(f"- {n['name']} [{n['kind']}{', ' + n['origin'] if n.get('origin') else ''}]: {n.get('what', '')}" + (f" (코드: {', '.join(n['code'])})" if n.get("code") else ""))
    nm = {n["id"]: n["name"] for n in y.get("nodes", [])}
    L += ["", "## 선"] + [f"- {nm.get(l['from'])} → {nm.get(l['to'])}: {l['label']}" + (" (문서로만 확인)" if l.get("sure") == "doc" else "") for l in y.get("links", [])]
    L += ["", "## 바깥 서비스"] + [f"- {x['name']}: {x.get('what', '')}" for x in y.get("externals", [])]
    L += ["", "## 기능 묶음 (AI 가 화면을 묶은 것)"] + [f"- {g['name']}: 화면 {len(g['screens'])} — {g.get('description', '')}" for g in m.groups.get("groups", [])]
    unk = [n["name"] + ": " + u["text"] for n in y.get("nodes", []) for u in n.get("unknown", [])] + [u["text"] for u in y.get("unknown", [])]
    if unk: L += ["", "## 확인 못 한 것"] + [f"- {u}" for u in unk]
    return "\n".join(L)


@app.tool(description="지난 새로고침 뒤에 달라진 것. back=0 이 가장 최근, 1 이 그 전. 들어온 PR 과 그것이 닿는 기능 묶음·화면, 화면·서버 요청·화면 사이 길의 변화.")
def changes(project: str = "", back: int = 0) -> str:
    p = need(project); ch = mapcore._read(p, "changes") or {}
    es = ch.get("entries", [])
    if not es: return "기록이 없다. refresh 를 부르면 생긴다."
    e = es[min(back, len(es) - 1)]
    L = [f"# {e['since'][:16]} → {e['at'][:16]} (마지막 새로고침 {ago(ch['last_refresh'])})"]
    for b, d in e["branches"].items():
        L += ["", f"## {b} 브랜치 {d['from']} → {d['to']}"]
        for k, t in (("screens_added", "새 화면"), ("screens_removed", "사라진 화면")):
            L += [f"- {t}: {x['name']} ({x['path']})" for x in d[k]]
        for k, t in (("requests_added", "새 요청"), ("requests_removed", "사라진 요청")):
            by = {}
            for x in d[k]: by.setdefault((x["name"], x["what"]), []).append(x["screen_name"])
            L += [f"- {t}: {n} {w} — 화면 {', '.join(s)}" for (n, w), s in by.items()]
        L += [f"- 새 길: {x['from_name']} → {x['to_name']} ({x['label'] or '아이콘'})" for x in d["flows_added"]]
        L += [f"- 끊긴 길: {x['from_name']} → {x['to_name']} ({x['label'] or '아이콘'})" for x in d["flows_removed"]]
        L += [f"- 화면이 안 부르는 새 서버 기능: {x['name']} {x['what']}" for x in d["routes_added_no_screen"]]
    if not e["branches"]: L.append("\n코드 구조는 이 사이에 그대로다(기준 커밋이 바뀌지 않았다).")
    if e.get("ai_stale"): L.append(f"\nAI 가 적은 것 중 근거 줄이 바뀐 것: {e['ai_stale']} — 그 부분은 다시 읽기 전에는 믿지 않는다.")
    L += ["", f"## 들어온 PR {len(e['prs'])}"]
    for x in e["prs"]:
        where = ", ".join(x["groups"] or x["programs"]) or "지도에 자리 없음"
        L.append(f"- #{x['number']} {x['title']} [{'/'.join(x['kinds']) or '-'}] → {where}" + (f"; 화면 {len(x['screens'])}" if x["screens"] else "") + (f"; 이슈 {', '.join('#' + str(i) for i in x['issues'])}" if x["issues"] else ""))
    return "\n".join(L)


@app.tool(description="고치기 전에 영향 보기. target 에 파일 경로(frontend/…, backend/…, scripts/…), 화면 주소나 이름, 저장소(테이블) 이름, 서버 주소(예: POST /projects/{}/start) 중 하나를 넣는다.")
def impact(target: str, project: str = "") -> str:
    m = mapcore.Map(need(project)); t = target.strip(); L = []
    rows = [(x["path"], r) for x, _ in m.visible() for r in m.requests(x["path"])]
    untested = []  # 이 답에 나온 서버 기능 중 테스트를 잇지 못한 것
    def route_lines(rs):
        out = []
        for key in dict.fromkeys(r["key"] for _, r in rs):
            r = next(r for _, r in rs if r["key"] == key); rt = r["route"]
            scr = sorted({m.label(p) for p, x in rs if x["key"] == key})
            if not rt.get("tests"): untested.append(f"{rt['method']} {rt['path']} ({rt['file']}::{rt['function']})")
            out.append(f"- {r['name']} `{rt['method']} {rt['path']}` ({rt['file']}:{rt['line']}) 화면 {', '.join(scr)}; 저장소 {', '.join(rt.get('tables') or []) or '없음'}; 바깥 {', '.join(rt.get('externals') or []) or '없음'}; 테스트 " + (str(len(rt['tests'])) if rt.get('tests') else '안 보임(아래 안내)'))
            for name, j, exact in m.jobs_of(key):
                out.append(f"  - 이 요청 뒤에 {name}에서 이어서 하는 일: {j['name']} — 시작 조건: {j['starts_when']}" + ("" if exact else " (추정)"))
        return out
    screens = set()
    if "/" in t and "." in os.path.basename(t):  # 파일
        fs = m.m.get("file_screens", {}).get(t, [])
        screens |= set(fs)
        rs = [(p, r) for p, r in rows if r["route"]["file"] == t or t in (r["route"].get("services") or [])]
        o = m.owner_of(t)
        L.append(f"# 파일 {t}" + (f" — {o['name']}의 코드" if o else ""))
        if fs: L.append(f"닿는 화면 {len(fs)}: " + ", ".join(m.label(p) for p in fs[:20]) + (" …" if len(fs) > 20 else ""))
        if rs: L += ["", "## 이 파일을 거치는 서버 기능"] + route_lines(rs)
        cd = [(b, n["name"]) for f, b, n in m.copy_diffs() if f == t]
        if cd: L.append(f"\n주의: {cd[0][1]} 안에 이 파일의 다른 판이 있다 (사본 {', '.join(b for b, _ in cd)}). 고치면 두 판이 갈라진다.")
    elif (tu := m.table_use()) and t in tu:
        u = tu[t]; L.append(f"# 저장소 {t}")
        L.append("바꾸는 화면: " + (", ".join(m.label(p) for p in u["w"]) or "없음"))
        L.append("읽는 화면: " + (", ".join(m.label(p) for p in u["r"]) or "없음"))
        progs = [n["name"] for n in m.nodes() if t in (n.get("tables") or [])]
        if progs: L.append("서버를 거치지 않고 직접 쓰는 프로그램: " + ", ".join(progs))
        L += ["", "## 서버 기능"] + route_lines([(p, r) for p, r in rows if t in (r["route"].get("tables") or [])])
    elif t.split(" ")[0].upper() in ("GET", "POST", "PUT", "PATCH", "DELETE"):
        meth, path = t.split(" ", 1)
        rs = [(p, r) for p, r in rows if r["route"]["method"] == meth.upper() and r["route"]["path"] == path.strip()]
        L.append(f"# 서버 기능 {t}"); L += route_lines(rs) or ["화면에서 부르는 곳이 없다."]
    elif (p := m.find_screen(t)):
        screens.add(p); L.append(f"# 화면 {m.label(p)} ({p}) — 묶음 {m.group_of(p) or '없음'}")
        es = [e for e in m.edges() if not e["menu"]]
        L.append("오는 화면: " + (", ".join(f"{m.label(e['from'])}({e['label'] or '아이콘'})" for e in es if e["to"] == p) or "없음"))
        L.append("가는 화면: " + (", ".join(f"{m.label(e['to'])}({e['label'] or '아이콘'})" for e in es if e["from"] == p) or "없음"))
        L += ["", "## 서버 기능"] + route_lines([(p, r) for r in m.requests(p)])
    else:
        return f"'{t}' 를 지도에서 찾지 못했다. find 로 먼저 찾는다."
    work = {k: [] for k in ("open", "branches", "folders", "issues", "merged")}
    for s in screens:
        for k, v in m.work_of(s).items(): work[k] += [x for x in v if x not in work[k]]
    if any(work.values()):
        L += ["", "## 지금 같은 곳의 작업"]
        L += [f"- 열린 PR #{x['number']} {x['title']} ({x.get('author')})" for x in work["open"]]
        L += [f"- PR 없는 브랜치 {x['name']} ({x.get('author')}, {x['age_days']}일 전)" for x in work["branches"]]
        L += [f"- 이 맥 작업 폴더 {x['path']} ({x['branch']}, 커밋 안 한 변경 {len(x['uncommitted'])})" for x in work["folders"]]
        L += [f"- 이슈 #{x['number']} {x['title']}" + (" (후보)" if x["via"] == "text" else "") for x in work["issues"]]
        L += [f"- 최근 병합 #{x['number']} {x['title']}" for x in work["merged"][:8]]
    if untested:
        L += ["", mapcore.tests_prompt(m.project, list(dict.fromkeys(untested))[:15])]
    return "\n".join(L)


@app.tool(description="테스트 찾는 규칙 고치기. files 는 테스트 파일 이름 모양(예: test_*.py), calls 는 테스트가 서버 기능을 부르는 모양(자리 <method> <path> <function> <module>). 지금 규칙을 모두 다시 넘긴다. 저장한 뒤 refresh 로 결과를 본다.")
def set_test_rules(files: list[str], calls: list[str], project: str = "") -> str:
    p = need(project); home = os.path.join(mapcore.ROOT, p)
    for t in calls: mapcore.call_regex(t)  # 틀린 모양이면 여기서 ValueError 로 돌려보낸다
    if not files or not calls: raise ValueError("files 와 calls 가 비어 있으면 안 된다")
    path = os.path.join(home, "tests.json"); c = json.load(open(path)) if os.path.exists(path) else {}
    c.update(files=files, calls=calls); json.dump(c, open(path, "w"), ensure_ascii=False, indent=1)
    return f"저장했다. 테스트 파일 {files}, 부르는 모양 {calls}. refresh 를 부르면 이 규칙으로 다시 뽑는다."


@app.tool(description="규칙으로 안 잡히는 테스트 하나를 지도에 남기기. route 는 서버 기능(예: DELETE /generations/{}), file 은 테스트 파일, line 은 그 테스트에서 서버 기능을 부르는 줄 번호, quote 는 그 줄의 글자를 그대로(6자 이상). 그 줄에 그 글자가 없으면 저장하지 않는다.")
def record_test(route: str, file: str, line: int, quote: str, project: str = "") -> str:
    p = need(project); m = mapcore.Map(p); home = os.path.join(mapcore.ROOT, p)
    meth, _, path = route.strip().partition(" ")
    rs = [r for r in m.m.get("backend_routes", []) if r["method"] == meth.upper() and r["path"] == path.strip() and r.get("function")]
    if len(rs) != 1: return f"'{route}' 에 맞는 서버 기능이 {len(rs)}개다. find 로 주소를 확인한다."
    src = subprocess.run(["git", "-C", m.m["repo"], "show", f"{m.m['commit']}:{file}"], capture_output=True, text=True).stdout.splitlines()
    q = "".join(quote.split())
    if len(q) < 6 or not any(q in "".join(l.split()) for l in src[max(0, line - 3):line + 2]):
        return f"{file}:{line} 근처에 그 글자가 없다(지도 기준 커밋 {m.m['commit']}). 저장하지 않았다."
    pth = os.path.join(home, "tests.json"); c = json.load(open(pth)) if os.path.exists(pth) else {}
    rec = {"route": f"{rs[0]['file']}::{rs[0]['function']}", "file": file, "line": line, "quote": quote}
    if rec not in c.setdefault("records", []): c["records"].append(rec)
    json.dump(c, open(pth, "w"), ensure_ascii=False, indent=1)
    return f"저장했다({len(c['records'])}건). refresh 를 부르면 지도에 반영된다."


@app.tool(description="이름으로 찾기: 화면·버튼·서버 기능 이름·주소·PR/이슈 번호. impact 에 넣을 대상을 고를 때 쓴다.")
def find(query: str, project: str = "") -> str:
    m = mapcore.Map(need(project)); q = query.lower().lstrip("#"); out = []
    for x, _ in m.visible():
        p = x["path"]
        if q in m.label(p).lower() or q in p.lower(): out.append(f"화면 {m.label(p)} ({p})")
        for r in m.requests(p):
            if q in r["name"].lower() or q in r["route"]["path"].lower(): out.append(f"서버 기능 {r['name']} `{r['route']['method']} {r['route']['path']}` — 화면 {m.label(p)}")
    st = m.status
    for pr in st.get("open_prs", []) + st.get("merged_prs", []):
        if q == str(pr["number"]) or q in pr["title"].lower(): out.append(f"PR #{pr['number']} {pr['title']} — 화면 {len(pr['screens'])}곳")
    for i in st.get("issues", []):
        if q == str(i["number"]) or q in i["title"].lower(): out.append(f"이슈 #{i['number']} {i['title']}" + (f" — 화면 {len(i['screens'])}곳" if i["screens"] else " — 화면 연결 없음"))
    for t in sorted(set((m.m.get("models") or {}).values())):
        if q in t.lower(): out.append(f"저장소 {t}")
    out = list(dict.fromkeys(out))
    return "\n".join(out[:40]) + (f"\n… {len(out) - 40}개 더" if len(out) > 40 else "") if out else "없다."


@app.tool(description="새로고침: git fetch 뒤 바뀐 브랜치의 지도를 다시 뽑고 PR·이슈·세션을 모아 달라진 것을 기록한다. 1~2분 걸린다. 지도 파일만 쓰고 대상 저장소에는 쓰지 않는다.")
def refresh(project: str = "") -> str:
    p = need(project)
    r = subprocess.run(mapcore.python_command(os.path.join(HERE, "refresh.py"), p), capture_output=True, text=True, timeout=900)
    return (r.stdout[-1500:] if r.returncode == 0 else "실패: " + r.stderr[-800:]) + "\n\n" + changes(p)


if __name__ == "__main__":
    app.run("stdio")
