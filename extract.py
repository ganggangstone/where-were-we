#!/usr/bin/env python3
"""뼈대 추출. 화면(라우트) → 화면이 닿는 API 함수 → 백엔드 경로.

사용: extract.py <저장소 경로> <ref> [출력 json]
저장소는 체크아웃을 건드리지 않고 `git show <ref>:<path>` 로만 읽는다.
"""
import fnmatch, json, os, re, subprocess, sys
from collections import defaultdict
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mapcore

REPO, REF = sys.argv[1], sys.argv[2]
OUT = sys.argv[3] if len(sys.argv) > 3 else None


def git(*args):
    return subprocess.run(["git", "-C", REPO, *args], capture_output=True, text=True, errors="replace", check=True).stdout


_files = None
def ls():
    global _files
    if _files is None:
        _files = set(git("ls-tree", "-r", "--name-only", REF).splitlines())
    return _files


_cache = {}
def show(path):
    if path not in _cache:
        _cache[path] = git("show", f"{REF}:{path}") if path in ls() else None
    return _cache[path]


def commit():
    return git("rev-parse", "--short", REF).strip()


# ---------- 1. 화면: App.tsx 의 <Route path=... element={<X ...> ----------
LAYOUT = json.loads(os.environ.get("WHERE_WERE_WE_LAYOUT", "{}"))
SRC = LAYOUT.get("frontend") or ("src" if "src/App.tsx" in ls() else "frontend/src")
BACKEND = LAYOUT.get("backend") or ("app" if "app/main.py" in ls() else "backend/app")
APP = SRC + "/App.tsx"
for area, root, required in (("frontend", SRC, APP), ("backend", BACKEND, BACKEND + "/main.py")):
    if area in LAYOUT and LAYOUT[area] and required not in ls():
        raise ValueError(f"Configured {area} root is missing its entry file: {required}")

def resolve(frm, spec):
    """상대 import 를 저장소 경로로. 없으면 None."""
    if not spec.startswith("."):
        return None
    base = os.path.normpath(os.path.join(os.path.dirname(frm), spec))
    for cand in (base, base + ".ts", base + ".tsx", base + "/index.ts", base + "/index.tsx"):
        if cand in ls() and cand.endswith((".ts", ".tsx")):
            return cand
    return None


IMPORT_RE = re.compile(r"^import\s+(?:type\s+)?(\{[^}]*\}|\*\s+as\s+\w+|\w+(?:\s*,\s*\{[^}]*\})?)\s+from\s+['\"]([^'\"]+)['\"]", re.M)

def imports(path):
    """[(이름들 문자열, 해석된 경로)] — 이름들 문자열은 'X' / '{ a, b as c }' / '* as ns'."""
    src = show(path) or ""
    out = []
    for m in IMPORT_RE.finditer(src):
        names, spec = m.group(1), m.group(2)
        tgt = resolve(path, spec)
        if tgt:
            out.append((names.strip(), tgt))
    return out


def balanced(text, start, open_ch="{", close_ch="}"):
    """text[start] 가 open_ch 일 때 짝이 맞는 close_ch 까지의 안쪽 문자열."""
    depth, i = 0, start
    while i < len(text):
        if text[i] == open_ch: depth += 1
        elif text[i] == close_ch:
            depth -= 1
            if depth == 0:
                return text[start + 1:i]
        i += 1
    return text[start + 1:]


def screens():
    src = show(APP) or ""
    comp_file = {}
    for names, tgt in imports(APP):
        for n in re.findall(r"\w+(?:\s+as\s+\w+)?", names.strip("{} ")):
            comp_file[n.split()[-1]] = tgt
    rows = []
    starts = [m.start() for m in re.finditer(r"<Route\b", src)]
    for i, st in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else len(src)
        block = src[st:end]
        pm = re.search(r"\bpath=\"([^\"]+)\"", block)
        em = re.search(r"\belement=\{", block)
        if not pm or not em:
            continue
        element = balanced(block, em.end() - 1)
        line_start = src.rfind("\n", 0, st) + 1
        cond = re.search(r"import\.meta\.env\.(\w+)\s*===\s*'([^']*)'", src[line_start:st])
        comps = re.findall(r"<([A-Za-z_]\w*)", element)
        inner = [c for c in comps if c in comp_file]
        page = inner[-1] if inner else None
        rows.append({
            "path": pm.group(1),
            "component": page or (comps[0] if comps else None),
            "file": comp_file.get(page) if page else None,
            "evidence": f"{APP}:{src[:st].count(chr(10)) + 1}",
            "condition": f"{cond.group(1)} === '{cond.group(2)}'" if cond else None,
            "redirect": page is None,
        })
    return rows


