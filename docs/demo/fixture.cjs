// Entirely fictional input for the existing UI. No repository or API is consulted.
const clone = value => JSON.parse(JSON.stringify(value));
const project = 'Lumen Studio · 가상 데이터';
const at = '2026-06-08T21:00:00+09:00';
const since = '2026-06-08T20:00:00+09:00';
const routes = [];
const api = [];
const requestNames = {};
function request(name, title, method, path, tables, external = []) {
  const file = `backend/app/routers/${tables[0]}.py`;
  const line = 20 + routes.length * 15;
  const route = { file, line, function: name, method, path, tables,
    externals: external, mounted: true, inputs: method === 'GET' ? [] : ['render_id: str'],
    services: [], tests: name === 'request_revision' ? [] : [`backend/tests/test_${tables[0]}.py`] };
  routes.push(route);
  api.push({ name, file: `frontend/src/api/${tables[0]}.ts`, calls: [
    { method, path, line: 12, backend: [{ file, line }] }
  ] });
  requestNames[`${file}::${name}`] = title;
  return name;
}
request('list_assets', '미디어 목록 읽기', 'GET', '/assets', ['assets']);
request('read_asset', '미디어 상세 읽기', 'GET', '/assets/{id}', ['assets', 'credits']);
request('read_board', '스토리보드 읽기', 'GET', '/board', ['board_items', 'assets']);
request('add_to_board', '스토리보드에 추가', 'POST', '/board/items', ['board_items']);
request('start_render', '렌더 시작', 'POST', '/renders', ['renders', 'credits', 'board_items'], ['렌더 제공사']);
request('list_renders', '렌더 목록 읽기', 'GET', '/renders', ['renders']);
request('read_render', '렌더 상태 읽기', 'GET', '/renders/{id}', ['renders', 'render_items']);
request('cancel_render', '렌더 취소', 'POST', '/renders/{id}/cancel', ['renders', 'credits'], ['렌더 제공사']);
request('read_publication', '게시 상태 읽기', 'GET', '/publications/{id}', ['publications', 'renders'], ['게시 제공사']);
request('request_revision', '수정 요청', 'POST', '/revisions', ['revisions', 'renders']);
request('adjust_credits', '크레딧 조정', 'PATCH', '/credits/{id}', ['credits']);
request('usage_report', '사용량 읽기', 'GET', '/reports/sales', ['renders']);
function screen(path, heading, functions, nav = []) {
  const file = `frontend/src/pages/${path.replace(/[^a-z0-9]/g, '_')}.tsx`;
  return { path, heading, file, line: 10, redirect: false,
    api_functions: functions.map(name => ({ name, file: api.find(a => a.name === name).file })),
    actions: [
      ...nav.map(([label, to]) => ({ kind: 'nav', label, targets: [{ to }], file, line: 30 })),
      ...functions.filter(name => routes.find(r => r.function === name).method !== 'GET')
        .map(name => ({ kind: 'api', label: requestNames[routes.find(r => r.function === name).file + '::' + name],
          api_functions: [name], file, line: 42, calls: [] }))
    ] };
}
const screens = [
  screen('/assets', '미디어 목록', ['list_assets'], [['미디어 보기', '/assets/:id']]),
  screen('/assets/:id', '미디어 상세', ['read_asset', 'add_to_board'], [['스토리보드 보기', '/board']]),
  screen('/board', '스토리보드', ['read_board'], [['렌더 설정', '/renders/new']]),
  screen('/renders/new', '렌더 설정', ['start_render'], [['렌더 확인', '/renders/:id']]),
  screen('/renders', '내 렌더', ['list_renders'], [['렌더 상세', '/renders/:id']]),
  screen('/renders/:id', '렌더 상세', ['read_render', 'cancel_render'], [['게시 상태', '/publications/:id'], ['수정 요청', '/revisions/new']]),
  screen('/publications/:id', '게시 상태', ['read_publication'], [['렌더로', '/renders/:id']]),
  screen('/revisions/new', '수정 요청', ['request_revision'], [['내 렌더로', '/renders']]),
  screen('/admin/credits', '크레딧 관리', ['adjust_credits'], [['사용량 보기', '/admin/reports']]),
  screen('/admin/reports', '사용량 현황', ['usage_report'])
];
const dev = { repo: '/demo/lumen-studio', ref: 'origin/dev', commit: 'demo0002',
  screens, api_functions: api, backend_routes: routes,
  backend_routes_without_screen: [], unresolved_calls: [],
  models: Object.fromEntries([...new Set(routes.flatMap(r => r.tables))].map(t => [t, t])) };
