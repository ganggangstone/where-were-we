import support  # blocks real AI CLIs; drops an inherited WHERE_WERE_WE_SETTINGS
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]


def extract(files, layout=None):
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp) / 'r'
        support.repository(repo, files)
        out = Path(tmp) / 'out' / 'dev.json'
        env = {'PATH': '/usr/bin:/bin', 'HOME': tmp, 'WHERE_WERE_WE_LAYOUT': json.dumps(layout or {})}
        done = subprocess.run([sys.executable, str(HERE / 'extract.py'), str(repo), 'HEAD', str(out)], capture_output=True, text=True, env=env)
        assert done.returncode == 0, done.stderr
        return json.loads(out.read_text())


class RouteFiles(unittest.TestCase):
    def test_routes_defined_outside_app_tsx_and_lazy_pages_are_screens(self):
        m = extract({
            'web/src/shell/Main.tsx': "import { Route, Routes } from 'react-router-dom'\nimport Home from '../pages/Home'\nimport { phoneRoutes } from '../PhoneRoutes'\n"
                                      "const Orders = lazyPage(() => import('../pages/Orders'))\n"
                                      "export default () => <Routes><Route path=\"/\" element={<Guard><Home /></Guard>} />\n<Route\n  path=\"/orders/:id\"\n  element={<Orders />}\n/>{phoneRoutes()}</Routes>\n",
            'web/src/PhoneRoutes.tsx': "import { Navigate, Route } from 'react-router-dom'\nimport Phone from './pages/Phone'\n"
                                       "export const phoneRoutes = () => <><Route path=\"/p\" element={<Navigate to=\"/p/home\" />} /><Route path=\"/p/home\" element={<Phone />} /></>\n",
            'web/src/pages/Home.tsx': "export default function Home(){ return <h1>Home</h1> }\n",
            'web/src/pages/Orders.tsx': "export default function Orders(){ return <h1>Orders</h1> }\n",
            'web/src/pages/Phone.tsx': "export default function Phone(){ return <h1>Phone</h1> }\n",
            'web/src/pages/Icon.tsx': "import { Route } from 'icons'\nexport const I = () => <Route size={3} />\n",
            'web/tests/fixture.tsx': "<Route path=\"/test-only\" element={<X />} />\n",
        })
        got = {s['path']: (s['file'], s['redirect']) for s in m['screens']}
        self.assertEqual(got, {'/': ('web/src/pages/Home.tsx', False), '/orders/:id': ('web/src/pages/Orders.tsx', False),
                               '/p': (None, True), '/p/home': ('web/src/pages/Phone.tsx', False)})
        self.assertEqual(next(s for s in m['screens'] if s['path'] == '/')['heading'], 'Home')
        self.assertTrue(m['coverage']['frontend'])

    def test_named_handler_reads_the_arrow_definition_before_a_function_of_the_same_name(self):
        m = extract({
            'web/src/App.tsx': "import { Route, Routes } from 'react-router-dom'\nimport Page from './Page'\nexport default () => <Routes><Route path=\"/\" element={<Page />} /></Routes>\n",
            'web/src/Page.tsx': "import { useNavigate } from 'react-router-dom'\nexport default function Page(){ const navigate = useNavigate()\n"
                                "function open() { return 1 }\nconst open = () => navigate('/orders')\nreturn <button onClick={open}>Open orders</button> }\n",
        })
        action = next(a for s in m['screens'] for a in s.get('actions', []) if a.get('label') == 'Open orders')
        self.assertEqual(action['kind'], 'nav')
    def test_button_labels_are_screen_text_never_code_expressions(self):
        m = extract({
            'web/src/App.tsx': "import { Route, Routes } from 'react-router-dom'\nimport Page from './Page'\nexport default () => <Routes><Route path=\"/\" element={<Page />} /></Routes>\n",
            'web/src/Page.tsx': "export default function Page(){ return <div>\n"
                                "<button title={on ? 'Stop' : 'Start'} onClick={() => go()}><Icon /></button>\n"
                                "<button onClick={() => go()}><b>{n}</b>: <i>{k}</i></button>\n"
                                "<button onClick={() => go()}>Filter {n > 0 && (<b>{n}</b>)}</button>\n"
                                "<button title=\"Save draft\" onClick={() => go()}><Icon /></button>\n</div> }\n",
        })
        labels = [a['label'] for s in m['screens'] for a in s['actions']]
        self.assertEqual(labels, ['', '', 'Filter', 'Save draft'])

    def test_buttons_named_in_comments_are_not_actions_and_entities_are_decoded(self):
        m = extract({
            'web/src/App.tsx': "import { Route, Routes } from 'react-router-dom'\nimport Page from './Page'\nexport default () => <Routes><Route path=\"/\" element={<Page />} /></Routes>\n",
            'web/src/Page.tsx': "// The tile is a <button> so siblings hold the menu.\nimport x from './x'\n"
                                "export default function Page(){ return <div>\n"
                                "{/* a <button> cannot nest */}\n"
                                "<button onClick={() => go()}>R&amp;D room</button>\n</div> }\n",
        })
        self.assertEqual([a['label'] for s in m['screens'] for a in s['actions']], ['R&D room'])

    def test_route_objects_vue_router_and_next_pages(self):
        m = extract({
            'client/src/router.js': "import { createRouter } from 'vue-router'\nimport Cart from '@/views/Cart.vue'\n"
                                    "export default createRouter({ routes: [ { path: '/cart', component: Cart },\n { path: '/shop', component: () => import('./views/Shop.vue') } ] })\n",
            'client/src/views/Cart.vue': "<template><h1>Cart</h1></template>\n",
            'client/src/views/Shop.vue': "<template><h1>Shop</h1></template>\n",
            'site/package.json': '{"dependencies": {"next": "14.0.0"}}\n',
            'site/app/(shop)/items/[id]/page.tsx': "export default function P(){ return null }\n",
            'site/pages/about.tsx': "export default function A(){ return null }\n",
            'site/pages/api/ping.ts': "export default function h(){}\n",
            'site/pages/_app.tsx': "export default function App(){}\n",
            'other/pages/Plain.tsx': "export default function NotARoute(){}\n",
        })
        got = {s['path']: s['file'] for s in m['screens']}
        self.assertEqual(got, {'/cart': 'client/src/views/Cart.vue', '/shop': 'client/src/views/Shop.vue',
                               '/items/:id': 'site/app/(shop)/items/[id]/page.tsx', '/about': 'site/pages/about.tsx'})

    def test_fastapi_app_found_wherever_it_lives(self):
        m = extract({
            'services/api/server.py': "from fastapi import FastAPI\nfrom .http.users import router as users_router\nfrom .http import items\napp = FastAPI()\n"
                                      "app.include_router(users_router, prefix='/users')\napp.include_router(items.router)\n",
            'services/api/http/users.py': "from fastapi import APIRouter\nrouter = APIRouter()\n@router.get('/{uid}')\ndef read_user(uid: int):\n    return {}\n",
            'services/api/http/items.py': "from fastapi import APIRouter\nrouter = APIRouter(prefix='/items')\n@router.post('')\ndef add_item(name: str):\n    return {}\n",
            'services/api/db/tables.py': "class Item(Base):\n    __tablename__ = 'items'\n",
        })
        got = {(r['method'], r['path'], r['mounted']) for r in m['backend_routes']}
        self.assertEqual(got, {('GET', '/users/{}', True), ('POST', '/items', True)})
        self.assertEqual(m['models'], {'Item': 'items'})
        self.assertTrue(m['coverage']['backend'])