# ---------- 2. 화면 파일에서 상대 import 를 따라 닿는 파일 ----------
def reachable(start):
    seen, stack = {start}, [start]
    while stack:
        f = stack.pop()
        for _, tgt in imports(f):
            if tgt.startswith(SRC) and tgt not in seen:
                seen.add(tgt); stack.append(tgt)
    return seen


# ---------- 3. API 함수: frontend/src/api/*.ts 의 export 함수 → api.<method>(<path>) ----------
API_DIR = SRC + "/api/"
EXPORT_RE = re.compile(r"^export\s+(?:async\s+)?(?:function\s+(\w+)|const\s+(\w+)\s*=)", re.M)
CALL_RE = re.compile(r"\bapi\.(get|post|put|patch|delete)(?:<[^(]*?>)?\(\s*(`[^`]*`|'[^']*'|\"[^\"]*\"|[A-Za-z_]\w*)")

CONST_TPL_RE = re.compile(r"\bconst\s+(\w+)\s*=\s*(?:\([^)]*\)\s*=>\s*)?`([^`]*)`")

def const_templates(src):
    """같은 파일/함수 안의 `const base = (id) => `/x/${id}`` 와 `const url = `...`` 를 모은다."""
    return {m.group(1): m.group(2) for m in CONST_TPL_RE.finditer(src)}


def expand(tpl, table, depth=0):
    """템플릿 안의 ${NAME} / ${NAME(...)} 를 같은 파일의 const 템플릿으로 바꾼다. 나머지 ${...} 는 {}."""
    out, i = "", 0
    while i < len(tpl):
        if tpl.startswith("${", i):
            inner = balanced(tpl, i + 1)
            i += len(inner) + 3
            nm = re.match(r"\s*(\w+)\s*(\(|$)", inner)
            if nm and nm.group(1) in table and depth < 3:
                out += expand(table[nm.group(1)], table, depth + 1)
            else:
                out += "{}"
        else:
            out += tpl[i]; i += 1
    return out


def normalize(p, table=None):
    """프런트 경로 템플릿과 FastAPI 경로를 같은 꼴로. 변수 자리는 {}."""
    p = p.strip("`'\"")
    p = expand(p, table or {})
    p = p.split("?")[0]
    p = re.sub(r"\{[^}]*\}", "{}", p)
    return p.rstrip("/") or "/"


def calls_in(src, lo=0, hi=None):
    out = []
    text = src[lo:hi]
    table = {**const_templates(src), **const_templates(text)}
    for m in CALL_RE.finditer(text):
        line = src[: lo + m.start()].count("\n") + 1
        raw = m.group(2)
        kind = "variable" if re.fullmatch(r"[A-Za-z_]\w*", raw) else ("template" if raw.startswith("`") else "string")
        if kind == "variable" and raw in table:
            path, kind = normalize(table[raw], table), "template"
        elif kind == "variable":
            path = None
        else:
            path = normalize(raw, table)
        out.append({"method": m.group(1).upper(), "path": path, "raw": raw, "kind": kind, "line": line})
    return out


def api_functions():
    """{(file, name): {calls:[...], line}}  +  파일 단위 인라인 호출(함수 밖/다른 파일)."""
    fns = {}
    for f in sorted(x for x in ls() if x.startswith(SRC) and x.endswith((".ts", ".tsx"))):
        src = show(f)
        if "api." not in src:
            continue
        if f.startswith(API_DIR):
            marks = [(m.start(), m.group(1) or m.group(2)) for m in EXPORT_RE.finditer(src)]
            for i, (pos, name) in enumerate(marks):
                end = marks[i + 1][0] if i + 1 < len(marks) else None
                cs = calls_in(src, pos, end)
                if cs:
                    fns[(f, name)] = {"file": f, "name": name, "line": src[:pos].count("\n") + 1, "calls": cs}
        else:
            cs = calls_in(src)
            if cs:
                fns[(f, "<inline>")] = {"file": f, "name": "<inline>", "line": cs[0]["line"], "calls": cs}
    return fns


def used_api_functions(file, fns):
    """이 파일이 import 해서 실제로 부르는 api 함수 + 이 파일의 인라인 호출."""
    src = show(file) or ""
    used = set()
    for names, tgt in imports(file):
        if not tgt.startswith(API_DIR):
            continue
        ns = re.fullmatch(r"\*\s+as\s+(\w+)", names)
        if ns:
            for (f, n) in fns:
                if f == tgt and re.search(rf"\b{ns.group(1)}\.{n}\b", src):
                    used.add((f, n))
            continue
        for item in re.findall(r"\w+(?:\s+as\s+\w+)?", names.strip("{} ")):
            parts = item.split()
            orig, local = parts[0], parts[-1]
            if (tgt, orig) in fns and len(re.findall(rf"\b{local}\b", src)) > 1:
                used.add((tgt, orig))
    if (file, "<inline>") in fns:
        used.add((file, "<inline>"))
    return used


