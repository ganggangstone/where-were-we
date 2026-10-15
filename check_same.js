// 화면(ui/index.html)과 mapcore.py 가 같은 지도에서 같은 답을 내는지 맞춰 본다. 규칙이 두 곳에 있어서 갈라지면 여기서 걸린다.
// 사용: node check_same.js <프로젝트> [브랜치=dev]
const fs = require('fs'), os = require('os'), { execFileSync } = require('child_process');
const [project, branch = 'dev'] = process.argv.slice(2);
const html = fs.readFileSync(__dirname + '/ui/index.html', 'utf8');
const js = html.slice(html.indexOf('<script>') + 8, html.lastIndexOf('</script>'));
const el = () => ({ innerHTML: '', style: {}, dataset: {}, classList: { toggle() {} }, querySelectorAll() { return []; } });
const els = {}; global.document = { getElementById: (id) => els[id] ??= el(), querySelectorAll() { return []; } };
global.window = { __TAURI__: { core: { invoke: async () => [] } } }; global.navigator = {};
const D = os.homedir() + '/.where-were-we/' + project + '/'; const load = (n) => { try { return JSON.parse(fs.readFileSync(D + n + '.json', 'utf8')); } catch (e) { return null; } };
const py = JSON.parse(execFileSync(__dirname + '/.venv/bin/python', ['-c', `
import json, sys; sys.path.insert(0, ${JSON.stringify(__dirname)}); import mapcore
m = mapcore.Map(${JSON.stringify(project)}, ${JSON.stringify(branch)})
print(json.dumps({"req": {x["path"]: sorted(r["key"] + "=" + r["name"] for r in m.requests(x["path"])) for x, _ in m.visible()},
                  "flow": sorted(e["from"] + ">" + e["to"] for e in m.edges() if not e["menu"]), "label": {x["path"]: m.label(x["path"]) for x, _ in m.visible()}}, ensure_ascii=False))`], { maxBuffer: 1 << 28 }).toString());
eval(js + `
S.maps = { [branch]: load(branch) }; S.branch = branch; S.groups = load('groups'); S.flows = load('flows'); S.system = load('system'); S.jobs = load('jobs');
const m = M(); let bad = 0; const say = (w) => { if (++bad <= 10) console.log('다름:', w); };
const jsReq = {}; for (const s of visibleScreens(m)) jsReq[s.path] = requests(m, s.path).map(r => r.key + '=' + reqLabel(r)).sort();
for (const p of new Set([...Object.keys(jsReq), ...Object.keys(py.req)])) if (JSON.stringify(jsReq[p] || null) !== JSON.stringify(py.req[p] || null)) say('요청 ' + p + ' 화면 ' + (jsReq[p] || []).length + ' / mapcore ' + (py.req[p] || []).length);
const jsFlow = edges(m).filter(e => !e.common).map(e => e.from + '>' + e.to).sort(); if (JSON.stringify(jsFlow) !== JSON.stringify(py.flow)) say('흐름 길 화면 ' + jsFlow.length + ' / mapcore ' + py.flow.length);
for (const s of visibleScreens(m)) if (label(m, s.path) !== py.label[s.path]) say('이름 ' + s.path + ': ' + label(m, s.path) + ' / ' + py.label[s.path]);
console.log(bad ? bad + '곳 다름' : 'same: 화면 ' + Object.keys(jsReq).length + ', 요청 ' + Object.values(jsReq).flat().length + ', 흐름 길 ' + jsFlow.length);
process.exitCode = bad ? 1 : 0;
`);
