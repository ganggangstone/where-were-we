#!/usr/bin/env python3
"""디자인 값이 DESIGN.md 한 곳에만 있는지 검사한다.
- app.css, tokens.css, index.html 에 색·px 값이 직접 적혀 있으면 실패한다.
- tokens.generated.css 가 DESIGN.md 의 표와 다르면(고치고 build 를 안 돌렸으면) 실패한다.
- 정의되지 않은 이름을 쓰면 실패한다.
사용: python3 ui/check_tokens.py"""
import os, re, sys
here = os.path.dirname(os.path.abspath(__file__))
RAW = re.compile(r"#[0-9a-fA-F]{3,8}\b|rgba?\(|\d*\.?\d+(px|em|vw)\b")
bad = []
sys.path.insert(0, here)
import build_tokens
gen_path = os.path.join(here, "tokens.generated.css")
gen = open(gen_path, encoding="utf-8").read() if os.path.exists(gen_path) else ""
if gen != build_tokens.build():
    bad.append("tokens.generated.css 가 DESIGN.md 와 다르다. python3 ui/build_tokens.py 를 돌린다")
read = lambda f: open(os.path.join(here, f), encoding="utf-8").read()
css = read("app.css"); sem = read("tokens.css")
for fname, text in (("app.css", css), ("tokens.css", sem)):
    for n, line in enumerate(re.sub(r"/\*.*?\*/", lambda m: "\n" * m.group(0).count("\n"), text, flags=re.S).splitlines(), 1):
        for m in RAW.finditer(line):
            bad.append(f"{fname}:{n}: {m.group(0)}")
html = open(os.path.join(here, "index.html"), encoding="utf-8").read()
if "<style" in html:
    bad.append("index.html: <style> 블록이 있다. 스타일은 app.css 에 둔다")
for n, line in enumerate(html.splitlines(), 1):
    for m in re.finditer(r'style="([^"]*)"', line):
        if not re.fullmatch(r"width:\$\{[^}]*\}%", m.group(1)):  # 자료에서 계산하는 막대 길이만 허용
            bad.append(f"index.html:{n}: style=\"{m.group(1)[:50]}\"")
used = set(re.findall(r"var\((--[\w-]+)", css))
sem_defined = set(re.findall(r"(--[\w-]+)\s*:", sem)); gen_defined = set(re.findall(r"(--[\w-]+)\s*:", gen))
bad += [f"app.css: tokens.css 에 없는 이름 {t}" for t in sorted(used - sem_defined)]
bad += [f"tokens.css: DESIGN.md 에 없는 이름 {t}" for t in sorted(set(re.findall(r"var\((--[\w-]+)", sem)) - sem_defined - gen_defined)]
print("\n".join(bad) if bad else f"ok: DESIGN.md 값 {len(gen_defined)}개, 쓰임새 {len(sem_defined)}개, app.css 가 쓰는 것 {len(used)}개, 직접 적힌 값 없음")
sys.exit(1 if bad else 0)
