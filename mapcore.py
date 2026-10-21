"""지도 파일(~/.where-were-we/<프로젝트>/*.json)을 읽어 사람이 읽는 말로 답하는 함수들.
에이전트 연결(mcp_server.py)과 변경 기록(collect.py)이 쓴다.

화면(ui/index.html)도 같은 규칙을 자바스크립트로 따로 갖고 있다. 두 곳이 갈라지지 않도록
check_same.js 가 같은 지도에서 두 쪽의 숫자(화면별 서버 요청 수, 흐름 길 수)를 맞춰 본다.
규칙: 리다이렉트는 빼고 /m/… 모바일 판은 같은 주소의 데스크톱 화면에 붙인다. 화면의 1/3 넘게 들어 있는 부품이 부르는 요청은
그 화면의 요청에서 뺀다. 세 화면 넘게 똑같이 들어 있는 부품의 링크는 메뉴로 치고 흐름에서 뺀다.
"""
import fnmatch, json, os, re, shlex, sys
from collections import defaultdict
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ROOT = os.environ.get("WHERE_WERE_WE_ROOT") or os.path.expanduser("~/.where-were-we")

SETTINGS_DEFAULT = {'open_refresh':False, 'since':'last_refresh', 'since_time':''}

def settings_path():
    return os.environ.get('WHERE_WERE_WE_SETTINGS') or os.path.join(ROOT,'settings.json')

def settings():
    path=settings_path()
    if not os.path.isfile(path):return dict(SETTINGS_DEFAULT)
    with open(path) as stream:value=json.load(stream)
    return {**SETTINGS_DEFAULT, **{k:v for k,v in value.items() if k in SETTINGS_DEFAULT}}

def save_settings(value):
    from datetime import datetime
    from pathlib import Path
    import project
    if not isinstance(value,dict):raise ValueError('Invalid settings')
    result={**SETTINGS_DEFAULT, **{k:v for k,v in value.items() if k in SETTINGS_DEFAULT}}
    if type(result['open_refresh']) is not bool or result['since'] not in ('last_refresh','my_commit','time'):
        raise ValueError('Invalid refresh settings')
    if not isinstance(result['since_time'],str):raise ValueError('Invalid comparison time')
    if result['since']=='time':
        try:datetime.fromisoformat(result['since_time'])
        except ValueError:raise ValueError('Choose a valid comparison time') from None
    project.atomic(Path(settings_path()),result)
    return result

def since_of(repo,last_refresh,now):
    """Resolve the selected baseline separately for each repository."""
    from datetime import datetime,timedelta
    import subprocess
    st=settings();fallback=last_refresh or now-timedelta(days=1)
    if st['since']=='time' and st['since_time']:
        chosen=datetime.fromisoformat(st['since_time'])
        return (chosen if chosen.tzinfo else chosen.astimezone()),'지정한 시각 이후'
    if st['since']=='my_commit':
        def git(*args):
            result=subprocess.run(['git','-C',repo,*args],capture_output=True,text=True)
            return result.stdout.strip() if result.returncode==0 else ''
        email=git('config','user.email')
        stamp=git('log','--all','--fixed-strings','--author=<'+email+'>','-1','--format=%cI') if email else ''
        if stamp:return datetime.fromisoformat(stamp),'내 마지막 커밋 이후'
        return fallback,'내 커밋을 찾지 못해 지난 새로고침 이후'
    return fallback,'지난 새로고침 이후'

def project_home(project):
    return os.path.join(ROOT, project)

def configured_refs():
    return json.loads(os.environ.get("WHERE_WERE_WE_REFS", '{"dev":"origin/dev","main":"origin/main"}'))


def python_command(script, *args):
    """Use the same interpreter and isolation flags for nested backend scripts."""
    return [sys.executable, '-I', '-B', script, *args]


def projects():
    return sorted(d for d in os.listdir(ROOT) if os.path.isdir(os.path.join(ROOT, d)) and not d.startswith(".")) if os.path.isdir(ROOT) else []


def _read(project, name):
    if os.path.isfile(os.path.join(ROOT, project, "project.json")):
        import project as projects_module
        return projects_module.read_bundle(project).get(name)
    p = os.path.join(ROOT, project, name + ".json")
    return json.load(open(p)) if os.path.exists(p) else None


