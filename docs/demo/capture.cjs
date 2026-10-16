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
if (process.argv.includes('--check-projects')) {
  const code = `import json,sys,tempfile,copy
from pathlib import Path
sys.path.insert(0,sys.argv[1])
import mapcore,project
maps=json.load(sys.stdin)
with tempfile.TemporaryDirectory() as temp:
 mapcore.ROOT=temp
 conf={'repositories':[{'id':'web','path':'/demo/web','api_targets':['api']},{'id':'api','path':'/demo/api'},{'id':'admin','path':'/demo/admin'},{'id':'worker','path':'/demo/worker'}]}
 project.configure('studio',conf)
 for rid in ['web','api','admin','worker']:
  raw=copy.deepcopy(maps)
  for role in ['dev','main','dev.prev','main.prev']:
   m=raw[role];m['repo']='/demo/'+rid
   if rid in ['api','worker']:m['screens']=[];m['api_functions']=[]
   if rid in ['web','admin','worker']:m['backend_routes']=[];m['backend_routes_without_screen']=[];m['models']={}
   if rid in ['web','admin']:
    for f in m['api_functions']:
     for c in f['calls']:c['backend']=[]
   if rid=='admin':m['screens']=[s for s in m['screens'] if s['path']=='/renders/:id']
  raw['flows']={'routes':{}}
  if rid!='web':raw['groups']={'groups':[],'names':{},'request_names':{}}
  raw['system']=None;raw['jobs']=None
  project.publish('studio',rid,raw,{'fingerprint':project.fingerprint(next(r for r in project.config('studio')['repositories'] if r['id']==rid))})
 print(json.dumps({rid:project.read_bundle('studio',rid) for rid in ['', 'web','api','admin','worker']}))`;
  fixture.bundles = JSON.parse(execFileSync('python3',['-c',code,root],{input:JSON.stringify(fixture.maps),encoding:'utf8'}));
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
      if (command === 'save_project') {window.__savedConfiguration=JSON.parse(args.configuration);return 'Saved';}
      if (command === 'list_projects') return window.__emptyProjects ? [] : [data.project];
      if (command === 'read_map') {
        if (!(args.branch in data.maps)) throw Error('No demo fixture: ' + args.branch);
        return JSON.stringify(data.maps[args.branch]);
      }
      if (command === 'refresh') {
        if (window.__holdRefresh) return new Promise(resolve=>{window.__finishRefresh=resolve;});
        return 'Demo only: no repository was accessed.';
      }
      if (command === 'make_steps' || command === 'suggest_groups' || command === 'make_jobs') {window.__actionArgs=args;return 'Demo only';}
      if (command === 'setup_prompt') return data.setup;
      if (command === 'tests_prompt') return args.lang === 'en' ? 'Fictional example: find and link revision API tests.' : '가상 예시: 수정 요청 API의 테스트를 찾아 연결해 주세요.';
      if (command === 'make_system') {
        window.__pendingCalls = (window.__pendingCalls || 0) + 1;
        return new Promise(resolve => { window.__finishSystem = resolve; });
      }
      throw Error('Not available in the capture: ' + command);
    } } };
    document.addEventListener('DOMContentLoaded', () => {
      const style = document.createElement('style');
      style.textContent = '#demo-label{height:38px;flex:none;display:flex;align-items:center;justify-content:space-between;padding:0 22px;background:#edf3ff;border-bottom:1px solid #d5e1fa;color:#32476a;font:12px -apple-system,BlinkMacSystemFont,sans-serif} #demo-cursor{position:fixed;width:18px;height:18px;border:2px solid #007aff;border-radius:50%;background:#007aff22;pointer-events:none;z-index:1000;left:-100px;top:-100px}';
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
  let recording = true;
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
  await page.goto(base);
  await page.waitForFunction(() => document.querySelector('#status').textContent === '' && document.querySelector('#map h2'));
  if (process.argv.includes('--check-projects')) {
    assert.equal(await page.locator('#repository option').count(),5);
    await page.locator('[data-v="map"]').click();
    assert.equal(await page.locator('[data-scr="/@web/renders/:id"]').count(),1);
    assert.equal(await page.locator('[data-scr="/@admin/renders/:id"]').count(),1);
    await page.locator('[data-scr="/@web/renders/:id"]').click();
    assert.match(await page.locator('#insp').innerText(), /web/);
    await page.locator('[data-req="api/backend/app/routers/renders.py::cancel_render"]').click();
    assert.match(await page.locator('#insp').innerText(), /사용자가 지정한 레포 연결/);
    await page.locator('#mk').click();
    await page.waitForFunction(()=>window.__actionArgs?.repository==='api');
    assert.match(await page.evaluate(()=>window.__actionArgs.screen),/^@routes:/);
    await page.locator('#repository').selectOption('web');
    await page.waitForFunction(()=>document.querySelector('#repository').value==='web' && !document.querySelector('[data-scr="/@admin/renders/:id"]'));
    await page.locator('#language [data-lang="en"]').click();
    assert.equal(await page.locator('#manageRepositories').innerText(),'Manage repositories');
    await page.locator('#manageRepositories').click();
    assert.equal(await page.locator('[data-repository-row]').count(),4);
    assert.equal(await page.locator('[data-repository-row="0"] [data-field="id"]').isDisabled(),true);
    await page.locator('#cancelProject').click();
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
    await row.locator('[data-field="id"]').fill('new');
    await row.locator('[data-field="path"]').fill('/demo/new');
    await page.locator('#saveProject').click();
    await page.waitForFunction(()=>window.__savedConfiguration);
    assert.deepEqual(await page.evaluate(()=>window.__savedConfiguration.shared_data),[]);
    assert.equal(await page.evaluate(()=>window.__savedConfiguration.repositories[0].id),'new');
    assert.deepEqual(errors,[]);assert.deepEqual(blocked,[]);
    console.log('Project checks passed: shared composition, filtering, configured calls, target AI scope, settings, new project, and refresh/selection race.');
    return;
  }
  if (process.argv.includes('--check-updates')) {
    assert.equal(await page.locator('#updates').count(), 1, 'Version and update control');
    await page.waitForFunction(() => window.__releaseChecks === 1);
    await page.locator('#updates').click();
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
    const knownRelease = await page.evaluate(() => JSON.parse(localStorage.getItem('where-were-we.release-check')).result);
    await page.locator('#closeRelease').click();
    await page.reload();
    await page.waitForSelector('#release-banner:not([hidden])');
    assert.equal(await page.evaluate(() => window.__releaseChecks || 0), 0, 'Cached checks do not hit the network again');
    await page.locator('#updates').click();
    await page.evaluate(() => { window.__releaseFailure = true; });
    await page.locator('#checkRelease').click();
    await page.waitForFunction(() => document.querySelector('#release-dialog').textContent.includes('확인하지 못했어요'));
    await page.locator('#closeRelease').click();
    await page.locator('#language [data-lang="en"]').click();
    await page.locator('#updates').click();
    assert.match(await page.locator('#release-dialog').innerText(), /Could not check/);
    await page.locator('#autoRelease').uncheck();
    await page.locator('#closeRelease').click();
    await page.reload();
    await page.waitForSelector('#map h2');
    await page.locator('#updates').click();
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
    await page.locator('#updates').click();
    await page.waitForFunction(() => document.querySelector('#release-dialog').textContent.includes('Could not check'));
    assert.match(await page.locator('#release-dialog').innerText(), /Showing information from an earlier check/);
    assert.deepEqual(errors, []);
    assert.deepEqual(blocked, []);
    console.log('Update checks passed: versions, notes, escaping, cache, failures, language, opt-out, manual checks.');
    return;
  }
  if (process.argv.includes('--check-language')) {
    assert.equal(await page.locator('html').getAttribute('lang'), 'ko');
    assert.equal(await page.locator('#language [data-lang="en"]').count(), 1, 'English language control');
    await page.locator('[data-v="map"]').click();
    await page.locator('[data-scr="/renders/:id"]').click();
    await page.locator('#language [data-lang="en"]').click();
    assert.equal(await page.locator('html').getAttribute('lang'), 'en');
    assert.equal(await page.locator('[data-v="map"]').innerText(), 'Screen map');
    assert.equal(await page.locator('#insp h2').innerText(), title, 'Source project title must be preserved');
    assert.equal(await page.locator('[data-scr="/renders/:id"]').evaluate(el => el.classList.contains('sel')), true, 'Selection survives language change');
    assert.match(await page.locator('#insp').innerText(), /Requests/);
    await page.locator('[data-v="sys"]').click();
    assert.equal(await page.locator('#insp h2').innerText(), 'System');
    await page.locator('[data-v="feat"]').click();
    assert.equal(await page.locator('#insp h2').innerText(), 'Features');
    await page.locator('[data-v="changes"]').click();
    assert.match(await page.locator('#map').innerText(), /New screens/);
    await page.locator('#agent').click();
    assert.equal(await page.locator('#insp h2').innerText(), 'Connect agent');
    assert.equal(await page.locator('#insp pre').textContent(), fixture.setup, 'Generated prompt stays verbatim');
    await page.locator('#language [data-lang="ko"]').click();
    assert.equal(await page.locator('#insp h2').innerText(), '에이전트 연결');
    assert.equal(await page.locator('#insp pre').textContent(), fixture.setup, 'Open prompt survives switching');
    await page.locator('#language [data-lang="en"]').click();
    await page.setViewportSize({ width: 1480, height: 900 });
    assert.equal(await page.locator('header').evaluate(el => el.scrollWidth <= el.clientWidth), true, 'English toolbar fits');
    await page.reload();
    await page.waitForSelector('#map h2');
    assert.equal(await page.locator('html').getAttribute('lang'), 'en', 'Language survives reload');
    await page.locator('#language [data-lang="ko"]').click();
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
    await page.locator('#language [data-lang="en"]').click();
    assert.equal(await page.locator('html').getAttribute('lang'), 'en', 'Session switching works without storage');
    await page.locator('[data-v="sys"]').click();
    await page.locator('#remakeSys').click();
    assert.equal(await page.locator('#remakeSys').isDisabled(), true);
    await page.locator('#language [data-lang="ko"]').click();
    assert.equal(await page.locator('#remakeSys').isDisabled(), true, 'Pending analysis stays disabled after language change');
    assert.equal(await page.evaluate(() => window.__pendingCalls), 1);
    await page.evaluate(() => window.__finishSystem('Done'));
    await page.waitForFunction(() => !document.querySelector('#remakeSys').disabled);
    await page.addInitScript(() => { window.__emptyProjects = true; });
    await page.reload();
    await page.waitForSelector('#project [data-empty]', { state: 'attached' });
    await page.locator('#language [data-lang="en"]').click();
    assert.equal(await page.locator('#project').innerText(), '(None)', 'Empty project label switches to English');
    await page.locator('#language [data-lang="ko"]').click();
    assert.equal(await page.locator('#project').innerText(), '(없음)', 'Empty project label switches to Korean');
    assert.deepEqual(errors, []);
    assert.deepEqual(blocked, []);
    console.log('Language checks passed: default, switching, source text, selection, prompts, persistence, invalid/unavailable storage, toolbar.');
    return;
  }
  if (language === 'en') await page.locator('#language [data-lang="en"]').click();
  await page.setViewportSize({ width: 1760, height: 1600 });
  await still('changes');
  await page.setViewportSize({ width: 1760, height: 900 });
  assert.ok((await page.locator('#map').innerText()).includes(language === 'en' ? 'Cancel render' : '렌더 취소'));
  await click('[data-v="sys"]');
  assert.equal(await page.locator('[data-node].card').count(), 5, JSON.stringify({ errors, text: await page.locator('#map').innerText() }));
  timeline.length = 0; // Start the GIF on the architecture, not the initial loading view.
  await still('overview'); await hold(2.5);
  await click('[data-node="backend"]'); await hold(2);
  await click('[data-v="feat"]');
  await click('[data-feat="2"]');
  assert.ok((await page.locator('#insp').innerText()).includes(language === 'en' ? 'Rendering' : '렌더'));
  await still('features'); await hold(2.5);
  await click('[data-goscr="/renders/:id"]');
  assert.equal(await page.locator('#insp h2').innerText(), title);
  await still('screen-map'); await hold(2.5);
  const key = 'backend/app/routers/renders.py::cancel_render';
  await click(`[data-req="${key}"]`);
  await page.setViewportSize({ width: 1760, height: 1200 });
  await page.locator('#insp').evaluate(el => { el.scrollTop = 0; });
  await page.locator('#insp').evaluate(el => { el.scrollTop = el.querySelector('.detail').offsetTop - 100; });
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
  await click('[data-f="table|credits"]');
  await still('data-impact'); await hold(2.5);
  await click('[data-v="changes"]');
  await page.locator('#map').evaluate(el => { el.scrollTop = 0; });
  await page.locator('#insp').evaluate(el => { el.scrollTop = 0; });
  await hold(2.5);
  recording = false; // The remaining clicks create PNGs only, not extra GIF scenes.
  await click('[data-v="map"]');
  await click('[data-scr="/revisions/new"]');
  await click('[data-req="backend/app/routers/revisions.py::request_revision"]');
  await click('[data-f="route|backend/app/routers/revisions.py::request_revision"]');
  await page.locator('#insp').evaluate(el => { el.scrollTop = 0; });
  await page.locator('#map').evaluate(el => { el.scrollTop = 0; el.scrollLeft = 0; });
  await page.locator('#insp details').last().evaluate(el => { el.open = true; });
  await still('tests');
  assert.match(await page.locator('#insp').innerText(), language === 'en' ? /Missing test links/ : /테스트 코드가 안 보인다면/);
  await click('[data-v="map"]');
  for (const [selector, name] of [['!orphans','orphan-requests'],['!unres','unresolved-requests'],['!issues','unlinked-issues'],['!gone','removed-items']]) {
    await click(`[data-scr="${selector}"]`); await still(name);
  }
  await click('[data-scr="/renders/:id"]');
  await page.locator('#map').evaluate(el => {el.scrollTop = 0; el.scrollLeft = 0;});
  await page.locator('#insp').evaluate(el => {el.scrollTop = 0;});
  await page.locator('#q').fill(language === 'en' ? 'cancel' : '취소');
  await still('search');
  await page.locator('#q').fill('');
  await click('[data-v="sys"]');
  await page.locator('#map').evaluate(el => { el.scrollTop = 0; el.scrollLeft = 0; });
  await page.locator('#insp').evaluate(el => { el.scrollTop = 0; });
  await click('[data-node="worker"]');
  await page.setViewportSize({width:1760,height:1200});
  await still('worker');
  await click('#agent');
  await page.locator('#insp').evaluate(el => { el.scrollTop = 0; });
  await page.waitForSelector('#cpAgent'); await still('agent-setup');
  await click('#updates');
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
