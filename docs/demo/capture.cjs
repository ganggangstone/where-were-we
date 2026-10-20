// Capture the real UI with fictional in-memory responses; never run the Rust/Python backend.
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const http = require('node:http');
const { execFileSync } = require('node:child_process');
const assert = require('node:assert/strict');
const { chromium } = require('playwright');
const language = process.argv.includes('--en') ? 'en' : 'ko';
let fixture = require('./fixture.cjs').create(language);
const title = language === 'en' ? 'Render details' : '렌더 상세';
const root = path.resolve(__dirname, '../..');
// Screenshots and project checks use one fictional project with four connected codes:
// web and admin screens call the API server; the render worker shares data with the API.
const projectCheck = process.argv.includes('--check-projects');
if (projectCheck || !process.argv.some(a => a.startsWith('--check-'))) {
  const code = `import copy,json,sys,tempfile
sys.path.insert(0,sys.argv[1])
import mapcore,project
data=json.load(sys.stdin);ko=sys.argv[2]=='ko';maps=data['maps'];name=data['project']
names={'web':'웹' if ko else 'Web','api':'서버' if ko else 'Server','admin':'관리자' if ko else 'Admin','worker':'작업기' if ko else 'Worker'}
def part(rid,m):
 m=copy.deepcopy(m);m['repo']='/demo/'+rid
 if rid in ('web','admin'):
  m['screens']=[s for s in m['screens'] if s['path'].startswith('/admin')==(rid=='admin')]
  used={f['name'] for s in m['screens'] for f in s['api_functions']}
  m['api_functions']=[f for f in m['api_functions'] if f['name'] in used]
  for f in m['api_functions']:
   for c in f['calls']:c['backend']=[]
  m['backend_routes']=[];m['backend_routes_without_screen']=[];m['models']={}
  if rid=='admin':m['unresolved_calls']=[]
 else:
  m['screens']=[];m['api_functions']=[];m['unresolved_calls']=[]
  if rid=='worker':m['backend_routes']=[];m['backend_routes_without_screen']=[];m['models']={'renders':'renders','credits':'credits'}
 return m
system=maps['system'];pick=lambda ids:[n for n in system['nodes'] if n['id'] in ids]
systems={'web':{**system,'nodes':pick({'web'}),'links':[],'externals':[]},
 'api':{**system,'nodes':pick({'backend','queue','db'}),'links':[l for l in system['links'] if l['from']=='backend']},
 'worker':{**system,'nodes':[{**n,'uses':[]} for n in pick({'worker'})],'links':[],'externals':[]},'admin':None}
groups=maps['groups'];admin=lambda g:all(p.startswith('/admin') for p in g['screens'])
admin_groups={g['name'] for g in groups['groups'] if admin(g)}
def web_only(value):
 # PRs and work recorded by the web code point only at web screens and groups.
 if isinstance(value,list):return [web_only(v) for v in value]
 if not isinstance(value,dict):return value
 return {k:[p for p in v if not str(p).startswith('/admin') and p not in admin_groups] if k in ('screens','groups') and isinstance(v,list) else web_only(v) for k,v in value.items()}
with tempfile.TemporaryDirectory() as temp:
 mapcore.ROOT=temp
 project.configure(name,{'repositories':[{'id':'web','name':names['web'],'path':'/demo/web','api_targets':['api']},{'id':'api','name':names['api'],'path':'/demo/api'},
  {'id':'admin','name':names['admin'],'path':'/demo/admin','api_targets':['api']},{'id':'worker','name':names['worker'],'path':'/demo/worker'}],
  'shared_data':[{'id':t.replace('_','-'),'members':[{'repository':'api','table':t},{'repository':'worker','table':t}]} for t in ('renders','credits')]})
 for rid in ['web','api','admin','worker']:
  raw={role:part(rid,maps[role]) for role in ('dev','main','dev.prev','main.prev')}
  raw['system']=systems[rid];raw['jobs']=maps['jobs'] if rid=='worker' else None
  raw['flows']=maps['flows'] if rid=='api' else {'routes':{}}
  raw['groups']={'names':{},'request_names':groups['request_names'] if rid=='api' else {},'groups':[g for g in groups['groups'] if rid in ('web','admin') and admin(g)==(rid=='admin')]}
  raw['status']=web_only(maps['status']) if rid=='web' else None;raw['changes']=web_only(maps['changes']) if rid=='web' else None
  project.publish(name,rid,raw,{'fingerprint':project.fingerprint(next(r for r in project.config(name)['repositories'] if r['id']==rid))})
 print(json.dumps({rid:project.read_bundle(name,rid) for rid in ['','web','api','admin','worker']}))`;
  const home = fs.mkdtempSync(path.join(os.tmpdir(), 'where-were-we-capture-home-'));
  fixture.bundles = JSON.parse(execFileSync(process.env.CAPTURE_PYTHON || 'python3', ['-c', code, root, language],
    { input: JSON.stringify(fixture), encoding: 'utf8', env: { ...process.env, HOME: home } }));
  fs.rmSync(home, { recursive: true, force: true });
}
const output = path.join(root, 'docs/images', language);
const frames = fs.mkdtempSync(path.join(os.tmpdir(), 'where-were-we-frames-'));
const mime = { '.html': 'text/html', '.css': 'text/css', '.js': 'text/javascript' };
// Only serve the UI directory. No real project data or home directory is accessible.
const server = http.createServer((req, res) => {
  const rel = decodeURIComponent(new URL(req.url, 'http://localhost').pathname);
  const file = path.resolve(root, 'ui', '.' + (rel === '/' ? '/index.html' : rel));
  if (!file.startsWith(path.join(root, 'ui') + path.sep) || !fs.existsSync(file) || !fs.statSync(file).isFile()) {
    res.writeHead(404); return res.end();
  }
  res.setHeader('Content-Type', mime[path.extname(file)] || 'application/octet-stream');
  res.end(fs.readFileSync(file));
});
let browser;
(async () => {
  fs.mkdirSync(output, { recursive: true });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const base = `http://127.0.0.1:${server.address().port}`;
  browser = await chromium.launch({ headless: true,
    ...(process.env.CAPTURE_BROWSER ? { executablePath: process.env.CAPTURE_BROWSER } : {}) });
  const page = await browser.newPage({ viewport: { width: 1760, height: 900 }, deviceScaleFactor: 1,
    locale: language === 'en' ? 'en-US' : 'ko-KR', timezoneId: 'Asia/Seoul', reducedMotion: 'reduce' });
  const errors = [], blocked = [];
  page.on('pageerror', e => errors.push(e.stack || e.message));
  await page.route('**/*', route => {
    if (route.request().url().startsWith(base + '/')) return route.continue();
    blocked.push(route.request().url()); return route.abort();
  });
  await page.addInitScript(data => {
    const NativeDate = Date;
    window.Date = class extends NativeDate {
      constructor(...args) { super(...(args.length ? args : [data.now])); }
      static now() { return data.now; }
    };
    window.__TAURI__ = { core: { invoke: async (command, args) => {
      if (command === 'app_version') return '0.1.0';
      if (command === 'app_update_status') return window.__updateState || null;
      if (command === 'start_app_update') {
        window.__updateStarts=(window.__updateStarts || []).concat([args]);
        if (window.__updateFailure) throw Error(window.__updateFailure);
        window.__updateState={stage:'checking',version:args.version,error:null};return null;
      }
      if (command === 'check_release') {
        window.__releaseChecks = (window.__releaseChecks || 0) + 1;
        if (window.__releaseFailure) throw Error('Offline fixture');
        return window.__releaseReply || { current: '0.1.0', latest: null };
      }
      if (command === 'read_project') {
        window.__readCalls=(window.__readCalls || []).concat([args]);
        if (window.__holdRead && args.repository===window.__holdRead) return new Promise(resolve=>{window.__finishRead=()=>resolve(JSON.stringify(data.bundles[args.repository]));});
        return JSON.stringify(data.bundles ? data.bundles[args.repository || ''] : {...data.maps, project:{name:data.project,repositories:[]}});
      }
      if (command === 'save_project') {window.__savedConfiguration=JSON.parse(args.configuration);return args.configuration;} // configure prints the saved JSON
      if (command === 'list_projects') return window.__emptyProjects ? [] : [data.project];
      if (command === 'read_map') {
        if (!(args.branch in data.maps)) throw Error('No demo fixture: ' + args.branch);
        return JSON.stringify(data.maps[args.branch]);
      }
      if (command === 'refresh') {
        if (window.__holdRefresh) return new Promise(resolve=>{window.__finishRefresh=resolve;});
        return 'Demo only: no repository was accessed.';
      }
      if (command === 'analysis_request') {window.__actionArgs=args;if(window.__holdAnalysis)return new Promise(resolve=>{window.__finishAnalysis=()=>resolve(JSON.stringify({handoff:'Old web analysis request'}));});return JSON.stringify({handoff:'Use MCP analyze, analysis_source and record_analysis with your connected agent.'});}
      if (command === 'make_steps' || command === 'suggest_groups' || command === 'make_jobs') {window.__actionArgs=args;return JSON.stringify({handoff:'Use request_ai_task and record_ai_task for '+command});}
      if (command === 'setup_prompt') return data.setup;
      if (command === 'tests_prompt') return args.lang === 'en' ? 'Fictional example: find and link revision API tests.' : '가상 예시: 수정 요청 API의 테스트를 찾아 연결해 주세요.';
      if (command === 'make_system') {
        window.__actionArgs=args;if(window.__autoSystem)return JSON.stringify({handoff:'Use request_ai_task and record_ai_task for system'});
        window.__pendingCalls = (window.__pendingCalls || 0) + 1;
        return new Promise(resolve => { window.__finishSystem = resolve; });
      }
      throw Error('Not available in the capture: ' + command);
    } } };
    document.addEventListener('DOMContentLoaded', () => {
      const style = document.createElement('style');
      style.textContent = '#demo-label{height:38px;flex:none;display:flex;align-items:center;justify-content:space-between;padding:0 var(--space-5);background:var(--color-accent-tint);border-bottom:var(--border-hairline);color:var(--color-text);font:var(--font-secondary)} #demo-cursor{position:fixed;width:18px;height:18px;border:var(--outline-selected);border-radius:var(--radius-pill);background:var(--color-accent-tint);pointer-events:none;z-index:1000;left:-100px;top:-100px}';
      document.head.appendChild(style);
      const badge = document.createElement('div'); badge.id = 'demo-label';
      const name = document.createElement('b'); name.textContent = 'where-were-we / Lumen Studio';
      const note = document.createElement('span'); note.textContent = data.project.includes('fictional') ? 'Fictional data · real UI · simulated collection and AI responses' : '가상 데이터 · 실제 UI · 수집·AI 응답은 촬영용 예시';
      badge.append(name, note); document.body.prepend(badge);
      const cursor = document.createElement('div'); cursor.id = 'demo-cursor'; document.body.append(cursor);
      document.addEventListener('mousemove', e => { cursor.style.left = (e.clientX - 9) + 'px'; cursor.style.top = (e.clientY - 9) + 'px'; });
    });
  }, fixture);
  const timeline = [];
  let recording = !process.argv.some(a => a.startsWith('--check-'));
  const settle = () => page.evaluate(() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r))));
  async function still(name) {
    await page.evaluate(() => { document.getElementById('demo-cursor').style.opacity = '0'; });
    await settle();
    await page.screenshot({ path: path.join(output, name + '.png') });
    await page.evaluate(() => { document.getElementById('demo-cursor').style.opacity = '1'; });
  }
  async function hold(seconds) {
    if (!recording) return;
    await settle();
    const file = path.join(frames, String(timeline.length).padStart(3, '0') + '.png');
    await page.screenshot({ path: file }); timeline.push({ file, seconds });
  }
  async function click(selector) {
    const element = page.locator(selector).first();
    await element.scrollIntoViewIfNeeded();
    const b = await element.boundingBox();
    await page.mouse.move(b.x + b.width / 2, b.y + b.height / 2, { steps: 12 });
    await hold(0.25); await element.click(); await settle();
  }
  // Rare tools live in the menu and screen views live under "What it does"; open them the way a person would.
  async function menu(selector) {
    if (!(await page.locator('#menu').evaluate(el => el.open))) await click('#menu > summary');
    await click(selector);
  }
  async function view(v) {
    if (['feat', 'map', 'focus'].includes(v) && await page.locator('#subview').isHidden()) await click('#view [data-v="work"]');
    await click(`${['feat', 'map', 'focus'].includes(v) ? '#subview' : '#view'} [data-v="${v}"]`);
  }
  const setLanguage = async lang => { await menu(`#language [data-lang="${lang}"]`); await page.keyboard.press('Escape'); await page.evaluate(() => document.activeElement?.blur()); };
  await page.goto(base);
  await page.waitForFunction(() => document.querySelector('#status').textContent === '' && document.querySelector('#map h2'));
  if (projectCheck) {
    const web = '/@web/renders/:id', cancel = 'api/backend/app/routers/renders.py::cancel_render';
    assert.equal(await page.locator('#repository option').count(),5);
    await view('map');
    assert.equal(await page.locator(`[data-scr="${web}"]`).count(),1);
    assert.equal(await page.locator('[data-scr="/@admin/admin/credits"]').count(),1);
    await page.locator(`[data-scr="${web}"]`).click();
    assert.match(await page.locator('#insp').innerText(), /\[웹\]/);
    await page.evaluate(k=>{delete S.branchDetails.dev.flows.routes[k];render();},cancel); // Leave one request without steps.
    await page.locator(`[data-req="${cancel}"]`).click();
    assert.match(await page.locator('#insp').innerText(), /사용자가 지정한 코드 사이 연결/);
    await page.locator('#mk').click();
    await page.waitForFunction(()=>window.__actionArgs?.repository==='api');
    assert.match(await page.evaluate(()=>window.__actionArgs.screen),/^@routes:/);
    await page.waitForFunction(()=>document.querySelector('#insp').textContent.includes('record_ai_task'));
    assert.equal(await page.evaluate(()=>window.__actionArgs.lang),'ko');
    await page.locator('#repository').selectOption('worker');
    await page.waitForFunction(()=>S.repository==='worker');
    await view('sys');
    await page.locator('.card[data-node="worker::worker"]').click();
    // The app has no jobs re-analysis button; agents prepare it through app control.
    await page.evaluate(()=>applyAppCommand({action:'prepare_analysis',arguments:{task:'jobs',target:'worker::worker'}}));
    await page.waitForFunction(()=>document.querySelector('#insp').textContent.includes('record_ai_task'));
    assert.equal(await page.evaluate(()=>window.__actionArgs.repository),'worker');
    assert.equal(await page.evaluate(()=>window.__actionArgs.node),'worker');
    assert.equal(await page.evaluate(()=>window.__actionArgs.branch),'dev');
    await page.evaluate(()=>{window.__autoSystem=true;});
    await page.locator('#remakeSys').click();
    await page.waitForFunction(()=>document.querySelector('#insp').textContent.includes('for system'));
    assert.equal(await page.evaluate(()=>window.__actionArgs.repository),'worker');
    await page.locator('#repository').selectOption('web');
    await page.waitForFunction(()=>document.querySelector('#repository').value==='web' && S.repository==='web');
    await view('map');
    assert.equal(await page.locator('[data-scr="/@admin/admin/credits"]').count(),0);
    await page.locator('#regroup').click();
    await page.waitForFunction(()=>document.querySelector('#insp').textContent.includes('for suggest_groups'));
    assert.equal(await page.evaluate(()=>window.__actionArgs.repository),'web');
    await page.evaluate(()=>{S.branchDetails.main.groups.names['/@web/renders/:id']='Main label';S.branchDetails.dev.groups.names['/@web/renders/:id']='Dev label';});
    await page.locator('#branch [data-b="main"]').click();
    assert.equal(await page.evaluate(()=>aiName('/@web/renders/:id')),'Main label');
    await page.locator('#branch [data-b="dev"]').click();
    assert.equal(await page.evaluate(()=>aiName('/@web/renders/:id')),'Dev label');
    // AI analysis opens one panel; with one code in scope the request goes to that code.
    await page.locator('#analyzeMap').click();
    await page.locator('[data-analysis-task="analysis_request"]').click();
    await page.waitForFunction(()=>window.__actionArgs?.repository==='web' && window.__actionArgs?.lang==='ko');
    assert.match(await page.locator('#insp').textContent(),/record_analysis/); // The request text sits in the folded "View request".
    await page.evaluate(()=>{window.__holdAnalysis=true;});
    await page.locator('#analyzeMap').click();
    await page.locator('[data-analysis-task="analysis_request"]').click();
    await page.waitForFunction(()=>!!window.__finishAnalysis);
    await page.locator('#repository').selectOption('admin');
    await page.waitForFunction(()=>S.repository==='admin');
    await page.evaluate(()=>{window.__finishAnalysis();window.__holdAnalysis=false;});
    await page.waitForFunction(()=>!pendingActions.has('analysis_request'));
    assert.equal(await page.evaluate(()=>S.agentPrompt),null);
    assert.doesNotMatch(await page.locator('#insp').innerText(),/Old web analysis request/);
    assert.equal(await page.locator('#status').innerText(),'','Progress for the abandoned scope is cleared');
    await page.locator('#repository').selectOption('web');
    await page.waitForFunction(()=>S.repository==='web');
    await setLanguage('en');
    assert.equal(await page.locator('#analyzeMap').innerText(),'AI analysis · waiting for result check','The prepared web request stays reachable');
    assert.equal(await page.locator('#manageRepositories').innerText(),'Manage code');
    await page.evaluate(()=>{S.projectInfo.repositories[3].layout={frontend:null,backend:null};});
    await page.locator('#manageRepositories').click();
    assert.equal(await page.locator('[data-repository-row]').count(),4);
    assert.equal(await page.locator('[data-repository-row="0"] [data-field="id"]').getAttribute('type'),'hidden','Code IDs are kept, not edited');
    assert.equal(await page.locator('#addSharedData').count(),1);
    await page.locator('#shared-data-options > summary').click();
    const group = String(await page.locator('[data-shared-group]').count());
    await page.locator('#addSharedData').click();
    await page.locator(`[data-add-member="${group}"]`).click();
    const members = page.locator(`[data-shared-group="${group}"]`);
    await members.locator('[data-member-repo]').nth(0).selectOption('api');
    await members.locator('[data-member-table]').nth(0).fill('assets');
    await members.locator('[data-member-repo]').nth(1).selectOption('worker');
    await members.locator('[data-member-table]').nth(1).fill('assets');
    await page.locator('#addRepository').click();
    assert.equal(await members.locator('[data-member-table]').nth(1).inputValue(),'assets','Adding code keeps typed shared data');
    await page.locator('[data-repository-row="4"] [data-field="path"]').fill('/demo/extra');
    await page.locator(`[data-add-member="${group}"]`).click();
    assert.equal(await members.locator('[data-shared-member="2"] [data-member-repo] option').count()>4,true,'New code can be chosen');
    await page.locator(`[data-remove-member="${group}:2"]`).click();
    assert.equal(await members.locator('[data-member-table]').nth(1).inputValue(),'assets');
    await page.locator('[data-remove="4"]').click();
    await page.locator('#saveProject').click();
    await page.waitForFunction(()=>window.__savedConfiguration);
    assert.deepEqual(await page.evaluate(()=>window.__savedConfiguration.shared_data.at(-1).members),
      [{repository:'api',table:'assets'},{repository:'worker',table:'assets'}]);
    assert.deepEqual(await page.evaluate(()=>window.__savedConfiguration.repositories[3].layout),{frontend:null,backend:null});
    await page.evaluate(()=>{window.__savedConfiguration=null;});
    // Hold A's refresh and B's read. Completing A must not cancel B's selection.
    await page.evaluate(()=>{window.__holdRefresh=true;window.__holdRead='admin';});
    await page.locator('#refresh').click();
    await page.waitForFunction(()=>window.__finishRefresh);
    await page.locator('#repository').selectOption('admin');
    await page.waitForFunction(()=>window.__finishRead);
    await page.evaluate(()=>window.__finishRefresh('Done'));
    await page.evaluate(()=>window.__finishRead());
    await page.waitForFunction(()=>document.querySelector('#repository').value==='admin');
    assert.equal(await page.locator('[data-scr="/@web/renders/:id"]').count(),0);
    await page.evaluate(()=>{window.__holdRefresh=false;window.__holdRead='';});
    await page.locator('#newProject').click();
    await page.locator('#projectName').fill('new-studio');
    const row=page.locator('[data-repository-row="0"]');
    await row.locator('[data-field="path"]').fill('/demo/new');
    await page.locator('#saveProject').click();
    await page.waitForFunction(()=>window.__savedConfiguration);
    assert.deepEqual(await page.evaluate(()=>window.__savedConfiguration.shared_data),[]);
    assert.equal(await page.evaluate(()=>window.__savedConfiguration.repositories[0].path),'/demo/new');
    assert.deepEqual(errors,[]);assert.deepEqual(blocked,[]);
    console.log('Project checks passed: four-code composition, filtering, configured calls, target AI scope, settings, new project, and refresh/selection race.');
    return;
  }
  if (process.argv.includes('--check-updates')) {
    assert.equal(await page.locator('#menu #updates').count(), 1, 'Version and update control lives in the menu');
    await page.waitForFunction(() => window.__releaseChecks === 1);
    await menu('#updates');
    await page.waitForSelector('#release-dialog[open]');
    assert.match(await page.locator('#release-dialog').innerText(), /0\.1\.0/);
    await page.evaluate(() => { window.__releaseReply = { current: '0.1.0', latest: {
      version: '0.2.0', newer: true,
      url: 'https://github.com/ganggangstone/where-were-we/releases/tag/v0.2.0',
      notes: '### 한국어\n- 가상 변경\n\n### English\n- Fictional change\n<img src=x onerror="throw Error(1)">'
    } }; });
    await page.locator('#checkRelease').click();
    await page.waitForFunction(() => document.querySelector('#release-banner').textContent.includes('0.2.0'));
    assert.match(await page.locator('#release-dialog').innerText(), /Fictional change/);
    assert.equal(await page.locator('#release-dialog img').count(), 0, 'Notes are rendered as text');
    assert.equal(await page.locator('#upgradeCommand').textContent(), 'brew update && brew upgrade --cask ganggangstone/tap/where-were-we');
    assert.equal(await page.locator('#installUpdate').count(), 1, 'One-click installation control');
    await page.evaluate(() => { window.__updateFailure='Wait for collection or AI work to finish before updating'; });
    await page.locator('#installUpdate').click();
    await page.waitForFunction(() => document.querySelector('#updateStatus').textContent.includes('Wait for collection'));
    assert.equal(await page.locator('#installUpdate').isEnabled(), true, 'Failed preflight can be retried');
    await page.evaluate(() => { window.__updateFailure=null;window.__updateStarts=[]; });
    await page.locator('#installUpdate').click();
    await page.waitForFunction(() => window.__updateStarts?.length===1);
    assert.equal(await page.locator('#installUpdate').isDisabled(), true, 'Duplicate installs blocked');
    assert.equal(await page.evaluate(() => window.__updateStarts[0].version), '0.2.0');
    await page.evaluate(() => { window.__updateState={stage:'failed',version:'0.2.0',error:'Homebrew does not have the requested stable version yet'}; });
    await page.waitForFunction(() => document.querySelector('#updateStatus').textContent.includes('Homebrew does not have'));
    assert.equal(await page.locator('#installUpdate').isEnabled(), true);
    const knownRelease = await page.evaluate(() => JSON.parse(localStorage.getItem('where-were-we.release-check')).result);
    await page.locator('#closeRelease').click();
    await page.reload();
    await page.waitForSelector('#release-banner:not([hidden])');
    assert.equal(await page.evaluate(() => window.__releaseChecks || 0), 0, 'Cached checks do not hit the network again');
    await menu('#updates');
    await page.evaluate(() => { window.__releaseFailure = true; });
    await page.locator('#checkRelease').click();
    await page.waitForFunction(() => document.querySelector('#release-dialog').textContent.includes('확인하지 못했어요'));
    await page.locator('#closeRelease').click();
    await setLanguage('en');
    await menu('#updates');
    assert.match(await page.locator('#release-dialog').innerText(), /Could not check/);
    await page.locator('#autoRelease').uncheck();
    await page.locator('#closeRelease').click();
    await page.reload();
    await page.waitForSelector('#map h2');
    await menu('#updates');
    assert.equal(await page.locator('#autoRelease').isChecked(), false);
    assert.equal(await page.evaluate(() => window.__releaseChecks || 0), 0, 'Opting out prevents automatic requests');
    await page.locator('#checkRelease').click();
    await page.waitForFunction(() => window.__releaseChecks === 1);
    await page.evaluate(() => {
      localStorage.setItem('where-were-we.release-auto', 'true');
      localStorage.setItem('where-were-we.release-check', '{broken');
    });
    await page.reload();
    await page.waitForSelector('#map h2');
    await page.waitForFunction(() => window.__releaseChecks === 1, null, { timeout: 2000 });
    await page.evaluate(now => localStorage.setItem('where-were-we.release-check', JSON.stringify({current:'0.1.0', at:now, result:{broken:true}, failed:false})), fixture.now);
    await page.reload();
    await page.waitForFunction(() => window.__releaseChecks === 1, null, { timeout: 2000 });
    await page.evaluate(({now, result}) => localStorage.setItem('where-were-we.release-check', JSON.stringify({current:'0.1.0', at:now - 86400001, result, failed:false})), {now:fixture.now, result:knownRelease});
    await page.addInitScript(() => { window.__releaseFailure = true; });
    await page.reload();
    await page.waitForSelector('#release-banner:not([hidden])');
    await menu('#updates');
    await page.waitForFunction(() => document.querySelector('#release-dialog').textContent.includes('Could not check'));
    assert.match(await page.locator('#release-dialog').innerText(), /Showing information from an earlier check/);
    assert.deepEqual(errors, []);
    assert.deepEqual(blocked, []);
    console.log('Update checks passed: versions, notes, escaping, cache, failures, language, opt-out, manual checks.');
    return;
  }
  if (process.argv.includes('--check-language')) {
    assert.equal(await page.locator('html').getAttribute('lang'), 'ko');
    assert.equal(await page.locator('#menu #language [data-lang="en"]').count(), 1, 'English language control lives in the menu');
    await view('map');
    await page.locator('[data-scr="/renders/:id"]').click();
    await page.evaluate(()=>{S.status.worktrees[0].session_count=1;S.status.worktrees[0].sessions=[{tool:'Claude Code',id:'legacy-session',last:new Date().toISOString()}];render();});
    assert.doesNotMatch(await page.locator('#insp').innerText(),/세션|session|resume/i);
    assert.equal(await page.locator('[data-copytext*="--resume"]').count(),0);
    await setLanguage('en');
    assert.doesNotMatch(await page.locator('#insp').innerText(),/세션|session|resume/i);
    assert.equal(await page.locator('html').getAttribute('lang'), 'en');
    assert.equal(await page.locator('[data-v="map"]').innerText(), 'Screen map');
    assert.equal(await page.locator('#insp h2').innerText(), title, 'Source project title must be preserved');
    assert.equal(await page.locator('[data-scr="/renders/:id"]').evaluate(el => el.classList.contains('sel')), true, 'Selection survives language change');
    assert.match(await page.locator('#insp').innerText(), /Requests/);
    await view('sys');
    assert.equal(await page.locator('#insp h2').innerText(), 'Structure');
    await view('feat');
    assert.equal(await page.locator('#insp h2').innerText(), 'Features');
    await view('changes');
    assert.match(await page.locator('#map').innerText(), /New screens/);
    await menu('#agent');
    assert.equal(await page.locator('#insp h2').innerText(), 'Connect agent');
    assert.equal(await page.locator('#insp pre').textContent(), fixture.setup, 'Generated prompt stays verbatim');
    await setLanguage('ko');
    assert.equal(await page.locator('#insp h2').innerText(), '에이전트 연결');
    assert.equal(await page.locator('#insp pre').textContent(), fixture.setup, 'Open prompt survives switching');
    await setLanguage('en');
    await page.setViewportSize({ width: 1280, height: 900 });
    assert.equal(await page.locator('header').evaluate(el => el.scrollWidth <= el.clientWidth), true, 'English toolbar fits');
    await page.reload();
    await page.waitForSelector('#map h2');
    assert.equal(await page.locator('html').getAttribute('lang'), 'en', 'Language survives reload');
    await setLanguage('ko');
    assert.equal(await page.locator('[data-v="map"]').innerText(), '화면 지도');
    await page.evaluate(() => localStorage.setItem('where-were-we.language', 'unsupported'));
    await page.reload();
    await page.waitForSelector('#map h2');
    assert.equal(await page.locator('html').getAttribute('lang'), 'ko', 'Unknown preference falls back to Korean');
    await page.addInitScript(() => {
      Object.defineProperty(window, 'localStorage', { get() { throw new DOMException('Unavailable', 'SecurityError'); } });
    });
    await page.reload();
    await page.waitForSelector('#map h2');
    assert.equal(await page.locator('html').getAttribute('lang'), 'ko', 'Unavailable storage falls back to Korean');
    await setLanguage('en');
    assert.equal(await page.locator('html').getAttribute('lang'), 'en', 'Session switching works without storage');
    await view('sys');
    await page.locator('#remakeSys').click();
    assert.equal(await page.locator('#remakeSys').isDisabled(), true);
    await setLanguage('ko');
    assert.equal(await page.locator('#remakeSys').isDisabled(), true, 'Pending analysis stays disabled after language change');
    assert.equal(await page.evaluate(() => window.__pendingCalls), 1);
    await page.evaluate(() => window.__finishSystem(JSON.stringify({handoff:'Use request_ai_task and record_ai_task for system'})));
    await page.waitForFunction(() => !document.querySelector('#remakeSys').disabled);
    await page.addInitScript(() => { window.__emptyProjects = true; });
    await page.reload();
    await page.waitForSelector('#project [data-empty]', { state: 'attached' });
    await setLanguage('en');
    assert.equal(await page.locator('#project').innerText(), '(None)', 'Empty project label switches to English');
    await setLanguage('ko');
    assert.equal(await page.locator('#project').innerText(), '(없음)', 'Empty project label switches to Korean');
    assert.deepEqual(errors, []);
    assert.deepEqual(blocked, []);
    console.log('Language checks passed: default, switching, source text, selection, prompts, persistence, invalid/unavailable storage, toolbar.');
    return;
  }
  if (language === 'en') await setLanguage('en');
  const web = p => '/@web' + p, api = f => 'api/backend/app/routers/' + f;
  await page.setViewportSize({ width: 1760, height: 1600 });
  await still('changes');
  await page.setViewportSize({ width: 1760, height: 900 });
  assert.ok((await page.locator('#map').innerText()).includes(language === 'en' ? 'Cancel render' : '렌더 취소'));
  await view('sys');
  assert.equal(await page.locator('[data-node].card').count(), 6, JSON.stringify({ errors, text: await page.locator('#map').innerText() }));
  timeline.length = 0; // Start the GIF on the architecture, not the initial loading view.
  await still('overview'); await hold(2.5);
  await click('[data-node="api::backend"]'); await hold(2);
  await view('feat');
  const render = await page.evaluate(name => groupsOf(M()).findIndex(g => g.name.endsWith(name)), language === 'en' ? 'Rendering' : '렌더');
  await click(`[data-feat="${render}"]`);
  assert.ok((await page.locator('#insp').innerText()).includes(language === 'en' ? 'Rendering' : '렌더'));
  await still('features'); await hold(2.5);
  await click(`[data-goscr="${web('/renders/:id')}"]`);
  assert.equal(await page.locator('#insp h2').innerText(), `${title} [${language === 'en' ? 'Web' : '웹'}]`, 'Screens carry the code display name');
  await still('screen-map'); await hold(2.5);
  const key = api('renders.py::cancel_render');
  await click(`[data-req="${key}"]`);
  await page.setViewportSize({ width: 1760, height: 1200 });
  await page.locator('#insp').evaluate(el => { el.scrollTop = 0; });
  await page.locator('#insp').evaluate(el => { const row = el.querySelector('[data-req][aria-expanded="true"]'); el.scrollTop += row.getBoundingClientRect().top - el.getBoundingClientRect().top - 16; });
  await still('request-flow');
  await page.setViewportSize({ width: 1760, height: 900 });
  await page.locator('#insp .detail').evaluate(el => el.scrollIntoView({ block: 'center' }));
  await hold(3);
  await click('#next'); await click('#next'); await hold(1.5);
  await click(`[data-f="route|${key}"]`);
  await page.locator('#map').evaluate(el => { el.scrollLeft = 0; el.scrollTop = 0; });
  await page.locator('#insp').evaluate(el => { el.scrollTop = 0; });
  assert.match(await page.locator('#map').innerText(), /credits/);
  await still('connections'); await hold(3);
  await click('[data-f="table|shared::credits"]');
  await still('data-impact'); await hold(2.5);
  await view('changes');
  await page.locator('#map').evaluate(el => { el.scrollTop = 0; });
  await page.locator('#insp').evaluate(el => { el.scrollTop = 0; });
  await hold(2.5);
  recording = false; // The remaining clicks create PNGs only, not extra GIF scenes.
  await view('map');
  await click(`[data-scr="${web('/revisions/new')}"]`);
  await click(`[data-req="${api('revisions.py::request_revision')}"]`);
  await click(`[data-f="route|${api('revisions.py::request_revision')}"]`);
  await page.locator('#insp').evaluate(el => { el.scrollTop = 0; });
  await page.locator('#map').evaluate(el => { el.scrollTop = 0; el.scrollLeft = 0; });
  await page.locator('#insp details').last().evaluate(el => { el.open = true; });
  await still('tests');
  assert.match(await page.locator('#insp').innerText(), language === 'en' ? /Missing test links/ : /테스트 코드가 안 보인다면/);
  await view('map');
  for (const [selector, name] of [['!orphans','orphan-requests'],['!unres','unresolved-requests'],['!issues','unlinked-issues'],['!gone','removed-items']]) {
    await click(`[data-scr="${selector}"]`); await still(name);
  }
  await click(`[data-scr="${web('/renders/:id')}"]`);
  await page.locator('#map').evaluate(el => {el.scrollTop = 0; el.scrollLeft = 0;});
  await page.locator('#insp').evaluate(el => {el.scrollTop = 0;});
  await page.locator('#q').fill(language === 'en' ? 'cancel' : '취소');
  assert.ok(await page.locator('[data-search-result]').count() > 0, 'Search lists results in every view');
  await still('search');
  await page.locator('#q').fill('');
  await view('sys');
  await page.locator('#map').evaluate(el => { el.scrollTop = 0; el.scrollLeft = 0; });
  await page.locator('#insp').evaluate(el => { el.scrollTop = 0; });
  await click('[data-node="worker::worker"]');
  await page.setViewportSize({width:1760,height:1200});
  await still('worker');
  await menu('#agent');
  await page.locator('#insp').evaluate(el => { el.scrollTop = 0; });
  await page.waitForSelector('#cpAgent'); await still('agent-setup');
  await menu('#updates');
  await page.waitForSelector('#release-dialog[open]');
  await page.evaluate(() => { window.__releaseReply = {current:'0.1.0', latest:{version:'0.2.0',newer:true,url:'https://github.com/ganggangstone/where-were-we/releases/tag/v0.2.0',notes:'Fictional release example / 가상 릴리즈 예시\n\n### 한국어\n- 렌더 요청과 크레딧 사용 화면의 연결을 개선했습니다.\n\n### English\n- Improved render request and credit usage connections.'}}; });
  await page.locator('#checkRelease').click();
  await page.waitForFunction(() => document.querySelector('#release-banner').textContent.includes('0.2.0'));
  await still('updates');
  await page.locator('#closeRelease').click();
  assert.deepEqual(errors, [], 'Browser errors');
  assert.deepEqual(blocked, [], 'Unexpected network requests');
  const list = path.join(frames, 'frames.txt');
  fs.writeFileSync(list, timeline.map(x => `file '${x.file}'\nduration ${x.seconds}`).join('\n') + `\nfile '${timeline.at(-1).file}'\n`);
  execFileSync('ffmpeg', ['-hide_banner', '-loglevel', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', list,
    '-filter_complex', '[0:v]fps=6,scale=1280:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=192[p];[b][p]paletteuse=dither=bayer:bayer_scale=3',
    '-loop', '0', path.join(output, 'demo.gif')]);
  console.log('Created demo.gif and 16 PNG screenshots. Browser errors: 0. External requests: 0.');
})().catch(e => { console.error(e); process.exitCode = 1; }).finally(async () => {
  if (browser) await browser.close(); server.close();
  fs.rmSync(frames, { recursive: true, force: true });
});
