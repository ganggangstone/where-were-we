#!/usr/bin/env python3
"""뼈대 추출. 화면(라우트) → 화면이 닿는 API 함수 → 백엔드 경로.

사용: extract.py <저장소 경로> <ref> [출력 json]
저장소는 체크아웃을 건드리지 않고 `git show <ref>:<path>` 로만 읽는다.
"""
import fnmatch, functools, html, json, os, re, subprocess, sys
from collections import defaultdict
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mapcore
import source_signals
import structure_index

REPO, REF = sys.argv[1], sys.argv[2]
OUT = sys.argv[3] if len(sys.argv) > 3 else None


def git(*args):
    return subprocess.run(["git", "-C", REPO, *args], capture_output=True, text=True, errors="replace", check=True).stdout


PIN = git('rev-parse', '--verify', REF + '^{commit}').strip()
_entries, _files, _oids = [], set(), {}
for row in subprocess.check_output(['git', '-C', REPO, 'ls-tree', '-rz', '--full-tree', PIN]).split(b'\0'):
    if not row:
        continue
    meta, path = row.split(b'\t', 1)
    mode, _, oid = meta.split(b' ')
    _entries.append((mode, path))
    if mode in (b'100644', b'100755'):
        try:
            _files.add(path.decode('utf-8')); _oids[path.decode('utf-8')] = oid
        except UnicodeDecodeError:
            # Count all tracked files; map evidence paths must round-trip through UTF-8 JSON.
            continue


def ls():
    return _files


_cache = {}
def show(path):
    if path not in _cache:
        _cache[path] = git("show", f"{PIN}:{path}") if path in ls() else None
    return _cache[path]


def preload(paths):
    """Read many tracked files through one git process into the show() cache."""
    want = [(p, _oids[p]) for p in paths if p not in _cache and p in _oids]
    if not want:
        return
    out = subprocess.run(["git", "-C", REPO, "cat-file", "--batch"], input=b"".join(o + b"\n" for _, o in want), capture_output=True, check=True).stdout
    pos = 0
    for p, _ in want:
        nl = out.index(b"\n", pos); size = int(out[pos:nl].split()[2])
        _cache[p] = out[nl + 1:nl + 1 + size].decode("utf-8", "replace"); pos = nl + 2 + size


def commit():
    return git("rev-parse", "--short", PIN).strip()


# ---------- 1. 화면: 라우트를 정의한 파일(어디에 있든)의 <Route path=... element={<X ...>, 라우트 객체 배열, 파일 기반 라우트 ----------
LAYOUT = json.loads(os.environ.get("WHERE_WERE_WE_LAYOUT", "{}"))
JS = (".tsx", ".jsx", ".ts", ".js", ".vue")
ROUTE_MARK = re.compile(r"<Route\b[^>]*\bpath=|\b(?:createBrowserRouter|createHashRouter|createMemoryRouter|useRoutes|createRouter)\(|\bnew\s+VueRouter\b")
MAX_FRONTEND_FILES = 4000  # files read to find route definitions; a larger frontend is read in path order up to this many

def inside(f, root):
    return not root or f.startswith(root.rstrip("/") + "/")

def _code(f, root=None):
    return f.endswith(JS) and source_signals.kind(f) == "code" and "/node_modules/" not in "/" + f and inside(f, root)

def _src_root(f):
    """The source root of a frontend file: up to its src folder, else its top folder."""
    parts = f.split("/")
    return "/".join(parts[:parts.index("src") + 1]) if "src" in parts[:-1] else (parts[0] if len(parts) > 1 else "")

def _framework_pages():
    """Next.js / Nuxt file routes: (route file, root) under app/ or pages/ next to a package.json that depends on next or nuxt."""
    out = []
    for f in sorted(ls()):
        parts = f.split("/")
        at = next((i for i, x in enumerate(parts[:-1]) if x in ("app", "pages")), None)
        if at is None or not _code(f, LAYOUT.get("frontend")) or "api" in parts[at + 1:-1]:
            continue
        pkg = "/".join(parts[:at - 1] if at and parts[at - 1] == "src" else parts[:at])
        if not re.search(r'"(next|nuxt)"\s*:', show((pkg + "/" if pkg else "") + "package.json") or ""):
            continue
        rest = "/".join(parts[at + 1:]).rsplit(".", 1)[0]
        if parts[at] == "app":
            if not re.search(r"(^|/)page$", rest):
                continue
            rest = rest[:-4]
        elif re.search(r"(^|/)_(app|document|error)$", rest):
            continue
        segs = [x for x in rest.split("/") if x and x != "index" and not re.fullmatch(r"\(.*\)|@.*", x)]
        segs = ["*" if x.startswith("[...") or x.startswith("[[...") else ":" + x.strip("[]") if x.startswith("[") else x for x in segs]
        out.append((f, "/" + "/".join(segs)))
    return out

