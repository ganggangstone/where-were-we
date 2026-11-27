"""App worker lifecycle with synthetic Git and injected executors; no real AI calls."""
import copy
import json
import os
from pathlib import Path
import sys
import time
import unittest
import os;os.environ.pop('WHERE_WERE_WE_SETTINGS',None)  # fixtures isolate settings through mapcore.ROOT; an inherited settings file would bypass that and be shared
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

    ROUTE='server/items.go::SaveItem'
    STEPS={'task':'steps','targets':[{'repository':'service','target':'@routes:["server/items.go::SaveItem"]'}]}

    def prepare(self,**kwargs):return analysis_run.prepare('demo',lang='en',**kwargs)
    def steps(self):return self.prepare(intent=self.STEPS)
    def seed_map(self):
        """Save the map, structure and groups directly; 분석하기 (full) owns how they are made."""
        data=copy.deepcopy(self.data)
        for route in data['backend_routes']:route.pop('steps',None)  # the steps are the detail these tests ask for
        req=ai_extract.request('demo','dev','en','service')
        ai_extract.record(**req['record_arguments'],result_json=json.dumps(test_ai_extract.agent_answer(req,data)))
        system={**self.SYSTEM,'nodes':[{k:v for k,v in n.items() if k!='jobs'} for n in self.SYSTEM['nodes']]}  # and so are the jobs
        for task,result in (('system',system),('groups',self.GROUPS)):
            req=ai_extract.task_request('demo',task,'dev','en','service');ai_extract.task_record(**req['record_arguments'],result_json=json.dumps(result))
    def two_routes(self):
        """A second endpoint, so one steps intent with two targets makes two tasks."""
        (self.repo/'server/other.go').write_text('func Other() {}\nrouter.GET("/other", Other)\n')
        self.git('add','.');self.git('commit','-qm','Independent second endpoint')
        self.data['backend_routes'].append({'file':'server/other.go','line':2,'quote':'router.GET("/other", Other)',
            'method':'GET','path':'/other','function':'Other'})
        self.seed_map()
        return {'task':'steps','targets':[self.STEPS['targets'][0],{'repository':'service','target':'@routes:["server/other.go::Other"]'}]}
    def routes(self):return {'routes':{self.ROUTE:{'steps':[],'unknown':'No further steps established'}}}
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

    def test_explicit_steps_target_only_and_retry_keeps_intent(self):
        (self.repo/'server/other.go').write_text('func Other() {}\nrouter.GET("/other", Other)\n')
        self.git('add','.');self.git('commit','-qm','Independent second endpoint')
        self.data['backend_routes'].append({'file':'server/other.go','line':2,'quote':'router.GET("/other", Other)',
            'method':'GET','path':'/other','function':'Other'})
        self.seed_map()
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
            self.assertEqual({s['file'] for s in p['sources']},{'server/items.go','pages/items.vue'})  # the route and the screen code that sends it
            return self.fake(prompt,**kwargs)
        done=analysis_run.run(again['id'],fake)
        self.assertEqual(done['state'],'completed',done.get('error'));self.assertEqual(len(calls),1)

    def test_cli_prepare_preserves_selected_intent_and_overview_keeps_proven_details(self):
        import subprocess
        self.seed_map()
        intent={'task':'steps','targets':[{'repository':'service','target':'/items'}]}
        argv=[sys.executable,'-B',str(Path(analysis_run.__file__)),'prepare','demo','--lang','en','--intent',json.dumps(intent)]
        result=subprocess.run(argv,env={**os.environ,'WHERE_WERE_WE_ROOT':str(self.home)},text=True,capture_output=True,check=True)
        value=json.loads(result.stdout);self.assertEqual(value['intent'],intent)
        done=analysis_run.run(value['id'],self.fake);self.assertEqual(done['state'],'completed',done.get('error'))
        flow=copy.deepcopy(self.raw()['dev']['task_outputs']['flows']['routes']['server/items.go::SaveItem'])
        (self.repo/'independent.txt').write_text('An independent file without route dependencies.\n')
        self.git('add','.');self.git('commit','-qm','Independent text change')
        self.seed_map()
        carried=self.raw()['dev']['task_outputs']['flows']['routes']['server/items.go::SaveItem']
        self.assertEqual(carried['steps'],flow['steps'])
        self.assertEqual(carried['verified_commit'],flow['commit'])
        self.assertEqual(carried['carried_from'],flow['commit'])

    def test_small_invalid_nested_claims_are_not_silently_filtered(self):
        self.seed_map()
        jobs={'task':'jobs','targets':[{'repository':'service','target':'api'}]}
        for fault,intent in (('language',self.STEPS),('step_target',self.STEPS),('jobs_language',jobs)):
            with self.subTest(fault=fault):
                before=self.raw();value=self.prepare(intent=intent)
                def executor(prompt,**kwargs):
                    if fault=='language':return {**self.routes(),'lang':'ko'}
                    if fault=='step_target':return {'routes':{'unknown::handler':{'steps':[],'unknown':'Not established'}}}
                    return {'jobs':[],'unknown':[{'text':'No jobs established','needs':'read'}],'language':'ko'}
                done=analysis_run.run(value['id'],executor)
                self.assertEqual(done['state'],'failed',done.get('error'))
                self.assertEqual(self.raw(),before)

    def test_evidence_accepts_literal_unicode_and_tab_in_tracked_path(self):
        path='작업\t명령.py'
        (self.repo/path).write_text('run_command()\n')
        self.git('add','.');self.git('commit','-qm','Add named command')
        commit=self.git('rev-parse','HEAD').strip()
        evidence={'file':path,'line':1,'quote':'run_command()'}
        analysis_run._strict_result('analysis',{'inspected':[evidence]},str(self.repo),commit)

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

    def test_provider_failure_keeps_saved_results_and_retry_only_finishes_missing_tasks(self):
        intent=self.two_routes();calls=[]
        def executor(prompt,**kwargs):
            calls.append(prompt)
            if 'server/other.go::Other' in prompt:raise ValueError('Synthetic provider unavailable')  # also on the one retry
            return self.fake(prompt,**kwargs)
        value=self.prepare(intent=intent);failed=analysis_run.run(value['id'],executor)
        self.assertEqual(failed['state'],'failed')
        self.assertEqual([t['task'] for t in failed['completed_tasks']],['steps'])
        saved=copy.deepcopy(self.raw()['dev']['task_outputs']['flows']['routes'][self.ROUTE])
        retried=analysis_run.retry(value['id']);self.assertNotEqual(retried['id'],value['id'])
        self.assertEqual([t['target'] for t in retried['tasks']],['@routes:["server/other.go::Other"]'])
        done=analysis_run.run(retried['id'],self.fake)
        self.assertEqual(done['state'],'completed',done.get('error'))
        self.assertEqual(self.raw()['dev']['task_outputs']['flows']['routes'][self.ROUTE],saved)

    def test_invalid_output_is_failed_without_publishing(self):
        self.seed_map();before=self.raw();value=self.steps()
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

    def test_pin_change_during_execution_rejects_save(self):
        self.seed_map();before=self.raw();value=self.steps()
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
        self.seed_map();value=self.steps()
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
        self.seed_map();value=self.steps();before=self.raw()
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
        self.seed_map();value=self.steps()
        with patch.object(cli_executor,'availability',return_value={'available':True,'authenticated':True,'account':current}),patch.object(analysis_run.subprocess,'Popen') as spawn:
            with self.assertRaisesRegex(ValueError,'account changed'):analysis_run.start(value['id'],shown)
            spawn.assert_not_called()
        self.assertEqual(analysis_run.status(value['id'])['error']['code'],'CLI_ACCOUNT_CHANGED')

    def fake_cli(self):
        import cli_executor
        folder=Path(self.temp.name)/'bin';folder.mkdir()
        fixtures=Path(self.temp.name)/'fixtures.json'
        fixtures.write_text(json.dumps({'flags':' '.join(cli_executor.REQUIRED_FLAGS)}))
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
    result={'routes':{k:{'steps':[],'unknown':'No further steps established'} for k in payload['input']['routes']}}
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
        self.seed_map()
        with patch.dict(os.environ,self.fake_cli()):
            account=cli_executor.availability()['account'];value=self.steps()
            started=analysis_run.start(value['id'],account)
            self.assertEqual(started['account'],account)
            done=self.wait_terminal(value['id'])
        self.assertEqual(done['state'],'completed',done.get('error'))
        self.assertEqual([t['task'] for t in done['completed_tasks']],['steps'])

    def test_detached_cancellation_stops_only_its_owned_fake_cli_without_saving(self):
        import cli_executor
        env=self.fake_cli();marker=Path(self.temp.name)/'model-started';env['TEST_ANALYSIS_PAUSE']=str(marker)
        self.seed_map();before=self.raw()
        with patch.dict(os.environ,env):
            account=cli_executor.availability()['account'];value=self.steps()
            analysis_run.start(value['id'],account)
            until=time.monotonic()+10
            while not marker.exists() and time.monotonic()<until:time.sleep(.05)
            self.assertTrue(marker.exists(),'Synthetic model did not start')
            analysis_run.cancel(value['id']);done=self.wait_terminal(value['id'])
        self.assertEqual(done['state'],'cancelled');self.assertEqual(self.raw(),before)

    def test_program_jobs_and_briefing_require_explicit_intent(self):
        self.SYSTEM={**self.SYSTEM,'nodes':self.SYSTEM['nodes']+[{'id':'web','name':'Web','kind':'program','code':['pages'],
            'ev':[{'file':'pages/items.vue','line':1,'quote':'<button @click="saveItem">'}]}]}
        self.data={**self.data,'screens':[]};self.GROUPS={'groups':[],'names':{},'request_names':{}}
        self.seed_map()
        raw=self.raw();self.assertFalse(raw['dev']['task_outputs'].get('jobs',{}).get('nodes'))
        value=self.prepare(intent={'task':'jobs','targets':[{'repository':'service','target':'api'}]})
        calls=[]
        def jobs(prompt,**kwargs):
            p=json.loads(prompt.split('\n',1)[1]);calls.append(p)
            self.assertEqual(p['input']['node']['id'],'api')
            self.assertEqual({s['file'] for s in p['sources']},{'server/items.go'})
            return {'jobs':[],'unknown':[{'text':'No jobs established by supplied source','needs':'read'}]}
        done=analysis_run.run(value['id'],jobs)
        self.assertEqual(done['state'],'completed',done.get('error'));self.assertEqual(len(calls),1)
        self.assertEqual(done['input_stats']['by_kind'],{'jobs':1})
        raw=self.raw();self.assertEqual(raw['dev']['task_outputs']['jobs']['nodes']['api']['source'],'ai')
        # Frozen briefing evidence changes schedule a real briefing task, whose claims still pass its validator.
        # Supply a minimal frozen evidence window directly, without any external collection.
        raw['changes']={'last_result':{'since':'2026-10-01T00:00:00+00:00','at':'2026-10-02T00:00:00+00:00','changed':True,'evidence':{
            'commits':{'dev':{'from':self.commit,'to':self.commit}},'comparison':{'since':'last_refresh','since_time':''},
            'structure':{},'prs':[],'issues':[],'collection':{}}}}
        project._publish('demo','service',raw,{},collection=False)
        # Changed briefing evidence never adds a briefing task to another intent.
        value=self.steps();self.assertEqual([t['task'] for t in value['tasks']],['steps']);analysis_run.cancel(value['id'])
        value=self.prepare(intent={'task':'briefing'});self.assertEqual([t['task'] for t in value['tasks']],['briefing'])
        def executor(prompt,**kwargs):
            payload=json.loads(prompt.split('\n',1)[1]);self.assertIn('sources',payload)
            return json.dumps({'cards':[],'unknown':['The collected evidence does not establish a specific problem']})
        done=analysis_run.run(value['id'],executor)
        self.assertEqual(done['state'],'completed',done.get('error'))
        self.assertEqual(briefing.view('demo','','dev','en')['state'],'saved')
        self.assertEqual(set(done['input_stats']['by_kind']),{'briefing'});self.assertEqual(sum(done['input_stats']['by_kind'].values()),done['input_stats']['calls'])

    # Detail tasks: locally chosen bounded input, a fixed number of calls, each retried once, cited by integer ref.
    @staticmethod
    def packet(prompt):return json.loads(prompt.split('\n',1)[1])
    @staticmethod
    def ref(packet,text):return next(row[0] for s in packet['sources'] for row in s['lines'] if text in row[2])
    def steps_reply(self,prompt):
        p=self.packet(prompt)
        self.assertNotIn('needs:[',prompt);self.assertNotIn('"needs"',json.dumps(p['schema']))
        return {'routes':{k:{'name':'Save item','steps':[{'ref':self.ref(p,'db.Table'),'lane':'저장소','text':'Store the item'}]} for k in p['input']['routes']}}

    def test_steps_one_call_rebuilds_evidence_from_refs(self):
        self.seed_map();calls=[]
        def executor(prompt,**kwargs):calls.append(prompt);return self.steps_reply(prompt)
        value=self.steps();done=analysis_run.run(value['id'],executor)
        self.assertEqual(done['state'],'completed',done.get('error'));self.assertEqual(len(calls),1)
        self.assertEqual(done['input_stats']['by_kind'],{'steps':1})
        flow=self.raw()['dev']['task_outputs']['flows']['routes'][self.ROUTE]
        self.assertEqual([(s['file'],s['line'],s['quote'],s['text']) for s in flow['steps']],[('server/items.go',2,'db.Table("items").Create(item)','Store the item')])
        self.assertNotIn('unknown',flow)

    def test_steps_invalid_reply_is_retried_once_then_fails_keeping_the_old_flow(self):
        self.seed_map()
        for reply in ({'routes':{self.ROUTE:{'steps':[{**self.EV,'lane':'서버','text':'Quote written by the model'}]}}},None):
            with self.subTest(reply=bool(reply)):
                before=self.raw();calls=[]
                def executor(prompt,**kwargs):
                    calls.append(prompt);return reply or {**self.steps_reply(prompt),'needs':[{'file':'server/items.go'}]}
                done=analysis_run.run(self.steps()['id'],executor)
                self.assertEqual(done['state'],'failed');self.assertEqual(len(calls),2);self.assertEqual(self.raw(),before)

        for bad,expected in ((2,'failed'),(1,'completed')):  # a saved flow makes a later request for it a no-op
            with self.subTest(bad=bad):
                before=self.raw();calls=[]
                def executor(prompt,**kwargs):
                    calls.append(prompt)
                    if len(calls)<=bad:return {'routes':{self.ROUTE:{'steps':[{'ref':99999,'lane':'서버','text':'Invented'}]}}}
                    return self.steps_reply(prompt)
                done=analysis_run.run(self.steps()['id'],executor)
                self.assertEqual(done['state'],expected,done.get('error'));self.assertEqual(len(calls),2)
                if expected=='failed':self.assertEqual(self.raw(),before)
    def test_steps_route_over_budget_is_saved_as_not_read(self):
        self.two_routes();other='server/other.go::Other'
        value=self.prepare(intent={'task':'steps','targets':[{'repository':'service','target':json.dumps([self.ROUTE,other]).join(['@routes:',''])}]});calls=[]
        def executor(prompt,**kwargs):
            calls.append(self.packet(prompt));return self.steps_reply(prompt)
        with patch.object(analysis_run,'DETAIL_BYTES',1),patch.object(analysis_run,'MAX_STEPS_CALLS',1):done=analysis_run.run(value['id'],executor)
        self.assertEqual(done['state'],'completed',done.get('error'));self.assertEqual(len(calls),1)
        self.assertEqual(list(calls[0]['input']['routes']),[self.ROUTE])
        flows=self.raw()['dev']['task_outputs']['flows']['routes']
        self.assertTrue(flows[self.ROUTE]['steps'])
        self.assertEqual(flows[other]['steps'],[]);self.assertEqual(flows[other]['unknown'],analysis_run.NOT_READ['en'])

    def test_steps_read_the_screen_code_that_sends_the_request_and_screen_steps_cite_only_it(self):
        self.seed_map()
        for lane_file,expected in (('router.POST','failed'),('fetch("/items"','completed')):
            with self.subTest(screen_step=lane_file):
                before=self.raw();calls=[]
                def executor(prompt,**kwargs):
                    p=self.packet(prompt);calls.append(p)
                    self.assertEqual(p['input']['routes'][self.ROUTE]['callers'],[{'file':'pages/items.vue','line':2}])
                    self.assertIn('pages/items.vue',{s['file'] for s in p['sources']})
                    return {'routes':{self.ROUTE:{'name':'Save item','steps':[{'ref':self.ref(p,lane_file),'lane':'화면','text':'The screen sends the item'},
                        {'ref':self.ref(p,'db.Table'),'lane':'저장소','text':'Store the item'}]}}}
                done=analysis_run.run(self.prepare(intent={'task':'steps','targets':[{'repository':'service','target':'/items'}]})['id'],executor)
                self.assertEqual(done['state'],expected,done.get('error'))
                if expected=='failed':self.assertEqual(len(calls),2);self.assertEqual(self.raw(),before);continue
                steps=self.raw()['dev']['task_outputs']['flows']['routes'][self.ROUTE]['steps']
                self.assertEqual([(x['lane'],x['file'],x['line']) for x in steps],[('화면','pages/items.vue',2),('저장소','server/items.go',2)])

    def test_mcp_screen_step_outside_the_callers_is_not_saved(self):
        self.seed_map()
        req=ai_extract.task_request('demo','steps','dev','en','service','/items')
        self.assertEqual(req['input']['routes'][self.ROUTE]['callers'],[{'file':'pages/items.vue','line':2}])
        self.assertIn('"화면" steps only from those caller and use files',req['prompt'])
        server={'file':'server/items.go','line':4,'quote':'router.POST("/items", SaveItem)','lane':'화면','text':'Pretend screen'}
        screen={'file':'pages/items.vue','line':2,'quote':'fetch("/items",','lane':'화면','text':'The screen sends the item'}
        ai_extract.task_record(**req['record_arguments'],result_json=json.dumps({'routes':{self.ROUTE:{'name':'Save item','steps':[server,screen]}}}))
        steps=self.raw()['dev']['task_outputs']['flows']['routes'][self.ROUTE]['steps']
        self.assertEqual([(x['lane'],x['file']) for x in steps],[('화면','pages/items.vue')])

    def test_callers_put_the_selected_screen_first_and_are_capped(self):
        m={'api_functions':[{'file':f'pages/p{i}.vue','name':f'f{i}','calls':[{'line':i+1,'backend':[{'file':'server/items.go','line':4}]}]} for i in range(5)],
           'screens':[{'path':'/chosen','api_functions':[{'file':'pages/p4.vue','name':'f4'}]}],
           'backend_routes':[{'file':'server/items.go','line':4,'function':'SaveItem','method':'POST','path':'/items','mounted':True}]}
        with patch.object(project,'branch_bundle',lambda raw,branch:raw):
            got=ai_extract.task_input({'dev':m},'steps','dev','/chosen')['routes'][self.ROUTE]['callers']
        self.assertEqual(got,[{'file':'pages/p4.vue','line':5},{'file':'pages/p0.vue','line':1},{'file':'pages/p1.vue','line':2}])

    def test_uses_are_the_selected_screen_lines_that_use_the_caller_function(self):
        (self.repo/'pages/api').mkdir()
        (self.repo/'pages/api/orders.ts').write_text('export function loadOrders() {\n  return api.get("/items")\n}\nexport function get() { return api.get("/items") }\n')
        (self.repo/'pages/orders.vue').write_text('import { loadOrders, get } from "./api/orders"\n'+'const rows = await loadOrders()\n'*4+'get()\nloadOrdersLater()\n')
        self.git('add','.');self.git('commit','-qm','Wrapper and screen');head=self.git('rev-parse','HEAD').strip()
        backend=[{'file':'server/items.go','line':4}]
        m={'api_functions':[{'file':'pages/api/orders.ts','name':'loadOrders','calls':[{'line':2,'backend':backend}]},
                            {'file':'pages/api/orders.ts','name':'get','calls':[{'line':4,'backend':backend}]}],
           'screens':[{'path':'/orders','api_functions':[{'file':'pages/api/orders.ts','name':n,'via':'pages/orders.vue'} for n in ('loadOrders','get')]}],
           'backend_routes':[{'file':'server/items.go','line':4,'function':'SaveItem','method':'POST','path':'/items','mounted':True}]}
        with patch.object(project,'branch_bundle',lambda raw,branch:raw):
            route=ai_extract.task_input({'dev':m},'steps','dev','/orders',str(self.repo),head)['routes'][self.ROUTE]
            # The import line and a longer name are not uses; a name under MIN_USE_NAME is not searched; at most MAX_USES.
            self.assertEqual(route['uses'],[{'file':'pages/orders.vue','line':n} for n in (2,3,4)])
            self.assertEqual(ai_extract.screen_files(route),{'pages/api/orders.ts','pages/orders.vue'})
            self.assertEqual(ai_extract.task_input({'dev':m},'steps','dev','/orders')['routes'][self.ROUTE]['uses'],[])
            self.assertEqual(ai_extract.task_input({'dev':m},'steps','dev','@routes:["server/items.go::SaveItem"]',str(self.repo),head)['routes'][self.ROUTE]['uses'],[])

    def test_steps_read_the_screen_lines_that_use_the_request_and_screen_steps_may_cite_them(self):
        (self.repo/'pages/list.vue').write_text('<form @submit="onSave">\nfunction onSave() { saveItemNow().then(showSaved) }\n</form>\n')
        (self.repo/'pages/other.vue').write_text('<p>saveItemNow</p>\n')
        self.git('add','.');self.git('commit','-qm','Screen that uses the request');self.seed_map()
        raw=self.raw();m=raw['dev']
        for f in m['api_functions']:f['name']='saveItemNow'
        for s in m['screens']:s['api_functions']=[{**f,'name':'saveItemNow','via':'pages/list.vue'} for f in s['api_functions']]
        project._publish('demo','service',raw,{},collection=False)
        sizes={}
        # The completed run uses the screen + its route keys, the target the app sends for the screen's own repository.
        for lane_file,expected,target in (('router.POST','failed','/items'),('saveItemNow().then','completed','/items@routes:'+json.dumps([self.ROUTE]))):
            with self.subTest(screen_step=lane_file):
                before=self.raw();calls=[]
                def executor(prompt,**kwargs):
                    p=self.packet(prompt);calls.append(p);sizes['with']=len(prompt.encode())
                    sizes['without']=len(prompt.encode())-len(json.dumps([s for s in p['sources'] if s['file']=='pages/list.vue']).encode())
                    self.assertEqual(p['input']['routes'][self.ROUTE]['uses'],[{'file':'pages/list.vue','line':2}])
                    self.assertIn('pages/list.vue',{s['file'] for s in p['sources']});self.assertNotIn('pages/other.vue',{s['file'] for s in p['sources']})
                    return {'routes':{self.ROUTE:{'name':'Save item','steps':[{'ref':self.ref(p,lane_file),'lane':'화면','text':'Saving the form sends the item'},
                        {'ref':self.ref(p,'db.Table'),'lane':'저장소','text':'Store the item'}]}}}
                done=analysis_run.run(self.prepare(intent={'task':'steps','targets':[{'repository':'service','target':target}]})['id'],executor)
                self.assertEqual(done['state'],expected,done.get('error'))
                if expected=='failed':self.assertEqual(len(calls),2);self.assertEqual(self.raw(),before);continue
                steps=self.raw()['dev']['task_outputs']['flows']['routes'][self.ROUTE]['steps']
                self.assertEqual([(x['lane'],x['file'],x['line']) for x in steps],[('화면','pages/list.vue',2),('저장소','server/items.go',2)])
                # The step from the screen's own use line is kept with that screen; the server step is shown everywhere.
                self.assertEqual([x.get('screen') for x in steps],['/items',None])
                composed=project.read_bundle('demo')['flows']['routes']['service/'+self.ROUTE]['steps']
                self.assertEqual([x.get('screen') for x in composed],[project.qscreen('service','/items'),None])
        print('\nsteps packet bytes without uses',sizes['without'],'with uses',sizes['with'],file=sys.stderr)
        req=ai_extract.task_request('demo','steps','dev','en','service','/items')
        self.assertIn('state what the user does only when a shown line shows it',req['prompt'])
        # The MCP path takes the same field: it must name the selected screen.
        step={'file':'pages/list.vue','line':2,'quote':'saveItemNow().then','lane':'화면','text':'Saving the form sends the item'}
        record=lambda screen:ai_extract.task_record(result_json=json.dumps({'routes':{self.ROUTE:{'name':'Save item','steps':[{**step,'screen':screen}]}}}),**req['record_arguments'])
        with self.assertRaisesRegex(ValueError,'selected screen'):record('/other')
        record('/items');self.assertEqual(self.raw()['dev']['task_outputs']['flows']['routes'][self.ROUTE]['steps'][0]['screen'],'/items')

    def wrapper_map(self,screens):
        """A wrapper loadOrders in pages/api/orders.ts sending SaveItem, used by the given screens through pages/<screen>.vue."""
        backend=[{'file':'server/items.go','line':4}]
        return {'api_functions':[{'file':'pages/api/orders.ts','name':'loadOrders','calls':[{'line':2,'backend':backend}]}],
                'screens':[{'path':'/'+n,'api_functions':[{'file':'pages/api/orders.ts','name':'loadOrders','via':f'pages/{n}.vue'}]} for n in screens],
                'backend_routes':[{'file':'server/items.go','line':4,'function':'SaveItem','method':'POST','path':'/items','mounted':True}]}

    def test_multi_line_imports_are_not_uses_and_bare_list_names_come_last(self):
        (self.repo/'pages/api').mkdir()
        (self.repo/'pages/api/orders.ts').write_text('export function loadOrders() {\n  return api.get("/items")\n}\n')
        (self.repo/'pages/orders.vue').write_text('import {\n  loadOrders,\n  other\n} from "./api/orders"\nfrom x import (\n    loadOrders,\n)\n'
                                                  'const { loadOrders: alias } = require("./api")\nuse orders::{\n    loadOrders,\n};\n'
                                                  'export {\n  loadOrders,\n}\nconst rows = await loadOrders()\nwatch(id, () => loadOrders())\n')
        self.git('add','.');self.git('commit','-qm','Screen with multi-line imports');head=self.git('rev-parse','HEAD').strip()
        with patch.object(project,'branch_bundle',lambda raw,branch:raw):
            route=ai_extract.task_input({'dev':self.wrapper_map(['orders'])},'steps','dev','/orders',str(self.repo),head)['routes'][self.ROUTE]
        # Lines 2, 6, 8 and 10 sit in import statements; line 13 is a bare name in an export list, kept after the clear uses.
        self.assertEqual(route['uses'],[{'file':'pages/orders.vue','line':n} for n in (15,16,13)])

    def test_a_request_another_screen_also_reaches_still_gets_this_screens_uses(self):
        (self.repo/'pages/api').mkdir()
        (self.repo/'pages/api/orders.ts').write_text('export function loadOrders() {\n  return api.get("/items")\n}\n')
        for n in ('orders','report'):(self.repo/f'pages/{n}.vue').write_text('const rows = await loadOrders()\n')
        self.git('add','.');self.git('commit','-qm','Two screens on one wrapper');head=self.git('rev-parse','HEAD').strip()
        with patch.object(project,'branch_bundle',lambda raw,branch:raw):
            alone=ai_extract.task_input({'dev':self.wrapper_map(['orders'])},'steps','dev','/orders',str(self.repo),head)['routes'][self.ROUTE]
            both=ai_extract.task_input({'dev':self.wrapper_map(['orders','report'])},'steps','dev','/orders',str(self.repo),head)['routes'][self.ROUTE]
            m=self.wrapper_map(['orders']);m['api_functions'].append({'file':'pages/api/report.ts','name':'fetchReport','calls':[{'line':1,'backend':[{'file':'server/items.go','line':4}]}]})
            m['screens'].append({'path':'/report','api_functions':[{'file':'pages/api/report.ts','name':'fetchReport'}]})
            other=ai_extract.task_input({'dev':m},'steps','dev','/orders',str(self.repo),head)['routes'][self.ROUTE]
        # The selected screen's own code reaches the model even when other screens send the request; its steps are kept with it.
        for route in (alone,both,other):self.assertEqual(route['uses'],[{'file':'pages/orders.vue','line':1}])
        self.assertEqual(ai_extract.screen_files(both),{'pages/api/orders.ts','pages/orders.vue'})

    def two_request_screen(self,padding=30):
        """/items sends SaveItem and Other from pages/list.vue (its use on line padding+2) through the wrapper saveItemNow."""
        (self.repo/'server/other.go').write_text('func Other() {}\nrouter.GET("/other", Other)\n')
        (self.repo/'pages/items.vue').write_text('<button @click="saveItem">Save item</button>\nfetch("/items", {method:"POST"})\nfetch("/other")\n')
        (self.repo/'pages/list.vue').write_text('<form @submit="onSave">\n'+'<p>padding line of the screen</p>\n'*padding+'function onSave() { saveItemNow().then(showSaved) }\n</form>\n')
        self.git('add','.');self.git('commit','-qm','Screen with two requests')
        self.data['screens'][0]['calls'].append({'file':'pages/items.vue','line':3,'quote':'fetch("/other")','method':'GET','path':'/other'})
        self.data['backend_routes'].append({'file':'server/other.go','line':2,'quote':'router.GET("/other", Other)','method':'GET','path':'/other','function':'Other'})
        self.seed_map();raw=self.raw();m=raw['dev']
        for f in m['api_functions']:f['name']='saveItemNow'
        for s in m['screens']:s['api_functions']=[{**f,'name':'saveItemNow','via':'pages/list.vue'} for f in s['api_functions']]
        project._publish('demo','service',raw,{},collection=False)

    def test_a_partly_fresh_screen_asks_its_missing_requests_with_the_screen_uses(self):
        self.two_request_screen();other='server/other.go::Other'
        done=analysis_run.run(self.steps()['id'],self.fake);self.assertEqual(done['state'],'completed',done.get('error'))
        value=self.prepare(intent={'task':'steps','targets':[{'repository':'service','target':'/items'}]})
        self.assertEqual([t['target'] for t in value['tasks']],['/items@routes:'+json.dumps([other])])
        req=ai_extract.task_request('demo','steps','dev','en','service',value['tasks'][0]['target'])
        self.assertEqual(list(req['input']['routes']),[other])
        self.assertEqual(req['input']['routes'][other]['uses'],[{'file':'pages/list.vue','line':32}])
        with self.assertRaisesRegex(ValueError,'route targets'):ai_extract.task_request('demo','steps','dev','en','service','/items@routes:["server/none.go::None"]')
        calls=[]
        def executor(prompt,**kwargs):
            calls.append(self.packet(prompt));return self.fake(prompt,**kwargs)
        done=analysis_run.run(value['id'],executor);self.assertEqual(done['state'],'completed',done.get('error'))
        self.assertEqual(list(calls[0]['input']['routes']),[other])

    def test_a_small_use_file_goes_whole_once_per_call_and_a_large_one_in_windows(self):
        self.two_request_screen();sizes={}
        for cap,whole in ((analysis_run.USE_FILE_BYTES,True),(100,False)):
            with self.subTest(whole=whole):
                calls=[]
                def executor(prompt,**kwargs):
                    p=self.packet(prompt);calls.append(p);sizes[whole]=len(prompt.encode())
                    rows=[(s.get('routes') or [s.get('route')],r[1]) for s in p['sources'] if s['file']=='pages/list.vue' for r in s['lines']]
                    if whole:
                        # The opening form tag (31 lines above the use) is shown, once, for both requests.
                        self.assertEqual([n for _,n in rows],list(range(1,34)));self.assertEqual(rows[0][0],[self.ROUTE,'server/other.go::Other'])
                        self.assertIn('supplied whole',p['prompt'])
                    else:self.assertNotIn(1,[n for _,n in rows]);self.assertIn(32,[n for _,n in rows])
                    return self.fake(prompt,**kwargs)
                with patch.object(analysis_run,'USE_FILE_BYTES',cap):
                    done=analysis_run.run(self.prepare(intent={'task':'steps','targets':[{'repository':'service','target':'/items'}]})['id'],executor)
                self.assertEqual(done['state'],'completed',done.get('error'));self.assertEqual(len(calls),1)
                raw=self.raw();raw['dev']['task_outputs']['flows']['routes']={};raw['flows']={'routes':{}}
                for r in raw['dev']['backend_routes']:r.pop('flow',None)
                project._publish('demo','service',raw,{},collection=False)
        print('\nsteps packet bytes with use windows',sizes[False],'with whole use files',sizes[True],file=sys.stderr)

    def test_jobs_one_bounded_call_with_files_read_note(self):
        for i in range(20):(self.repo/f'server/pad{i:02}.txt').write_text('ordinary padding line\n'*600)
        self.git('add','.');self.git('commit','-qm','Many program files');self.seed_map()
        prompts=[]
        def executor(prompt,**kwargs):
            prompts.append(prompt);p=self.packet(prompt);ref=self.ref(p,'router.POST')
            self.assertEqual(p['input']['node']['id'],'api');self.assertLessEqual(len({s['file'] for s in p['sources']}),analysis_run.MAX_JOB_FILES)
            return {'jobs':[{'name':'Save','what':'Saves an item','starts_when':'POST /items','trigger':{'ref':ref},'made_by':[],
                             'steps':[{'ref':self.ref(p,'db.Table'),'lane':'저장소','text':'Store the item'}]}]}
        done=analysis_run.run(self.prepare(intent={'task':'jobs','targets':[{'repository':'service','target':'api'}]})['id'],executor)
        self.assertEqual(done['state'],'completed',done.get('error'));self.assertEqual(len(prompts),1)
        self.assertLess(len(prompts[0].encode()),analysis_run.DETAIL_BYTES+16*1024)
        saved=self.raw()['dev']['task_outputs']['jobs']['nodes']['api']
        self.assertEqual(saved['jobs'][0]['trigger'],{'file':'server/items.go','line':4,'quote':'router.POST("/items", SaveItem)'})
        self.assertEqual(saved['jobs'][0]['steps'][0]['line'],2)
        self.assertEqual(saved['unknown'],[{'text':'8 of 21 files read.','needs':'read'}])

    def test_jobs_small_program_files_go_whole_and_no_note_when_all_were_read(self):
        (self.repo/'server/hooks.go').write_text('func Start() {}\n'+'// spacer comment line\n'*30+'func Stop() { close(db) }\n')
        self.git('add','.');self.git('commit','-qm','Start and stop hooks');self.seed_map();sent=[]
        def executor(prompt,**kwargs):
            p=self.packet(prompt);sent.extend((s['file'],row[1]) for s in p['sources'] for row in s['lines'])
            return {'jobs':[],'unknown':[{'text':'No jobs established','needs':'read'}]}
        done=analysis_run.run(self.prepare(intent={'task':'jobs','targets':[{'repository':'service','target':'api'}]})['id'],executor)
        self.assertEqual(done['state'],'completed',done.get('error'))
        self.assertIn(('server/hooks.go',32),sent)  # the line after the signal window
        self.assertEqual(self.raw()['dev']['task_outputs']['jobs']['nodes']['api']['unknown'],[{'text':'No jobs established','needs':'read'}])

    def test_jobs_ref_outside_the_supplied_program_lines_is_rejected(self):
        self.seed_map();before=self.raw();calls=[]
        def executor(prompt,**kwargs):
            calls.append(prompt);return {'jobs':[{'name':'Fake','what':'x','starts_when':'x','trigger':{'ref':99999},'made_by':[],'steps':[]}]}
        done=analysis_run.run(self.prepare(intent={'task':'jobs','targets':[{'repository':'service','target':'api'}]})['id'],executor)
        self.assertEqual(done['state'],'failed');self.assertEqual(len(calls),2);self.assertEqual(self.raw(),before)

    def briefing_prs(self,count,body=1000,issues=()):
        self.seed_map();raw=self.raw()
        prs=[{'number':n,'title':f'Fix problem number {n}','body':f'Body of change {n}. '+'x'*body,'merged_at':f'2026-10-01T12:{n:02d}:00+00:00',
              'base':'dev','branch':f'fix-{n}','issues':[]} for n in range(1,count+1)]
        raw['changes']={'last_result':{'since':'2026-10-01T00:00:00+00:00','at':'2026-10-02T00:00:00+00:00','changed':True,'evidence':{
            'commits':{'dev':{'from':self.commit,'to':self.commit}},'comparison':{'since':'last_refresh','since_time':''},
            'structure':{},'prs':prs,'issues':list(issues),'collection':{}}}}
        project._publish('demo','service',raw,{},collection=False)
        return self.prepare(intent={'task':'briefing'})
    def briefing_reply(self,prompt,quote=None):
        p=self.packet(prompt);texts={s['id']:s['text'] for s in p['sources']}
        unknown={'text':'Not established','unknown':True}
        return {'cards':[{'id':f'fix-{pr["number"]}','title':pr['title'],'priority':'medium','prs':[pr['id']],'terms':[],
                          **{f:unknown for f in briefing.FIELDS},'problem':{'text':'The problem','evidence':[{'source':pr['title_source'],'quote':quote or texts[pr['title_source']]}]}}
                         for pr in p['input']['prs']],'unknown':[]}

    def test_briefing_small_set_one_call_and_bad_quote_retried_once(self):
        # An issue no PR links is not change evidence and is not sent.
        value=self.briefing_prs(3,issues=[{'number':90+n,'title':f'Old unrelated issue {n}','body':'y'*4000,'url':f'https://github.com/o/r/issues/{90+n}'} for n in range(3)]);calls=[]
        def executor(prompt,**kwargs):
            calls.append(prompt);return self.briefing_reply(prompt,'invented quote text' if len(calls)==1 else None)
        done=analysis_run.run(value['id'],executor)
        self.assertEqual(done['state'],'completed',done.get('error'));self.assertEqual(len(calls),2);self.assertEqual(value['announced']['total'],1)
        # The retry names what the check rejected; the first ask does not.
        self.assertIn("no exact text 'invented quote text'",calls[1]);self.assertNotIn('rejected',calls[0])
        self.assertFalse([s for c in calls for s in self.packet(c)['input']['sources'] if s.get('kind')=='issue'])
        self.assertEqual(len(briefing.stored('demo')['results'][briefing.key('','dev','en')]['cards']),3)

    def test_briefing_answer_that_is_not_json_is_retried_with_the_parse_error(self):
        import cli_executor
        value=self.briefing_prs(2);calls=[]
        def executor(prompt,**kwargs):
            calls.append(prompt)
            if len(calls)==1:raise cli_executor.CLIExecutionError('CLI_INVALID_OUTPUT',"Claude Code did not return the requested JSON object (Expecting ',' delimiter at character 9)")
            return self.briefing_reply(prompt)
        done=analysis_run.run(value['id'],executor)
        self.assertEqual(done['state'],'completed',done.get('error'));self.assertEqual(len(calls),2)
        self.assertIn('at character 9',calls[1]);self.assertIn('bracket nesting',calls[1])

    def test_briefing_rejected_twice_keeps_the_reason(self):
        value=self.briefing_prs(2);calls=[]
        def executor(prompt,**kwargs):
            calls.append(prompt);reply=self.briefing_reply(prompt);reply['cards']=reply['cards'][:1];return reply
        done=analysis_run.run(value['id'],executor)
        self.assertEqual(done['state'],'failed');self.assertEqual(len(calls),2)
        self.assertIn('missing',calls[1]);self.assertIn('Every collected PR must be covered',done['error']['message'])
        self.assertIn(':pr:',done['error']['message'])

    def test_briefing_many_prs_split_into_at_most_four_calls_and_older_prs_left_out_plainly(self):
        calls=[]
        def executor(prompt,**kwargs):calls.append(self.packet(prompt));return self.briefing_reply(prompt)
        with patch.object(analysis_run,'DETAIL_BYTES',6*1024):
            value=self.briefing_prs(12);done=analysis_run.run(value['id'],executor)
        self.assertEqual(value['announced']['total'],len(calls))  # the announced count is the planned calls
        self.assertEqual(done['state'],'completed',done.get('error'));self.assertTrue(1<len(calls)<=analysis_run.MAX_BRIEFING_CALLS)
        self.assertTrue(all(len(s['text'])<=analysis_run.BRIEF_BODY_CHARS for p in calls for s in p['sources']))
        saved=briefing.stored('demo')['results'][briefing.key('','dev','en')]
        self.assertEqual(len(saved['cards']),12);self.assertEqual(saved['pr_count'],12)
        value=self.briefing_prs(40,3000);calls=[]
        with patch.object(analysis_run,'DETAIL_BYTES',6*1024):done=analysis_run.run(value['id'],executor)
        self.assertEqual(done['state'],'completed',done.get('error'));self.assertEqual(len(calls),analysis_run.MAX_BRIEFING_CALLS)
        sent=[int(pr['number']) for p in calls for pr in p['input']['prs']]
        self.assertEqual(sorted(sent),list(range(41-len(sent),41)))  # the newest PRs
        saved=briefing.stored('demo')['results'][briefing.key('','dev','en')]
        self.assertEqual(saved['pr_count'],40);self.assertEqual(len(saved['left_out']),40-len(sent))
        self.assertIn(f'leaves out {40-len(sent)} older PRs',saved['unknown'][0])
        ctx={'input':{'prs':[{'id':'r:pr:1','merged_at':'2026-10-01T00:00:00+00:00'},{'id':'r:pr:2','merged_at':'2026-10-02T00:00:00+00:00'}],'has_changes':True},'sources':{'s':{'text':'quoted text','url':None}}}
        card={'id':'c','title':'t','prs':['r:pr:1'],**{f:{'text':'x','unknown':True} for f in briefing.FIELDS}}
        with self.assertRaises(ValueError):briefing.normalize({'cards':[card],'unknown':['older left out'],'left_out':['r:pr:2']},ctx)  # a newer PR cannot be left out
        with self.assertRaises(ValueError):briefing.normalize({'cards':[{**card,'prs':['r:pr:2']}],'left_out':['r:pr:1']},ctx)  # nor silently
        self.assertEqual(briefing.normalize({'cards':[{**card,'prs':['r:pr:2']}],'unknown':['older left out'],'left_out':['r:pr:1']},ctx)['left_out'],['r:pr:1'])

if __name__=='__main__':unittest.main()