const orphan = {file:'backend/app/routers/hooks.py',line:18,function:'receive_callback',method:'POST',path:'/hooks/render',tables:['renders'],externals:[],mounted:true,inputs:[],services:[],tests:[]};
dev.backend_routes.push(orphan);
dev.backend_routes_without_screen.push(orphan);
dev.unresolved_calls.push({method:'POST',raw:'`${workspaceUrl}/publish`',api_function:'frontend/src/api/publish.ts',line:31});
const main = clone(dev);
main.ref = 'origin/main'; main.commit = 'demo0001';
main.screens = main.screens.filter(s => s.path !== '/revisions/new');
main.backend_routes = main.backend_routes.filter(r => !['request_revision', 'cancel_render', 'receive_callback'].includes(r.function));
main.screens.forEach(s => {
  s.api_functions = s.api_functions.filter(a => a.name !== 'cancel_render');
  s.actions = s.actions.filter(a => !(a.targets || []).some(t => t.to === '/revisions/new') && !(a.api_functions || []).includes('cancel_render'));
});
main.backend_routes_without_screen = [];
const previous = clone(main);
previous.commit = 'demo0000';
previous.screens.push(screen('/legacy/export', '이전 내보내기', ['read_render']));
requestNames['backend/app/routers/hooks.py::receive_callback'] = '제공사 콜백';
const groups = { names: {}, request_names: requestNames, groups: [
  { name: '미디어 라이브러리', description: '업로드된 이미지와 영상 탐색', screens: ['/assets', '/assets/:id'] },
  { name: '스토리보드', description: '장면 구성과 렌더 설정', screens: ['/board', '/renders/new'] },
  { name: '렌더', description: '렌더 진행·취소·크레딧 반환', screens: ['/renders', '/renders/:id'] },
  { name: '게시·수정', description: '게시 상태와 수정 요청', screens: ['/publications/:id', '/revisions/new'] },
  { name: '워크스페이스 관리', description: '크레딧과 사용량 확인', screens: ['/admin/credits', '/admin/reports'] }
] };
const cancel = routes.find(r => r.function === 'cancel_render');
const flows = { routes: Object.fromEntries(routes.map(r => [r.file + '::' + r.function, {
  name: requestNames[r.file + '::' + r.function],
  steps: r.function === 'cancel_render' ? [
    { lane: '서버', text: '진행 중인 렌더인지 확인한다', line: cancel.line + 1, quote: 'ensure_cancellable(render)' },
    { lane: '외부', text: '렌더 제공사에 취소를 요청한다', line: cancel.line + 3, quote: 'renderer.cancel(render.provider_id)' },
    { lane: '저장소', text: '렌더를 취소 상태로 저장한다', line: cancel.line + 5, quote: "render.status = 'cancelled'" },
    { lane: '저장소', text: '예약한 크레딧을 반환한다', line: cancel.line + 6, quote: 'credits.release(render.reservation)' }
  ] : [{ lane: '서버', text: requestNames[r.file + '::' + r.function], line: r.line + 1, quote: `${r.function}()` }]
}])) };
const url = n => `https://example.invalid/lumen-studio/pull/${n}`;
const merged = { number: 42, title: '렌더 취소와 크레딧 반환 연결', author: 'demo-agent',
  url: url(42), screens: ['/renders/:id', '/admin/credits'],
  files: ['backend/app/routers/renders.py', 'backend/app/routers/credits.py', 'frontend/src/pages/_renders__id.tsx'], merged_at: at };