class Map:
    def __init__(self, project, branch="dev", data=None, bundle=None):
        self.project, self.branch = project, branch
        if bundle is None:
            import project as projects_module
            bundle = projects_module.read_bundle(project,branch=branch)
        if bundle.get('branch_details'):
            bundle={**bundle,**bundle['branch_details'].get(branch,{})}
        read = (lambda p, key: bundle.get(key)) if bundle is not None else _read
        self.m = data if data is not None else read(project, branch) or {}
        self.groups = read(project, "groups") or {}
        self.flows = (read(project, "flows") or {}).get("routes", {})
        self.system = read(project, "system")
        self.jobs = (read(project, "jobs") or {}).get("nodes", {})
        self.status = read(project, "status") or {}
        s = self.m.get("screens", [])
        self.by_path = {x["path"]: x for x in s}
        self.fn = {(f["file"], f["name"]): f for f in self.m.get("api_functions", [])}
        self.route_at = {(r["file"], r["line"]): r for r in self.m.get("backend_routes", [])}
        cnt = defaultdict(int)
        for sc in s:
            for v in {a.get("via") for a in sc["actions"]} | {a.get("via") for a in sc["api_functions"]}:
                if v and v != sc.get('file'): cnt[v] += 1
        totals = defaultdict(int)
        for screen in s: totals[screen.get("repository", "")] += 1
        self.common = {v for v, c in cnt.items() if c > 1 and c > totals.get(v.split("/", 1)[0] if self.m.get("multi_repo") else "", len(s)) / 3}
        self._req = {}

    # ---------- 화면 ----------
    def fold(self, p):
        if p and p.startswith("/m/"):
            t = p[2:]
            if t in self.by_path and not self.by_path[t].get("redirect"):
                return t
        return p

    def visible(self):
        """[(데스크톱 화면, 모바일 짝 또는 None)]"""
        s = self.m.get("screens", [])
        desk = {x["path"]: [x, None] for x in s if not x.get("redirect") and not x["path"].startswith("/m/") and x["path"] != "/m"}
        out = []
        for x in s:
            if x.get("redirect") or not (x["path"].startswith("/m/") or x["path"] == "/m"): continue
            d = desk.get(x["path"][2:] or "/")
            if d: d[1] = x
            else: out.append([x, None])
        return [tuple(v) for v in desk.values()] + [tuple(v) for v in out]

    def label(self, p):
        x = self.by_path.get(p); h = x and x.get("heading")
        if x and x.get("repository"):
            return (h or (self.groups.get("names") or {}).get(p) or x.get("source_path", p)) + " [" + x["repository"] + "]"
        if not h:
            return (self.groups.get("names") or {}).get(p) or p
        same = [y["path"] for y in self.m["screens"] if y.get("heading") == h and not y.get("redirect") and not y["path"].startswith("/m/")]
        return h + " · " + p if len(same) > 1 and p != min(same, key=len) else h

    def group_of(self, p):
        for g in self.groups.get("groups", []):
            if p in g["screens"]: return g["name"]
        return None

    def find_screen(self, q):
        q = q.strip()
        if q in self.by_path: return self.fold(q)
        source_hits = [x for x, _ in self.visible() if x.get("source_path") == q]
        if len(source_hits) > 1: raise ValueError("Ambiguous screen; specify repository: " + ", ".join(x["repository"] for x in source_hits))
        if source_hits: return source_hits[0]["path"]
        ql = q.lower()
        hits = [x for x, _ in self.visible() if ql in self.label(x["path"]).lower() or ql in x["path"].lower()]
        if len(hits) > 1 and len({x.get("repository") for x in hits}) > 1:
            raise ValueError("Ambiguous screen; specify repository: " + ", ".join(sorted({x["repository"] for x in hits})))
        return hits[0]["path"] if hits else None

    # ---------- 서버 요청 ----------
    def requests(self, path):
        if path in self._req: return self._req[path]
        x = self.by_path.get(path)
        if not x: return []
        mob = next((m for d, m in self.visible() if d["path"] == path), None)
        parts = [x] + ([mob] if mob else [])
        tags = defaultdict(list)
        for p in parts:
            for a in p["actions"]:
                if a["kind"] != "api" or not a["label"]: continue
                keys = [n for n in a["api_functions"] if n != "<inline>"] + [a["file"] + " " + c["method"] + " " + str(c["path"]) for c in a.get("calls", [])]
                for k in keys:
                    if a["label"] not in tags[k]: tags[k].append(a["label"])
        rows, seen = [], set()
        for p in parts:
            for ref in p["api_functions"]:
                if ref.get("via") != p.get('file') and ref.get("via") in self.common: continue
                f = self.fn.get((ref["file"], ref["name"]))
                if not f: continue
                for c in f["calls"]:
                    for b in c["backend"]:
                        r = self.route_at.get((b["file"], b["line"]))
                        if not r or (r["file"], r["line"]) in seen: continue
                        seen.add((r["file"], r["line"]))
                        k = f["file"] + " " + c["method"] + " " + str(c["path"]) if f["name"] == "<inline>" else f["name"]
                        btns = tags.get(k, []) if r["method"] != "GET" else []
                        rows.append({"key": r["file"] + "::" + str(r["function"]), "route": r, "btns": btns, "connection_basis": c.get("connection_basis")})
        cnt = defaultdict(int)
        for row in rows:
            if row["btns"]: cnt[row["btns"][0]] += 1
        for row in rows:
            row["name"] = self.req_name(row["route"], row["btns"], cnt[row["btns"][0]] > 1 if row["btns"] else False)
        self._req[path] = rows
        return rows

    def ai_name(self, r):
        key = r["file"] + "::" + str(r["function"])
        if r.get('flow'):return r['flow'].get('name')
        return (self.flows.get(key) or {}).get("name") or (self.groups.get("request_names") or {}).get(key)

    def req_name(self, r, btns=(), dup=False):
        if btns:
            return btns[0] + (f" 외 {len(btns) - 1}" if len(btns) > 1 else "") + (" · " + (self.ai_name(r) or str(r["function"])) if dup else "")
        name = self.ai_name(r) or str(r["function"])
        return name + " [" + r["repository"] + "]" if r.get("repository") else name

    # ---------- 흐름 ----------
    def edges(self):
        nv = defaultdict(set)
        for sc in self.m.get("screens", []):
            for a in sc["actions"]:
                if a["kind"] == "nav" and a.get("via"): nv[a["via"]].add(self.fold(sc["path"]))
        out = {}
        for sc in self.m.get("screens", []):
            f = self.fold(sc["path"])
            for a in sc["actions"]:
                if a["kind"] != "nav": continue
                menu = bool(a.get("via") and len(nv[a["via"]]) >= 3)
                for t in a.get("targets") or []:
                    if not t.get("to"): continue
                    to = self.fold(t["to"])
                    if to == f: continue
                    e = out.setdefault((f, to), {"from": f, "to": to, "label": a.get("label") or "", "menu": menu})
                    if not e["label"] and a.get("label"): e["label"] = a["label"]
                    if e["menu"] and not menu: e["menu"] = False
        return list(out.values())

    # ---------- 이어진 것 ----------
    def nodes(self):
        return (self.system or {}).get("nodes", [])

    def owner_of(self, path):
        best, ln = None, -1
        for n in self.nodes():
            for c in n.get("code") or []:
                c = c.rstrip("/")
                if (path + "/").startswith(c + "/") and len(c) > ln: best, ln = n, len(c)
        return best

    def copy_diffs(self):
        return [(f["path"], c["branch"], n) for n in self.nodes() for c in n.get("copies", []) for f in c["files"] if not f["same"]]

    def jobs_of(self, key):
        out = []
        for nid, v in self.jobs.items():
            name = next((n["name"] for n in self.nodes() if n["id"] == nid), nid)
            for j in v["jobs"]:
                hit = next((r for r in j["routes"] if r["key"] == key), None)
                if hit: out.append((name, j, hit["exact"]))
        return out

    def work_of(self, path):
        st = self.status; has = lambda x: path in (x.get("screens") or [])
        return {"open": [p for p in st.get("open_prs", []) if has(p)], "merged": [p for p in st.get("merged_prs", []) if has(p)],
                "branches": [b for b in st.get("branches", []) if has(b) and b.get("ahead_of_dev") and not b.get("stale") and not b.get("has_open_pr")],
                "folders": [w for w in st.get("worktrees", []) if has(w)], "issues": [i for i in st.get("issues", []) if has(i)]}

    def table_use(self):
        t = defaultdict(lambda: {"w": defaultdict(list), "r": defaultdict(list)})
        for x, _ in self.visible():
            for row in self.requests(x["path"]):
                for tb in row["route"].get("tables") or []:
                    t[tb]["r" if row["route"]["method"] == "GET" else "w"][x["path"]].append(row)
        return t


