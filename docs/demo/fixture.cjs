// Entirely fictional input for the existing UI. No repository or API is consulted.
const clone = value => JSON.parse(JSON.stringify(value));
const project = 'Cedar Shop · 가상 데이터';
const at = '2026-06-08T21:00:00+09:00';
const since = '2026-06-08T20:00:00+09:00';
const routes = [];
const api = [];
const requestNames = {};
function request(name, title, method, path, tables, external = []) {
  const file = `backend/app/routers/${tables[0]}.py`;
  const line = 20 + routes.length * 15;
  const route = { file, line, function: name, method, path, tables,
    externals: external, mounted: true, inputs: method === 'GET' ? [] : ['order_id: str'],
    services: [], tests: name === 'create_return' ? [] : [`backend/tests/test_${tables[0]}.py`] };
  routes.push(route);
  api.push({ name, file: `frontend/src/api/${tables[0]}.ts`, calls: [
    { method, path, line: 12, backend: [{ file, line }] }
  ] });
  requestNames[`${file}::${name}`] = title;
  return name;
}
request('list_products', '상품 목록 읽기', 'GET', '/products', ['products']);
request('read_product', '상품 상세 읽기', 'GET', '/products/{id}', ['products', 'inventory']);
request('read_cart', '장바구니 읽기', 'GET', '/cart', ['cart_items', 'products']);
request('add_to_cart', '장바구니에 담기', 'POST', '/cart/items', ['cart_items']);
request('create_order', '주문하기', 'POST', '/orders', ['orders', 'inventory', 'cart_items'], ['결제 서비스']);
request('list_orders', '주문 목록 읽기', 'GET', '/orders', ['orders']);
request('read_order', '주문 상세 읽기', 'GET', '/orders/{id}', ['orders', 'order_items']);
request('cancel_order', '주문 취소', 'POST', '/orders/{id}/cancel', ['orders', 'inventory'], ['결제 서비스']);
request('read_shipment', '배송 상태 읽기', 'GET', '/shipments/{id}', ['shipments', 'orders'], ['택배 서비스']);
request('create_return', '반품 신청', 'POST', '/returns', ['returns', 'orders']);
request('manage_stock', '재고 수정', 'PATCH', '/inventory/{id}', ['inventory']);
request('sales_report', '매출 읽기', 'GET', '/reports/sales', ['orders']);
function screen(path, heading, functions, nav = []) {
  const file = `frontend/src/pages/${heading.replaceAll(' ', '')}.tsx`;
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
  screen('/products', '상품 목록', ['list_products'], [['상품 보기', '/products/:id']]),
  screen('/products/:id', '상품 상세', ['read_product', 'add_to_cart'], [['장바구니 보기', '/cart']]),
  screen('/cart', '장바구니', ['read_cart'], [['주문서 작성', '/checkout']]),
  screen('/checkout', '주문서', ['create_order'], [['주문 확인', '/orders/:id']]),
  screen('/orders', '내 주문', ['list_orders'], [['주문 상세', '/orders/:id']]),
  screen('/orders/:id', '주문 상세', ['read_order', 'cancel_order'], [['배송 조회', '/shipments/:id'], ['반품 신청', '/returns/new']]),
  screen('/shipments/:id', '배송 조회', ['read_shipment'], [['주문으로', '/orders/:id']]),
  screen('/returns/new', '반품 신청', ['create_return'], [['내 주문으로', '/orders']]),
  screen('/admin/inventory', '재고 관리', ['manage_stock'], [['매출 보기', '/admin/reports']]),
  screen('/admin/reports', '매출 현황', ['sales_report'])
];
const dev = { repo: '/demo/cedar-shop', ref: 'origin/dev', commit: 'demo0002',
  screens, api_functions: api, backend_routes: routes,
  backend_routes_without_screen: [], unresolved_calls: [],
  models: Object.fromEntries([...new Set(routes.flatMap(r => r.tables))].map(t => [t, t])) };
const main = clone(dev);
main.ref = 'origin/main'; main.commit = 'demo0001';
main.screens = main.screens.filter(s => s.path !== '/returns/new');
main.backend_routes = main.backend_routes.filter(r => !['create_return', 'cancel_order'].includes(r.function));
main.screens.forEach(s => {
  s.api_functions = s.api_functions.filter(a => a.name !== 'cancel_order');
  s.actions = s.actions.filter(a => !(a.targets || []).some(t => t.to === '/returns/new') && !(a.api_functions || []).includes('cancel_order'));
});
const groups = { names: {}, request_names: requestNames, groups: [
  { name: '상품 탐색', description: '상품을 찾고 자세히 보기', screens: ['/products', '/products/:id'] },
  { name: '장바구니', description: '담은 상품 확인과 주문서 작성', screens: ['/cart', '/checkout'] },
  { name: '주문', description: '주문 내역 확인과 취소', screens: ['/orders', '/orders/:id'] },
  { name: '배송·반품', description: '배송 조회와 반품 신청', screens: ['/shipments/:id', '/returns/new'] },
  { name: '상점 관리', description: '재고와 매출 확인', screens: ['/admin/inventory', '/admin/reports'] }
] };
const cancel = routes.find(r => r.function === 'cancel_order');
const flows = { routes: Object.fromEntries(routes.map(r => [r.file + '::' + r.function, {
  name: requestNames[r.file + '::' + r.function],
  steps: r.function === 'cancel_order' ? [
    { lane: '서버', text: '취소할 수 있는 주문인지 확인한다', line: cancel.line + 1, quote: 'ensure_cancellable(order)' },
    { lane: '외부', text: '결제 서비스에 환불을 요청한다', line: cancel.line + 3, quote: 'payments.refund(order.payment_id)' },
    { lane: '저장소', text: '주문을 취소 상태로 저장한다', line: cancel.line + 5, quote: "order.status = 'cancelled'" },
    { lane: '저장소', text: '주문한 수량만큼 재고를 되돌린다', line: cancel.line + 6, quote: 'inventory.restore(order.items)' }
  ] : [{ lane: '서버', text: requestNames[r.file + '::' + r.function], line: r.line + 1, quote: `${r.function}()` }]
}])) };
const url = n => `https://example.invalid/cedar-shop/pull/${n}`;
const merged = { number: 42, title: '주문 취소와 재고 복구 연결', author: 'demo-agent',
  url: url(42), screens: ['/orders/:id', '/admin/inventory'],
  files: ['backend/app/routers/orders.py', 'backend/app/routers/inventory.py', 'frontend/src/pages/주문상세.tsx'], merged_at: at };
