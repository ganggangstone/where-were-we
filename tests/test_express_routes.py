import support  # blocks real AI CLIs; drops an inherited WHERE_WERE_WE_SETTINGS
import unittest

from express_routes import express_routes
import service_flow
from structure_index import _parser


def routes(source, grammar='javascript'):
    return express_routes(_parser(grammar).parse(source.encode()).root_node,'server.ts')


class ExpressRoutes(unittest.TestCase):
    def test_esm_commonjs_and_typed_listener_match_literal_browser_request(self):
        fetch = _parser('javascript').parse(b"fetch('/items',{method:'POST'})").root_node
        requests = service_flow.javascript_requests(fetch,'client.js')
        imports = [("const api = require('express');",'javascript'),
                   ("import api from 'express';",'javascript'),
                   ("import api, {type Express} from 'express';",'typescript')]
        for declaration, grammar in imports:
            with self.subTest(grammar=grammar, declaration=declaration):
                annotation = ': Express' if grammar == 'typescript' else ''
                server = declaration + f"\nconst app{annotation}=api();\n" + """
function persist(req,res){res.send('ok')}
app.post('/items',persist);
app.get('/state', (req,res)=>res.end());
app.listen(3000);
"""
                flow=service_flow.connect(routes(server,grammar),requests)
                self.assertEqual(flow['coverage'],{'requests':1,'routes':2,'unresolved_requests':0})
                self.assertEqual(flow['connections'][0]['server'],{'file':'server.ts','line':5,'function':'persist'})

    def test_rejects_non_express_unmounted_conditional_dynamic_and_overwritten_routes(self):
        base="const api=require('express'); const app=api(); "
        for source in ["const fake=other(); fake.get('/x',()=>{});fake.listen(30)",
                       base+"app.get('/x',()=>{});",
                       base+"if(active) app.get('/x',()=>{}); app.listen(30)",
                       base+"app.get('/x/:id?',()=>{}); app.listen(30)",
                       base+"app.get('/x',external); app.listen(30)",
                       base+"app.get=custom;app.get('/x',()=>{});app.listen(30)",
                       "function require(x){return fake} "+base+"app.get('/x',()=>{});app.listen(30)"]:
            with self.subTest(source=source):
                self.assertEqual(routes(source),[])


class ExportedAppFactory(unittest.TestCase):
    def test_resolves_a_listened_factory_and_a_module_constant(self):
        import structure_index
        import express_routes as adapter
        from service_flow import javascript_requests, connect
        parse=lambda code:structure_index._parser('javascript').parse(code.encode()).root_node
        def application(body):
            return parse("import create from 'express';\nexport function app() {\n"+body+"\n}")
        body="const server=create(); server.get('/v1/tasks', () => []); return server;"
        launch=parse("import {app} from './api.js';\napp().listen(3000)")
        modules={'api.js':adapter.app_factories(application(body),'api.js'),
                 'index.js':adapter.app_factories(launch,'index.js')}
        edge={'file':'index.js','line':1,'target':'api.js'}
        requests=javascript_requests(parse("const BASE='/v1/tasks';\nfetch(BASE)"),'browser.js')
        routes=adapter.factory_routes(modules,[edge])
        result=connect(routes,requests)['connections']
        self.assertEqual(len(result),1)
        self.assertEqual(result[0]['evidence'],[{'file':'browser.js','line':1}])
        self.assertEqual(result[0]['mounts'][1],{'file':'index.js','line':2})
        self.assertEqual(adapter.factory_routes(modules,[]),[])
        for other in ["if (alternate) return alternate; "+body,"const create=()=>fake; "+body]:
            modules['api.js']=adapter.app_factories(application(other),'api.js')
            self.assertEqual(adapter.factory_routes(modules,[edge]),[])
        self.assertEqual(javascript_requests(parse("const BASE='/v1/tasks'; function go(BASE){fetch(BASE)}"),'browser.js'),[])

    def test_unencoded_parameter_has_only_a_conditional_unique_shape_match(self):
        import structure_index
        import express_routes as adapter
        from service_flow import javascript_requests, connect
        parse=lambda code:structure_index._parser('javascript').parse(code.encode()).root_node
        def routes(patterns):
            code="import express from 'express'; const app=express();\n"
            code+='\n'.join(f"app.patch('{path}', () => null);" for path in patterns)
            return adapter.express_routes(parse(code+'\napp.listen(3000);'),'api.js')
        requests=javascript_requests(parse("const BASE='/items'; fetch(`${BASE}/${itemId}`,{method:'PATCH'})"),'ui.js')
        row,=connect(routes(['/items/:id']),requests)['connections']
        self.assertEqual((row['basis'],row['path'],row['server_path']),('path_template','/items/{itemId}','/items/:id'))
        for overlap in ['/items/:name','/items/current']:
            self.assertEqual(connect(routes(['/items/:id',overlap]),requests)['connections'],[])
        for url in ['`/${unknown}/items`','`/items/${compute()}`','`/items/${id}x`','`/items/${id}?raw`']:
            self.assertEqual(javascript_requests(parse("fetch("+url+")"),'ui.js'),[])
