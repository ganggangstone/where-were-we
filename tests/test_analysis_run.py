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
        self.assertEqual(ai_extract.plan('demo',lang='en')['tasks'],[])
        again=self.prepare()
        done=analysis_run.run(again['id'],lambda *a,**k:self.fail('Current analysis must not call a model'))
        self.assertEqual(done['state'],'completed')

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

    def test_oversized_source_fails_honestly_without_executor(self):
        value=self.prepare();before=self.raw()
        with patch.object(analysis_run,'MAX_FILE_BYTES',5):
            done=analysis_run.run(value['id'],lambda *a,**k:self.fail('Input exceeds limit'))
        self.assertEqual(done['error']['code'],'source_too_large');self.assertEqual(self.raw(),before)

    def test_large_binary_assets_are_omitted_but_large_text_is_rejected(self):
        (self.repo/'picture.png').write_bytes(b'X'*400_000)
        (self.repo/'binary-unknown').write_bytes(b'\x00'*400_000)
        self.git('add','.');self.git('commit','-qm','Synthetic binary assets')
        commit=self.git('rev-parse','HEAD').strip()
        exported=analysis_run.export_source(str(self.repo),commit)
        self.assertEqual({x['reason'] for x in exported[0]['omitted']},{'binary_asset','binary'})
        (self.repo/'huge.txt').write_text('text source '*40000)
        self.git('add','.');self.git('commit','-qm','Synthetic oversized text')
        with self.assertRaisesRegex(ValueError,'tracked file exceeds'):
            analysis_run.export_source(str(self.repo),self.git('rev-parse','HEAD').strip())
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

    def test_program_jobs_and_briefing_are_executed_as_sequential_tasks(self):
        self.data={**self.data,'screens':[]}
        value=self.prepare();done=analysis_run.run(value['id'],self.fake)
        self.assertEqual(done['state'],'completed',done.get('error'))
        raw=self.raw();node=raw['dev']['task_outputs']['jobs']['nodes']['api']
        self.assertEqual(node['source'],'ai')
        # Frozen briefing evidence changes schedule a real briefing task, whose claims still pass its validator.
        # Supply a minimal frozen evidence window directly, without any external collection.
        raw['changes']={'last_result':{'since':'2026-10-01T00:00:00+00:00','at':'2026-10-02T00:00:00+00:00','changed':True,'evidence':{
            'commits':{'dev':{'from':self.commit,'to':self.commit}},'comparison':{'since':'last_refresh','since_time':''},
            'structure':{},'prs':[],'issues':[],'collection':{}}}}
        project._publish('demo','service',raw,{},collection=False)
        value=self.prepare();self.assertEqual([t['task'] for t in value['tasks']],['briefing'])
        def executor(prompt,**kwargs):
            payload=json.loads(prompt.split('\n',1)[1]);self.assertIn('sources',payload)
            return json.dumps({'cards':[],'unknown':['The collected evidence does not establish a specific problem']})
        done=analysis_run.run(value['id'],executor)
        self.assertEqual(done['state'],'completed',done.get('error'))
        self.assertEqual(briefing.view('demo','','dev','en')['state'],'saved')

if __name__=='__main__':unittest.main()