# ---------- 두 지도 사이에 달라진 것 ----------
def diff(old, new):
    """old, new: Map. 사람·에이전트가 읽을 구조 변화."""
    vo = {x["path"] for x, _ in old.visible()}; vn = {x["path"] for x, _ in new.visible()}
    ro = {(r["method"], r["path"]) for r in old.m.get("backend_routes", []) if r.get("mounted")}
    rn = {(r["method"], r["path"]): r for r in new.m.get("backend_routes", []) if r.get("mounted")}
    out = {"screens_added": [{"path": p, "name": new.label(p), "group": new.group_of(p)} for p in sorted(vn - vo)],
           "screens_removed": [{"path": p, "name": old.label(p)} for p in sorted(vo - vn)],
           "requests_added": [], "requests_removed": [], "flows_added": [], "flows_removed": [],
           "routes_added_no_screen": []}
    for p in sorted(vo & vn):
        a = {(r["route"]["method"], r["route"]["path"]): r for r in old.requests(p)}
        b = {(r["route"]["method"], r["route"]["path"]): r for r in new.requests(p)}
        out["requests_added"] += [{"screen": p, "screen_name": new.label(p), "name": b[k]["name"], "what": " ".join(k)} for k in sorted(set(b) - set(a))]
        out["requests_removed"] += [{"screen": p, "screen_name": new.label(p), "name": a[k]["name"], "what": " ".join(k)} for k in sorted(set(a) - set(b))]
    eo = {(e["from"], e["to"]): e for e in old.edges() if not e["menu"]}
    en = {(e["from"], e["to"]): e for e in new.edges() if not e["menu"]}
    out["flows_added"] = [{"from": f, "to": t, "from_name": new.label(f), "to_name": new.label(t), "label": en[(f, t)]["label"]} for f, t in sorted(set(en) - set(eo))]
    out["flows_removed"] = [{"from": f, "to": t, "from_name": old.label(f), "to_name": old.label(t), "label": eo[(f, t)]["label"]} for f, t in sorted(set(eo) - set(en))]
    used = {(r["route"]["method"], r["route"]["path"]) for x, _ in new.visible() for r in new.requests(x["path"])}
    out["routes_added_no_screen"] = [{"what": " ".join(k), "name": new.req_name(rn[k]), "file": rn[k]["file"]} for k in sorted(set(rn) - ro) if k not in used]
    return out


