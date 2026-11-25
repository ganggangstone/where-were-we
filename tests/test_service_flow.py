import ast
import unittest

import service_flow
import structure_index


class ServiceFlow(unittest.TestCase):
    def test_explicit_namespace_child_router_requires_unique_module_below_own_package(self):
        app="""from fastapi import FastAPI
from myapp.routers import (
    items as inventory,
)
app=FastAPI()
app.include_router(inventory.router,prefix='/v1')
"""
        target="""from fastapi import APIRouter
router=APIRouter()
@router.get('/items')
def list_items(): pass
"""
        external={'routers':{},'mounts':[]}
        files={'backend/myapp/__init__.py':'','backend/myapp/main.py':app,'backend/myapp/routers/items.py':target}
        for path, source in files.items():service_flow.python_routes(ast.parse(source),path,external)
        rows=service_flow.mounted_routes(external,[],set(files),set(files))
        self.assertEqual([(r['method'],r['path'],r['server']['function']) for r in rows],[('GET','/v1/items','list_items')])
        self.assertEqual([m['line'] for m in rows[0]['mounts']],[2,3,6])
        for extra in ('backend/myapp/routers/__init__.py','backend/myapp/routers.py','other/myapp/routers/items.py','other/myapp/__init__.py'):
            self.assertEqual(service_flow.mounted_routes(external,[],set(files)|{extra},set(files)),[])
        self.assertEqual(service_flow.mounted_routes(external,[],set(files),set(files)-{'backend/myapp/routers/items.py'}),[])

    def test_backend_only_registrations_keep_handlers_parameters_and_existing_data_evidence(self):
        raw="""from fastapi import FastAPI, APIRouter
app = FastAPI()
other = APIRouter()
@app.get('/items/{item_id}')
def detail(): pass
@app.get('/items')
def list_items(): pass
@other.get('/unmounted')
def hidden(): pass
"""
        routes=service_flow.python_routes(ast.parse(raw),'main.py')
        routes[1]['data_steps']=[{'operation':'read','model':'Item','file':'main.py','line':7}]
        graph=service_flow.connect(routes,[])
        self.assertEqual(graph['connections'],[])
        self.assertEqual(graph['coverage']['routes'],2)
        rows={r['path']:r for r in graph['registered_routes']}
        self.assertEqual(set(rows),{'/items','/items/{item_id}'})
        self.assertEqual(rows['/items/{item_id}']['server'],{'file':'main.py','function':'detail','line':4})
        self.assertEqual(rows['/items']['data_steps'],routes[1]['data_steps'])
        many=[dict(routes[1],path='/items/'+str(i)) for i in range(service_flow.MAX_REGISTERED_ROUTES+1)]
        complete=service_flow.connect(many[:291],[])
        self.assertEqual({r['path'] for r in complete['registered_routes']},{r['path'] for r in many[:291]})
        capped=service_flow.connect(many,[])
        self.assertEqual(len(capped['registered_routes']),service_flow.MAX_REGISTERED_ROUTES)
        self.assertEqual(capped['coverage']['routes'],len(many))

    def test_resource_groups_preserve_each_verified_action_and_keep_nested_paths_distinct(self):
        def route(method,path,**more):
            return {'method':method,'path':path,'server':{'file':'server.js','line':3},**more}
        def request(method,path,**more):
            return {'method':method,'path':path,'client':{'file':'client.js','line':4},**more}
        action={'label':'Save task','event':'onSubmit','file':'Form.tsx','line':9}
        routes=[route('GET','/v1/tasks'),route('POST','/v1/tasks'),route('PATCH','/v1/tasks/:id',express_parameters=True),
                route('GET','/v1/tasks/history'),route('GET','/v2/tasks')]
        requests=[request('GET','/v1/tasks'),request('POST','/v1/tasks',actions=[action]),
                  request('PATCH','/v1/tasks/{id}',basis='path_template'),request('GET','/v1/tasks/history'),
                  request('GET','/v2/tasks'),request('GET','/unmatched')]
        flow=service_flow.connect(routes,requests)
        self.assertEqual(flow['feature_groups'],[{'resource':'/v1/tasks','connection_indexes':[0,1,2]},
                        {'resource':'/v1/tasks/history','connection_indexes':[3]},
                        {'resource':'/v2/tasks','connection_indexes':[4]}])
        self.assertEqual(flow['connections'][1]['actions'],[action])
        self.assertEqual(flow['connections'][2]['basis'],'path_template')
        self.assertEqual(flow['coverage']['unresolved_requests'],1)
        self.assertEqual(service_flow.connect([],requests)['feature_groups'],[])

    def test_mounted_fastapi_and_literal_typescript_fetch_share_evidence(self):
        server = """from fastapi import APIRouter, FastAPI
app = FastAPI()
router = APIRouter(prefix='/shop')
@router.post('/items')
def create_item(): pass
app.include_router(router, prefix='/v1')
"""
        routes = service_flow.python_routes(ast.parse(server), 'api.py')
        source = b"""const fake = "fetch('/shop/items')";
// fetch('/shop/items')
export async function create() {
  return fetch('/v1/shop/items', {method: 'POST'});
}"""
        root = structure_index._parser('typescript').parse(source).root_node
        requests = service_flow.javascript_requests(root, 'client.ts')
        flow = service_flow.connect(routes, requests)
        self.assertEqual(flow['coverage'], {'requests': 1, 'routes': 1, 'unresolved_requests': 0})
        self.assertEqual(flow['connections'], [{'method': 'POST', 'path': '/v1/shop/items',
            'client': {'file': 'client.ts', 'line': 4}, 'server': {'file': 'api.py', 'line': 4, 'function': 'create_item'},
            'mounts': [{'file': 'api.py', 'line': 6}]}])
        self.assertEqual(service_flow.connect(routes * 2, requests)['connections'], [])

    def test_dynamic_unmounted_and_shadowed_calls_are_excluded(self):
        source = """from fastapi import FastAPI, APIRouter
app = FastAPI()
router = APIRouter()
@app.get('/fixed')
def fixed(): pass
@router.get('/hidden')
def hidden(): pass
app.include_router(router, prefix=runtime_prefix)
"""
        self.assertEqual([row['path'] for row in service_flow.python_routes(ast.parse(source), 'api.py')], ['/fixed'])
        for sample in (b"fetch(dynamic)", b"fetch('/x',opts)", b"fetch('/x',{...opts})",
                       b"function go(fetch){fetch('/x')}", b"fetch('//other/x')", b"fetch('/x',{method:compute()})"):
            root = structure_index._parser('javascript').parse(sample).root_node
            self.assertEqual(service_flow.javascript_requests(root, 'ui.js'), [], sample)

    def test_inline_script_and_explicit_import_mount_keep_three_source_sites(self):
        source = b"""<script src="/remote.js">fetch('/external')</script>
<template><script>fetch('/inert')</script></template>
<script>
  fetch('/todos');
</script>"""
        requests = service_flow.html_requests(source, 'index.html', structure_index._parser('javascript').parse)
        self.assertEqual(requests, [{'method':'GET', 'path':'/todos', 'client':{'file':'index.html','line':4}}])
        external = {'mounts':[], 'routers':{}}
        server = "from fastapi import APIRouter\nrouter = APIRouter()\n@router.get('/todos')\ndef todos(): pass"
        app = "from fastapi import FastAPI\nfrom api import router as jobs\napp = FastAPI()\napp.include_router(jobs)"
        for tree, file in [(app, 'main.py'), (server, 'api.py')]:
            self.assertEqual(service_flow.python_routes(ast.parse(tree), file, external), [])
        self.assertEqual(service_flow.mounted_routes(external, []), [])
        routes = service_flow.mounted_routes(external, [{'file':'main.py','line':2,'target':'api.py'}])
        connection = service_flow.connect(routes, requests)['connections'][0]
        self.assertEqual(connection['mounts'], [{'file':'main.py','line':2},{'file':'main.py','line':4}])
        self.assertEqual(connection['server'], {'file':'api.py','line':3,'function':'todos'})

    def test_python_requests_read_only_literal_addresses_and_constant_bases(self):
        source = """import os, requests, subprocess, urllib.request
API = os.getenv("API_URL", "http://127.0.0.1:9000/")
OTHER = compute()
requests.post(API + "/skip")
requests.get(f"{API}/items")
requests.put("http://localhost:8000/items/7")
urllib.request.urlopen(urllib.request.Request(f"{API}/items", data=b"x"))
subprocess.run(["curl", "localhost:8000/audio", "-F", "f=@a"])
requests.get(f"{OTHER}/nope")
requests.get(f"{API}/item{n}")
requests.get(f"{API}/a/{n}/b")
cache.get("/not-an-address")
"""
        rows = service_flow.python_requests(ast.parse(source), 'tool.py')
        self.assertEqual([(r['method'], r['path'], r['client']['line'], r.get('basis')) for r in rows],
                         [('GET', '/items', 5, None), ('PUT', '/items/7', 6, None), ('POST', '/items', 7, None),
                          ('POST', '/audio', 8, None), ('GET', '/a/{param}/b', 11, 'path_template')])