_FRONT = sorted((f for f in ls() if _code(f, LAYOUT.get("frontend"))), key=lambda f: (f.count("/"), f))[:MAX_FRONTEND_FILES]
preload(_FRONT)
ROUTE_FILES = sorted(f for f in _FRONT if ROUTE_MARK.search(show(f) or ""))
PAGE_FILES = _framework_pages()
_roots = [_src_root(f) for f in ROUTE_FILES + [f for f, _ in PAGE_FILES]]
SRC = LAYOUT.get("frontend") or (max(sorted(set(_roots)), key=_roots.count) if _roots else ("src" if "src/App.tsx" in ls() else "frontend/src"))
_PY = sorted((f for f in ls() if f.endswith(".py") and source_signals.kind(f) == "code" and inside(f, LAYOUT.get("backend"))), key=lambda f: (f.count("/"), f))[:MAX_FRONTEND_FILES]
preload(_PY)
# The FastAPI application file closest to the repository root, wherever it lives.
BACKEND_MAIN = next((f for f in _PY if re.search(r"=\s*FastAPI\(", show(f) or "")), None) or ((LAYOUT.get("backend") or ("app" if "app/main.py" in ls() else "backend/app")) + "/main.py")
BACKEND = LAYOUT.get("backend") or os.path.dirname(BACKEND_MAIN)
BP = BACKEND.rstrip("/") + "/" if BACKEND else ""
for area, root in (("frontend", SRC), ("backend", BACKEND)):
    if area in LAYOUT and LAYOUT[area] and not any(f.startswith(root.rstrip("/")+"/") for f in ls()):
        raise ValueError(f"Configured {area} source root has no tracked files: {root}")

def resolve(frm, spec):
    """상대 import 를 저장소 경로로. 없으면 None."""
    if spec.startswith(("@/", "~/")):
        spec, frm = "./" + spec[2:], _src_root(frm) + "/x"  # the alias names the importing file's source root
    if not spec.startswith("."):
        return None
    base = os.path.normpath(os.path.join(os.path.dirname(frm), spec))
    for cand in (base, *(base + e for e in JS), *(base + "/index" + e for e in JS)):
        if cand in ls() and cand.endswith(JS):
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


LAZY_RE = re.compile(r"\bconst\s+(\w+)\s*=[^;\n]*?\bimport\(\s*['\"]([^'\"]+)['\"]")

def components(path):
    """{local component name: file} from static imports and `const X = lazy(() => import('./X'))`."""
    out = {}
    for names, tgt in imports(path):
        for n in re.findall(r"\w+(?:\s+as\s+\w+)?", names.strip("{} ")):
            out[n.split()[-1]] = tgt
    for m in LAZY_RE.finditer(show(path) or ""):
        tgt = resolve(path, m.group(2))
        if tgt:
            out[m.group(1)] = tgt
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


def _row(path, comps, comp_file, evidence, cond=None):
    inner = [c for c in comps if c in comp_file]
    page = inner[-1] if inner else None
    # ponytail: a nested relative path is read from the root, joining parent paths needs a JSX tree walk
    return {"path": path if path.startswith("/") or path == "*" else "/" + path, "component": page or (comps[0] if comps else None),
            "file": comp_file.get(page) if page else None, "evidence": evidence, "condition": cond, "redirect": page is None}


def screens():
    rows = []
    for app in ROUTE_FILES:
        src = show(app) or ""
        comp_file = components(app)
        starts = [m.start() for m in re.finditer(r"<Route\b", src)]
        for i, st in enumerate(starts):
            end = starts[i + 1] if i + 1 < len(starts) else len(src)
            block = src[st:end]
            pm = re.search(r"\bpath=(?:\"([^\"]+)\"|'([^']+)'|\{\s*['\"`]([^'\"`$]+)['\"`]\s*\})", block)
            em = re.search(r"\b(?:element|component|Component)=\{", block)
            if not pm or not em:
                continue
            element = balanced(block, em.end() - 1)
            line_start = src.rfind("\n", 0, st) + 1
            cond = re.search(r"import\.meta\.env\.(\w+)\s*===\s*'([^']*)'", src[line_start:st])
            rows.append(_row(next(g for g in pm.groups() if g), re.findall(r"<([A-Za-z_]\w*)" if em.group(0) == "element={" else r"([A-Za-z_]\w*)", element),
                             comp_file, f"{app}:{src[:st].count(chr(10)) + 1}", f"{cond.group(1)} === '{cond.group(2)}'" if cond else None))
        if "<Route" in src:
            continue
        # Route object arrays (createBrowserRouter, useRoutes, Vue Router): { path: '/x', element: <X/> | component: X | () => import('./X') }
        marks = [m for m in re.finditer(r"\bpath\s*:\s*(['\"`])([^'\"`$]*)\1", src)]
        for i, m in enumerate(marks):
            seg = src[m.end():marks[i + 1].start() if i + 1 < len(marks) else len(src)]
            cm = re.search(r"\b(?:element\s*:\s*<\s*(\w+)|[cC]omponent\s*:\s*(\w+)\s*[,}\n]|(?:[cC]omponent|lazy)\s*:\s*\(\)\s*=>\s*import\(\s*['\"]([^'\"]+)['\"])", seg)
            if not cm:
                continue
            table = dict(comp_file)
            if cm.group(3):
                table["<lazy>"] = resolve(app, cm.group(3))
            name = cm.group(1) or cm.group(2) or ("<lazy>" if table.get("<lazy>") else cm.group(3))
            rows.append(_row(m.group(2), [name], {k: v for k, v in table.items() if v}, f"{app}:{src[:m.start()].count(chr(10)) + 1}"))
    for f, path in PAGE_FILES:
        rows.append({"path": path, "component": os.path.basename(f).rsplit(".", 1)[0], "file": f, "evidence": f"{f}:1", "condition": None, "redirect": False})
    seen = set()
    return [r for r in rows if not ((r["path"], r["file"]) in seen or seen.add((r["path"], r["file"])))]


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
    return mapcore.normalize_http_path(p)


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
    depth, plain = 0, []
    for ch in inner:  # {식} 안의 > 와 < 가 글자로 읽히지 않게 식을 먼저 지운다
        depth += ch == "{"
        if not depth: plain.append(ch)
        depth -= ch == "}" and depth > 0
    parts = [" ".join(html.unescape(t).split()) for t in JSX_TEXT_RE.findall(">" + "".join(plain) + "<")]
    parts = [t for t in parts if re.search(r"\w", t)]  # 글자·숫자가 없는 조각(":", "·")은 버튼 글자가 아니다
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


