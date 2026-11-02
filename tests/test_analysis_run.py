"""App worker lifecycle with synthetic Git and injected executors; no real AI calls."""
import copy
import json
import os
from pathlib import Path
import sys
import time
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parent))
import analysis_run
import ai_extract
import briefing
import project
import test_ai_extract

class AnalysisRun(unittest.TestCase):
    setUp=test_ai_extract.Analysis.setUp
    git=test_ai_extract.Analysis.git
    EV={'file':'server/items.go','line':2,'quote':'db.Table("items").Create(item)'}
    SYSTEM={'nodes':[{'id':'api','name':'API','kind':'program','code':['server'],'ev':[EV],'jobs':[]}],
            'links':[],'externals':[],'others':[],'unknown':[]}
    GROUPS={'groups':[{'name':'Items','screens':['/items']}],'names':{},'request_names':{}}

    def prepare(self,**kwargs):return analysis_run.prepare('demo',lang='en',**kwargs)
    def raw(self):return project.raw_bundle(project.repository_folder('demo',project.config('demo')['repositories'][0],project.states('demo')))
    def fake(self,prompt,*,cancelled,timeout):
        self.assertFalse(cancelled());self.assertLessEqual(timeout,analysis_run.TASK_SECONDS)
        self.assertNotIn('record_arguments',prompt);self.assertNotIn(str(self.repo),prompt)
        payload=json.loads(prompt.split('\n',1)[1]);schema=payload['schema']
        if 'screens' in schema:
            request={'mode':payload['mode'],'inspect':payload.get('inspect',[]),'recheck':payload.get('recheck',[])}
            return json.dumps(test_ai_extract.agent_answer(request,self.data))
        if 'nodes' in schema:return json.dumps(self.SYSTEM)
        if 'groups' in schema:return json.dumps(self.GROUPS)
        if 'routes' in schema:return json.dumps({'routes':{k:{'steps':[],'unknown':'No further steps established'} for k in payload['input']['routes']}})
        self.fail('Unexpected task schema')

    def test_app_overview_excludes_embedded_details_and_reuses_map(self):
        calls=[]
        def fake(prompt,**kwargs):
            p=json.loads(prompt.split('\n',1)[1]);calls.append(p)
            if 'screens' in p['schema']:
                self.assertNotIn('steps',p['schema']['backend_routes'][0])
                self.assertNotIn('and request steps',p['prompt'])
                result=copy.deepcopy(self.data)
                for route in result['backend_routes']:route.pop('steps',None)
                return result
            if 'nodes' in p['schema']:
                self.assertNotIn('jobs',p['schema']['nodes'][0])
                self.assertFalse([f for snapshot in p.get('snapshots',[]) for f in snapshot['files']])
                self.assertTrue(p['input']['map']['backend_routes'])
                result=copy.deepcopy(self.SYSTEM)
                for node in result['nodes']:node.pop('jobs',None)
                return result
            return self.fake(prompt,**kwargs)
        done=analysis_run.run(self.prepare()['id'],fake)
        self.assertEqual(done['state'],'completed',done.get('error'))
        self.assertEqual([t['task'] for t in done['completed_tasks']],['analysis','system','groups'])
        self.assertFalse((self.raw()['dev'].get('task_outputs',{}).get('flows') or {}).get('routes'))
        self.assertFalse((self.raw()['dev'].get('task_outputs',{}).get('jobs') or {}).get('nodes'))
        again=analysis_run.run(self.prepare()['id'],lambda *a,**k:self.fail('unchanged overview'))
        self.assertEqual(again['state'],'completed')

    def test_explicit_steps_target_only_and_retry_keeps_intent(self):
        (self.repo/'server/other.go').write_text('func Other() {}\nrouter.GET("/other", Other)\n')
        self.git('add','.');self.git('commit','-qm','Independent second endpoint')
        self.data['backend_routes'].append({'file':'server/other.go','line':2,'quote':'router.GET("/other", Other)',
            'method':'GET','path':'/other','function':'Other'})
        done=analysis_run.run(self.prepare()['id'],self.fake)
        self.assertEqual(done['state'],'completed',done.get('error'))
        intent={'task':'steps','targets':[{'repository':'service','target':'@routes:["server/items.go::SaveItem"]'}]}
        value=self.prepare(intent=intent)
        self.assertEqual([t['task'] for t in value['tasks']],['steps'])
        def bad(prompt,**kwargs):return {'routes':{'not/requested':{'steps':[],'unknown':'unknown'}}}
        before=self.raw();failed=analysis_run.run(value['id'],bad)
        self.assertEqual(failed['state'],'failed');self.assertEqual(self.raw(),before)
        again=analysis_run.retry(value['id']);self.assertEqual(again['intent'],intent)
        calls=[]
        def fake(prompt,**kwargs):
            p=json.loads(prompt.split('\n',1)[1]);calls.append(p)
            self.assertEqual(set(p['input']['routes']),{'server/items.go::SaveItem'})
            self.assertEqual({f['file'] for ss in p['snapshots'] for f in ss['files']},{'server/items.go'})
            return self.fake(prompt,**kwargs)
        done=analysis_run.run(again['id'],fake)
        self.assertEqual(done['state'],'completed',done.get('error'));self.assertEqual(len(calls),1)

    def test_cold_detail_runs_only_map_prerequisite_and_chosen_routes(self):
        intent={'task':'steps','targets':[{'repository':'service','target':'@routes:["server/items.go::SaveItem"]'}]}
        value=self.prepare(intent=intent)
        self.assertEqual([t['task'] for t in value['tasks']],['analysis'])
        done=analysis_run.run(value['id'],self.fake)
        self.assertEqual(done['state'],'completed',done.get('error'))
        self.assertEqual([t['task'] for t in done['completed_tasks']],['analysis','steps'])
        self.assertFalse(self.raw()['dev']['task_outputs'].get('system'))

    def test_cli_prepare_preserves_selected_intent_and_overview_keeps_proven_details(self):
        import subprocess
        done=analysis_run.run(self.prepare()['id'],self.fake)
        self.assertEqual(done['state'],'completed',done.get('error'))
        intent={'task':'steps','targets':[{'repository':'service','target':'/items'}]}
        argv=[sys.executable,'-B',str(Path(analysis_run.__file__)),'prepare','demo','--lang','en','--intent',json.dumps(intent)]
        result=subprocess.run(argv,env={**os.environ,'WHERE_WERE_WE_ROOT':str(self.home)},text=True,capture_output=True,check=True)
        value=json.loads(result.stdout);self.assertEqual(value['intent'],intent)
        done=analysis_run.run(value['id'],self.fake);self.assertEqual(done['state'],'completed',done.get('error'))
        flow=copy.deepcopy(self.raw()['dev']['task_outputs']['flows']['routes']['server/items.go::SaveItem'])
        (self.repo/'independent.txt').write_text('An independent file without route dependencies.\n')
        self.git('add','.');self.git('commit','-qm','Independent text change')
        done=analysis_run.run(self.prepare()['id'],self.fake)
        self.assertEqual(done['state'],'completed',done.get('error'))
        carried=self.raw()['dev']['task_outputs']['flows']['routes']['server/items.go::SaveItem']
        self.assertEqual(carried['steps'],flow['steps'])
        self.assertEqual(carried['verified_commit'],flow['commit'])
        self.assertEqual(carried['carried_from'],flow['commit'])
        self.assertFalse((self.raw()['dev'].get('task_outputs',{}).get('jobs') or {}).get('nodes'))

    def test_sequential_worker_finishes_map_system_and_groups_without_collecting(self):
        raw=self.raw();raw['changes']={'last_refresh':'fixed','last_result':{'since':'fixed'}}
        project._publish('demo','service',raw,{},collection=False)
        baseline=self.raw()['changes'];before_state=project.states('demo')['service'].get('last_success')
        value=self.prepare();self.assertEqual(value['state'],'preparing')
        done=analysis_run.run(value['id'],self.fake)
        self.assertEqual(done['state'],'completed',done.get('error'))
        self.assertEqual([t['task'] for t in done['completed_tasks']],['analysis','system','groups'])
        self.assertEqual(done['pins'],value['pins'])
        self.assertEqual(self.raw()['changes'],baseline)
        self.assertEqual(project.states('demo')['service'].get('last_success'),before_state)
        self.assertEqual(ai_extract.plan('demo',lang='en',overview=True)['tasks'],[])
        self.assertFalse((self.raw()['dev'].get('task_outputs',{}).get('flows') or {}).get('routes'))
        self.assertFalse((self.raw()['dev'].get('task_outputs',{}).get('jobs') or {}).get('nodes'))
        again=self.prepare()
        done=analysis_run.run(again['id'],lambda *a,**k:self.fail('Current analysis must not call a model'))
        self.assertEqual(done['state'],'completed')

    def test_large_first_unknown_stack_is_split_and_saved_as_one_map(self):
        # The deterministic collector does not understand this syntax. Registration,
        # handler and service are deliberately in different files and source units.
        for file in ('pages/items.vue','server/items.go'):
            self.git('rm','-q',file)
        sources={
            'web.screen':'screen /items calls POST /v1/items\n',
            'api.mount':'mount POST /v1/items => SaveItem\n',
            'handler.source':'function SaveItem uses StoreItems\n',
            'store.source':'function StoreItems persists items\n',
        }
        for file,text in sources.items():(self.repo/file).write_text(text)
        for i in range(6):(self.repo/f'padding{i}.source').write_text('ordinary unrelated source line\n'*9000)
        self.git('add','.');self.git('commit','-qm','Unknown stack larger than one input')
        value=self.prepare();self.assertEqual(value['tasks'][0]['mode'],'full')
        calls=[];coverage=set();map_saves=[]
        real_record=ai_extract.record
        def save(**kwargs):
            map_saves.append(kwargs);return real_record(**kwargs)
        def executor(prompt,**kwargs):
            calls.append(len(prompt.encode()));self.assertLessEqual(calls[-1],128*1024)
            p=json.loads(prompt.split('\n',1)[1]);schema=p['schema']
            if 'screens' not in schema:
                result=({'nodes':[{'id':'api','name':'API','kind':'program','code':['.'],
                    'ev':[{'file':'api.mount','line':1,'quote':'mount POST /v1/items'}],'jobs':[]}],
                    'links':[],'externals':[],'others':[],'unknown':[]} if 'nodes' in schema else self.GROUPS)
            else:
                files={f['file']:f for s in p.get('snapshots',[]) for f in s['files']}
                result={'screens':[],'backend_routes':[],'inspected':[],'unknown':[]}
                if 'web.screen' in files:
                    result['screens']=[{'path':'/items','file':'web.screen','line':1,'quote':'screen /items',
                        'calls':[{'file':'web.screen','line':1,'quote':'calls POST /v1/items','method':'POST','path':'/v1/items'}]}]
                if 'api.mount' in files:
                    missing=[f for f in ('handler.source','store.source') if f not in files]
                    if missing:
                        return {'batch':p['batch']['id'],'covered':p['batch']['units'],'result':result,
                                'needs':[{'file':f,'start':1,'limit':10} for f in missing]}
                    result['backend_routes']=[{'file':'api.mount','line':1,'quote':'mount POST /v1/items',
                        'method':'POST','path':'/v1/items','function':'SaveItem',
                        'dependencies':[{'file':'handler.source','line':1,'quote':'function SaveItem uses StoreItems'}],
                        'services':[{'file':'store.source','line':1,'quote':'function StoreItems persists items'}],
                        'steps':[{'file':'store.source','line':1,'quote':'function StoreItems persists items','text':'Store items','lane':'저장소'}]}]
            if 'batch' in p:
                coverage.update(p['batch']['units'])
                return {'batch':p['batch']['id'],'covered':p['batch']['units'],'result':result}
            return result
        with patch.object(ai_extract,'record',side_effect=save):done=analysis_run.run(value['id'],executor)
        self.assertEqual(done['state'],'completed',done.get('error'))
        m=self.raw()['dev'];self.assertEqual([s['path'] for s in m['screens']],['/items'])
        self.assertEqual([(r['method'],r['path'],r['function']) for r in m['backend_routes']],[('POST','/v1/items','SaveItem')])
        self.assertEqual(m['api_functions'][0]['calls'][0]['backend'][0]['function'],'SaveItem')
        self.assertEqual(m['backend_routes'][0]['services'],['store.source'])
        self.assertGreater(len(coverage),6);self.assertEqual(len(map_saves),1)
        self.assertGreater(len(calls),3)
        self.input_metrics={'calls':len(calls),'bytes':sum(calls),'maximum':max(calls)}

    def test_small_patch_excludes_unrelated_source_and_unchanged_run_calls_nothing(self):
        (self.repo/'unrelated.source').write_text('UNRELATED_CONTENT_MUST_NOT_BE_RESENT\n')
        self.git('add','.');self.git('commit','-qm','Independent source')
        done=analysis_run.run(self.prepare()['id'],self.fake)
        self.assertEqual(done['state'],'completed',done.get('error'))
        done=analysis_run.run(self.prepare()['id'],lambda *a,**k:self.fail('Unchanged source must make zero calls'))
        self.assertEqual(done['state'],'completed')
        before=copy.deepcopy(self.raw()['dev'])
        f=self.repo/'server/items.go';f.write_text(f.read_text()+'// changed independently\n')
        self.git('add','.');self.git('commit','-qm','Independent handler change')
        prompts=[]
        def executor(prompt,**kwargs):
            self.assertNotIn('UNRELATED_CONTENT_MUST_NOT_BE_RESENT',prompt)
            p=json.loads(prompt.split('\n',1)[1]);prompts.append(p)
            if p.get('mode')=='patch':
                self.assertEqual({f['file'] for s in p['snapshots'] for f in s['files']},{'server/items.go'})
            return self.fake(prompt,**kwargs)
        done=analysis_run.run(self.prepare()['id'],executor)
        self.assertEqual(done['state'],'completed',done.get('error'))
        self.assertEqual(self.raw()['dev']['screens'][0]['verified_commit'],before['screens'][0]['verified_commit'])
        self.assertTrue(prompts)

    def source_fake(self,prompt,**kwargs):
        """Respond only to evidence actually delivered, never the whole hidden fixture."""
        p=json.loads(prompt.split('\n',1)[1]);schema=p['schema']
        files={f['file'] for s in p.get('snapshots',[]) for f in s['files']}
        supplied='\n'.join(line['text'] for s in p.get('snapshots',[]) for f in s['files'] for line in f['lines'])
        if 'screens' in schema:
            data={**self.data,'screens':self.data['screens'] if '<button @click="saveItem">' in supplied else [],
                  'backend_routes':self.data['backend_routes'] if 'router.POST("/items", SaveItem)' in supplied else []}
            result=test_ai_extract.agent_answer({'mode':p['mode'],'inspect':p.get('inspect',[]),'recheck':p.get('recheck',[])},data)
            # Absence in a partial source unit does not establish a deletion.
            if 'batch' in p:result.pop('removed',None)
        elif 'nodes' in schema:result=self.SYSTEM if 'server/items.go' in files or any(ev.get('quote')==self.EV['quote'] for ev in ai_extract.cited(p.get('input',{}))) else {'nodes':[],'links':[],'externals':[],'others':[],'unknown':[]}
        else:return self.fake(prompt,**kwargs)
        return {'batch':p['batch']['id'],'covered':p['batch']['units'],'result':result} if 'batch' in p else result

    def test_huge_utf8_line_and_file_are_read_completely_with_original_offsets(self):
        text='가나다012345'*50000+'TAIL_MUST_BE_READ'
        (self.repo/'huge.source').write_text(text)
        self.git('add','.');self.git('commit','-qm','Large UTF-8 source line')
        pieces={};calls=[]
        def executor(prompt,**kwargs):
            self.assertLessEqual(len(prompt.encode()),128*1024);calls.append(len(prompt.encode()))
            p=json.loads(prompt.split('\n',1)[1])
            for snapshot in p.get('snapshots',[]):
                for file in snapshot['files']:
                    if file['file']=='huge.source' and 'screens' in p['schema']:
                        for line in file['lines']:
                            self.assertEqual(line['line'],1)
                            pieces[line.get('offset',0)]=line['text']
            return self.source_fake(prompt,**kwargs)
        done=analysis_run.run(self.prepare()['id'],executor)
        self.assertEqual(done['state'],'completed',done.get('error'))
        reconstructed=''
        for offset,part in sorted(pieces.items()):
            self.assertLessEqual(offset,len(reconstructed));self.assertEqual(reconstructed[offset:],part[:len(reconstructed)-offset])
            reconstructed+=part[len(reconstructed)-offset:]
        self.assertEqual(reconstructed,text);self.assertGreater(len(calls),3)

    def test_bad_batch_coverage_claim_cancel_and_changed_pin_preserve_last_good_map(self):
        done=analysis_run.run(self.prepare()['id'],self.fake);self.assertEqual(done['state'],'completed')
        (self.repo/'changed.source').write_text('independent source line\n'*13000)
        self.git('add','.');self.git('commit','-qm','Large independent changed source')
        for fault in ('missing','duplicate','quote','method','needs_type','cancel','commit'):
            with self.subTest(fault=fault):
                before=self.raw();value=self.prepare();calls=[]
                def executor(prompt,**kwargs):
                    answer=self.source_fake(prompt,**kwargs);calls.append(prompt)
                    if len(calls)==2:
                        if fault=='missing':answer['covered']=[]
                        if fault=='duplicate':answer['covered']*=2
                        if fault=='quote':answer['result']['inspected']=[{'file':'changed.source','line':1,'quote':'invented content'}]
                        if fault=='method':answer['result']['backend_routes']=[{'file':'server/items.go','line':4,'quote':'router.POST("/items", SaveItem)','method':'BAD','path':'/items','function':'SaveItem'}]
                        if fault=='needs_type':answer['needs']={}
                        if fault=='cancel':analysis_run.cancel(value['id'])
                        if fault=='commit':
                            f=self.repo/'changed.source';f.write_text(f.read_text()+'more\n');self.git('add','.');self.git('commit','-qm','Change during batch')
                    return answer
                done=analysis_run.run(value['id'],executor)
                self.assertEqual(done['state'],'cancelled' if fault=='cancel' else 'failed',done.get('error'))
                self.assertEqual(self.raw(),before);self.assertGreaterEqual(len(calls),2)

    def test_oversized_group_metadata_is_paged_without_source_or_final_fusion_call(self):
        done=analysis_run.run(self.prepare()['id'],self.fake);self.assertEqual(done['state'],'completed')
        raw=self.raw();screen=raw['dev']['screens'][0]
        raw['dev']['screens']=[{**screen,'path':f'/screen/{i}','heading':'Long screen title '*80} for i in range(200)]
        raw['dev']['task_outputs'].pop('groups')
        project._publish('demo','service',raw,{},collection=False)
        value=self.prepare();self.assertEqual([t['task'] for t in value['tasks']],['groups'])
        calls=[]
        def executor(prompt,**kwargs):
            calls.append(len(prompt.encode()));self.assertLessEqual(calls[-1],128*1024)
            p=json.loads(prompt.split('\n',1)[1]);self.assertNotIn('snapshots',p)
            screens=[page['value']['path'] for page in p.get('context_pages',[]) if page['path'][:2]==['input','screens']]
            result={'groups':[{'name':'Items','screens':screens}]} if screens else {'groups':[]}
            return {'batch':p['batch']['id'],'covered':p['batch']['units'],'result':result}
        done=analysis_run.run(value['id'],executor)
        self.assertEqual(done['state'],'completed',done.get('error'))
        groups=self.raw()['dev']['task_outputs']['groups']['groups']
        self.assertEqual(set(groups[0]['screens']),{f'/screen/{i}' for i in range(200)})
        self.assertGreater(len(calls),1);self.assertEqual(done['input_stats']['calls'],len(calls))

    def test_small_invalid_nested_claims_are_not_silently_filtered(self):
        for fault in ('action','nav_target','link','job_step','language'):
            with self.subTest(fault=fault):
                before=self.raw();value=self.prepare()
                def executor(prompt,**kwargs):
                    p=json.loads(prompt.split('\n',1)[1]);result=json.loads(self.fake(prompt,**kwargs))
                    if fault=='action' and 'screens' in p['schema']:
                        result['screens'][0]['actions']=[{'file':'pages/items.vue','line':1,'quote':'<button @click="saveItem">','kind':'invented'}]
                    if fault=='nav_target' and 'screens' in p['schema']:
                        result['screens'][0]['actions']=[{'file':'pages/items.vue','line':1,'quote':'<button @click="saveItem">','kind':'nav','to':{'path':'/items'}}]
                    if fault=='language' and 'screens' in p['schema']:result['lang']='ko'
                    if fault=='link' and 'nodes' in p['schema']:result['links']=[{'from':'api','to':'missing','ev':[self.EV]}]
                    if fault=='job_step' and 'nodes' in p['schema']:
                        result['nodes'][0]['jobs']=[{'name':'Job','trigger':self.EV,'steps':[{'file':'pages/items.vue','line':1,'quote':'<button @click="saveItem">','text':'Wrong program'}]}]
                    if fault=='step_target' and 'screens' in p['schema']:
                        result['backend_routes'][0].pop('steps',None)
                    if fault=='step_target' and 'routes' in p['schema']:
                        result={'routes':{'unknown::handler':{'steps':[],'unknown':'Not established'}}}
                    return result
                done=analysis_run.run(value['id'],executor)
                self.assertEqual(done['state'],'failed',done.get('error'))
                if fault in ('action','nav_target','language'):self.assertEqual(self.raw(),before)
                elif fault!='step_target':self.assertNotIn('system',self.raw()['dev'].get('task_outputs',{}))
                else:self.assertNotIn('unknown::handler',self.raw()['dev']['task_outputs'].get('flows',{}).get('routes',{}))
                # Reset this synthetic bundle only; each subtest starts from the same last-good map.
                project._publish('demo','service',before,{},collection=False)

    def test_two_mounts_keep_identity_when_fragments_reverse_and_prefix_changes(self):
        for name,prefix in (('mount-a.source','one'),('mount-b.source','two')):
            (self.repo/name).write_text(f'prefix("/{prefix}", SaveItem)\n')
        (self.repo/'filler.source').write_text('p'*150000)
        routes=[]
        for file,prefix in (('mount-a.source','one'),('mount-b.source','two')):
            route=copy.deepcopy(self.data['backend_routes'][0]);route['path']=f'/{prefix}/items'
            route['dependencies']=[{'file':file,'line':1,'quote':f'prefix("/{prefix}", SaveItem)'}];routes.append(route)
        self.data['backend_routes']=routes
        self.git('add','.');self.git('commit','-qm','Two independent mounts')
        reverse=False
        def executor(prompt,**kwargs):
            p=json.loads(prompt.split('\n',1)[1]);files={f['file'] for s in p.get('snapshots',[]) for f in s['files']}
            if 'screens' not in p['schema']:return self.source_fake(prompt,**kwargs)
            if p.get('mode')=='patch':
                self.assertNotIn('mount-b.source',files)
                changed=copy.deepcopy(routes[0]);changed['path']='/uno/items'
                changed['dependencies'][0]['quote']='prefix("/uno", SaveItem)'
                changed['replaces']=next(r['id'] for r in p['recheck'] if r['path']=='/one/items')
                return {'backend_routes':[changed],'accounted':[{'file':'mount-a.source','kind':'items'}]}
            result={'screens':self.data['screens'] if 'pages/items.vue' in files else [],'backend_routes':[]}
            needs=[]
            if 'server/items.go' in files:
                needs=[{'file':f,'limit':10} for f in ('mount-a.source','mount-b.source') if f not in files]
                if not needs:result['backend_routes']=list(reversed(routes)) if reverse else routes
            return {'batch':p['batch']['id'],'covered':p['batch']['units'],'result':result,'needs':needs}
        done=analysis_run.run(self.prepare()['id'],executor);self.assertEqual(done['state'],'completed',done.get('error'))
        saved={r['path']:r['id'] for r in self.raw()['dev']['backend_routes']};self.assertEqual(len(saved),2)
        reverse=True
        done=analysis_run.run(analysis_run.prepare('demo',lang='ko')['id'],executor)
        self.assertEqual(done['state'],'completed',done.get('error'))
        self.assertEqual({r['path']:r['id'] for r in self.raw()['dev']['backend_routes']},saved)
        (self.repo/'mount-a.source').write_text('prefix("/uno", SaveItem)\n')
        self.git('add','.');self.git('commit','-qm','Change one mount prefix')
        done=analysis_run.run(analysis_run.prepare('demo',lang='ko')['id'],executor)
        self.assertEqual(done['state'],'completed',done.get('error'))
        after={r['path']:r['id'] for r in self.raw()['dev']['backend_routes']}
        self.assertEqual(set(after),{'/uno/items','/two/items'});self.assertEqual(after['/two/items'],saved['/two/items'])

    def test_rename_and_delete_use_required_old_blobs_without_unrelated_source(self):
        done=analysis_run.run(self.prepare()['id'],self.fake);self.assertEqual(done['state'],'completed')
        self.git('mv','server/items.go','server/renamed.go');self.git('add','.');self.git('commit','-qm','Rename handler')
        old=self.raw()['dev']['backend_routes'][0]['id'];data=copy.deepcopy(self.data)
        route=data['backend_routes'][0]
        for ev in [route,*route['tables'],*route['steps']]:ev['file']='server/renamed.go'
        route['replaces']=old
        calls=[]
        def executor(prompt,**kwargs):
            p=json.loads(prompt.split('\n',1)[1]);calls.append(p)
            if 'screens' in p['schema']:
                self.assertEqual({f['file'] for s in p['snapshots'] for f in s['files']},{'server/items.go','server/renamed.go'})
                return {'backend_routes':[route],'accounted':[{'file':'server/renamed.go','kind':'items'}]}
            if 'nodes' in p['schema']:
                system=copy.deepcopy(self.SYSTEM);system['nodes'][0]['ev'][0]['file']='server/renamed.go';return system
            return self.fake(prompt,**kwargs)
        done=analysis_run.run(self.prepare()['id'],executor)
        self.assertEqual(done['state'],'completed',done.get('error'))
        self.assertEqual(self.raw()['dev']['backend_routes'][0]['file'],'server/renamed.go')
        renamed=self.raw()['dev']['backend_routes'][0]['id']
        self.git('rm','-q','server/renamed.go');self.git('commit','-qm','Delete handler')
        def deleted(prompt,**kwargs):
            p=json.loads(prompt.split('\n',1)[1])
            if 'screens' in p['schema']:return {'removed':[renamed],'accounted':[]}
            if 'nodes' in p['schema']:
                return {'nodes':[{'id':'web','name':'Web','kind':'program','code':['pages'],'ev':[{'file':'pages/items.vue','line':1,'quote':'<button @click="saveItem">'}],'jobs':[]}],'links':[],'externals':[],'others':[]}
            return self.fake(prompt,**kwargs)
        done=analysis_run.run(self.prepare()['id'],deleted)
        self.assertEqual(done['state'],'completed',done.get('error'));self.assertEqual(self.raw()['dev']['backend_routes'],[])

    def test_source_reads_and_literal_search_stay_inside_eligible_pinned_files(self):
        (self.repo/'big.source').write_text('p'*150000)
        (self.repo/'.env').write_text('PRIVATE_DO_NOT_SEND=credential\n')
        (self.repo/'link.source').symlink_to('/etc/passwd')
        self.git('add','.');self.git('commit','-qm','Pinned read eligibility fixture')
        (self.repo/'untracked.source').write_text('UNTRACKED_DO_NOT_SEND\n')
        for file in ('../outside','.env','link.source','untracked.source'):
            with self.subTest(file=file):
                before=self.raw();value=self.prepare()
                def denied(prompt,**kwargs):
                    p=json.loads(prompt.split('\n',1)[1]);self.assertNotIn('PRIVATE_DO_NOT_SEND',prompt);self.assertNotIn('UNTRACKED_DO_NOT_SEND',prompt)
                    return {'batch':p['batch']['id'],'covered':p['batch']['units'],'result':{},'needs':[{'file':file}]}
                done=analysis_run.run(value['id'],denied)
                self.assertEqual(done['state'],'failed');self.assertEqual(self.raw(),before)
        calls=[];searched=False
        def searching(prompt,**kwargs):
            nonlocal searched
            p=json.loads(prompt.split('\n',1)[1]);calls.append(p)
            self.assertNotIn('PRIVATE_DO_NOT_SEND',prompt);self.assertNotIn('UNTRACKED_DO_NOT_SEND',prompt)
            if not searched:
                searched=True
                return {'batch':p['batch']['id'],'covered':p['batch']['units'],'result':{},'needs':[{'query':'db.Table','start':1,'limit':1}]}
            return self.source_fake(prompt,**kwargs)
        done=analysis_run.run(self.prepare()['id'],searching)
        self.assertEqual(done['state'],'completed',done.get('error'))
        self.assertTrue(any(page['value'].get('query')=='db.Table' and page['value']['total']==1 for p in calls for page in p.get('context_pages',[]) if isinstance(page['value'],dict)))

    def test_literal_searches_in_one_analysis_do_not_reread_pinned_blobs(self):
        import subprocess
        # The padding fills the first batch, so its rounds carry only search hits from the other files.
        padding='a-padding.source';(self.repo/padding).write_text('ordinary unrelated source line\n'*9000)
        self.git('add','.');self.git('commit','-qm','Padding that splits the input')
        files=[padding,'pages/items.vue','server/items.go']
        names={self.git('rev-parse','HEAD:'+f).strip():f for f in files}
        needs=[{'query':'"/items"','start':1,'limit':1},{'query':'"/items"','start':2,'limit':1},{'query':'db.Table','start':1,'limit':1}]
        expected=[({'query':'"/items"','start':1,'total':2,'next':2},[('pages/items.vue',2,'fetch("/items", {method:"POST"})')]),
                  ({'query':'"/items"','start':2,'total':2,'next':None},[('server/items.go',4,'router.POST("/items", SaveItem)')]),
                  ({'query':'db.Table','start':1,'total':1,'next':None},[('server/items.go',2,' db.Table("items").Create(item)')])]
        answers=[];seen=set();first=None
        def executor(prompt,**kwargs):
            nonlocal first
            p=json.loads(prompt.split('\n',1)[1])
            if 'screens' not in p['schema']:return self.fake(prompt,**kwargs)
            first=first or p['batch']['id']
            pages=[page for page in p.get('context_pages',[]) if page.get('path')==['read_page']]
            if p['batch']['id']==first and len(pages)==1:
                hits=[(f['file'],line['line'],line['text']) for s in p.get('snapshots',[]) for f in s['files'] if f['file']!=padding for line in f['lines']]
                answers.append((pages[0]['value'],[hit for hit in hits if hit not in seen]));seen.update(hits)
            answer={'batch':p['batch']['id'],'covered':p['batch']['units'],'result':{}}
            if p['batch']['id']==first:
                if needs:answer['needs']=[needs.pop(0)]
                else:answer['result']=self.data
            return answer
        value=self.prepare();blob_reads=[];real_popen=subprocess.Popen
        def observed(command,*args,**kwargs):
            # cat-file -s reads only the size; a future reader that hides object IDs from argv fails the exact count.
            if '-s' not in command:blob_reads.extend(names[arg] for arg in command if arg in names)
            return real_popen(command,*args,**kwargs)
        with patch('subprocess.Popen',observed):done=analysis_run.run(value['id'],executor)
        self.assertEqual(done['state'],'completed',done.get('error'))
        self.assertEqual(answers,expected)
        self.assertEqual({f:blob_reads.count(f) for f in files},{f:1 for f in files})

    def read_source(self,commit,need,blobs,cancelled=None):
        units=analysis_run._needed(str(self.repo),commit,[need],cancelled,None,{},blobs)
        return [(u['value']['file'],line['line'],line['text']) for u in units if u['kind']=='source' for line in u['value']['lines']]

    def test_reused_source_keeps_full_lines_after_partial_reads_and_pages(self):
        (self.repo/'pages.txt').write_text('needle one\nplain\nneedle two\n')
        self.git('add','.');self.git('commit','-qm','Lines to page')
        commit=self.git('rev-parse','HEAD').strip();blobs={}
        self.assertEqual(self.read_source(commit,{'file':'pages.txt','start':2,'limit':1},blobs),[('pages.txt',2,'plain')])
        self.assertEqual(self.read_source(commit,{'query':'needle','start':2,'limit':1},blobs),[('pages.txt',3,'needle two')])
        self.assertEqual(self.read_source(commit,{'file':'pages.txt'},blobs),[('pages.txt',1,'needle one'),('pages.txt',2,'plain'),('pages.txt',3,'needle two')])
        self.assertEqual(self.read_source(commit,{'query':'needle'},blobs),[('pages.txt',1,'needle one'),('pages.txt',3,'needle two')])

    def test_selected_initial_source_does_not_limit_a_later_full_search(self):
        (self.repo/'chosen.txt').write_text('needle chosen\n');(self.repo/'other.txt').write_text('needle other\n')
        self.git('add','.');self.git('commit','-qm','Chosen and unchosen files')
        commit=self.git('rev-parse','HEAD').strip();blobs={}
        exported=analysis_run.export_source(str(self.repo),commit,selected={commit:{'chosen.txt'}},blobs=blobs)
        self.assertEqual([f['file'] for f in exported[0]['files']],['chosen.txt'])
        self.assertEqual(self.read_source(commit,{'query':'needle'},blobs),[('chosen.txt',1,'needle chosen'),('other.txt',1,'needle other')])

    def test_reused_source_stays_separate_between_commits(self):
        (self.repo/'state.txt').write_text('needle old\n');(self.repo/'removed.txt').write_text('needle removed\n')
        self.git('add','.');self.git('commit','-qm','Old state');old=self.git('rev-parse','HEAD').strip()
        (self.repo/'state.txt').write_text('needle new\n');(self.repo/'removed.txt').unlink()
        self.git('add','.');self.git('commit','-qm','New state');new=self.git('rev-parse','HEAD').strip()
        blobs={}
        exported=analysis_run.export_source(str(self.repo),new,[old],blobs=blobs)
        lines={s['commit']:{f['file']:[l['text'] for l in f['lines']] for f in s['files'] if f['file'] in ('state.txt','removed.txt')} for s in exported}
        self.assertEqual(lines,{new:{'state.txt':['needle new']},old:{'state.txt':['needle old'],'removed.txt':['needle removed']}})
        self.assertEqual(self.read_source(new,{'query':'needle'},blobs),[('state.txt',1,'needle new')])
        self.assertEqual(self.read_source(old,{'query':'needle'},blobs),[('removed.txt',1,'needle removed'),('state.txt',1,'needle old')])

    def test_reused_content_does_not_make_an_excluded_path_eligible(self):
        # One object ID at four paths: only the path and mode decide eligibility.
        text='needle shared'
        for name in ('plain.txt','.env','photo.png'):(self.repo/name).write_text(text)
        os.symlink(text,self.repo/'link.txt')
        self.git('add','-f','.');self.git('commit','-qm','One blob at excluded paths')
        commit=self.git('rev-parse','HEAD').strip();blobs={}
        self.assertEqual(self.read_source(commit,{'file':'plain.txt'},blobs),[('plain.txt',1,text)])
        self.assertEqual(self.read_source(commit,{'query':'needle'},blobs),[('plain.txt',1,text)])
        omitted={x['file']:x['reason'] for x in analysis_run.export_source(str(self.repo),commit,blobs=blobs)[0]['omitted']}
        self.assertEqual({k:omitted[k] for k in ('.env','photo.png','link.txt')},{'.env':'credential_file','photo.png':'binary_asset','link.txt':'not_regular_source'})
        for name in ('.env','photo.png','link.txt'):
            with self.assertRaisesRegex(analysis_run.RunError,'not eligible'):self.read_source(commit,{'file':name},blobs)

    def test_reused_binary_blob_stays_omitted_without_rereading(self):
        (self.repo/'data.bin').write_bytes(b'needle\x00')
        self.git('add','.');self.git('commit','-qm','Binary without a known suffix')
        commit=self.git('rev-parse','HEAD').strip();blobs={}
        for _ in range(2):
            omitted=analysis_run.export_source(str(self.repo),commit,blobs=blobs)[0]['omitted']
            self.assertIn({'file':'data.bin','reason':'binary'},omitted)
            with patch.object(analysis_run,'_git',wraps=analysis_run._git) as git:self.assertEqual(self.read_source(commit,{'query':'needle'},blobs),[])
            self.assertFalse([c for c in git.call_args_list if c.args[1]=='cat-file'])

    def test_cancellation_and_deadline_stop_a_search_over_reused_source(self):
        commit=self.git('rev-parse','HEAD').strip();blobs={}
        self.read_source(commit,{'query':'needle'},blobs)
        checks=[]
        self.read_source(commit,{'query':'needle'},blobs,lambda:checks.append(1) or False)
        # Every checkpoint of a fully reused search must still stop it, including the last one.
        for stop in range(1,len(checks)+1):
            seen=[]
            with self.assertRaises(analysis_run.Cancelled):
                self.read_source(commit,{'query':'needle'},blobs,lambda:seen.append(1) or len(seen)>=stop)
        tree=len(self.git('ls-tree','-r','--name-only',commit).splitlines())
        # The commit, each ls-tree entry and its trailing empty entry are checked before any search begins.
        self.assertGreater(len(checks),2+tree,'the search over reused lines needs its own checkpoints')
        with self.assertRaises(analysis_run.RunError) as caught:
            analysis_run._needed(str(self.repo),commit,[{'query':'needle'}],None,time.monotonic()-1,{},blobs)
        self.assertEqual(caught.exception.code,'timeout')

    def test_source_reuse_spans_tasks_in_a_run_but_not_separate_runs(self):
        seen=[];real=analysis_run.generate
        def observed(*args,**kwargs):
            seen.append(args[7]);return real(*args,**kwargs)
        with patch.object(analysis_run,'generate',observed):
            done=analysis_run.run(self.prepare()['id'],self.fake);self.assertEqual(done['state'],'completed',done.get('error'))
            first=list(seen);seen.clear()
            self.assertGreater(len(first),1)
            self.assertTrue(all(x is first[0] for x in first))
            (self.repo/'server/items.go').write_text((self.repo/'server/items.go').read_text()+'// Second run source.\n')
            self.git('add','.');self.git('commit','-qm','Change for a second run')
            done=analysis_run.run(self.prepare()['id'],self.fake);self.assertEqual(done['state'],'completed',done.get('error'))
        self.assertTrue(seen)
        self.assertFalse([x for x in seen if x is first[0]])

    def test_split_patch_retrieves_old_ids_only_from_actual_metadata_context(self):
        mount='server/mount.source';file='server/routes.source';new=[];text=[]
        for i in range(600):
            fn=f'handler_{i:04}_'+('x'*48);quote=f'route POST /r{i} {fn}'
            text.append(quote)
            new.append({'file':file,'line':i+1,'quote':quote,'method':'POST','path':f'/v0/r{i}','function':fn,
                'dependencies':[{'file':mount,'line':1,'quote':'prefix /v0'}],
                'steps':[{'file':file,'line':i+1,'quote':quote,'text':'Handle request','lane':'서버'}]})
        (self.repo/file).write_text('\n'.join(text)+'\n');(self.repo/mount).write_text('prefix /v0\n')
        self.git('add','.');self.git('commit','-qm','Many pinned route identities')
        self.data['backend_routes']+=new
        req=ai_extract.request('demo','dev','en','service')
        ai_extract.record(**req['record_arguments'],result_json=json.dumps(test_ai_extract.agent_answer(req,self.data)))
        for task,result in (('system',self.SYSTEM),('groups',self.GROUPS)):
            req=ai_extract.task_request('demo',task,'dev','en','service');ai_extract.task_record(**req['record_arguments'],result_json=json.dumps(result))
        (self.repo/mount).write_text('prefix /v1\n');self.git('add','.');self.git('commit','-qm','Change the shared prefix')
        calls=[];metadata_reads=[]
        def executor(prompt,**kwargs):
            p=json.loads(prompt.split('\n',1)[1]);calls.append(len(prompt.encode()));self.assertLessEqual(calls[-1],128*1024)
            if 'screens' not in p['schema']:return self.fake(prompt,**kwargs)
            self.assertIn('batch',p)
            lines={line['text']:(f['file'],line['line']) for s in p.get('snapshots',[]) for f in s['files'] for line in f['lines']}
            functions={line.split()[-1] for line in lines if line.startswith('route POST')}
            items=list(p.get('recheck',[]));page=None
            for entry in p.get('context_pages',[]):
                if entry['path']==['recheck']:items+=entry['value']
                elif entry['path'][:1]==['recheck'] and isinstance(entry['value'],dict):items.append(entry['value'])
                if entry['path']==['read_page'] and entry['value'].get('metadata')==['recheck']:page=entry['value']
            routes=[]
            if functions and 'prefix /v1' in lines:
                for item in items:
                    if item['function'] not in functions:continue
                    quote=next(line for line in lines if line.startswith('route POST') and line.split()[-1]==item['function'])
                    routes.append({'file':file,'line':lines[quote][1],'quote':quote,'method':item['method'],
                        'path':item['path'].replace('/v0/','/v1/'),'function':item['function'],'replaces':item['id'],
                        'dependencies':[{'file':mount,'line':1,'quote':'prefix /v1'}],
                        'steps':[{'file':file,'line':lines[quote][1],'quote':quote,'text':'Handle request','lane':'서버'}]})
            needs=[]
            if functions:
                start=page['next'] if page else 1
                if start:
                    metadata_reads.append(start);needs.append({'metadata':['recheck'],'start':start,'limit':100})
                if 'prefix /v1' not in lines:needs.append({'file':mount,'limit':1})
            result={'backend_routes':routes}
            if routes:result['accounted']=[{'file':mount,'kind':'items'}]
            return {'batch':p['batch']['id'],'covered':p['batch']['units'],'result':result,'needs':needs}
        done=analysis_run.run(self.prepare()['id'],executor)
        self.assertEqual(done['state'],'completed',done.get('error'))
        self.assertTrue(metadata_reads)
        self.assertEqual({r['path'] for r in self.raw()['dev']['backend_routes']},{'/items',*[f'/v1/r{i}' for i in range(600)]})

    def test_same_url_in_unrelated_handlers_does_not_widen_changed_input(self):
        files={'backend/app/main.py':'from fastapi import FastAPI\nfrom app.routers import a, b\napp = FastAPI()\napp.include_router(a.router)\napp.include_router(b.router)\n'}
        routes=[]
        for name in ('a','b'):
            router=f'backend/app/routers/{name}.py';service=f'backend/app/services/health_{name}.py'
            files[router]=f'from fastapi import APIRouter\nfrom ..services.health_{name} import check_health\nrouter = APIRouter()\n@router.get("/health")\ndef health_{name}():\n    return check_health()\n'
            files[service]=f'def check_health():\n    return "PRIVATE_UNRELATED_{name.upper()}"\n'
            routes.append({'file':router,'line':4,'quote':'@router.get("/health")','method':'GET','path':'/health','function':f'health_{name}',
                'services':[{'file':service,'line':1,'quote':'def check_health():'}],
                'steps':[{'file':service,'line':1,'quote':'def check_health():','text':'Check health','lane':'서버'}]})
        for file,text in files.items():
            p=self.repo/file;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text)
        self.git('add','.');self.git('commit','-qm','Same URL in independent handler files')
        self.data['backend_routes']+=routes
        req=ai_extract.request('demo','dev','en','service')
        ai_extract.record(**req['record_arguments'],result_json=json.dumps(test_ai_extract.agent_answer(req,self.data)))
        for task,result in (('system',self.SYSTEM),('groups',self.GROUPS)):
            req=ai_extract.task_request('demo',task,'dev','en','service');ai_extract.task_record(**req['record_arguments'],result_json=json.dumps(result))
        changed=self.repo/'backend/app/services/health_a.py';changed.write_text(changed.read_text()+'# changed\n')
        self.git('add','.');self.git('commit','-qm','Change only service A')
        req=ai_extract.request('demo','dev','en','service')
        self.assertEqual([r['function'] for r in req['recheck']],['health_a'])
        def executor(prompt,**kwargs):
            self.assertNotIn('PRIVATE_UNRELATED_B',prompt)
            return self.fake(prompt,**kwargs)
        done=analysis_run.run(self.prepare()['id'],executor)
        self.assertEqual(done['state'],'completed',done.get('error'))

    def test_direct_reply_needs_are_fulfilled_before_any_result_is_saved(self):
        helper='server/helper.go';(self.repo/helper).write_text('func HiddenHelper() { return }\n')
        self.git('add','.');self.git('commit','-qm','Initially uncited helper')
        done=analysis_run.run(self.prepare()['id'],self.fake);self.assertEqual(done['state'],'completed')
        path=self.repo/'server/items.go'
        path.write_text(path.read_text()+'HiddenHelper()\n//'+('x'*120000)+'\n')
        self.git('add','.');self.git('commit','-qm','Reference the previously uncited helper')
        before=self.raw();calls=[];saw_helper=False
        def executor(prompt,**kwargs):
            nonlocal saw_helper
            p=json.loads(prompt.split('\n',1)[1]);calls.append(len(prompt.encode()))
            if 'screens' not in p['schema']:return self.fake(prompt,**kwargs)
            files={f['file'] for s in p.get('snapshots',[]) for f in s['files']}
            if len(calls)==1:
                self.assertNotIn('batch',p);self.assertNotIn(helper,files)
                result=json.loads(self.fake(prompt,**kwargs));result['needs']=[{'file':helper,'limit':10}];return result
            self.assertEqual(self.raw(),before,'The provisional direct reply must not be saved')
            answer=self.source_fake(prompt,**kwargs)
            if helper in files:
                saw_helper=True
                for route in answer['result'].get('backend_routes',[]):route['services']=[{'file':helper,'line':1,'quote':'func HiddenHelper()'}]
            return answer
        done=analysis_run.run(self.prepare()['id'],executor)
        self.assertEqual(done['state'],'completed',done.get('error'));self.assertTrue(saw_helper)
        self.assertEqual(self.raw()['dev']['backend_routes'][0]['services'],[helper]);self.assertGreater(len(calls),1)
        self.assertLessEqual(max(calls),128*1024)

    def test_provisional_system_link_can_resolve_after_needed_node_is_read(self):
        helper='outside/store.source';(self.repo/'outside').mkdir();(self.repo/helper).write_text('store StoreRuntime\n')
        self.git('add','.');self.git('commit','-qm','Initially uncited store')
        done=analysis_run.run(self.prepare()['id'],self.fake);self.assertEqual(done['state'],'completed')
        path=self.repo/'server/items.go';path.write_text(path.read_text()+'connect StoreRuntime()\n')
        self.git('add','.');self.git('commit','-qm','Reference an outside store')
        system_before=None;system_calls=[]
        def executor(prompt,**kwargs):
            nonlocal system_before
            p=json.loads(prompt.split('\n',1)[1])
            if 'nodes' not in p['schema']:return self.fake(prompt,**kwargs)
            files={f['file'] for s in p.get('snapshots',[]) for f in s['files']};system_calls.append(files)
            api=copy.deepcopy(self.SYSTEM['nodes'][0])
            link={'from':'api','to':'store','label':'Uses store','ev':[{'file':'server/items.go','line':5,'quote':'connect StoreRuntime()'}]}
            if len(system_calls)==1:
                system_before=self.raw();self.assertNotIn(helper,files);self.assertNotIn('batch',p)
                return {'nodes':[api],'links':[link],'externals':[],'others':[],'needs':[{'file':helper,'limit':10}]}
            self.assertEqual(self.raw(),system_before)
            self.assertIn(helper,files)
            store={'id':'store','name':'Store','kind':'store','code':[],'ev':[{'file':helper,'line':1,'quote':'store StoreRuntime'}]}
            return {'batch':p['batch']['id'],'covered':p['batch']['units'],
                    'result':{'nodes':[store],'links':[],'externals':[],'others':[]}}
        done=analysis_run.run(self.prepare()['id'],executor)
        self.assertEqual(done['state'],'completed',done.get('error'));self.assertEqual(len(system_calls),2)
        system=self.raw()['dev']['task_outputs']['system']
        self.assertEqual({n['id'] for n in system['nodes']},{'api','store'});self.assertEqual(system['links'][0]['to'],'store')

    def test_provider_failure_keeps_saved_map_and_retry_only_finishes_missing_tasks(self):
        calls=[]
        def executor(prompt,**kwargs):
            calls.append(prompt)
            if len(calls)==2:raise ValueError('Synthetic provider unavailable')
            return self.fake(prompt,**kwargs)
        value=self.prepare();failed=analysis_run.run(value['id'],executor)
        self.assertEqual(failed['state'],'failed')
        self.assertEqual([t['task'] for t in failed['completed_tasks']],['analysis'])
        saved=copy.deepcopy(self.raw()['dev'])
        retried=analysis_run.retry(value['id']);self.assertNotEqual(retried['id'],value['id'])
        self.assertNotIn('analysis',[t['task'] for t in retried['tasks']])
        done=analysis_run.run(retried['id'],self.fake)
        self.assertEqual(done['state'],'completed',done.get('error'))
        self.assertEqual(self.raw()['dev']['analysis'],saved['analysis'])

    def test_invalid_output_is_failed_without_publishing(self):
        before=self.raw();value=self.prepare()
        done=analysis_run.run(value['id'],lambda *a,**k:'not JSON')
        self.assertEqual(done['state'],'failed');self.assertEqual(self.raw(),before)

    def test_cancel_before_start_and_while_model_runs_retains_previous_results(self):
        value=self.prepare();cancelled=analysis_run.cancel(value['id'])
        self.assertEqual(cancelled['state'],'cancelled')
        before=self.raw();value=self.prepare()
        def executor(prompt,*,cancelled,timeout):
            analysis_run.cancel(value['id']);self.assertTrue(cancelled())
            return self.fake(prompt,cancelled=lambda:False,timeout=timeout)
        done=analysis_run.run(value['id'],executor)
        self.assertEqual(done['state'],'cancelled');self.assertEqual(self.raw(),before)

    def test_full_pin_change_during_execution_rejects_save(self):
        before=self.raw();value=self.prepare()
        def executor(prompt,**kwargs):
            result=self.fake(prompt,**kwargs)
            (self.repo/'server/items.go').write_text((self.repo/'server/items.go').read_text()+'// changed\n')
            self.git('add','.');self.git('commit','-qm','Changed while model runs')
            return result
        done=analysis_run.run(value['id'],executor)
        self.assertEqual(done['state'],'failed');self.assertEqual(done['error']['code'],'pins_changed')
        self.assertEqual(self.raw(),before)

    def test_configuration_changes_and_repository_membership_are_pinned(self):
        value=self.prepare();conf=project.config('demo');conf['repositories'][0]['layout']={'frontend':'pages'}
        project.atomic(project.home('demo')/'project.json',conf)
        done=analysis_run.run(value['id'],lambda *a,**k:self.fail('Pins changed before invocation'))
        self.assertEqual(done['error']['code'],'pins_changed')

    def test_duplicate_preparations_are_rejected_and_status_is_scoped(self):
        value=self.prepare()
        with self.assertRaisesRegex(ValueError,'already'):self.prepare()
        with self.assertRaisesRegex(ValueError,'already'):analysis_run.prepare('demo',branch='main',lang='ko')
        self.assertEqual(analysis_run.status(project='demo',lang='en')['id'],value['id'])
        self.assertEqual(analysis_run.status(project='demo',branch='main',lang='en')['id'],value['id'])
        self.assertEqual(analysis_run.status(project='demo',lang='ko')['id'],value['id'])
        analysis_run.cancel(value['id']);self.assertEqual(analysis_run.status(value['id'])['state'],'cancelled')
        self.assertIsNone(analysis_run.status(project='demo',lang='ko'))

    def test_recovery_distinguishes_prepared_live_and_interrupted_workers(self):
        value=self.prepare()
        self.assertEqual(analysis_run.status(value['id'])['state'],'preparing')
        self.assertFalse(analysis_run.active()['active'])
        value.update(state='running',launch_epoch=time.time()-60);analysis_run.write(value)
        with (analysis_run.root()/(value['id']+'.worker.lock')).open('a') as lock:
            import fcntl
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            self.assertEqual(analysis_run.status(value['id'])['state'],'running')
            self.assertTrue(analysis_run.active()['active'])
        done=analysis_run.status(value['id'])
        self.assertEqual(done['state'],'failed');self.assertEqual(done['error']['code'],'interrupted')
        self.assertFalse(analysis_run.active()['active'])
        startup=analysis_run.retry(value['id'],launch_intended=True)
        startup['prepare_epoch']=time.time()-120;analysis_run.write(startup)
        self.assertEqual(analysis_run.status(startup['id'])['error']['code'],'interrupted')

    def test_export_uses_commit_blobs_omits_credentials_and_symlinks(self):
        (self.repo/'.env').write_text('SECRET=do-not-send\n')
        (self.repo/'.git-credentials').write_text('https://user:never-send@github.com\n')
        (self.repo/'.netrc').write_text('machine service password never-send\n')
        (self.repo/'auth.json').write_text('{"token":"never-send"}')
        (self.repo/'server'/'link').symlink_to('/etc/passwd')
        self.git('add','.');self.git('commit','-qm','Synthetic credentials and link')
        commit=self.git('rev-parse','HEAD').strip()
        (self.repo/'server/items.go').write_text('working-tree-secret')
        exported=analysis_run.export_source(str(self.repo),commit)
        text=json.dumps(exported)
        self.assertNotIn('never-send',text);self.assertNotIn('do-not-send',text);self.assertNotIn('working-tree-secret',text)
        self.assertIn('router.POST',text);self.assertIn('not_regular_source',text)
        self.assertIn('credential_file',text)

    def test_input_that_cannot_fit_one_encoded_unit_fails_without_executor(self):
        value=self.prepare();before=self.raw()
        with patch.object(analysis_run,'MAX_PROMPT_BYTES',32):
            done=analysis_run.run(value['id'],lambda *a,**k:self.fail('Input exceeds limit'))
        self.assertEqual(done['error']['code'],'source_too_large');self.assertEqual(self.raw(),before)

    def test_large_binary_assets_are_omitted_and_large_text_is_available_for_batches(self):
        (self.repo/'picture.png').write_bytes(b'X'*400_000)
        (self.repo/'binary-unknown').write_bytes(b'\x00'*400_000)
        self.git('add','.');self.git('commit','-qm','Synthetic binary assets')
        commit=self.git('rev-parse','HEAD').strip()
        exported=analysis_run.export_source(str(self.repo),commit)
        self.assertEqual({x['reason'] for x in exported[0]['omitted']},{'binary_asset','binary'})
        (self.repo/'huge.txt').write_text('text source '*40000)
        self.git('add','.');self.git('commit','-qm','Synthetic oversized text')
        exported=analysis_run.export_source(str(self.repo),self.git('rev-parse','HEAD').strip())
        huge=next(f for f in exported[0]['files'] if f['file']=='huge.txt')
        self.assertEqual(huge['lines'][0]['text'],'text source '*40000)
        with self.assertRaises(analysis_run.Cancelled):
            analysis_run.export_source(str(self.repo),commit,cancelled=lambda:True)

    def test_start_rejects_changed_displayed_account_before_worker_launch(self):
        import cli_executor
        shown={'email':'shown@example.invalid','auth_method':'claude.ai'}
        current={'email':'other@example.invalid','auth_method':'claude.ai'}
        value=self.prepare()
        with patch.object(cli_executor,'availability',return_value={'available':True,'authenticated':True,'account':current}),patch.object(analysis_run.subprocess,'Popen') as spawn:
            with self.assertRaisesRegex(ValueError,'account changed'):analysis_run.start(value['id'],shown)
            spawn.assert_not_called()
        self.assertEqual(analysis_run.status(value['id'])['error']['code'],'CLI_ACCOUNT_CHANGED')

    def fake_cli(self):
        import cli_executor
        folder=Path(self.temp.name)/'bin';folder.mkdir()
        fixtures=Path(self.temp.name)/'fixtures.json'
        fixtures.write_text(json.dumps({'analysis':self.data,'system':self.SYSTEM,'groups':self.GROUPS,'flags':' '.join(cli_executor.REQUIRED_FLAGS)}))
        script=folder/'claude'
        script.write_text('#!'+sys.executable+'\n'+"""
import json, os, sys, time
fixtures=json.load(open(os.environ['TEST_ANALYSIS_FIXTURES']))
if '--help' in sys.argv:print(fixtures['flags'])
elif sys.argv[1:]==['auth','status']:
    print(json.dumps({'loggedIn':True,'authMethod':'claude.ai','email':'fake@example.invalid'}))
else:
    payload=json.loads(sys.stdin.read().split('\\n',1)[1]);schema=payload['schema']
    if os.environ.get('TEST_ANALYSIS_PAUSE'):
        open(os.environ['TEST_ANALYSIS_PAUSE'],'w').write('started')
        time.sleep(30)
    result=fixtures['analysis'] if 'screens' in schema else fixtures['system'] if 'nodes' in schema else fixtures['groups']
    if payload.get('mode')=='review':result={'keep':'all',**result}
    print(json.dumps({'result':json.dumps(result)}))
""")
        script.chmod(0o700)
        return {'PATH':str(folder)+os.pathsep+os.environ.get('PATH',''),'TEST_ANALYSIS_FIXTURES':str(fixtures)}

    def wait_terminal(self,run_id,seconds=15):
        until=time.monotonic()+seconds
        while time.monotonic()<until:
            value=analysis_run.status(run_id)
            if value['state'] in analysis_run.TERMINAL:return value
            time.sleep(.05)
        self.fail('Detached synthetic worker did not finish')

    def test_real_detached_worker_uses_fake_cli_and_pinned_account(self):
        import cli_executor
        with patch.dict(os.environ,self.fake_cli()):
            account=cli_executor.availability()['account'];value=self.prepare()
            started=analysis_run.start(value['id'],account)
            self.assertEqual(started['account'],account)
            done=self.wait_terminal(value['id'])
        self.assertEqual(done['state'],'completed',done.get('error'))
        self.assertEqual([t['task'] for t in done['completed_tasks']],['analysis','system','groups'])

    def test_detached_cancellation_stops_only_its_owned_fake_cli_without_saving(self):
        import cli_executor
        env=self.fake_cli();marker=Path(self.temp.name)/'model-started';env['TEST_ANALYSIS_PAUSE']=str(marker)
        before=self.raw()
        with patch.dict(os.environ,env):
            account=cli_executor.availability()['account'];value=self.prepare()
            analysis_run.start(value['id'],account)
            until=time.monotonic()+10
            while not marker.exists() and time.monotonic()<until:time.sleep(.05)
            self.assertTrue(marker.exists(),'Synthetic model did not start')
            analysis_run.cancel(value['id']);done=self.wait_terminal(value['id'])
        self.assertEqual(done['state'],'cancelled');self.assertEqual(self.raw(),before)

    def test_program_jobs_and_briefing_require_explicit_intent(self):
        self.SYSTEM={**self.SYSTEM,'nodes':self.SYSTEM['nodes']+[{'id':'web','name':'Web','kind':'program','code':['pages'],
            'ev':[{'file':'pages/items.vue','line':1,'quote':'<button @click="saveItem">'}]}]}
        self.data={**self.data,'screens':[]}
        value=self.prepare();done=analysis_run.run(value['id'],self.fake)
        self.assertEqual(done['state'],'completed',done.get('error'))
        raw=self.raw();self.assertFalse(raw['dev']['task_outputs'].get('jobs',{}).get('nodes'))
        value=self.prepare(intent={'task':'jobs','targets':[{'repository':'service','target':'api'}]})
        calls=[]
        def jobs(prompt,**kwargs):
            p=json.loads(prompt.split('\n',1)[1]);calls.append(p)
            self.assertEqual(p['input']['node']['id'],'api')
            self.assertEqual({f['file'] for snapshot in p['snapshots'] for f in snapshot['files']},{'server/items.go'})
            return {'jobs':[],'unknown':[{'text':'No jobs established by supplied source','needs':'read'}]}
        done=analysis_run.run(value['id'],jobs)
        self.assertEqual(done['state'],'completed',done.get('error'));self.assertEqual(len(calls),1)
        raw=self.raw();self.assertEqual(raw['dev']['task_outputs']['jobs']['nodes']['api']['source'],'ai')
        # Frozen briefing evidence changes schedule a real briefing task, whose claims still pass its validator.
        # Supply a minimal frozen evidence window directly, without any external collection.
        raw['changes']={'last_result':{'since':'2026-10-01T00:00:00+00:00','at':'2026-10-02T00:00:00+00:00','changed':True,'evidence':{
            'commits':{'dev':{'from':self.commit,'to':self.commit}},'comparison':{'since':'last_refresh','since_time':''},
            'structure':{},'prs':[],'issues':[],'collection':{}}}}
        project._publish('demo','service',raw,{},collection=False)
        value=self.prepare();self.assertEqual(value['tasks'],[])
        analysis_run.run(value['id'],lambda *a,**k:self.fail('Overview must not explain changes'))
        value=self.prepare(intent={'task':'briefing'});self.assertEqual([t['task'] for t in value['tasks']],['briefing'])
        def executor(prompt,**kwargs):
            payload=json.loads(prompt.split('\n',1)[1]);self.assertIn('sources',payload)
            return json.dumps({'cards':[],'unknown':['The collected evidence does not establish a specific problem']})
        done=analysis_run.run(value['id'],executor)
        self.assertEqual(done['state'],'completed',done.get('error'))
        self.assertEqual(briefing.view('demo','','dev','en')['state'],'saved')

if __name__=='__main__':unittest.main()
