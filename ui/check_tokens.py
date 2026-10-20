#!/usr/bin/env python3
"""디자인 값이 DESIGN.md 한 곳에만 있는지 검사한다.
- app.css, tokens.css, index.html 에 색·px 값이 직접 적혀 있으면 실패한다.
- tokens.generated.css 가 DESIGN.md 의 표와 다르면(고치고 build 를 안 돌렸으면) 실패한다.
- index.html·control.js·connection.js 의 스크립트가 화면 값을 글자 그대로 넣으면 실패한다:
  el.style.x = / el.style['x'] = / style.setProperty / Object.assign(el.style, {..}) / setAttribute('fill'·'stroke'·..)
  / SVG fill="" stroke-width="" 같은 속성, 따옴표 안의 색·px, 토큰 대체값 var(--x, 값), getPropertyValue(..) || 숫자.
  var(--..) 와 계산식(x + 'px')은 통과한다. 배치 낱말(none, block 등)도 통과한다.
- 한계: 한 줄씩 정규식으로 본다. 여러 줄에 걸친 대입, 변수에 담았다가 넣는 값(const c = 'red'; el.style.color = c),
  classList·innerHTML 로 만든 style 글자의 일부, 다른 파일(capture.cjs 등)은 보지 않는다. SVG 도형 값
  (viewBox, markerWidth, d)은 디자인 값이 아니어서 보지 않는다. 통과가 DESIGN.md 를 다 지켰다는 뜻은 아니다.
- 정의되지 않은 이름을 쓰면 실패한다.
사용: python3 ui/check_tokens.py [ui 폴더]"""
import os, re, sys
here = os.path.dirname(os.path.abspath(__file__))
ui = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else here
RAW = re.compile(r"#[0-9a-fA-F]{3,8}\b|(rgb|hsl)a?\(|\d*\.?\d+(px|r?em|vw|vh|pt)\b|font-weight\s*:\s*\d|opacity\s*:\s*\.?\d|scale\(\s*\.?\d")
# 스크립트: 따옴표 안의 색·크기 글자, cssText, 홑따옴표 style, 토큰을 읽고 숫자로 대신하기
JS_RAW = re.compile(r"['\"`]#[0-9a-fA-F]{3,8}['\"`]|(rgb|hsl)a?\(|['\"`]-?\d*\.?\d+(px|r?em|vw|vh|pt)\b|cssText|style='|getPropertyValue\([^)]*\)\)?\s*(\|\||\?\?)\s*\d")
# 토큰 뒤에 붙인 대체값은 그 값의 사본이다: var(--x, #06c)
FALLBACK = re.compile(r"var\(\s*--[\w-]+\s*,")
# 화면에 그리는 값을 넣는 자리. 오른쪽이 글자·숫자 그대로면 실패, var(...) 나 계산식(x + 'px')이면 통과
SVG_PROP = r"fill|stroke|stroke-width|stroke-dasharray|stop-color|opacity"
ASSIGN = [re.compile(p) for p in (
    r"\.style\.(\w+)\s*=(?!=)\s*(.+)",                                   # el.style.color = ...
    r"\.style\[\s*['\"]([\w-]+)['\"]\s*\]\s*=(?!=)\s*(.+)",              # el.style['color'] = ...
    r"\.style\.setProperty\(\s*['\"]([\w-]+)['\"]\s*,\s*(.+)",          # el.style.setProperty('color', ...)
    r"setAttribute\(\s*['\"](" + SVG_PROP + r"|style|color)['\"]\s*,\s*(.+)",
    r"['\"]?\b(" + SVG_PROP + r")['\"]?\s*:\s*(.+)",                     # { fill: ... } 를 setAttribute 로 넘기는 묶음
)]
STYLE_OBJ = re.compile(r"Object\.assign\(\s*[\w.$]+\.style\s*,\s*\{([^}]*)\}")
SVG_ATTR = re.compile(r"\b(" + SVG_PROP + r")\s*=\s*\"([^\"$]*)\"")       # <path stroke-width="2">
# 디자인 값이 아닌 배치 낱말은 그대로 적어도 된다
KEYWORDS = {"", "none", "block", "flex", "grid", "inline", "inline-block", "hidden", "visible", "auto", "absolute", "relative"}
def literal(rhs):
    """오른쪽이 디자인 값을 그대로 적은 것이면 그 글자를 돌려준다."""
    rhs = rhs.strip()
    if re.match(r"-?\.?\d", rhs):
        return re.match(r"-?[\d.]+", rhs).group(0)
    m = re.match(r"(['\"`])(.*?)\1", rhs)
    if m and not m.group(2).startswith("var(") and m.group(2).strip() not in KEYWORDS:
        return m.group(0)
    return None
