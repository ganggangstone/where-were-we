#!/usr/bin/env python3
"""③ 누르면 생기는 일. 화면 하나가 부르는 서버 함수의 코드를 설치된 에이전트(claude -p)에 읽혀 단계를 받는다.

사용: steps.py <프로젝트 이름> <브랜치> <화면 주소> [최대 함수 수=12]
결과: ~/.where-were-we/<프로젝트>/flows.json
에이전트가 쓴 단계마다 줄 번호와 원문 토막을 요구하고, 그 줄(±2)에 그 토막이 실제로 있는지 대조한다. 없으면 그 단계는 싣지 않는다.
"""
import hashlib, json, os, re, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mapcore

PROJECT, BRANCH, SCREEN = sys.argv[1], sys.argv[2], sys.argv[3]
LIMIT = int(sys.argv[4]) if len(sys.argv) > 4 else 12
HOME = mapcore.project_home(PROJECT)
m = json.load(open(os.path.join(HOME, f"{BRANCH}.json")))
REPO, COMMIT = m["repo"], m["commit"]
FLOWS = os.path.join(HOME, "flows.json")
flows = json.load(open(FLOWS)) if os.path.exists(FLOWS) else {"routes": {}}

_src = {}
def source(path):
    if path not in _src:
        _src[path] = subprocess.run(["git", "-C", REPO, "show", f"{COMMIT}:{path}"], capture_output=True, text=True, errors="replace").stdout.splitlines()
    return _src[path]


def func_range(lines, name, near):
    """def <name> 이 시작하는 줄(1부터)과 끝 줄. near(장식자 줄) 뒤에서 찾는다."""
    start = None
    for i in range(max(0, near - 1), len(lines)):
        if re.match(rf"\s*(async\s+)?def\s+{re.escape(name)}\s*\(", lines[i]):
            start = i; break
    if start is None:
        return None
    indent = len(lines[start]) - len(lines[start].lstrip())
    end = len(lines)
    for j in range(start + 1, len(lines)):
        l = lines[j]
        if l.strip() and (len(l) - len(l.lstrip())) <= indent and not l.lstrip().startswith((")", "]")):
            end = j; break
    return start + 1, min(end, start + 160)


# 화면(과 모바일 짝)이 부르는 서버 함수. 화면의 1/3 넘게 들어 있는 부품이 부르는 것은 뺀다.
count = {}
for sc in m["screens"]:
    for v in {a.get("via") for a in sc["api_functions"]} - {None}:
        count[v] = count.get(v, 0) + 1
common = {v for v, c in count.items() if c > len(m["screens"]) / 3}
parts = [s for s in m["screens"] if s["path"] in (SCREEN, "/m" + SCREEN)]
fn_index = {(f["file"], f["name"]): f for f in m["api_functions"]}
route_index = {(r["file"], r["line"]): r for r in m["backend_routes"]}
targets = {}
for p in parts:
    for ref in p["api_functions"]:
        if ref.get("via") in common:
            continue
        f = fn_index.get((ref["file"], ref["name"]))
        for c in (f or {}).get("calls", []):
            for b in c["backend"]:
                r = route_index.get((b["file"], b["line"]))
                if r and r["function"]:
                    targets[r["file"] + "::" + r["function"]] = r

if SCREEN.startswith('@routes:'):
    keys=json.loads(SCREEN[len('@routes:'):])
    targets={r['file']+'::'+r['function']:r for r in m['backend_routes'] if r.get('function') and r['file']+'::'+r['function'] in keys}
    if len(targets)!=len(set(keys)):raise ValueError('Some requested routes are not in this repository snapshot')

todo = []
for key, r in sorted(targets.items()):
    lines = source(r["file"])
    rng = func_range(lines, r["function"], r["line"])
    if not rng:
        continue
    body = "\n".join(lines[rng[0] - 1:rng[1]])
    h = hashlib.sha1(body.encode()).hexdigest()[:12]
    if flows["routes"].get(key, {}).get("hash") == h:
        continue  # 코드가 그대로면 다시 만들지 않는다
    todo.append((key, r, rng, h))