const status = {
  open_prs: [{ number: 43, title: '수정 요청 화면 연결', author: 'demo-agent', url: url(43),
    screens: ['/revisions/new', '/renders/:id'], files: ['backend/app/routers/revisions.py'], updated_at: since }],
  merged_prs: [merged], branches: [{name:'demo/retry-render', screens:['/renders/:id'], ahead_of_dev:2,
    stale:false, has_open_pr:false, author:'demo-agent', age_days:1}],
  worktrees: [{path:'/demo/workspaces/retry-render', branch:'demo/retry-render', screens:['/renders/:id'],
    uncommitted:['backend/app/routers/renders.py'], session_count:0, sessions:[]}],
  issues: [{ number: 18, title: '취소 후 크레딧 반환 확인', url: 'https://example.invalid/lumen-studio/issues/18',
    screens: ['/renders/:id'], via: 'pr', hits: ['#42'] }]
};
status.open_prs.push({number:44, title:'렌더 취소와 재시도 경합 처리', author:'demo-reviewer',
  url:url(44), screens:['/renders/:id','/admin/credits'],
  files:['backend/app/routers/renders.py','worker/consumer.py'], updated_at:since});
status.issues.push({number:19,title:'게시 콜백 재시도 기준',url:'https://example.invalid/lumen-studio/issues/19',screens:[],via:'text',hits:[]});
const node = (id, name, what, kind, extra = {}) => ({ id, name, what, kind, uses: [], ev: [], unknown: [], ...extra });
const system = { written: '가상 시나리오', checked: 'demo0002', nodes: [
  node('web', '제작 웹', '미디어 · 스토리보드 · 렌더', 'program', { origin: 'repo', origin_text: '가상 플랫폼의 웹 클라이언트', code: ['frontend'], detail: 'map' }),
  node('backend', '제작 API', '렌더 접수 · 크레딧 예약 · 게시', 'program', { origin: 'repo', origin_text: '가상 플랫폼의 API', code: ['backend'], uses: ['renderer', 'publisher'], detail: 'map' }),
  node('queue', '렌더 대기열', '작업 ID와 재시도 예약', 'store'),
  node('db', '제작 데이터', '미디어 · 렌더 · 크레딧 기록', 'store'),
  node('worker', '렌더 작업기', '대기열 소비 · 제공사 호출 · 결과 저장', 'program', { origin: 'other', origin_text: '가상 렌더 작업 저장소', code: ['worker'], ev:[{file:'worker/consumer.py',line:28,ok:false}], uses: ['renderer'], tables: ['renders', 'credits'], copies:[{branch:'origin/worker', against:'origin/dev', files:[{path:'backend/app/routers/renders.py', same:false},{path:'backend/app/models/credits.py',same:true}]}], unknown: [{ needs: 'ops', text: '렌더 작업기가 실제로 실행 중인지' }] })
], externals: [{ id: 'renderer', name: '렌더 제공사', what: '비동기 영상 렌더와 취소' }, { id: 'publisher', name: '게시 제공사', what: '채널 게시와 상태 조회' }],
  unknown: [], others: [], links: [
    { from: 'web', to: 'backend', label: '미디어 조회 · 렌더 · 취소', sure: 'code' },
    { from: 'backend', to: 'db', label: '렌더와 크레딧 읽기·쓰기', sure: 'code' },
    { from: 'backend', to: 'queue', label: '렌더 작업 전달', sure: 'code' },
    { from: 'queue', to: 'worker', label: '대기 작업 소비', sure: 'code' },
    { from: 'worker', to: 'db', label: '렌더 결과 저장', sure: 'code' }
] };
const delta = { from: previous.commit, to: dev.commit,
  screens_added: [{ path: '/revisions/new', name: '수정 요청', group: '게시·수정' }], screens_removed: [{path:'/legacy/export',name:'이전 내보내기'}],
  requests_added: [{ screen: '/renders/:id', screen_name: '렌더 상세', name: '렌더 취소', what: 'POST /renders/{id}/cancel' }],
  requests_removed: [], flows_added: [
    { from: '/renders/:id', from_name: '렌더 상세', to: '/revisions/new', to_name: '수정 요청', label: '수정 요청' },
    { from: '/revisions/new', from_name: '수정 요청', to: '/renders', to_name: '내 렌더', label: '내 렌더로' }
  ],
  flows_removed: [], routes_added_no_screen: [{name:'제공사 콜백',what:'POST /hooks/render',file:'backend/app/routers/hooks.py'}] };