# ---------- 3b. 동작: 파일 안의 <button>, <Link>, navigate() ----------
TAG_RE = re.compile(r"<button\b")
JSX_TEXT_RE = re.compile(r">([^<>{}]+)<")

def jsx_text(inner):
    """JSX 안쪽에서 사람이 읽는 글자만. {식} 은 뺀다."""
    parts = [" ".join(t.split()) for t in JSX_TEXT_RE.findall(">" + inner + "<")]
    parts = [t for t in parts if t and not re.fullmatch(r"[\s/+\-·|•]*", t)]
    return " ".join(parts)


def attr(open_tag, name):
    m = re.search(rf"\b{name}=(?:\"([^\"]*)\"|'([^']*)'|\{{)", open_tag)
    if not m:
        return None
    if m.group(1) is not None or m.group(2) is not None:
        return m.group(1) if m.group(1) is not None else m.group(2)
    return balanced(open_tag, m.end() - 1)


def mutation_table(src):
    """const x = useMutation({ mutationFn: fn })  /  usePaidMutation(fn  →  {x: fn}"""
    t = {}
    for m in re.finditer(r"const\s+(\w+)\s*=\s*use(?:Paid)?Mutation\(", src):
        body = balanced(src, m.end() - 1, "(", ")")
        fm = re.search(r"mutationFn\s*:\s*(?:async\s*)?(?:\([^)]*\)\s*=>\s*)?(\w+)", body) or re.match(r"\s*(\w+)", body)
        if fm:
            t[m.group(1)] = fm.group(1)
    return t


def handler_body(src, expr):
    """onClick 식에서 실제로 실행되는 코드 조각. 이름만 있으면 같은 파일의 정의를 찾는다. 정의가 없으면(부모가 준 함수) None."""
    expr = expr.strip()
    if re.fullmatch(r"\w+", expr):
        m = re.search(rf"(?:const|let)\s+{expr}\s*=\s*(?:async\s*)?(?:\([^)]*\)|\w+)\s*=>\s*", src) or re.search(rf"(?:async\s+)?function\s+{expr}\s*\([^)]*\)\s*", src)
        if not m:
            return None
        rest = src[m.end():]
        return balanced(rest, 0) if rest.startswith("{") else rest.split("\n")[0]
    return expr


def expand_local(src, body, depth=2, seen=None):
    """핸들러 본문에서 부르는, 같은 파일에 정의된 함수의 본문을 depth 단계까지 붙인다."""
    if body is None or depth == 0:
        return body
    seen = seen if seen is not None else set()
    extra = []
    for name in set(re.findall(r"\b([a-zA-Z_]\w*)\s*\(", body)):
        if name in seen or len(name) < 3:
            continue
        seen.add(name)
        b = handler_body(src, name)
        if b and b != name:
            extra.append(expand_local(src, b, depth - 1, seen) or "")
    return body + "\n" + "\n".join(extra)


def classify(body, api_names, muts, nav_paths):
    """핸들러 코드 → (종류, 닿는 api 함수 이름들, 이동 주소)."""
    if body is None:
        return "prop", [], None
    apis = [n for n in api_names if re.search(rf"\b{n}\s*\(", body)]
    if re.search(r"\bapi\.(get|post|put|patch|delete)\s*[<(]", body):
        apis.append("<inline>")  # 이 파일 안에서 api.<method>(...) 를 직접 부른다
    for var, fn in muts.items():
        if re.search(rf"\b{var}\.mutate(Async)?\s*\(", body) and fn in api_names:
            apis.append(fn)
    nav = re.search(r"navigate\(", body)
    if apis:
        return "api", sorted(set(apis)), None
    if nav:
        expr = balanced(body, nav.end() - 1, "(", ")").split(",")[0]
        return "nav", [], expr
    if re.search(r"\bset[A-Z]\w*\s*\(", body) or re.search(r"\bopen\w*\s*\(", body):
        return "state", [], None
    return "unknown", [], None


def normalize_route(raw):
    """`/projects/${id}/board` → /projects/:p/board  (화면 주소와 맞추기 위해 변수 자리를 :p 로)."""
    p = raw.strip("`'\"").split("?")[0]
    p = expand(p, {})
    return re.sub(r"\{\}", ":p", p).rstrip("/") or "/"


