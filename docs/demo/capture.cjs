// Capture the real UI with fictional in-memory responses; never run the Rust/Python backend.
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const http = require('node:http');
const { execFileSync } = require('node:child_process');
const assert = require('node:assert/strict');
const { chromium } = require('playwright');
const fixture = require('./fixture.cjs');
const root = path.resolve(__dirname, '../..');
const output = path.join(root, 'docs/images');
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
    locale: 'ko-KR', timezoneId: 'Asia/Seoul', reducedMotion: 'reduce' });
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
      if (command === 'list_projects') return window.__emptyProjects ? [] : [data.project];
      if (command === 'read_map') {
        if (!(args.branch in data.maps)) throw Error('No demo fixture: ' + args.branch);
        return JSON.stringify(data.maps[args.branch]);
      }
      if (command === 'refresh') return 'Demo only: no repository was accessed.';
      if (command === 'setup_prompt') return data.setup;
      if (command === 'tests_prompt') return '가상 시나리오: 반품 API의 테스트를 찾아 연결해 주세요.';
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
      const name = document.createElement('b'); name.textContent = 'where-were-we / Cedar Shop';
      const note = document.createElement('span'); note.textContent = '가상 데이터 · 실제 UI · 수집·AI 응답은 촬영용 예시';
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
    await page.locator('[data-scr="/orders/:id"]').click();
    await page.locator('#language [data-lang="en"]').click();
    assert.equal(await page.locator('html').getAttribute('lang'), 'en');
    assert.equal(await page.locator('[data-v="map"]').innerText(), 'Screen map');
    assert.equal(await page.locator('#insp h2').innerText(), '주문 상세', 'Source project title must be preserved');
    assert.equal(await page.locator('[data-scr="/orders/:id"]').evaluate(el => el.classList.contains('sel')), true, 'Selection survives language change');
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
  await page.setViewportSize({ width: 1760, height: 1100 });
  await still('changes');
  await page.setViewportSize({ width: 1760, height: 900 });
  assert.match(await page.locator('#map').innerText(), /주문 취소/);
  await click('[data-v="sys"]');
  assert.equal(await page.locator('[data-node].card').count(), 4, JSON.stringify({ errors, text: await page.locator('#map').innerText() }));
  timeline.length = 0; // Start the GIF on the architecture, not the initial loading view.
  await still('overview'); await hold(2.5);
  await click('[data-node="backend"]'); await hold(2);
  await click('[data-v="feat"]');
  await click('[data-feat="2"]');
  assert.match(await page.locator('#insp').innerText(), /주문/);
  await still('features'); await hold(2.5);
  await click('[data-goscr="/orders/:id"]');
  assert.equal(await page.locator('#insp h2').innerText(), '주문 상세');
  await still('screen-map'); await hold(2.5);
  const key = 'backend/app/routers/orders.py::cancel_order';
  await click(`[data-req="${key}"]`);
  await page.setViewportSize({ width: 1760, height: 1200 });
  await page.locator('#insp').evaluate(el => { el.scrollTop = 0; });
  await still('request-flow');
  await page.setViewportSize({ width: 1760, height: 900 });
  await page.locator('#insp .detail').evaluate(el => el.scrollIntoView({ block: 'center' }));
  await hold(3);
  await click('#next'); await click('#next'); await hold(1.5);
  await click(`[data-f="route|${key}"]`);
  await page.locator('#map').evaluate(el => { el.scrollLeft = 0; el.scrollTop = 0; });
  await page.locator('#insp').evaluate(el => { el.scrollTop = 0; });
  assert.match(await page.locator('#map').innerText(), /inventory/);
  await still('connections'); await hold(3);
  await click('[data-f="table|inventory"]');
  await still('data-impact'); await hold(2.5);
  await click('[data-v="changes"]');
  await page.locator('#map').evaluate(el => { el.scrollTop = 0; });
  await page.locator('#insp').evaluate(el => { el.scrollTop = 0; });
  await hold(2.5);
  recording = false; // The remaining clicks create PNGs only, not extra GIF scenes.
  await click('[data-v="map"]');
  await click('[data-scr="/returns/new"]');
  await click('[data-req="backend/app/routers/returns.py::create_return"]');
  await click('[data-f="route|backend/app/routers/returns.py::create_return"]');
  await page.locator('#insp').evaluate(el => { el.scrollTop = 0; });
  await page.locator('#map').evaluate(el => { el.scrollTop = 0; el.scrollLeft = 0; });
  await page.locator('#insp details').last().evaluate(el => { el.open = true; });
  await still('tests');
  assert.match(await page.locator('#insp').innerText(), /테스트 코드가 안 보인다면/);
  await click('[data-v="sys"]');
  await page.locator('#map').evaluate(el => { el.scrollTop = 0; el.scrollLeft = 0; });
  await page.locator('#insp').evaluate(el => { el.scrollTop = 0; });
  await click('#agent');
  await page.locator('#insp').evaluate(el => { el.scrollTop = 0; });
  await page.waitForSelector('#cpAgent'); await still('agent-setup');
  assert.deepEqual(errors, [], 'Browser errors');
  assert.deepEqual(blocked, [], 'Unexpected network requests');
  const list = path.join(frames, 'frames.txt');
  fs.writeFileSync(list, timeline.map(x => `file '${x.file}'\nduration ${x.seconds}`).join('\n') + `\nfile '${timeline.at(-1).file}'\n`);
  execFileSync('ffmpeg', ['-hide_banner', '-loglevel', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', list,
    '-filter_complex', '[0:v]fps=6,scale=1280:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=192[p];[b][p]paletteuse=dither=bayer:bayer_scale=3',
    '-loop', '0', path.join(output, 'demo.gif')]);
  console.log('Created demo.gif and 9 PNG screenshots. Browser errors: 0. External requests: 0.');
})().catch(e => { console.error(e); process.exitCode = 1; }).finally(async () => {
  if (browser) await browser.close(); server.close();
  fs.rmSync(frames, { recursive: true, force: true });
});
