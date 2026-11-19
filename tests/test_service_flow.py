import ast
import unittest

import service_flow
import structure_index


class ServiceFlow(unittest.TestCase):
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