@functools.lru_cache(maxsize=8)
def _definitions(src):
    """같은 파일의 함수 정의 끝 위치. 화살표 함수(const/let) 정의가 function 정의보다 먼저다. 파일마다 한 번만 훑는다."""
    found = {}
    for pattern in (r"(?:const|let)\s+(\w+)\s*=\s*(?:async\s*)?(?:\([^)]*\)|\w+)\s*=>\s*", r"(?:async\s+)?function\s+(\w+)\s*\([^)]*\)\s*"):
        for m in re.finditer(pattern, src):
            found.setdefault(m.group(1), m.end())
    return found


def handler_body(src, expr):
    """onClick 식에서 실제로 실행되는 코드 조각. 이름만 있으면 같은 파일의 정의를 찾는다. 정의가 없으면(부모가 준 함수) None."""
    expr = expr.strip()
    if re.fullmatch(r"\w+", expr):
        end = _definitions(src).get(expr)
        if end is None:
            return None
        rest = src[end:]
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


def in_comment(src, st):
    """태그가 // 줄 주석이나 /* */ 주석 안에 적힌 글자인지."""
    return "//" in src[src.rfind("\n", 0, st) + 1:st] or src.rfind("/*", 0, st) > src.rfind("*/", 0, st)


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
        if in_comment(src, st): continue
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
        quoted = lambda name: (lambda m: m and (m.group(1) if m.group(1) is not None else m.group(2)))(re.search(rf"\b{name}=(?:\"([^\"]*)\"|'([^']*)')", open_tag))
        label = jsx_text(inner) or lit(quoted("title")) or lit(quoted("aria-label")) or ""  # {식} 속성은 글자가 아니다
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
        if in_comment(src, st): continue
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
    main = show(BACKEND_MAIN) or ""
    imps = py_imports(main)  # from .routers import users  /  from .routers.users import router as users_router
    mounted = {}  # (module, router var) -> include prefix
    for m in re.finditer(r"include_router\(\s*(\w+)(?:\.(\w+))?(.*?)\)", main, re.S):
        pm = re.search(r"prefix\s*=\s*[\"']([^\"']*)[\"']", m.group(3))
        mod, orig = imps.get(m.group(1), ("", m.group(1)))
        key = (orig, m.group(2)) if m.group(2) else (mod.split(".")[-1], orig)
        mounted[key] = pm.group(1) if pm else ""
    rows = []
    files = [BACKEND_MAIN] + [x for x in _PY if x.startswith(BP) and x != BACKEND_MAIN and "APIRouter(" in (show(x) or "")]
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
    for f in sorted(ls()):
        if not (f in _PY and f.startswith(BP)) or "__tablename__" not in (show(f) or ""):
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
    cand = BP + mod.replace(".", "/") + ".py"
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
    # 테스트 파일을 git 프로세스 하나로 미리 읽는다(파일마다 git show 를 부르면 큰 저장소에서 수 초).
    preload([f for f in ls() if any(fnmatch.fnmatch(f if "/" in g else os.path.basename(f), g) for g in conf["files"])])
    return mapcore.backend_test_links(be,ls(),show,conf,py_imports,module_file,normalize)


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
        "inventory": mapcore.tree_inventory(_entries, PIN),
        "structure_index": structure_index.build(REPO, PIN),
        "coverage": {"frontend": bool(ROUTE_FILES or PAGE_FILES) and LAYOUT.get("frontend", True) is not None, "backend": BACKEND_MAIN in ls() and LAYOUT.get("backend", True) is not None},
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