const status = {
  open_prs: [{ number: 43, title: '반품 신청 화면 연결', author: 'demo-agent', url: url(43),
    screens: ['/returns/new', '/orders/:id'], files: ['backend/app/routers/returns.py'], updated_at: since }],
  merged_prs: [merged], branches: [], worktrees: [],
  issues: [{ number: 18, title: '취소 후 재고 복구 확인', url: 'https://example.invalid/cedar-shop/issues/18',
    screens: ['/orders/:id'], via: 'pr', hits: ['#42'] }]
};
const node = (id, name, what, kind, extra = {}) => ({ id, name, what, kind, uses: [], ev: [], unknown: [], ...extra });
const system = { written: '가상 시나리오', checked: 'demo0002', nodes: [
  node('web', '상점 웹', '상품 탐색 · 장바구니 · 주문', 'program', { origin: 'repo', origin_text: '가상 상점의 프런트엔드', code: ['frontend'], detail: 'map' }),
  node('backend', '상점 API', '주문 · 재고 · 배송 요청 처리', 'program', { origin: 'repo', origin_text: '가상 상점의 서버', code: ['backend'], uses: ['payments'], detail: 'map' }),
  node('db', '상점 데이터', '주문 · 상품 · 재고 · 배송 기록', 'store'),
  node('shipping', '배송 작업기', '새 주문의 배송 접수와 상태 갱신', 'program', { origin: 'other', origin_text: '가상 배송 작업 저장소', code: ['worker'], uses: ['courier'], tables: ['shipments'], unknown: [{ needs: 'ops', text: '배송 작업기가 실제로 실행 중인지' }] })
], externals: [{ id: 'payments', name: '결제 서비스', what: '결제 승인과 취소' }, { id: 'courier', name: '택배 서비스', what: '배송 접수와 상태 조회' }],
  unknown: [], others: [], links: [
    { from: 'web', to: 'backend', label: '상품 조회 · 주문 · 취소', sure: 'code' },
    { from: 'backend', to: 'db', label: '주문과 재고 읽기·쓰기', sure: 'code' },
    { from: 'backend', to: 'shipping', label: '배송 접수 요청', sure: 'code' },
    { from: 'shipping', to: 'db', label: '배송 상태 저장', sure: 'code' }
] };
const delta = { from: 'demo0001', to: 'demo0002',
  screens_added: [{ path: '/returns/new', name: '반품 신청', group: '배송·반품' }], screens_removed: [],
  requests_added: [{ screen: '/orders/:id', screen_name: '주문 상세', name: '주문 취소', what: 'POST /orders/{id}/cancel' },
    { screen: '/returns/new', screen_name: '반품 신청', name: '반품 신청', what: 'POST /returns' }],
  requests_removed: [], flows_added: [
    { from: '/orders/:id', from_name: '주문 상세', to: '/returns/new', to_name: '반품 신청', label: '반품 신청' },
    { from: '/returns/new', from_name: '반품 신청', to: '/orders', to_name: '내 주문', label: '내 주문으로' }
  ],
  flows_removed: [], routes_added_no_screen: [] };
const changes = { last_refresh: at, entries: [{ at, since, branches: { dev: delta },
  ai_stale: {}, prs: [{ ...merged, files: merged.files.length,
    groups: groups.groups.filter(g => g.screens.some(p => merged.screens.includes(p))).map(g => g.name),
    programs: [], kinds: ['기능', '구조'], base: 'dev', issues: [18] }] }] };
const setup = `where-were-we를 내 에이전트에 연결해 주세요.\n\n1. 아래 MCP 서버를 등록해 주세요.\n   python3 /demo/where-were-we/mcp_server.py\n2. 계획 전에 changes로 바뀐 것을, 수정 전에 impact로 닿는 곳을 확인하도록 지침을 추가해 주세요.\n3. 설정 파일을 바꾸기 전에 허락을 구해 주세요.\n\n※ 촬영용 가상 응답입니다. 실제 경로와 설정은 앱의 에이전트 연결에서 생성합니다.`;
module.exports = { project, now: Date.parse(at), setup, maps: { dev, main, status, groups, flows, system,
  jobs: { nodes: {} }, changes, 'dev.prev': main, 'main.prev': main } };
