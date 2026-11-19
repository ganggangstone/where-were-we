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
                       base+"app.get('/x/:id',()=>{}); app.listen(30)",
                       base+"app.get('/x',external); app.listen(30)",
                       base+"app.get=custom;app.get('/x',()=>{});app.listen(30)",
                       "function require(x){return fake} "+base+"app.get('/x',()=>{});app.listen(30)"]:
            with self.subTest(source=source):
                self.assertEqual(routes(source),[])