def nav_targets(expr, screens):
    """이동 식 하나 → 갈래 목록. 식 안의 주소 글자마다 화면을 맞춘다. 주소 글자가 없으면 빈 목록(변수에서 옴)."""
    lits = re.findall(r"`[^`]*`|'[^']*'|\"[^\"]*\"", expr)
    out = []
    for raw in lits:
        r = normalize_route(raw)
        if not r.startswith("/"):
            continue
        out.append({"to": route_match(r, screens), "raw": raw.strip("`'\"")})
    cond = " ".join(expr.split()) if (len(out) != 1 or not re.fullmatch(r"\s*(`[^`]*`|'[^']*'|\"[^\"]*\")\s*", expr)) else None
    return out, cond


def route_match(target, screens):
    """이동 주소를 화면 주소 패턴에 맞춘다. 변수 자리는 아무 조각이나 된다."""
    ts = target.split("/")
    loose = []
    for sc in screens:
        ps = sc["path"].rstrip("?").split("/")
        if len(ps) != len(ts):
            continue
        if all(a == b or a.startswith(":") for a, b in zip(ps, ts)):
            return sc["path"]
        if all(a == b or a.startswith(":") or b == ":p" for a, b in zip(ps, ts)):
            loose.append(sc["path"])
    # 이동 주소의 변수 자리가 화면 주소의 고정 글자와 만나는 경우는 후보가 하나일 때만 받는다.
    return loose[0] if len(loose) == 1 else None


# `/projects/${id}` 가 /projects/archive 로 잘못 붙던 것을 막는 확인
assert route_match("/projects/:p", [{"path": "/projects/archive"}, {"path": "/projects/:projectId"}]) == "/projects/:projectId"
assert route_match("/admin/:p", [{"path": "/admin/users"}]) == "/admin/users"
assert route_match("/admin/:p", [{"path": "/admin/users"}, {"path": "/admin/usage"}]) is None


def actions_in(file, fns, screens):
    """파일 안의 버튼·링크·navigate 를 동작 목록으로."""
    src = show(file) or ""
    api_names = set()
    for names, tgt in imports(file):
        if tgt.startswith(API_DIR):
            for item in re.findall(r"\w+(?:\s+as\s+\w+)?", names.strip("{} ")):
                parts = item.split()
                if (tgt, parts[0]) in fns:
                    api_names.add(parts[-1])
    muts = mutation_table(src)
    out = []
    for m in TAG_RE.finditer(src):
        st = m.start()
        gt = src.find(">", st)
        if gt < 0: continue
        open_tag = src[st:gt + 1]
        while open_tag.count("{") > open_tag.count("}"):  # 속성 안의 > 를 건너뛴다
            gt = src.find(">", gt + 1)
            if gt < 0: break
            open_tag = src[st:gt + 1]
        end = src.find("</button>", gt)
        inner = src[gt + 1:end] if end > 0 else ""
        def lit(v):  # 글자 그대로 적힌 속성값만. 식이면 버린다.
            if not v or re.search(r"[`${}]", v) or re.fullmatch(r"[\w.?\[\]'\" ]*\w\.\w[\w.?\[\]'\" ]*", v) or re.fullmatch(r"\w+", v) and v.isascii():
                return ""
            return v
        label = jsx_text(inner) or lit(attr(open_tag, "title")) or lit(attr(open_tag, "aria-label")) or ""
        dynamic = bool(re.search(r"\{[^}]*\?[^}]*:[^}]*\}", inner))  # 상태에 따라 글자가 바뀜
        onclick = attr(open_tag, "onClick")
        body = expand_local(src, handler_body(src, onclick)) if onclick else None
        kind, apis, nav = classify(body, api_names, muts, None) if onclick else ("none", [], None)
        # 이 버튼의 처리 코드가 직접 보내는 요청. 같은 파일의 다른 버튼이 보내는 요청과 가르는 데 쓴다.
        direct = [{"method": c["method"], "path": c["path"]} for c in calls_in(src + "\n" + body, len(src) + 1) if c["path"]] if body and "<inline>" in apis else []
        line = src[:st].count("\n") + 1
        targets, cond = nav_targets(nav, screens) if nav else ([], None)
        out.append({"label": label, "dynamic_label": dynamic, "kind": kind, "api_functions": apis, "calls": direct,
                    "to": next((t["to"] for t in targets if t["to"]), None), "targets": targets, "cond": cond,
                    "to_raw": " ".join(nav.split()) if nav else None, "file": file, "line": line})
    for m in re.finditer(r"<(?:Link|NavLink)\b", src):
        st = m.start(); gt = src.find(">", st)
        open_tag = src[st:gt + 1]
        while open_tag.count("{") > open_tag.count("}"):
            gt = src.find(">", gt + 1); open_tag = src[st:gt + 1]
        end = src.find("</Link>", gt); end = end if end > 0 else src.find("</NavLink>", gt)
        to = attr(open_tag, "to")
        if not to: continue
        targets, cond = nav_targets(to if re.match(r"[`'\"]", to) else to, screens) if re.search(r"[`'\"]", to) else nav_targets("`" + to + "`", screens)
        if not [t for t in targets if t["to"]] and re.fullmatch(r"\w+\.(to|path|href)", to.strip()):
            # 메뉴 목록에서 고르는 링크: 같은 파일의 `to: '/…'` 항목들이 갈 수 있는 곳이다
            field = to.strip().split(".")[1]
            lits = re.findall(rf"\b{field}\s*:\s*(`[^`]*`|'[^']*'|\"[^\"]*\")", src)
            targets = [{"to": route_match(normalize_route(l), screens), "raw": l.strip("`'\"")} for l in lits if normalize_route(l).startswith("/")]
            cond = "메뉴 목록에서 고른 항목" if targets else None
        out.append({"label": jsx_text(src[gt + 1:end] if end > 0 else ""), "dynamic_label": False, "kind": "nav", "api_functions": [],
                    "to": next((t["to"] for t in targets if t["to"]), None), "targets": targets, "cond": cond,
                    "to_raw": " ".join(to.split()), "file": file, "line": src[:st].count("\n") + 1})
    return out