bad = []
sys.path.insert(0, here)
import build_tokens
gen_path = os.path.join(ui, "tokens.generated.css")
gen = open(gen_path, encoding="utf-8").read() if os.path.exists(gen_path) else ""
if gen != build_tokens.build():
    bad.append("tokens.generated.css 가 DESIGN.md 와 다르다. python3 ui/build_tokens.py 를 돌린다")
read = lambda f: open(os.path.join(ui, f), encoding="utf-8").read()
css = read("app.css"); sem = read("tokens.css")
for fname, text in (("app.css", css), ("tokens.css", sem)):
    for n, line in enumerate(re.sub(r"/\*.*?\*/", lambda m: "\n" * m.group(0).count("\n"), text, flags=re.S).splitlines(), 1):
        for m in [*RAW.finditer(line), *FALLBACK.finditer(line)]:
            bad.append(f"{fname}:{n}: {m.group(0)}")
html = read("index.html")
if "<style" in html:
    bad.append("index.html: <style> 블록이 있다. 스타일은 app.css 에 둔다")
for n, line in enumerate(html.splitlines(), 1):
    for m in re.finditer(r'style="([^"]*)"', line):
        if not re.fullmatch(r"width:\$\{[^}]*\}%", m.group(1)):  # 자료에서 계산하는 막대 길이만 허용
            bad.append(f"index.html:{n}: style=\"{m.group(1)[:50]}\"")
for fname, text in (("index.html", html), ("control.js", read("control.js")), ("connection.js", read("connection.js"))):
    for n, line in enumerate(text.splitlines(), 1):
        found = [m.group(0) for m in JS_RAW.finditer(line)] + [m.group(0) for m in FALLBACK.finditer(line)]
        found += [f"{m.group(1)}={v}" for rx in ASSIGN for m in rx.finditer(line) if (v := literal(m.group(2)))]
        found += [f"{k.strip()}={v}" for m in STYLE_OBJ.finditer(line) for k, _, r in (p.partition(":") for p in m.group(1).split(",")) if (v := literal(r))]
        found += [f"{m.group(1)}=\"{m.group(2)}\"" for m in SVG_ATTR.finditer(line) if not re.match(r"var\(|none$|url\(", m.group(2))]
        bad += [f"{fname}:{n}: {x}" for x in found]
used = set(re.findall(r"var\((--[\w-]+)", css))
sem_defined = set(re.findall(r"(--[\w-]+)\s*:", sem)); gen_defined = set(re.findall(r"(--[\w-]+)\s*:", gen))
bad += [f"app.css: tokens.css 에 없는 이름 {t}" for t in sorted(used - sem_defined)]
bad += [f"tokens.css: DESIGN.md 에 없는 이름 {t}" for t in sorted(set(re.findall(r"var\((--[\w-]+)", sem)) - sem_defined - gen_defined)]
print("\n".join(bad) if bad else f"ok: DESIGN.md 값 {len(gen_defined)}개, 쓰임새 {len(sem_defined)}개, app.css 가 쓰는 것 {len(used)}개, 직접 적힌 값 없음")
sys.exit(1 if bad else 0)