def pr_kind(files):
    """아침 브리핑과 같은 세 갈래. 기능: 화면이 달라짐, 구조: 서버 코드의 흐름, 시스템: DB·배포·설정·서버 밖 프로그램."""
    k = []
    if any(f.startswith("frontend/") for f in files): k.append("기능")
    if any(f.startswith("backend/app/") and "/tests/" not in f for f in files): k.append("구조")
    if any(re.match(r"(scripts/|\.github/|docker|Makefile|backend/alembic|.*\.env|.*launchd)", f) for f in files): k.append("시스템")
    return k


# ---------- 테스트 찾는 규칙 (extract.py 가 쓰고, 에이전트가 MCP 로 고친다) ----------
# ~/.where-were-we/<프로젝트>/tests.json = {"files": [...], "calls": [...], "records": [...]}
#   files: 테스트 파일 이름 모양(fnmatch). "/" 가 없으면 파일 이름만, 있으면 저장소 경로 전체와 맞춘다.
#   calls: 테스트가 서버 기능을 부르는 모양. 자리 <method> <path> <function> <module>(서버 기능 파일을 import 한 이름)만 쓴다.
#   records: 규칙으로 안 잡히는 테스트 한 줄씩 {"route": 파일::함수, "file", "line", "quote"}. 새로 뽑을 때마다 그 줄을 다시 대조한다.
TESTS_DEFAULT = {"files": ["test_*.py", "*_test.py"], "calls": ['client.<method>("<path>")']}
SLOTS = {"<method>": r"(?P<method>(?i:get|post|put|patch|delete))", "<path>": r"(?P<path>[^\"'`]+)",
         "<function>": r"(?P<function>\w+)", "<module>": r"(?P<module>\w+)"}


def tests_conf(home):
    p = os.path.join(home, "tests.json")
    if os.path.exists(p):
        with open(p) as stream:c=json.load(stream)
    else:c={}
    return {"files": c.get("files") or TESTS_DEFAULT["files"], "calls": c.get("calls") or TESTS_DEFAULT["calls"], "records": c.get("records", [])}


def call_regex(t):
    """부르는 모양 → 정규식. 틀린 모양이면 ValueError (조용히 0 이 되지 않게)."""
    bad = set(re.findall(r"<\w+>", t)) - set(SLOTS)
    if bad: raise ValueError(f"모르는 자리 {', '.join(bad)}. 쓸 수 있는 것: {' '.join(SLOTS)}")
    if "<path>" not in t and "<function>" not in t: raise ValueError("<path> 나 <function> 이 있어야 서버 기능에 이을 수 있다")
    if "<path>" in t and "<method>" not in t: raise ValueError("<path> 를 쓰면 <method> 도 있어야 한다")
    if "<module>" in t and "<function>" not in t: raise ValueError("<module> 을 쓰면 <function> 도 있어야 한다")
    out = ""
    t = t.rstrip()
    if t.endswith(")"): t = t[:-1]  # 끝의 닫는 괄호는 보지 않는다. 뒤에 인자가 더 붙어도 같은 호출이다
    for part in re.split(r"(<\w+>)", t):
        if part in SLOTS: out += SLOTS[part]; continue
        for ch in part:  # 따옴표는 ' " 아무거나(앞의 f 도), 여는 괄호와 쉼표 뒤에는 빈칸·줄바꿈을 허용한다
            out += "f?[\"']" if ch in "\"'" else r"\(\s*" if ch == "(" else r",\s*" if ch == "," else r"\s*" if ch == " " else re.escape(ch)
    return re.compile(out)


def normalize_http_path(value):
    value=value.strip("`'\"").split('?')[0]
    return re.sub(r"\$?\{[^}]*\}","{}",value).rstrip('/') or '/'