if __name__ == '__main__':
    unittest.main()


class Decoding(unittest.TestCase):
    def test_a_crlf_file_reads_the_same_whether_or_not_it_was_preloaded(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / 'r'; (repo / 'web/src').mkdir(parents=True)
            (repo / 'web/src/App.tsx').write_bytes(b"export const a = () => api.get('/x')\r\nconst b = 1\rconst c = '\xff'\r\n")
            git = lambda *a: subprocess.run(['git', '-C', str(repo), *a], check=True, capture_output=True)
            git('init', '-q'); git('add', '.'); git('-c', 'user.name=t', '-c', 'user.email=t@example.invalid', 'commit', '-qm', 'x')
            probe = ("import runpy,sys,json;sys.argv=['extract.py',sys.argv[1],'HEAD',sys.argv[2]];g=runpy.run_path(sys.argv[0],run_name='x');"
                     "f='web/src/App.tsx';g['_cache'].clear();shown=g['show'](f);g['_cache'].clear();g['preload']([f]);print(json.dumps([shown,g['show'](f)]))")
            done = subprocess.run([sys.executable, '-c', probe, str(repo), str(Path(tmp) / 'out.json')], capture_output=True, text=True, cwd=HERE,
                                  env={'PATH': '/usr/bin:/bin', 'HOME': tmp})
            self.assertEqual(done.returncode, 0, done.stderr)
            shown, preloaded = json.loads(done.stdout.splitlines()[-1])
            self.assertEqual(shown, preloaded); self.assertNotIn('\r', shown)