def heading_of(file):
    src = show(file) or ""
    m = re.search(r"<h1[^>]*>([^<{]+)<", src)
    return m.group(1).strip() if m else None


# ---------- 4. 백엔드: routers/*.py 의 prefix + @router.<method>("...") + def ----------
DECO_RE = re.compile(r"^@(\w+)\.(get|post|put|patch|delete)\(\s*(?:\n\s*)?([\"'][^\"']*[\"'])", re.M)
ROUTER_RE = re.compile(r"^(\w+)\s*=\s*APIRouter\((.*?)\)", re.M | re.S)

def backend_routes():
    main = show(BACKEND + "/main.py") or ""
    alias_mod = {}
    for m in re.finditer(r"^from\s+[\w.]*routers\s+import\s+(.+)$", main, re.M):
        for item in m.group(1).split(","):
            parts = item.strip().split()
            if parts:
                alias_mod[parts[-1]] = parts[0]
    mounted = {}  # (module, router var) -> include prefix
    for m in re.finditer(r"include_router\(\s*(\w+)\.(\w+)(.*?)\)", main, re.S):
        pm = re.search(r"prefix\s*=\s*[\"']([^\"']*)[\"']", m.group(3))
        mounted[(alias_mod.get(m.group(1), m.group(1)), m.group(2))] = pm.group(1) if pm else ""
    rows = []
    files = [BACKEND + "/main.py"] + sorted(x for x in ls() if x.startswith(BACKEND + "/routers/") and x.endswith(".py"))
    for f in files:
        src = show(f) or ""
        mod = os.path.basename(f)[:-3]
        prefixes = {}
        for rm in ROUTER_RE.finditer(src):
            pm = re.search(r"prefix\s*=\s*[\"']([^\"']*)[\"']", rm.group(2))
            prefixes[rm.group(1)] = pm.group(1) if pm else ""
        for m in DECO_RE.finditer(src):
            var = m.group(1)
            line = src[: m.start()].count("\n") + 1
            dm = re.search(r"^\s*(?:async\s+)?def\s+(\w+)", src[m.end():], re.M)
            is_mounted = var == "app" or (mod, var) in mounted
            inc = mounted.get((mod, var), "")
            rows.append({"method": m.group(2).upper(), "path": normalize(inc + prefixes.get(var, "") + m.group(3).strip("\"'")),
                         "function": dm.group(1) if dm else None, "file": f, "line": line, "mounted": is_mounted})
    return rows


# ---------- 4b. 백엔드 함수가 만지는 것: DB 테이블, 외부 서비스, 들어오는 것, 테스트 ----------
EXTERNAL_DIRS = {"byteplus": "BytePlus", "elevenlabs": "ElevenLabs", "topaz": "Topaz", "llm": "LLM(Anthropic)", "imagegen": "이미지 생성"}

def models():
    """{클래스 이름: 테이블 이름}"""
    out = {}
    for f in ls():
        if not (f.startswith(BACKEND + "/models/") and f.endswith(".py")):
            continue
        src = show(f)
        for m in re.finditer(r"^class\s+(\w+)\((?:Base|\w*Base)\):(.*?)(?=^class\s|\Z)", src, re.M | re.S):
            tm = re.search(r"__tablename__\s*=\s*[\"'](\w+)[\"']", m.group(2))
            out[m.group(1)] = tm.group(1) if tm else m.group(1)
    return out


