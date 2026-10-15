#!/usr/bin/env python3
"""묶음 제안. 화면 목록(주소·제목·버튼 글자)을 설치된 에이전트(claude -p)에 넘겨 기능 묶음 이름을 받는다.

사용: group.py <프로젝트 이름> [브랜치=dev]
결과: ~/.where-were-we/<프로젝트>/groups.json  (source: "ai" — 사람이 확정하기 전까지 AI가 붙인 이름이다)
코드는 넘기지 않는다. 넘기는 것은 화면 주소, <h1> 제목, 버튼 글자뿐이다.
"""
import json, os, re, subprocess, sys

PROJECT = sys.argv[1]
BRANCH = sys.argv[2] if len(sys.argv) > 2 else "dev"
HOME = os.path.expanduser("~/.where-were-we/" + PROJECT)
m = json.load(open(os.path.join(HOME, f"{BRANCH}.json")))

# 보여 주는 단위와 같게: 리다이렉트 제외, 모바일 판은 데스크톱 짝에 접음
desk = [s for s in m["screens"] if not s["redirect"] and not s["path"].startswith("/m/") and s["path"] != "/m"]
paths = {s["path"] for s in desk}
for s in m["screens"]:
    if s["redirect"] or not s["path"].startswith("/m/"):
        continue
    if (s["path"][2:] or "/") not in paths:
        desk.append(s)

rows = []
for s in desk:
    labels = []
    for a in s["actions"]:
        if a["label"] and not a.get("via") and a["label"] not in labels:
            labels.append(a["label"])
    rows.append({"path": s["path"], "title": s.get("heading"), "buttons": labels[:10]})

prompt = f"""아래는 어떤 웹 서비스의 화면 목록이다. 화면마다 주소, 제목, 그 화면에 있는 버튼 글자를 적었다.
이 화면들을 사용자가 하는 일 기준으로 5~9개 묶음으로 나누고, 묶음마다 쉬운 한국어 이름(2~6글자)과 한 줄 설명을 붙여라.
이름은 버튼·제목에 이미 쓰인 서비스의 말을 우선 쓴다. 모든 화면을 정확히 한 묶음에 넣어라. 화면 주소는 그대로 복사한다.
또 화면마다 쉬운 한국어 이름(2~10글자)을 붙여라. 제목(title)이 있으면 그 말을 살리고, 없으면 버튼 글자를 보고 그 화면에서 하는 일을 이름으로 쓴다. 주소 조각을 그대로 쓰지 않는다.
JSON만 출력한다. 형식: {{"groups":[{{"name":"...","description":"...","screens":["/path", ...]}}], "names":{{"/path":"화면 이름", ...}}}}

{json.dumps(rows, ensure_ascii=False, indent=0)}"""

out = subprocess.run(["claude", "-p", "--output-format", "text", "--model", "sonnet", prompt], capture_output=True, text=True)
text = out.stdout.strip()
mm = re.search(r"\{.*\}", text, re.S)
if not mm:
    sys.exit("에이전트 출력에 JSON이 없다:\n" + text[:500] + out.stderr[:500])
data = json.loads(mm.group(0))

# 검사: 모든 화면이 정확히 한 묶음에 있는가. 빠진 것은 "미분류"에, 지어낸 주소는 버린다.
known = {r["path"] for r in rows}
seen = set()
for g in data["groups"]:
    g["screens"] = [p for p in g["screens"] if p in known and p not in seen]
    seen.update(g["screens"])
missing = sorted(known - seen)
if missing:
    data["groups"].append({"name": "미분류", "description": "AI가 어느 묶음에도 넣지 않은 화면", "screens": missing})
names = {p: n for p, n in (data.get("names") or {}).items() if p in known and isinstance(n, str) and n.strip()}

# 서버 기능 이름. 함수 이름·주소·만지는 테이블만 넘긴다(코드는 안 넘긴다). 150개씩 나눠 부른다.
routes = [r for r in m["backend_routes"] if r.get("mounted") and r.get("function")]
request_names = {}
for i in range(0, len(routes), 150):
    chunk = routes[i:i + 150]
    lines = "\n".join(f"{k}\t{r['method']} {r['path']}\t{r['function']}\t{','.join(r.get('tables') or [])}\t{','.join(r.get('externals') or [])}" for k, r in enumerate(chunk))
    p2 = f"""아래는 웹 서비스 서버 기능 목록이다. 한 줄에 번호, 요청 주소, 함수 이름, 만지는 저장소 테이블, 외부 서비스가 탭으로 나뉘어 있다.
줄마다 코드를 모르는 사람이 읽을 쉬운 한국어 이름(2~6어절, "~하기"·"~보기" 꼴, 영어·함수명 금지)을 붙여라. 확실하지 않으면 주소와 함수 이름이 말하는 만큼만 쓴다.
JSON만 출력한다. 형식: {{"0":"이름", "1":"이름", ...}}

{lines}"""
    o = subprocess.run(["claude", "-p", "--output-format", "text", "--model", "sonnet", p2], capture_output=True, text=True)
    mm2 = re.search(r"\{.*\}", o.stdout, re.S)
    if not mm2:
        print(f"서버 기능 이름 {i}~: 에이전트 출력에 JSON이 없어 건너뜀", file=sys.stderr); continue
    for k, n in json.loads(mm2.group(0)).items():
        if k.isdigit() and int(k) < len(chunk) and isinstance(n, str) and n.strip():
            r = chunk[int(k)]; request_names[r["file"] + "::" + r["function"]] = n.strip()
data = {"source": "ai", "branch": BRANCH, "commit": m["commit"], "groups": [g for g in data["groups"] if g["screens"]], "names": names, "request_names": request_names}
json.dump(data, open(os.path.join(HOME, "groups.json"), "w"), ensure_ascii=False, indent=1)
print(f"서버 기능 이름 {len(request_names)}/{len(routes)}개")
for g in data["groups"]:
    print(f"{g['name']} ({len(g['screens'])}): {g['description']}")
    for p in g["screens"]:
        print(f"    {names.get(p, '(이름 없음)')}  ←  {p}")
