"""Exercise the live preview through the worker with a synthetic Git repository."""
import json
import time
import unittest

from test_analysis_run import AnalysisRun as _Fixture
import analysis_run


class Preview(unittest.TestCase):
    setUp = _Fixture.setUp
    git = _Fixture.git
    raw = _Fixture.raw
    prepare = _Fixture.prepare

    def test_verified_preview_precedes_final_map_and_cancel_preserves_baseline(self):
        # Keep a real route beyond line 500 in an unrecognized file type and use
        # distinct filler lines so that compression of repeated text cannot pass.
        self.git('mv', 'server/items.go', 'server/work.entry')
        self.git('mv', 'pages/items.vue', 'pages/items.screen')
        for path in ('server/work.entry', 'pages/items.screen'):
            source = self.repo / path
            source.write_text(''.join(f'prefix {i}\n' for i in range(501)) + source.read_text())
        (self.repo/'zzz-padding.other').write_text(''.join(f'padding {i}\n' for i in range(10000)))
        self.git('add', '.')
        self.git('commit', '-qm', 'Register custom service')
        baseline = self.raw()
        intent = {'task': 'analysis', 'targets': []}

        for cancel in (True, False):
            run = self.prepare(intent=intent)
            previews = []
            def executor(prompt, **kwargs):
                payload = json.loads(prompt.split('\n', 1)[1])
                preview = analysis_run.status(run_id=run['id']).get('preview')
                if preview:
                    self.assertEqual(preview['commit'], self.git('rev-parse', 'HEAD').strip())
                    self.assertEqual(preview['repository'], 'service')
                    self.assertEqual(self.raw(), baseline)
                    for item in preview['items']:
                        self.assertIn(item['quote'], (self.repo/item['file']).read_text().splitlines()[item['line']-1])
                    previews.extend(preview['items'])
                    if cancel:
                        analysis_run.cancel(run['id'])
                result = {'screens': [], 'backend_routes': [], 'unknown': []}
                for snapshot in payload.get('snapshots', []):
                    for file in snapshot['files']:
                        for line in file['lines']:
                            evidence = dict(file=file['file'], line=line['line'], quote=line['text'])
                            if '<button @click="saveItem">' in line['text']:
                                result['screens'].append(dict(evidence, path='/items'))
                            if line['text'] == 'router.POST("/items", SaveItem)':
                                result['backend_routes'].append(dict(evidence, path='/items', method='POST', function='SaveItem'))
                batch = payload.get('batch')
                return dict(batch=batch['id'], covered=batch['units'], result=result) if batch else result
            done = analysis_run.run(run['id'], executor)
            self.assertTrue(previews, done.get('error'))
            self.assertFalse(done.get('preview'))
            if cancel:
                self.assertEqual(done['state'], 'cancelled', done.get('error'))
                self.assertEqual(self.raw(), baseline)
                overview=analysis_run.status(project='demo',lang='en')['saved_overviews'][0]
                self.assertTrue(overview['items'])
                self.assertTrue(overview['files'])
                self.assertEqual(overview['configuration'],done['pins']['service']['configuration'])
                self.assertEqual(done['completed_tasks'],[])
                retry=analysis_run.retry(done['id'])
                self.assertEqual(analysis_run.status(project='demo',lang='en')['saved_overviews'],[overview])
                analysis_run.cancel(retry['id'])
            else:
                self.assertEqual(done['state'], 'completed', done.get('error'))
                mapped = self.raw()['dev']
                self.assertEqual([s['path'] for s in mapped['screens']], ['/items'])
                self.assertEqual([r['path'] for r in mapped['backend_routes']], ['/items'])

    def test_first_batch_only_sends_source_and_defers_review_metadata(self):
        for i in range(64):
            (self.repo/f'part{i}.odd').write_text(f'ordinary module {i}\n')
        self.git('add', '.')
        self.git('commit', '-qm', 'Large file inventory')
        run = self.prepare(intent={'task': 'analysis', 'targets': []})
        task = run['tasks'][0]
        request = analysis_run._request(run, task)
        known = [[f'id{i}', 'GET', f'/item/{i}', 'example', 'server/items.go', 'basic'] for i in range(600)]
        request.update(mode='review', known=known, recheck=[{'id': 'existing'}])
        complete = analysis_run.ai_extract.analysis_prompt(request['commit'],'en',{},request,overview=True)
        self.assertIn('every recheck id either again or in drop',complete)
        first_id = None
        seen_pages = set()
        extra_read = False
        final_sources = set()
        first_later_batch = None

        def executor(prompt, **kwargs):
            nonlocal first_id, extra_read, first_later_batch
            packet = json.loads(prompt.split('\n', 1)[1])
            batch = packet['batch']
            self.assertIn('The app merges fragments',packet['prompt'])
            self.assertIn('literal single-line quote',packet['prompt'])
            self.assertNotIn('every recheck id either again or in drop',packet['prompt'])
            self.assertNotIn('Read the whole commit',packet['prompt'])
            self.assertIn('Return the batch envelope',prompt.split('\n',1)[0])
            reply = {'batch': batch['id'], 'covered': batch['units'], 'result': {}}
            pages = packet.get('context_pages', [])
            sources = {f['file'] for snap in packet.get('snapshots', []) for f in snap['files']}
            final_sources.update(sources)
            if first_id is None:
                first_id = batch['id']
                self.assertTrue(sources)
                self.assertFalse(pages)
                self.assertNotIn('known', packet)
                self.assertNotIn('recheck', packet)
                self.assertLessEqual(len(batch['units']), 8)
                reply['needs'] = [{'metadata': ['known'], 'start': 5, 'limit': 1}]
            elif batch['id'] == first_id:
                self.assertTrue(any(p['path'] == ['known'] and p['value'] == [known[4]] for p in pages))
                extra_read = True
            else:
                if first_later_batch is None:
                    first_later_batch=batch['id']
                    self.assertTrue(sources, 'Second batch must include remaining source')
                self.assertEqual(packet['recheck'], request['recheck'])
                seen_pages.update(p['path'][1] for p in pages if p['path'][:1] == ['known'])
            return reply

        analysis_run.generate(run, task, request, executor, lambda: False,
                              time.monotonic()+60, lambda: None, {})
        self.assertTrue(extra_read)
        self.assertEqual(seen_pages, set(range(len(known))))
        self.assertEqual(final_sources, set(self.git('ls-files').splitlines()))

    def test_bounded_overview_finishes_and_reuses_a_pinned_sample_without_marking_full_map_complete(self):
        for i in range(68):
            folder=self.repo/f'part{i}'
            folder.mkdir()
            (folder/'module.odd').write_text('command dispatches current input\n'*600)
        self.git('add','.');self.git('commit','-qm','Large independent program inventory')
        baseline=self.raw();packets=[]
        def executor(prompt,**kwargs):
            p=json.loads(prompt.split('\n',1)[1])
            packets.append(p)
            self.assertLessEqual(len(prompt.encode()),analysis_run.MAX_PROMPT_BYTES)
            self.assertEqual(len({f['file'] for f in p['sources']}),4)
            self.assertTrue(all(len(f['lines'])<=24 for f in p['sources']))
            self.assertTrue(all(len(row['text'])<=160 for f in p['sources'] for row in f['lines']))
            return {'items':[{'name':'Dispatch','description':'Dispatches the current input.','ref':p['sources'][0]['lines'][0]['ref']}]}
        intent={'task':'overview','targets':[]}
        run=self.prepare(intent=intent)
        done=analysis_run.run(run['id'],executor)
        self.assertEqual(done['state'],'completed',done.get('error'))
        self.assertEqual(len(packets),1)
        self.assertEqual(self.raw(),baseline)
        group=done['overviews']['service']
        item=group['items'][0]
        self.assertIn(item['quote'],(self.repo/item['file']).read_text().splitlines()[item['line']-1])
        self.assertIn('analysis',[t['task'] for t in analysis_run._plan({**run,'intent':{'task':'all','targets':[]}})['tasks']])
        cached=analysis_run.run(self.prepare(intent=intent)['id'],executor)
        self.assertEqual(cached['state'],'completed',cached.get('error'))
        self.assertEqual(cached['overviews']['service'],group)
        self.assertEqual(len(packets),1)

    def test_overview_prioritizes_imports_and_declarations_over_evenly_sampled_lines(self):
        (self.repo/'entry.py').write_text('from worker import dispatch\n')
        (self.repo/'worker.py').write_text('# background information\n'*73+
                                          'def dispatch():\n    return "completed"\n'+'# another detail\n'*98)
        self.git('add','.');self.git('commit','-qm','Connect a Python entry point')
        run=self.prepare(intent={'task':'overview','targets':[]})
        def executor(prompt,**kwargs):
            packet=json.loads(prompt.split('\n',1)[1])
            sources={source['file']:source['lines'] for source in packet['sources']}
            self.assertTrue(any(row.get('imports')=='worker.py' for row in sources['entry.py']))
            row=next(row for row in sources['worker.py'] if row.get('name')=='dispatch')
            self.assertEqual(row['line'],74)
            return {'items':[{'name':'Dispatch','description':'Defines the dispatch function.','ref':row['ref']}]}
        done=analysis_run.run(run['id'],executor)
        self.assertEqual(done['state'],'completed',done.get('error'))
        item=done['overviews']['service']['items'][0]
        self.assertEqual((item['file'],item['line'],item['quote']),('worker.py',74,'def dispatch():'))

    def test_overview_pairs_two_features_across_client_and_server_in_one_call(self):
        for feature in ('orders','reports'):
            (self.repo/f'{feature}.ts').write_text(
                '// filler\n'*80+f"export function load() {{ return fetch('/{feature}'); }}\n")
            (self.repo/f'{feature}.py').write_text(
                'from fastapi import FastAPI\napp = FastAPI()\n'+
                f'@app.get("/{feature}")\ndef load_{feature}():\n    return []\n')
        (self.repo/'index.py').write_text('from utils import utility\n')
        (self.repo/'utils.py').write_text('def utility(): return True\n')
        self.git('add','.');self.git('commit','-qm','Add two client and server features')
        run=self.prepare(intent={'task':'overview','targets':[]})
        packets=[]
        def executor(prompt,**kwargs):
            packet=json.loads(prompt.split('\n',1)[1]);packets.append(packet)
            rows={row['ref']:(source['file'],row) for source in packet['sources'] for row in source['lines']}
            self.assertEqual({edge['path'] for edge in packet['connections']},{'/orders','/reports'})
            self.assertEqual(len(packet['sources']),4)
            self.assertLessEqual(len(rows),96)
            items=[]
            for edge in packet['connections']:
                feature=edge['path'][1:]
                client,row=rows[edge['client_ref']]
                self.assertEqual((client,row['line']),(feature+'.ts',81))
                self.assertIn('fetch',row['text'])
                server,row=rows[edge['server_ref']]
                self.assertEqual((server,row['line']),(feature+'.py',3))
                self.assertIn('@app.get',row['text'])
                items.append({'name':feature,'description':'Loads '+feature,'ref':edge['server_ref']})
            reports=next(edge for edge in packet['connections'] if edge['path']=='/reports')
            return {'items':items,'feature_groups':[{'name':'Reporting','connection_ids':[reports['id']]}]}
        done=analysis_run.run(run['id'],executor)
        self.assertEqual(done['state'],'completed',done.get('error'))
        self.assertEqual(len(packets),1)
        saved=analysis_run.status(project='demo',lang='en')['saved_overviews'][0]
        self.assertEqual(len(saved['items']),2)
        reports=next(edge for edge in saved['connections'] if edge['path']=='/reports')
        self.assertEqual(saved['feature_groups'],[{'name':'Reporting','connection_ids':[reports['id']]}])
        self.assertEqual({edge['path'] for edge in saved['connections']},{'/orders','/reports'})
        for edge in saved['connections']:
            for side in (edge['client'],edge['server']):
                self.assertIn(side['quote'],(self.repo/side['file']).read_text().splitlines()[side['line']-1])

    def test_one_call_covers_distinct_verified_resources_and_marks_omitted_scopes(self):
        (self.repo/'browser.ts').write_text("""export function listOrders(){return fetch('/orders')}
export function addOrder(){return fetch('/orders',{method:'POST'})}
export function listReports(){return fetch('/reports')}
export function listUsers(){return fetch('/users')}
""")
        (self.repo/'api.py').write_text("""from fastapi import FastAPI
app = FastAPI()
@app.get('/orders')
def orders(): pass
@app.post('/orders')
def add_order(): pass
@app.get('/reports')
def reports(): pass
@app.get('/users')
def users(): pass
""")
        self.git('add','.');self.git('commit','-qm','Register three feature scopes')
        intent={'task':'overview','targets':[]}
        run=self.prepare(intent=intent)
        calls=[]
        def answer(prompt,**kwargs):
            packet=json.loads(prompt.split('\n',1)[1])
            paths={edge['path'] for edge in packet['connections']}
            calls.append(paths)
            self.assertEqual(len(paths),2)
            self.assertLessEqual(len(packet['sources']),4)
            return {'items':[]}
        done=analysis_run.run(run['id'],answer)
        self.assertEqual(done['state'],'completed',done.get('error'))
        saved=done['overviews']['service']
        self.assertEqual(saved['scope_coverage']['total'],3)
        self.assertEqual(calls,[set(saved['scope_coverage']['selected'])])
        self.assertEqual(saved['version'],analysis_run.OVERVIEW_VERSION)
        cached=self.prepare(intent=intent)
        self.assertEqual(analysis_run.run(cached['id'],lambda *a,**k:self.fail('repeated AI'))['state'],'completed')
        for record in (done,analysis_run.read(cached['id'])):
            record['overviews']['service'].pop('version')
            analysis_run.write(record)
        upgrade=self.prepare(intent=intent)
        self.assertEqual([t['task'] for t in upgrade['tasks']],['overview'])

    def test_selected_resource_has_its_own_cache_and_never_replaces_initial_overview(self):
        for resource in ('orders','reports','stock'):
            (self.repo/f'{resource}.ts').write_text(f"export function load(){{return fetch('/{resource}')}}")
            (self.repo/f'{resource}.py').write_text(f"from fastapi import FastAPI\napp=FastAPI()\n@app.get('/{resource}')\ndef load():pass")
        self.git('add','.');self.git('commit','-qm','Add three independent resources')
        def start(path=None):
            targets=[{'repository':'service','target':path}] if path else []
            return self.prepare(intent={'task':'overview','targets':targets})['id']
        def reply(prompt,**kwargs):
            packet=json.loads(prompt.split('\n',1)[1])
            if 'resource' in packet:
                self.assertEqual({e['path'] for e in packet['connections']},{packet['resource']})
                self.assertEqual({f['file'].split('.')[0] for f in packet['sources']},{packet['resource'][1:]})
            return {'items':[]}
        initial=analysis_run.run(start(),reply)['overviews']['service']
        for path in ('/stock','/orders'):
            done=analysis_run.run(start(path),reply)
            self.assertEqual(done['state'],'completed',done.get('error'))
            detail=done['scope_overviews']['service'][path]
            self.assertEqual(detail['resource'],path)
            self.assertEqual(detail['connections'][0]['source_connection']['path'],path)
            reused=analysis_run.run(start(path),lambda *a,**k:self.fail('already saved scoped overview'))
            self.assertEqual(reused['scope_overviews']['service'][path],detail)
        saved=analysis_run.status(project='demo',lang='en')
        self.assertEqual(saved['saved_overviews'],[initial])
        self.assertEqual({v['resource'] for v in saved['saved_scope_overviews']},{'/orders','/stock'})
        failed=analysis_run.run(start('/invented'),lambda *a,**k:self.fail('unknown scope reached AI'))
        self.assertEqual(failed['state'],'failed')
        import structure_index
        def refresh_index():
            repo=analysis_run.store.config('demo')['repositories'][0]
            raw=self.raw()
            commit=self.git('rev-parse','HEAD').strip()
            raw['dev']['structure_index']=structure_index.build(str(self.repo),commit)
            analysis_run.store.publish('demo','service',raw,{'fingerprint':analysis_run.store.fingerprint(repo)})
            return commit
        (self.repo/'docs').mkdir()
        (self.repo/'docs/release.md').write_text('Documentation-only edit')
        self.git('add','.');self.git('commit','-qm','Update documentation')
        self.assertEqual(analysis_run.status(project='demo',lang='en')['saved_scope_overviews'],[])
        current=refresh_index()
        from unittest.mock import patch
        with patch.object(analysis_run,'_git',wraps=analysis_run._git) as git:
            saved=analysis_run.status(project='demo',lang='en')['saved_scope_overviews']
        self.assertEqual(sum('diff-tree' in c.args for c in git.call_args_list),1)
        self.assertEqual({v['resource'] for v in saved},{'/stock','/orders'})
        for v in saved:self.assertEqual((v['commit'],v['generated_commit']),(current,initial['commit']))
        reused=analysis_run.run(start('/stock'),lambda *a,**k:self.fail('documentation-only edit reached AI'))
        self.assertEqual(reused['scope_overviews']['service']['/stock']['commit'],current)
        (self.repo/'stock.py').write_text((self.repo/'stock.py').read_text()+'\n# change outside quoted line')
        self.git('add','.');self.git('commit','-qm','Change a cited file outside its selected lines')
        refresh_index()
        self.assertEqual(analysis_run.status(project='demo',lang='en')['saved_scope_overviews'],[])
        self.assertTrue(analysis_run.read(start('/stock'))['tasks'])


    def test_optional_flow_details_must_have_refs_and_reopen_as_pinned_source(self):
        import structure_index
        (self.repo/'api.js').write_text("export const api={save:()=>fetch('/save')};")
        (self.repo/'App.jsx').write_text("import {api} from './api.js';\nfunction App(){\nfunction submit(){api.save()}\nreturn <form onSubmit={submit}>\n<button type='submit'>Add</button></form>;}")
        (self.repo/'server.js').write_text("import express from 'express';\nconst app=express();\napp.get('/save',()=>null);\napp.listen(3000);")
        self.git('add','.');self.git('commit','-qm','Use a labeled form action')
        pin=self.git('rev-parse','HEAD').strip()
        index=structure_index.build(str(self.repo),pin)
        def invoke(packet):
            edge,=packet['connections']
            detail,=edge['details']
            rows={r['ref']:r for f in packet['sources'] for r in f['lines']}
            self.assertEqual((detail['label'],detail['event']),('Add','onSubmit'))
            self.assertEqual([rows[ref]['line'] for ref in detail['refs']],[4,3,5])
            return {'items':[{'name':'Add','description':'The form calls save','ref':detail['refs'][0]}]}
        result=analysis_run._quick_overview(str(self.repo),{'commit':pin},'en',invoke,None,None,{'structure_index':index})
        detail,=result['connections'][0]['details']
        self.assertEqual([row['file'] for row in detail['evidence']],['App.jsx']*3)
        self.assertIn('Add',detail['evidence'][-1]['quote'])
        self.assertNotIn('refs',detail)
        graph=index['service_flow']['connections'][0]
        graph['data_steps']=[{'operation':'read','model':'Item','file':'server.js','line':3,'evidence':[]},
                             {'operation':'write','model':'Item','file':'server.js','line':99,'evidence':[]}]
        def data_reply(packet):
            details=packet['connections'][0]['details']
            self.assertEqual([(d['model'],d['operation']) for d in details if d['kind']=='data'],[('Item','read')])
            return {'items':[]}
        analysis_run._quick_overview(str(self.repo),{'commit':pin},'en',data_reply,None,None,{'structure_index':index})

    def test_resource_wide_beta_confirms_budget_and_resumes_missing_scopes(self):
        import structure_index
        from unittest.mock import patch
        paths=['/orders','/reports','/users']
        (self.repo/'ui.ts').write_text('\n'.join(f"export function {p[1:]}(){{return fetch('{p}')}}" for p in paths))
        (self.repo/'api.py').write_text('from fastapi import FastAPI\napp=FastAPI()\n'+'\n'.join(f"@app.get('{p}')\ndef {p[1:]}():pass" for p in paths))
        self.git('add','.');self.git('commit','-qm','Register three resources')
        repo=analysis_run.store.config('demo')['repositories'][0];raw=self.raw()
        raw['dev']['structure_index']=structure_index.build(str(self.repo),self.git('rev-parse','HEAD').strip())
        analysis_run.store.publish('demo','service',raw,{'fingerprint':analysis_run.store.fingerprint(repo)})
        intent={'task':'resources','targets':[],'max_calls':3}
        with self.assertRaisesRegex(ValueError,'maximum call count'):self.prepare(intent={**intent,'max_calls':2})
        job=self.prepare(intent=intent)
        self.assertEqual(job['resource_estimate'],{'total':3,'cached':0,'max_calls':3})
        called=[]
        def interrupt(prompt,**kwargs):
            packet=json.loads(prompt.split('\n',1)[1]);called.append(packet['resource'])
            if len(called)==2:raise RuntimeError('simulated provider interruption')
            return {'items':[]}
        failed=analysis_run.run(job['id'],interrupt)
        self.assertEqual(failed['state'],'failed')
        self.assertEqual(set(failed['scope_overviews']['service']),{called[0]})
        retry=analysis_run.retry(job['id'])
        self.assertEqual(retry['resource_estimate'],{'total':3,'cached':1,'max_calls':2})
        pending=[]
        def finish(prompt,**kwargs):
            packet=json.loads(prompt.split('\n',1)[1]);pending.append(packet['resource'])
            self.assertLessEqual(len(packet['sources']),4)
            return {'items':[]}
        with patch.object(analysis_run,'MAX_TASKS',1):
            done=analysis_run.run(retry['id'],finish)
        self.assertEqual(done['state'],'completed',done.get('error'))
        self.assertEqual(set(pending),set(paths)-{called[0]})
        self.assertEqual(set(done['scope_overviews']['service']),set(paths))
        self.assertNotIn('overviews',done)
        cached=self.prepare(intent={**intent,'max_calls':0})
        self.assertEqual(cached['resource_estimate'],{'total':3,'cached':3,'max_calls':0})
        self.assertEqual(analysis_run.run(cached['id'],lambda *a,**k:self.fail('unexpected cached call'))['state'],'completed')
        self.git('commit','--allow-empty','-qm','Change pin')
        with self.assertRaises(analysis_run.RunError):analysis_run.retry(job['id'])

    def test_overview_preserves_conditional_url_match_in_prompt_and_saved_evidence(self):
        (self.repo/'app.js').write_text("import express from 'express';\nconst app=express();\napp.patch('/items/:id',()=>null);\napp.listen(3000);\n")
        (self.repo/'view.js').write_text("function update(id){fetch(`/items/${id}`,{method:'PATCH'})}\n")
        self.git('add','.');self.git('commit','-qm','Add a variable URL request')
        def executor(prompt,**kwargs):
            packet=json.loads(prompt.split('\n',1)[1])
            edge,=packet['connections']
            self.assertEqual(edge['basis'],'path_template')
            self.assertEqual(edge['server_path'],'/items/:id')
            self.assertIn('one path segment',packet['prompt'])
            return {'items':[{'name':'Edit item','description':'May reach the item handler.','ref':edge['client_ref']}],
                    'feature_groups':[{'name':'Item editing','connection_ids':[edge['id']]}]}
        run=self.prepare(intent={'task':'overview','targets':[]})
        done=analysis_run.run(run['id'],executor)
        self.assertEqual(done['state'],'completed',done.get('error'))
        edge,=done['overviews']['service']['connections']
        self.assertEqual(done['overviews']['service']['feature_groups'],[{'name':'Item editing','connection_ids':[edge['id']]}])
        self.assertEqual((edge['basis'],edge['path'],edge['server_path']),('path_template','/items/{id}','/items/:id'))

    def test_feature_groups_only_accept_unique_known_ids_and_bounded_labels(self):
        edges=[{'id':1},{'id':2}]
        group=lambda name,ids:{'name':name,'connection_ids':ids}
        valid=group('Orders',[1])
        for ids in ([1,1],[3],[True],[{}],[],[1,2,3],'1'):
            self.assertEqual(analysis_run._feature_groups([group('Orders',ids)],edges),[])
        for name in ('',' '*4,'long'*31,None):
            self.assertEqual(analysis_run._feature_groups([group(name,[1])],edges),[])
        self.assertEqual(analysis_run._feature_groups([valid,group('Orders',[2])],edges),[valid])
        self.assertEqual(analysis_run._feature_groups([valid,group('Other',[1])],edges),[valid])
        self.assertEqual(analysis_run._feature_groups([valid]*3,edges),[])
        self.assertEqual(analysis_run._feature_groups(None,edges),[])
        self.assertEqual(analysis_run._feature_groups([group('Fulfillment',[1,2])],edges),[group('Fulfillment',[1,2])])

    def test_legacy_overview_uses_current_git_and_config_pins_despite_an_older_basic_map(self):
        name='legacy'
        home=analysis_run.store.home(name)
        home.mkdir()
        snapshot=self.raw()['dev']
        analysis_run.store.atomic(home/'dev.json',snapshot)
        (self.repo/'worker.py').write_text('run_all_tasks()\n')
        self.git('add','.');self.git('commit','-qm','Advance the legacy branch')
        run=analysis_run.prepare(name,lang='en',intent={'task':'overview','targets':[]})
        def fake(prompt,**kwargs):
            ref=json.loads(prompt.split('\n',1)[1])['sources'][0]['lines'][0]['ref']
            return {'items':[{'name':'Worker','description':'Runs tasks','ref':ref}]}
        done=analysis_run.run(run['id'],fake)
        self.assertEqual(done['state'],'completed',done.get('error'))
        group=analysis_run.status(project=name,lang='en')['saved_overviews'][0]
        self.assertNotEqual(group['commit'],snapshot['commit'])
        self.assertEqual(group['commit'],self.git('rev-parse','HEAD').strip())
        self.git('branch','alias')
        analysis_run.store.atomic(home/'dev.json',{**snapshot,'ref':'alias'})
        self.assertEqual(analysis_run.status(project=name,lang='en')['saved_overviews'],[])
        analysis_run.store.atomic(home/'dev.json',snapshot)
        self.git('commit','--allow-empty','-qm','Move selected ref again')
        self.assertEqual(analysis_run.status(project=name,lang='en')['saved_overviews'],[])

    def test_source_units_share_the_queue_with_matching_review_rows(self):
        def page(key,index,data):
            return {'kind':'metadata','id':key+str(index),'value':{'path':[key,index],'value':data}}
        def source(file):
            return {'kind':'source','id':file,'value':{'file':file}}
        known=page('known',0,['id','GET','/path','handle','app','basic'])
        recheck=page('recheck',0,{'id':'other','file':'worker'})
        unmatched=page('known',1,['none','GET','/old','old','deleted','basic'])
        units=[unmatched,known,recheck,source('app'),source('worker'),source('third')]
        ordered=analysis_run._source_first(units)
        self.assertEqual(ordered,[source('app'),known,source('worker'),recheck,source('third'),unmatched])

    def test_web_free_command_with_unknown_extension_has_early_local_evidence(self):
        self.git('rm', '-q', 'pages/items.vue', 'server/items.go')
        source = self.repo/'work'/'app.odd'
        source.parent.mkdir()
        command = 'command sync executes worker'
        source.write_text(command + '\n' + 'x'*995)
        for i in range(64):
            other = self.repo/'rest'/f'part{i}.odd'
            other.parent.mkdir(exist_ok=True)
            other.write_text(f'unrelated module number {i}\n')
        self.git('add', '.')
        self.git('commit', '-qm', 'Command only; unfamiliar file format')
        run = self.prepare(intent={'task': 'analysis', 'targets': []})
        observed = []

        def executor(prompt, **kwargs):
            p = json.loads(prompt.split('\n', 1)[1])
            batch = p['batch']
            preview = (analysis_run.status(run_id=run['id']).get('preview') or {}).get('items', [])
            if preview and not observed:
                observed.extend(preview)
            items = []
            for snapshot in p.get('snapshots', []):
                for file in snapshot['files']:
                    for line in file['lines']:
                        if line['text'] == command:
                            items = [dict(name='Sync', file=file['file'], line=line['line'], quote=command),
                                     dict(name='Unsupported claim', file=file['file'], line=line['line'], quote='wrong evidence')]
            evidence = [{'file': source['file'], 'line': source['line'], 'quote': source['quote']} for source in items[:1]]
            result = {'inspected': evidence, 'unknown': ['No screens or server endpoints established.'] if evidence else []}
            return dict(batch=batch['id'], covered=batch['units'], result=result, preview_programs=items)

        done = analysis_run.run(run['id'], executor)
        self.assertEqual(observed, [dict(name='Sync', file='work/app.odd', line=1, quote=command, kind='program')], done.get('error'))
        self.assertEqual(done['state'], 'completed', done.get('error'))
        self.assertFalse(done.get('preview'))
        self.assertEqual(done['program_observations'], [
            {'repository': 'service', 'commit': self.git('rev-parse', 'HEAD').strip(), 'items': observed}
        ])


# Imported fixture is not itself a test class in this module's discovery.
del _Fixture