const changes = { last_refresh: at, entries: [{ at, since, branches: { dev: delta },
  ai_stale: {system:1}, prs: [{ ...merged, files: merged.files.length,
    groups: groups.groups.filter(g => g.screens.some(p => merged.screens.includes(p))).map(g => g.name),
    programs: [], kinds: ['기능', '구조'], base: 'dev', issues: [18] }] }] };
const setup = `where-were-we를 내 에이전트에 연결해 주세요.\n\n1. 아래 MCP 서버를 등록해 주세요.\n   python3 /demo/where-were-we/mcp_server.py\n2. 계획 전에 changes로 바뀐 것을, 수정 전에 impact로 닿는 곳을 확인하도록 지침을 추가해 주세요.\n3. 설정 파일을 바꾸기 전에 허락을 구해 주세요.\n\n※ 촬영용 가상 응답입니다. 실제 경로와 설정은 앱의 에이전트 연결에서 생성합니다.`;
const fixture = { project, now: Date.parse(at), setup, maps: { dev, main, status, groups, flows, system,
  jobs: { nodes: {worker:{jobs:[{name:'영상 렌더',what:'예약한 크레딧으로 영상을 만들고 결과를 저장한다',starts_when:'대기열에 렌더 ID가 도착하면',routes:[{key:'backend/app/routers/renders.py::start_render',exact:true},{key:'backend/app/routers/renders.py::cancel_render',exact:false}],steps:[{lane:'서버',text:'대기열에서 작업을 읽는다',file:'worker/consumer.py',line:22},{lane:'외부',text:'제공사에 렌더를 요청한다',file:'worker/consumer.py',line:28},{lane:'저장소',text:'결과와 크레딧 사용량을 저장한다',file:'worker/consumer.py',line:35}]}]}} }, changes, 'dev.prev': previous, 'main.prev': main } };