def backend_test_links(be,files,read_source,conf,imports_reader=None,module_resolver=None,normalize_path=normalize_http_path):
    """Apply one set of HTTP-pattern and verified-record rules to any source language."""
    be_index=defaultdict(list)
    for route in be:be_index[(route['method'],route['path'])].append(route)
    hits = defaultdict(set)
    by_func = defaultdict(list)  # (서버 기능 파일, 함수 이름) → 라우트
    for r in be:
        if r.get("function"):
            by_func[(r["file"], r["function"])].append(r)
    router_files = {k[0] for k in by_func}
    pats = [call_regex(t) for t in conf["calls"]]
    is_test = lambda f: any(fnmatch.fnmatch(f if "/" in g else os.path.basename(f), g) for g in conf["files"])
    for f in files:
        if not is_test(f):
            continue
        src = read_source(f) or ""
        imps = imports_reader(src) if imports_reader else {}
        for pat in pats:
            for m in pat.finditer(src):
                g = m.groupdict()
                if g.get("path"):
                    rs = be_index.get((g["method"].upper(), normalize_path(g["path"])), [])
                elif g.get("module"):  # 서버 기능 파일을 import 한 이름.함수(
                    mod, name = imps.get(g["module"], (None, None))
                    rf_ = mod is not None and module_resolver(f"{mod}.{name}" if mod else name, router_files)
                    rs = by_func.get((rf_, g["function"]), []) if rf_ else []
                else:  # 서버 기능 함수를 import 해서 바로 부름
                    mod, name = imps.get(g["function"], (None, None))
                    rf_ = mod and module_resolver(mod, router_files)
                    rs = by_func.get((rf_, name), []) if rf_ else []
                for r in rs:
                    hits[(r["file"], r["line"])].add(f)
    stale = 0
    for rec in conf["records"]:  # 에이전트가 하나씩 넘긴 것. 이 커밋에서도 그 줄(±2)에 그 글자가 있어야 센다
        r = next((r for r in be if f"{r['file']}::{r.get('function')}" == rec.get("route")), None)
        lines = (read_source(rec.get("file", "")) or "").splitlines(); q = re.sub(r"\s+", "", rec.get("quote") or ""); ln = rec.get("line") or 0
        if r and len(q) >= 6 and any(q in re.sub(r"\s+", "", l) for l in lines[max(0, ln - 3):ln + 2]):
            hits[(r["file"], r["line"])].add(rec["file"])
        else:
            stale += 1
    return hits, stale


def extractor_id(home):
    """뽑는 방법의 판. extract.py 와 테스트 규칙이 같으면 같다. 바뀌면 refresh 가 커밋이 그대로여도 다시 뽑는다."""
    import hashlib
    c = tests_conf(home)
    from pathlib import Path
    base=Path(__file__).resolve().parent
    raw = (base/'extract.py').read_bytes() + Path(__file__).read_bytes() + json.dumps(c,sort_keys=True,ensure_ascii=False).encode() + os.environ.get('WHERE_WERE_WE_LAYOUT','').encode()
    return hashlib.sha1(raw).hexdigest()[:10]


# 에이전트에게 복사해 주는 모든 안내가 이 문장을 붙인다. 사용자에게 답하는 언어만 정하고, 저장하는 결과의 언어는 각 요청이 정한다.
_REPLY_LANGUAGE = {
    "en": "Reply to the user in the language of the current conversation. If the user has explicitly asked for a language, use it. "
          "Use {} only when the conversation language is unknown.",
    "ko": "사용자에게는 지금 대화에서 쓰는 언어로 답하세요. 사용자가 언어를 직접 정해 달라고 했으면 그 언어를 따르세요. "
          "대화 언어를 알 수 없을 때만 {}로 답하세요.",
}
_SAVED_RESULT_LANGUAGE = {
    "en": "Saved results keep the language this request specifies.",
    "ko": "저장하는 결과의 언어는 요청이 정한 대로 둡니다.",
}
_LANGUAGE_NAMES = {"en": {"ko": "Korean", "en": "English"}, "ko": {"ko": "한국어", "en": "영어"}}


def reply_language(lang, written=None, *, saved_results=False):
    """lang 은 앱에서 고른 언어(대화 언어를 모를 때만 쓴다), written 은 이 문장을 쓰는 언어다. saved_results 는 저장 언어가 정해진 요청에만 쓴다."""
    lang = "en" if lang == "en" else "ko"
    written = lang if written is None else ("en" if written == "en" else "ko")
    policy = _REPLY_LANGUAGE[written].format(_LANGUAGE_NAMES[written][lang])
    return policy + (" " + _SAVED_RESULT_LANGUAGE[written] if saved_results else "")