def py_imports(src):
    """from ..a.b import x, y as z  →  {local: ('a.b', 'x')}"""
    t = {}
    # 괄호로 여러 줄에 걸친 것과 한 줄짜리를 따로 찾는다. 함수 안에서 들여 쓴 import 도 본다.
    found = [(m.group(1), m.group(2)) for m in re.finditer(r"^[ \t]*from\s+\.*([\w.]*)\s+import\s*\(([^)]*)\)", src, re.M)]
    found += [(m.group(1), m.group(2)) for m in re.finditer(r"^[ \t]*from\s+\.*([\w.]*)\s+import\s+([^(\s][^\n]*)$", src, re.M)]
    for mod, names in found:
        for item in names.split("#")[0].replace("\n", " ").split(","):
            parts = item.strip().split()
            if parts:
                t[parts[-1]] = (mod, parts[0])
    return t



# 함수 안에서 들여 쓴 import 와 괄호로 여러 줄에 걸친 import 를 놓치던 것을 막는 확인
assert py_imports("def f():\n  from ..services import a as A, b  # 메모\nfrom .m import (\n    p,\n    q as r,\n)\n") == {"A": ("services", "a"), "b": ("services", "b"), "p": ("m", "p"), "r": ("m", "q")}

def func_body(src, name):
    m = re.search(rf"^(\s*)(?:async\s+)?def\s+{re.escape(name)}\s*\(", src, re.M)
    if not m:
        return ""
    indent = m.group(1)
    rest = src[m.end():]
    end = re.search(rf"^{indent}(?:@|(?:async\s+)?def\s|class\s)", rest, re.M)
    return rest[: end.start()] if end else rest


def service_file(mod):
    """'services.pipeline_launch' → backend/app/services/pipeline_launch.py"""
    cand = BACKEND + "/" + mod.replace(".", "/") + ".py"
    return cand if cand in ls() else None


def route_touches(route, model_table):
    """라우트 함수 본문(+ 거기서 부르는 services 함수 한 단계)에서 테이블·외부·입력을 뽑는다."""
    src = show(route["file"])
    body = func_body(src, route["function"] or "")
    imps = py_imports(src)
    bodies = [body]
    services = []
    # 한 단계 따라가기: 본문에서 부르는, services/* 에서 가져온 함수
    for local, (mod, orig) in imps.items():
        if mod.startswith("services") and re.search(rf"\b{re.escape(local)}\s*\(", body):
            sf = service_file(mod)
            if sf:
                bodies.append(func_body(show(sf), orig)); services.append(sf)
        # from ..services import 모듈  →  모듈.함수(...) 로 부르는 경우
        if mod in ("services", "app.services") or mod.endswith(".services"):
            called = set(re.findall(rf"\b{re.escape(local)}\.(\w+)\s*\(", body))
            sf = service_file("services." + orig) if called else None
            if sf:
                ssrc = show(sf)
                bodies += [func_body(ssrc, fn) for fn in called]; services.append(sf)
    text = "\n".join(bodies)
    tables = sorted({model_table[c] for c in model_table if re.search(rf"\b{c}\b", text)})
    ext = set()
    for local, (mod, orig) in imps.items():
        top = mod.split(".")[0]
        if top in EXTERNAL_DIRS and re.search(rf"\b{re.escape(local)}\b", body):
            ext.add(EXTERNAL_DIRS[top])
    for sf_body in bodies[1:]:
        for top, nm in EXTERNAL_DIRS.items():
            if re.search(rf"\b{top}\b", sf_body):
                ext.add(nm)
    if re.search(r"\bhttpx\.", text):
        ext.add("HTTP 호출")
    dm = re.search(rf"def\s+{re.escape(route['function'] or '')}\s*\(", src)
    inputs = []
    if dm:
        params, depth, cur = [], 0, ""
        for ch in src[dm.end():]:
            if ch in "([{": depth += 1
            elif ch in ")]}":
                if depth == 0: break
                depth -= 1
            if ch == "," and depth == 0:
                params.append(cur); cur = ""; continue
            cur += ch
        params.append(cur)
        for prm in params:
            prm = " ".join(prm.split())
            if not prm or prm in ("*", "/"):
                continue
            nm = prm.split(":")[0].split("=")[0].strip()
            ty = prm.split(":", 1)[1].split("=")[0].strip() if ":" in prm else ""
            if re.search(r"Depends|AsyncSession|Session\b|Request\b|BackgroundTasks|Response\b", ty) or nm in ("self", "_", "db", "session", "current_user", "user", "me", "request"):
                continue
            ty = re.sub(r"^Annotated\[(.*?),.*\]$", r"\1", ty)
            inputs.append(f"{nm}: {ty}" if ty else nm)
    return {"tables": tables, "externals": sorted(ext), "inputs": inputs, "services": sorted(set(services))}