todo = todo[:LIMIT]
if not todo:
    print(f"새로 만들 것 없음 (서버 함수 {len(targets)}개 모두 최신)"); sys.exit(0)

blocks = []
for key, r, rng, h in todo:
    lines = source(r["file"])
    numbered = "\n".join(f"{n}: {lines[n - 1]}" for n in range(rng[0], rng[1] + 1))
    blocks.append(f"### {key}\n{r['method']} {r['path']}\n{numbered}")

prompt = """아래는 웹 서비스 백엔드의 함수들이다. 각 줄 앞의 숫자는 그 파일의 줄 번호다.
함수마다, 코드를 못 읽는 사람이 "이 요청을 보내면 서버 안에서 무슨 일이 차례로 일어나는지" 알 수 있게 3~7단계로 적어라.

규칙:
- name: 이 함수가 하는 일을 쉬운 한국어로 (2~6어절, 예: "대본 저장하기").
- steps: 순서대로. 각 단계는 {"lane", "text", "line", "quote", "uncertain"}.
  - lane 은 "서버"(검사·계산·판단), "저장소"(DB 읽기·쓰기), "외부"(다른 회사 서비스·다른 서버 호출), "화면"(화면에 돌려주는 것) 중 하나.
  - text 는 쉬운 한국어 한 문장. 함수명·변수명·영어 약어를 쓰지 않는다.
  - line 은 그 단계의 근거가 되는 줄 번호, quote 는 그 줄에 적힌 코드를 글자 그대로 일부(10자 이상) 복사한 것. 지어내지 않는다.
  - 코드만 봐서는 실제로 그렇게 되는지 확신할 수 없는 단계(설정값·다른 파일에 달린 것)는 uncertain 을 true 로.
- 마지막 단계는 보통 lane "화면"(무엇을 돌려주는지)이다.
JSON만 출력한다. 형식: {"<### 뒤의 키 그대로>": {"name": "...", "steps": [...]}, ...}

""" + "\n\n".join(blocks)

out = subprocess.run(["claude", "-p", "--output-format", "text", "--model", "sonnet", prompt], capture_output=True, text=True)
mm = re.search(r"\{.*\}", out.stdout, re.S)
if not mm:
    sys.exit("에이전트 출력에 JSON이 없다:\n" + out.stdout[:400] + out.stderr[:400])
data = json.loads(mm.group(0))

norm = lambda t: re.sub(r"\s+", "", t or "")
kept = dropped = 0
for key, r, rng, h in todo:
    got = data.get(key)
    if not got:
        continue
    lines = source(r["file"])
    steps = []
    for st in got.get("steps", []):
        ln, q = st.get("line"), norm(st.get("quote"))
        ok = isinstance(ln, int) and rng[0] <= ln <= rng[1] and len(q) >= 6 and any(q in norm(lines[k - 1]) for k in range(max(1, ln - 2), min(len(lines), ln + 2) + 1))
        if not ok:
            dropped += 1; continue  # 근거 대조 실패: 싣지 않는다
        if st.get("lane") not in ("서버", "저장소", "외부", "화면"):
            st["lane"] = "서버"
        steps.append({"lane": st["lane"], "text": st.get("text", ""), "line": ln, "quote": st.get("quote", ""), "uncertain": bool(st.get("uncertain"))})
        kept += 1
    flows["routes"][key] = {"name": got.get("name", ""), "steps": steps, "hash": h, "commit": COMMIT, "file": r["file"], "function": r["function"], "source": "ai"}
json.dump(flows, open(FLOWS, "w"), ensure_ascii=False, indent=1)
left = len(targets) - sum(1 for k in targets if k in flows["routes"])
print(f"서버 함수 {len(todo)}개 읽음: 단계 {kept}개 실음, 근거 대조 실패로 뺀 단계 {dropped}개. 이 화면에서 아직 안 만든 함수 {left}개")