def tests_prompt(project, routes=(), lang="ko", repository=""):
    """테스트가 안 이어진 서버 기능에 붙는 안내. MCP impact 답과 앱의 "프롬프트 복사"가 이것 하나를 쓴다."""
    rules_home = os.path.join(ROOT, project)
    tool_scope = ""
    if os.path.isfile(os.path.join(rules_home, "project.json")):
        import project as projects_module
        repo = projects_module.selected_repository(project, repository)
        rules_home = projects_module.repository_folder(project, repo, projects_module.states(project))
        if not rules_home: raise ValueError("Refresh this repository first")
        tool_scope = f"Tool arguments: project={project!r}, repository={repo['id']!r}. Preserve both arguments when recording tests or updating rules.\n"
        project = project + " / " + repo["id"]
    c = tests_conf(rules_home)
    lines = "\n".join(f"   - {r}" for r in routes) or "   - (impact 답에서 테스트가 0 인 서버 기능)"
    if lang == "en":
        lines = "\n".join(f"   - {r}" for r in routes) or "   - (server requests with zero linked tests in impact)"
        return f"""## If test code is missing
where-were-we({project}) could not link tests to these server requests. It only recognizes configured patterns; unlinked tests may still exist.
{lines}
{tool_scope}Current rules: files {c['files']}, call patterns {c['calls']}

1. Find tests in the repository that call these requests, including HTTP clients, direct imports, and shared helpers. Do not write to the target repository.
2. If the pattern repeats, update set_test_rules. Include the existing rules too: omitted rules are removed. Available placeholders: <method>, <path>, <function>, <module> (the imported server module). Examples: 'client.<method>("<path>")', '<module>.<function>(', '<function>('. Then call refresh and check that the requests have linked tests.
3. For one-off patterns or helper calls, use record_test with the server request, test file, line number, and exact text on that line. Only matching evidence is stored.
4. If nothing is found, report that result. Do not conclude that tests do not exist.

{reply_language(lang)}"""
    return f"""## 테스트 코드가 안 보인다면?
where-were-we({project})가 아래 서버 기능에 테스트를 잇지 못했다. 지도는 정해 둔 찾는 규칙으로만 테스트를 잇기 때문에, 테스트가 없다는 뜻이 아닐 수 있다.
{lines}
{tool_scope}지금 규칙: 테스트 파일 {c['files']}, 부르는 모양 {c['calls']}

1. 저장소에서 이 서버 기능을 부르는 테스트를 찾는다. 주소로 요청하는 것, 서버 함수를 import 해서 직접 부르는 것, 공용 도우미를 거치는 것 등 이 저장소가 실제로 쓰는 모양을 본다. 대상 저장소에는 아무것도 쓰지 않는다.
2. 찾은 모양이 다른 테스트에서도 되풀이되면 set_test_rules 로 규칙을 고친다. 지금 규칙도 같이 넘긴다(빠진 것은 지워진다).
   부르는 모양에 쓸 수 있는 자리: <method>, <path>, <function>, <module>(서버 기능 파일을 import 한 이름). 예: 'client.<method>("<path>")', '<module>.<function>(', '<function>('
   그다음 refresh 를 불러 "테스트가 닿는 백엔드 경로" 수가 늘었는지, 위 서버 기능에 테스트가 붙었는지 본다.
3. 규칙으로 잡히지 않는 테스트(한 곳에서만 쓰는 모양, 도우미를 거치는 것)는 record_test 로 하나씩 넘긴다. 서버 기능, 테스트 파일, 서버 기능을 부르는 줄 번호, 그 줄의 글자를 그대로 넘긴다. 지도는 그 줄에 그 글자가 실제로 있는 것만 저장한다.
4. 찾지 못했으면 "못 찾음"으로 보고한다. 테스트가 없다고 단정하지 않는다.

{reply_language(lang)}"""


assert call_regex('client.<method>("<path>")').search('client.delete(\n  f"/generations/{gid}")').group("path") == "/generations/{gid}"
assert call_regex('client.<method>("<path>")').search('client.post("/projects", json={"a": 1})').group("path") == "/projects"
assert call_regex("<module>.<function>(").search("await ProjectRouter.delete_project_hard(pid").groupdict() == {"module": "ProjectRouter", "function": "delete_project_hard"}