def module_file(mod, router_files):
    """import 에 적힌 모듈 경로(a.b.c, 앞의 점은 뗀 것) → 그 경로로 끝나는 서버 기능 파일. 하나로 정해지지 않으면 None."""
    tail = "/" + mod.replace(".", "/") + ".py"
    found = [f for f in router_files if ("/" + f).endswith(tail)]
    return found[0] if len(found) == 1 else None


assert module_file("routers.generations", {"backend/app/routers/generations.py"}) == "backend/app/routers/generations.py"
assert module_file("routers.users", {"a/routers/users.py", "b/routers/users.py"}) is None  # 둘이면 잇지 않는다
assert module_file("generations", {"backend/app/routers/old_generations.py"}) is None


def backend_tests(be_index, be, conf):
    """테스트 규칙(mapcore.tests_conf)으로 라우트마다 테스트 파일을 모은다. 돌려주는 것: (hits, 대조에 실패한 records 수)"""
    hits = defaultdict(set)
    by_func = defaultdict(list)  # (서버 기능 파일, 함수 이름) → 라우트
    for r in be:
        if r.get("function"):
            by_func[(r["file"], r["function"])].append(r)
    router_files = {k[0] for k in by_func}
    pats = [mapcore.call_regex(t) for t in conf["calls"]]
    is_test = lambda f: f.endswith(".py") and any(fnmatch.fnmatch(f if "/" in g else os.path.basename(f), g) for g in conf["files"])
    for f in ls():
        if not is_test(f):
            continue
        src = show(f) or ""
        imps = py_imports(src)
        for pat in pats:
            for m in pat.finditer(src):
                g = m.groupdict()
                if g.get("path"):
                    rs = be_index.get((g["method"].upper(), normalize(g["path"])), [])
                elif g.get("module"):  # 서버 기능 파일을 import 한 이름.함수(
                    mod, name = imps.get(g["module"], (None, None))
                    rf_ = mod is not None and module_file(f"{mod}.{name}" if mod else name, router_files)
                    rs = by_func.get((rf_, g["function"]), []) if rf_ else []
                else:  # 서버 기능 함수를 import 해서 바로 부름
                    mod, name = imps.get(g["function"], (None, None))
                    rf_ = mod and module_file(mod, router_files)
                    rs = by_func.get((rf_, name), []) if rf_ else []
                for r in rs:
                    hits[(r["file"], r["line"])].add(f)
    stale = 0
    for rec in conf["records"]:  # 에이전트가 하나씩 넘긴 것. 이 커밋에서도 그 줄(±2)에 그 글자가 있어야 센다
        r = next((r for r in be if f"{r['file']}::{r.get('function')}" == rec.get("route")), None)
        lines = (show(rec.get("file", "")) or "").splitlines(); q = re.sub(r"\s+", "", rec.get("quote") or ""); ln = rec.get("line") or 0
        if r and len(q) >= 6 and any(q in re.sub(r"\s+", "", l) for l in lines[max(0, ln - 3):ln + 2]):
            hits[(r["file"], r["line"])].add(rec["file"])
        else:
            stale += 1
    return hits, stale