const english = {
 '이전 내보내기':'Legacy export', '게시 콜백 재시도 기준':'Publishing callback retry policy', '제공사 콜백':'Provider callback',
 '대기열에서 작업을 읽는다':'Read a queued job', '제공사에 렌더를 요청한다':'Submit the render to the provider', '결과와 크레딧 사용량을 저장한다':'Save the result and credit usage',
  'Lumen Studio · 가상 데이터':'Lumen Studio · fictional data',
  '미디어 목록 읽기':'List media', '미디어 상세 읽기':'Read media', '스토리보드 읽기':'Read storyboard',
  '스토리보드에 추가':'Add to storyboard', '렌더 시작':'Start render', '렌더 목록 읽기':'List renders',
  '렌더 상태 읽기':'Read render status', '렌더 취소':'Cancel render', '게시 상태 읽기':'Read publication status',
  '수정 요청':'Request revision', '크레딧 조정':'Adjust credits', '사용량 읽기':'Read usage',
  '미디어 목록':'Media library', '미디어 상세':'Media details', '미디어 보기':'Open media',
  '스토리보드':'Storyboard', '스토리보드 보기':'Open storyboard', '렌더 설정':'Render settings',
  '렌더 확인':'View render', '내 렌더':'My renders', '렌더 상세':'Render details', '게시 상태':'Publication status',
  '렌더로':'Back to render', '내 렌더로':'Back to renders', '크레딧 관리':'Credit management',
  '사용량 보기':'View usage', '사용량 현황':'Usage report', '미디어 라이브러리':'Media library',
  '업로드된 이미지와 영상 탐색':'Browse uploaded images and videos', '장면 구성과 렌더 설정':'Arrange scenes and configure renders',
  '렌더':'Rendering', '렌더 진행·취소·크레딧 반환':'Progress, cancellation, and credit release',
  '게시·수정':'Publishing & revisions', '게시 상태와 수정 요청':'Publication status and revision requests',
  '워크스페이스 관리':'Workspace admin', '크레딧과 사용량 확인':'Review credits and usage',
  '진행 중인 렌더인지 확인한다':'Check that the render can be cancelled',
  '렌더 제공사에 취소를 요청한다':'Ask the render provider to cancel',
  '렌더를 취소 상태로 저장한다':'Save the cancelled render status', '예약한 크레딧을 반환한다':'Release the reserved credits',
  '렌더 제공사':'Render provider', '게시 제공사':'Publishing provider',
  '렌더 취소와 크레딧 반환 연결':'Connect cancellation and credit release',
  '수정 요청 화면 연결':'Connect the revision request screen', '취소 후 크레딧 반환 확인':'Verify credits after cancellation',
  '렌더 취소와 재시도 경합 처리':'Handle cancellation and retry races',
  '가상 시나리오':'Fictional scenario', '제작 웹':'Studio web', '미디어 · 스토리보드 · 렌더':'Media, storyboards, and rendering',
  '가상 플랫폼의 웹 클라이언트':'Fictional platform web client', '제작 API':'Studio API',
  '렌더 접수 · 크레딧 예약 · 게시':'Render submission, credit reservation, publishing',
  '가상 플랫폼의 API':'Fictional platform API', '렌더 대기열':'Render queue',
  '작업 ID와 재시도 예약':'Job IDs and scheduled retries', '제작 데이터':'Studio data',
  '미디어 · 렌더 · 크레딧 기록':'Media, renders, and credit records', '렌더 작업기':'Render worker',
  '대기열 소비 · 제공사 호출 · 결과 저장':'Consume jobs, call providers, save results',
  '가상 렌더 작업 저장소':'Fictional rendering worker repository',
  '렌더 작업기가 실제로 실행 중인지':'Whether the render worker is running',
  '비동기 영상 렌더와 취소':'Asynchronous video rendering and cancellation', '채널 게시와 상태 조회':'Channel publishing and status',
  '미디어 조회 · 렌더 · 취소':'Media lookup, rendering, cancellation',
  '렌더와 크레딧 읽기·쓰기':'Read and write renders and credits', '렌더 작업 전달':'Enqueue render jobs',
  '대기 작업 소비':'Consume queued jobs', '렌더 결과 저장':'Save render results',
  '영상 렌더':'Render video', '예약한 크레딧으로 영상을 만들고 결과를 저장한다':'Render video using reserved credits and save the result',
  '대기열에 렌더 ID가 도착하면':'When a render ID arrives in the queue'
};
function localized(value, key) {
  if (Array.isArray(value)) return value.map(v => localized(v, key));
  if (value && typeof value === 'object') return Object.fromEntries(Object.entries(value).map(([k,v]) => [k, localized(v,k)]));
  if (typeof value !== 'string' || ['lane','kinds'].includes(key)) return value;
  return english[value] || value;
}
module.exports = fixture;
module.exports.create = lang => {
  const data = lang === 'en' ? localized(fixture) : clone(fixture);
  if (lang === 'en') data.setup = `Connect where-were-we to my agent.\n\n1. Register the MCP server: python3 /demo/where-were-we/mcp_server.py\n2. Before planning, call changes; before editing, call impact.\n3. Show proposed configuration edits and ask permission first.\n\nFictional capture response. The installed app generates actual paths.`;
  return data;
};