# ---------- 에이전트 연결 프롬프트 (앱의 "에이전트 연결" 버튼과 README 가 이것 하나를 쓴다) ----------
def setup_prompt(lang="ko", onboarding=False):
    here = os.path.dirname(os.path.abspath(__file__))
    py, server = sys.executable, os.path.join(here, "mcp_server.py")
    command = python_command(server)
    shell_command = shlex.join(command)
    toml_command, toml_args = json.dumps(py, ensure_ascii=False), json.dumps(command[1:], ensure_ascii=False)
    other = "Other agents" if lang == "en" else "다른 에이전트"
    registration = (f"   - Claude Code: claude mcp add --scope user where-were-we -- {shell_command}\n"
                    f"   - Codex (~/.codex/config.toml):\n      [mcp_servers.where-were-we]\n      command = {toml_command}\n      args = {toml_args}\n"
                    f"   - {other}: stdio command {toml_command}, args {toml_args}")
    if onboarding:
        if lang == "en":
            return f"""Connect the service we are working on to where-were-we so I can see its code as a map. Do the setup for me; do not send me back to a project form or ask me to provide paths and branch names you can read yourself.

1. Inspect this agent's current MCP registration. If it needs changing, show the exact change and ask my permission first. Use only the configuration for this agent:
{registration}
Call projects to check the connection. If the tools are not available until a new session, explain that and stop; do not claim the service is connected.
2. From the current working folder and our conversation, identify the service and its code repositories. Read Git metadata to propose their names, locations and actual refs. Do not search unrelated folders or assume a linked repository is part of this service. Ask me about anything you cannot establish. Suggest a project name; check projects for an existing match and preserve existing repositories, refs, api_targets and shared_data when adding code.
3. Show a short proposal: service name, each repository and why it belongs. Ask me to confirm before saving, downloading code or collecting its first map. Do not include credentials in the proposal or configuration. Do not infer cross-repository API or shared database relationships from names alone.
4. After confirmation, use app_control action=catalog for the current command contract, then action=configure with project and configuration containing repositories and shared_data. Read the existing configuration first when changing a saved project; if you cannot read it, stop rather than replace it. Each repository needs a stable unique id, name, absolute local path or GitHub url, and refs based on real code. Preserve existing IDs and configuration. Use the existing code folder where available; do not move or edit the service code. For a new local folder connection, collect its initial map with refresh only if that collection was confirmed. Do not refresh already connected code or move an existing change comparison baseline as part of this setup.
5. A queued/running response is not completion. Query app_command_result with the same command ID until completed, then verify the actual result and app_state. Report each repository's connection and map separately; a saved connection is not proof that collection succeeded. Keep the guide available and tell me to continue to Connected code in the app. If a step fails, show what succeeded and the next action instead of claiming completion.
{reply_language(lang)}"""
        return f"""지금 함께 만드는 서비스를 where-were-we에 연결해서 코드 지도로 보고 싶어. 설정은 네가 도와줘. 앱에서 프로젝트 양식을 작성하라고 돌려보내거나, 네가 읽을 수 있는 폴더 경로와 브랜치 이름을 나에게 묻지 마.

1. 이 에이전트의 현재 MCP 등록을 확인해. 설정을 바꿔야 하면 바꿀 내용을 보여 주고 먼저 허락을 받아. 지금 사용하는 에이전트에 맞는 설정 하나만 사용해.
{registration}
projects를 불러 연결을 확인해. 새 세션을 열어야 도구가 보이면 그 사실과 다음 행동을 알려 주고 멈춰. 서비스를 연결했다고 말하지 마.
2. 현재 작업 폴더와 대화에서 서비스와 관련 코드 저장소를 확인해. Git 정보를 읽어 이름·위치·실제 refs를 제안하고, 관계없는 폴더를 탐색하거나 링크된 저장소를 모두 같은 서비스라고 단정하지 마. 알 수 없는 것만 물어봐. 프로젝트 이름을 제안하고 projects에서 같은 서비스가 이미 있는지 확인해. 기존 프로젝트에 추가할 때는 원래 repositories, refs, api_targets, shared_data를 보존해.
3. 저장하기 전에 서비스 이름·연결할 저장소·각 저장소를 포함하는 이유를 짧게 보여 줘. 저장·코드 다운로드·첫 지도 수집을 하기 전에 내 확인을 받아. 비밀값은 제안과 설정에 넣지 마. 이름만 보고 저장소 사이의 API 연결이나 같은 데이터베이스를 쓴다고 단정하지 마.
4. 확인받으면 app_control action=catalog로 현재 명령 형식을 읽고, action=configure에 project와 repositories·shared_data를 담은 configuration을 전달해. 기존 프로젝트를 바꿀 때는 원래 설정부터 읽고, 읽을 수 없으면 덮어쓰지 말고 멈춰. 저장소마다 고유하고 유지되는 id, name, 이 컴퓨터의 절대 path 또는 GitHub url, 실제 코드를 가리키는 refs를 써. 기존 ID와 설정을 보존해. 코드 폴더가 이미 있으면 그 폴더를 연결하고, 서비스 코드를 옮기거나 수정하지 마. 새로 연결한 폴더의 첫 지도는 내가 수집까지 확인한 경우에만 refresh로 가져와. 이미 연결된 코드에는 새로고침을 실행하거나 바뀐 것의 비교 시작점을 옮기지 마.
5. queued/running은 완료가 아니야. 같은 명령 ID로 app_command_result를 조회해 completed와 실제 결과를 확인하고 app_state를 읽어. 저장소마다 연결과 지도 수집 결과를 나눠 알려 줘. 연결 저장만 성공한 것을 지도 수집도 성공했다고 말하지 마. 안내 창은 남겨 두고 앱의 ‘연결한 코드’ 단계로 이어가도록 알려 줘. 실패하면 성공한 부분과 다음 행동을 알려 줘.
{reply_language(lang)}"""
    repos = []
    targets = []
    for p in projects():
        m = _read(p, "dev") or _read(p, "main") or {}
        if m.get("repositories"):
            targets.extend((p + " / " + repo["id"], {"repo": repo.get("configured_path", repo["path"])}) for repo in m["repositories"])
        else: targets.append((p,m))
    for p,m in targets:
        if m.get("repo"):
            import subprocess
            result = subprocess.run(["git", "-C", m["repo"], "remote", "get-url", "origin"], capture_output=True, text=True)
            url = result.stdout.strip() if result.returncode == 0 else ""
            if lang == "en":
                location = f"any working folder cloned from {url} (on this Mac, for example: {m['repo']})" if url else m["repo"]
            else:
                location = f"원격 {url} 을 받은 작업 폴더 어디서든 (이 맥에서는 예: {m['repo']})" if url else m["repo"]
            repos.append(f"   - {p}: {location}")
    if lang == "en":
        repo_lines = "\n".join(repos) or "   - (No maps yet; extract a project first.)"
        return f"""Connect where-were-we (a code structure map) to this agent and adapt it to my workflow. Before changing configuration, show the proposed edits and ask my permission.

1. Register the MCP server using the configuration for the agent you are running:
{registration}
2. Call the projects tool to verify the connection and show the result. Explain if a new session is needed to discover the tools.
3. Update the existing matching section in my global instructions (Claude Code: ~/.claude/CLAUDE.md; Codex: ~/.codex/AGENTS.md; otherwise the agent's global instructions). Add a section only if there is no matching one:

   ## where-were-we
   Use the where-were-we MCP tools when working in these repositories:
{repo_lines}
   - Before starting the day's work or making a plan, call changes. If the last refresh is over a day old, call refresh first.
   - Before editing files, screens, server requests, or data stores, call impact to check affected areas and overlapping PRs, branches, and issues. Include the affected areas in the plan.
   - To show a discussed feature in the running app, use app_targets to obtain its target ID and revision, then app_control select with the explicit project/repository/branch. Read app_state for the current selection. Only completed responses confirm application; use app_command_result for queued/running commands.
   - Preserve qualifications such as candidate, inferred, and unverified; do not report them as confirmed facts.
   - {reply_language(lang)}

4. Ask how much impact detail to include (screen count, screen/request lists, or overlapping work too). Apply my answer to the section.
5. Show the files and lines you changed."""
    repo_lines = "\n".join(repos) or "   - (아직 지도가 없다. 앱에서 프로젝트를 먼저 뽑는다)"
    return f"""where-were-we(코드 구조 지도)를 너에게 연결하고 내 작업 방식에 맞게 설정해 줘. 아래를 순서대로 하고, 설정 파일을 바꾸기 전에는 바꿀 내용을 보여 주고 내 허락을 받아.

1. MCP 서버를 등록한다. 지금 네가 어느 에이전트인지 보고 맞는 것 하나만 한다.
{registration}
2. 등록이 끝나면 where-were-we 의 projects 도구를 불러 연결을 확인하고 결과를 보여 준다. 도구가 안 보이면 새 세션에서 다시 확인해야 하는지 알려 준다.
3. 내 전역 지침 파일(Claude Code 는 ~/.claude/CLAUDE.md, Codex 는 ~/.codex/AGENTS.md, 다른 에이전트는 그 에이전트의 전역 지침)에 아래 단락을 넣는다. 비슷한 단락이 이미 있으면 새로 덧붙이지 말고 그 자리를 고친다.

   ## where-were-we
   아래 저장소에서 일할 때 where-were-we MCP 도구를 쓴다.
{repo_lines}
   - 하루 일을 시작하거나 계획을 세우기 전에 changes 를 부른다. 마지막 새로고침이 하루보다 오래됐으면 refresh 를 먼저 부른다.
   - 파일·화면·서버 기능·저장소를 고치기 전에 impact 로 닿는 곳과 같은 곳에서 진행 중인 PR·브랜치·이슈를 보고, 계획에 영향받는 곳을 적는다.
   - 대화 중인 기능을 실행 앱에 표시하려면 app_targets로 대상 ID와 revision을 얻고, 프로젝트·레포·브랜치를 명시해 app_control select로 선택한다. 현재 선택은 app_state로 읽는다. completed만 적용 완료이며 queued/running은 app_command_result로 확인한다.
   - 답에 "후보", "추정", "확인 못 한 것"이 붙은 내용은 사실로 옮기지 않는다.
   - {reply_language(lang)}

4. impact 결과를 계획에 얼마나 자세히 적을지 묻고 3번 단락에 반영한다(닿는 화면 수만 / 화면·서버 기능 목록까지 / 진행 중인 작업까지).
5. 마지막에 바꾼 파일과 바꾼 줄을 보여 준다."""