# ---------- 5. 조립 ----------
def main():
    scr = [] if "frontend" in LAYOUT and LAYOUT["frontend"] is None else screens()
    fns = {} if "frontend" in LAYOUT and LAYOUT["frontend"] is None else api_functions()
    be = [] if "backend" in LAYOUT and LAYOUT["backend"] is None else backend_routes()
    be_index = defaultdict(list)
    for r in be:
        be_index[(r["method"], r["path"])].append(r)
    model_table = models()
    HOME = os.path.dirname(os.path.abspath(OUT)) if OUT else ""
    test_hits, stale_records = backend_tests(be_index, be, mapcore.tests_conf(HOME))
    for r in be:
        if r["mounted"]:
            r.update(route_touches(r, model_table))
        r["tests"] = sorted(test_hits.get((r["file"], r["line"]), ()))

    def match(call):
        if call["path"] is None:
            return []
        return be_index.get((call["method"], call["path"]), [])

    # 화면 → api 함수.  file_screens: 파일 → 그 파일이 닿는 화면 (PR·브랜치가 건드린 파일을 화면에 잇는 데 쓴다)
    hit_fns = set()
    file_screens = defaultdict(set)
    for s in scr:
        s["api_functions"] = []
        if not s["file"]:
            continue
        files = reachable(s["file"])
        for f in files:
            file_screens[f].add(s["path"])
        used = {}  # api 함수 → 그 함수를 실제로 쓰는 파일(화면 파일이거나 그 아래 부품)
        for f in sorted(files, key=lambda x: (x != s["file"], x)):
            for key in used_api_functions(f, fns):
                used.setdefault(key, f)
        for key, via in sorted(used.items()):
            hit_fns.add(key)
            s["api_functions"].append({"file": key[0], "name": key[1], "via": via})
            for c in fns[key]["calls"]:
                for h in match(c):
                    for f in [h["file"], *h.get("services", [])]:  # 서버 쪽 파일을 고친 PR 도 화면에 잇는다
                        file_screens[f].add(s["path"])

    # 화면 → 동작 (버튼·링크). 화면 파일의 것이 먼저, 그다음 부품 파일.
    for s in scr:
        s["heading"] = heading_of(s["file"]) if s["file"] else None
        s["actions"] = []
        if not s["file"]:
            continue
        for f in sorted(reachable(s["file"]), key=lambda x: (x != s["file"], x)):
            if f.startswith(API_DIR):
                continue
            for a in actions_in(f, fns, scr):
                a["via"] = None if f == s["file"] else f
                s["actions"].append(a)

    # api 함수 → 백엔드
    matched_be = set()
    unresolved = []
    fn_rows = []
    for key, fn in sorted(fns.items()):
        row = dict(fn); row["calls"] = []
        for c in fn["calls"]:
            hits = match(c)
            for h in hits:
                matched_be.add((h["file"], h["line"]))
            row["calls"].append({**c, "backend": [{"file": h["file"], "line": h["line"], "function": h["function"]} for h in hits]})
            if not hits:
                unresolved.append({"api_function": f"{fn['file']}:{fn['name']}", **c})
        row["used_by_screens"] = key in hit_fns
        fn_rows.append(row)

    orphans = [r for r in be if r["mounted"] and (r["file"], r["line"]) not in matched_be]
    out = {
        "ref": mapcore.configured_refs().get(os.path.basename(OUT or "")[:-5], REF), "commit": commit(), "repo": os.path.abspath(REPO), "models": model_table,
        "coverage": {"frontend": APP in ls() and LAYOUT.get("frontend", True) is not None, "backend": BACKEND + "/main.py" in ls() and LAYOUT.get("backend", True) is not None},
        "extractor": mapcore.extractor_id(HOME),  # 뽑는 방법(코드와 테스트 규칙)이 바뀌면 지도 두 장을 그대로 비교할 수 없다
        "screens": scr, "api_functions": fn_rows, "backend_routes": be,
        "unresolved_calls": unresolved, "backend_routes_without_screen": orphans,
        "file_screens": {f: sorted(v) for f, v in sorted(file_screens.items())},
    }
    if OUT:
        os.makedirs(os.path.dirname(OUT), exist_ok=True)
        # 직전 지도 한 장(P5): 기준 커밋이 바뀌었으면 지금 것을 .prev 로 남기고 새로 쓴다
        if os.path.exists(OUT) and json.load(open(OUT)).get("commit") != out["commit"]:
            os.replace(OUT, OUT[:-5] + ".prev.json")
        json.dump(out, open(OUT, "w"), ensure_ascii=False, indent=1)

    total_calls = sum(len(f["calls"]) for f in fn_rows)
    ok = total_calls - len(unresolved)
    print(f"{REF} ({out['commit']})")
    print(f"  화면 {len(scr)}개 (그중 리다이렉트/래퍼만 {sum(1 for s in scr if s['redirect'])}, 파일 못 찾음 {sum(1 for s in scr if not s['redirect'] and not s['file'])})")
    print(f"  api 함수 {len(fn_rows)}개, 호출 {total_calls}개: 짝 맞음 {ok}, 짝 못 찾음 {len(unresolved)} (변수 경로 {sum(1 for u in unresolved if u['kind']=='variable')})")
    print(f"  백엔드 경로 {len(be)}개 (마운트됨 {sum(1 for r in be if r['mounted'])}), 어느 화면도 안 부름 {len(orphans)}")
    print(f"  화면에서 안 쓰는 api 함수 {sum(1 for f in fn_rows if not f['used_by_screens'])}")
    acts = [a for s in scr for a in s["actions"]]
    kinds = defaultdict(int)
    for a in acts: kinds[a["kind"]] += 1
    tested = sum(1 for r in be if r["mounted"] and r["tests"])
    print(f"  테이블 {len(set(model_table.values()))}개, 테스트가 닿는 백엔드 경로 {tested}/{sum(1 for r in be if r['mounted'])}" + (f", 대조에 실패한 테스트 기록 {stale_records}" if stale_records else ""))
    print(f"  동작 {len(acts)}개 (화면별 중복 포함): " + ", ".join(f"{k} {v}" for k, v in sorted(kinds.items())) + f", 글자 없음 {sum(1 for a in acts if not a['label'])}, 이동 짝 못 찾음 {sum(1 for a in acts if a['kind']=='nav' and not a['to'])}")


if __name__ == "__main__":
    main()
