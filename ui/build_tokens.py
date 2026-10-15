#!/usr/bin/env python3
"""DESIGN.md 맨 위 표(YAML)를 CSS 변수로 옮긴다. 디자인 값의 정본은 DESIGN.md 하나다.
사용: python3 ui/build_tokens.py          → ui/tokens.generated.css 를 쓴다
      python3 ui/build_tokens.py --print  → 쓰지 않고 내용만 출력 (검사용)"""
import os, re, sys
here = os.path.dirname(os.path.abspath(__file__))
KEEP = ("colors", "typography", "rounded", "spacing", "app")   # components 는 설명용이라 옮기지 않는다
SHORT = {"fontFamily": "family", "fontSize": "size", "fontWeight": "weight", "lineHeight": "leading", "letterSpacing": "tracking"}


def build():
    lines = open(os.path.join(here, "..", "DESIGN.md"), encoding="utf-8").read().split("\n")
    end = lines.index("---", 1)
    out, path = [], []
    for raw in lines[1:end]:
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        m = re.match(r"^( *)([\w-]+):\s*(.*)$", raw)
        if not m:
            continue
        depth, key, val = len(m.group(1)) // 2, m.group(2), m.group(3).strip()
        path = path[:depth] + [key]
        if val and path[0] in KEEP:
            val = val.strip('"').strip("'")
            name = "-".join([path[0]] + [SHORT.get(p, p) for p in path[1:]])
            out.append(f"  --{name}:{val};")
    return "/* 자동 생성. 손으로 고치지 않는다. 정본은 DESIGN.md, 만드는 것은 ui/build_tokens.py */\n:root {\n" + "\n".join(out) + "\n}\n"


if __name__ == "__main__":
    css = build()
    if "--print" in sys.argv:
        sys.stdout.write(css)
    else:
        open(os.path.join(here, "tokens.generated.css"), "w", encoding="utf-8").write(css)
        print(f"tokens.generated.css: 변수 {css.count('--') - 0}개")