_prompt_repository = ""
if __name__ == "__main__":
    for argument in sys.argv[:]:
        if argument.startswith("--repository="):
            _prompt_repository = argument.partition("=")[2];sys.argv.remove(argument)

if __name__ == "__main__" and "--lang=en" in sys.argv:
    sys.argv.remove("--lang=en")
    _prompt_lang = "en"
else:
    _prompt_lang = "ko"
    if __name__ == "__main__" and "--lang=ko" in sys.argv:
        sys.argv.remove("--lang=ko")

if __name__ == "__main__" and sys.argv[1:] == ["settings"]:
    print(json.dumps(settings(),ensure_ascii=False))
elif __name__ == "__main__" and sys.argv[1:2] == ["save-settings"]:
    print(json.dumps(save_settings(json.loads(sys.argv[2])),ensure_ascii=False))
elif __name__ == "__main__" and sys.argv[1:] == ["setup"]:
    print(setup_prompt(lang=_prompt_lang))
elif __name__ == "__main__" and sys.argv[1:] == ["setup", "--onboarding"]:
    print(setup_prompt(lang=_prompt_lang, onboarding=True))
elif __name__ == "__main__" and sys.argv[1:2] == ["tests"]:  # mapcore.py tests <프로젝트> [서버 기능 …]
    print(tests_prompt(sys.argv[2], sys.argv[3:], lang=_prompt_lang, repository=_prompt_repository))
