"""AI analysis tests use synthetic commits and a fake AI process only."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import mapcore
import project
import ai_extract

class Analysis(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.repo=Path(self.temp.name)/'code';self.repo.mkdir()
        self.home=Path(self.temp.name)/'maps'
        self.patch=patch.object(mapcore,'ROOT',str(self.home));self.patch.start();self.addCleanup(self.patch.stop)
        real_run=subprocess.run
        def guard(command,**kwargs):
            if Path(str(command[0])).name=='claude':raise AssertionError('Real AI calls are forbidden in tests; supply a fake runner')
            return real_run(command,**kwargs)
        block=patch('subprocess.run',side_effect=guard);block.start();self.addCleanup(block.stop)
        self.git('init','-q');self.git('config','user.name','Demo');self.git('config','user.email','demo@example.invalid')
        for name,text in {'pages/items.vue':'<button @click="saveItem">Save item</button>\nfetch("/items", {method:"POST"})\n',
                          'server/items.go':'func SaveItem() {\n db.Table("items").Create(item)\n}\nrouter.POST("/items", SaveItem)\n'}.items():
            p=self.repo/name;p.parent.mkdir(exist_ok=True);p.write_text(text)
        self.git('add','.');self.git('commit','-qm','Synthetic code')
        self.commit=self.git('rev-parse','HEAD').strip()
        self.conf=project.configure('demo',{'repositories':[{'id':'service','path':str(self.repo),'refs':{'dev':'HEAD','main':None}}]})
        self.data={'screens':[{'path':'/items','heading':'Items','file':'pages/items.vue','line':1,'quote':'<button @click="saveItem">',
            'calls':[{'file':'pages/items.vue','line':2,'quote':'fetch("/items",','method':'POST','path':'/items'}]}],
            'backend_routes':[{'file':'server/items.go','line':4,'quote':'router.POST("/items", SaveItem)',
             'method':'POST','path':'/items','function':'SaveItem',
             'tables':[{'name':'items','file':'server/items.go','line':2,'quote':'db.Table("items").Create(item)'}],
             'steps':[{'file':'server/items.go','line':2,'quote':'db.Table("items").Create(item)','lane':'저장소','text':'Store the item','uncertain':False}]}],
            'unknown':['Authentication was not established.']}
        project.publish('demo','service',{'dev':{'repo':str(self.repo),'commit':self.commit,'ref':'HEAD','screens':[],
            'api_functions':[],'backend_routes':[],'models':{},'file_screens':{},'unresolved_calls':[],'backend_routes_without_screen':[]}},{'fingerprint':project.fingerprint(self.conf['repositories'][0])})
    def git(self,*args):
        return subprocess.run(['git','-C',str(self.repo),*args],check=True,capture_output=True,text=True).stdout
    def normalize(self,data=None):
        return ai_extract.normalize(self.data if data is None else data,str(self.repo),self.commit,'HEAD')
    def test_vue_go_map_and_steps_have_verified_source_evidence(self):
        m,flows=self.normalize()
        self.assertEqual(m['backend_routes'][0]['tables'],['items'])
        self.assertEqual(m['api_functions'][0]['calls'][0]['connection_basis'],'ai')
        self.assertEqual(m['file_screens']['server/items.go'],['/items'])
        self.assertEqual(m['analysis']['source'],'ai')
        self.assertIn('Authentication',m['analysis']['unknown'][0])
        self.assertEqual(flows['routes']['server/items.go::SaveItem']['steps'][0]['text'],'Store the item')
    def test_fabricated_paths_quotes_and_unknown_targets_are_not_published(self):
        data=copy.deepcopy(self.data)
        data['screens'][0]['calls'][0]['quote']='this is fabricated'
        data['backend_routes'][0]['tables'][0]['file']='../outside'
        m,flows=self.normalize(data)
        self.assertEqual(m['api_functions'],[])
        self.assertEqual(m['backend_routes'][0]['tables'],[])
        self.assertGreater(m['analysis']['rejected'],0)
        data['backend_routes'][0]['quote']='invented declaration'
        data['screens'][0]['file']='not-in-the-commit.vue'
        with self.assertRaisesRegex(ValueError,'evidence'):self.normalize(data)
    def test_ai_action_is_explicit_cached_and_does_not_modify_the_checkout(self):
        calls=[]
        def fake(command,**kwargs):
            calls.append((command,kwargs))
            return subprocess.CompletedProcess(command,0,json.dumps(self.data),'')
        before=self.git('status','--porcelain')
        ai_extract.analyze('demo','dev','en',runner=fake)
        m=project.read_bundle('demo')['dev']
        self.assertEqual(m['screens'][0]['source_path'],'/items')
        self.assertEqual(len(calls),1)
        self.assertIn('--allowedTools',calls[0][0]);self.assertEqual(Path(calls[0][1]['cwd']).resolve(),self.repo.resolve())
        self.assertIn(self.commit,calls[0][1]['input'])
        ai_extract.analyze('demo','dev','en',runner=fake)
        self.assertEqual(len(calls),1)
        self.assertEqual(self.git('status','--porcelain'),before)
    def test_normal_refresh_retains_ai_map_and_marks_changed_commit(self):
        import runpy
        self.git('remote','add','origin',str(self.repo))
        m,_=self.normalize()
        folder=self.home/'stage';folder.mkdir();(folder/'dev.json').write_text(json.dumps(m))
        (self.repo/'server/items.go').write_text((self.repo/'server/items.go').read_text()+'// changed\n')
        self.git('add','.');self.git('commit','-qm','Synthetic change')
        real_run=subprocess.run;commands=[]
        def run(command,**kwargs):
            commands.append(command)
            if any(str(x).endswith('/collect.py') for x in command):return subprocess.CompletedProcess(command,0,'','')
            return real_run(command,**kwargs)
        with patch.object(sys,'argv',['refresh.py','stage',str(self.repo)]),patch.dict(os.environ,{'WHERE_WERE_WE_REFS':json.dumps({'dev':'HEAD','main':None})}),patch('subprocess.run',side_effect=run):
            runpy.run_path(str(Path(__file__).resolve().parents[1]/'refresh.py'),run_name='__main__')
        refreshed=json.loads((folder/'dev.json').read_text())
        self.assertEqual(refreshed['commit'],self.commit)
        self.assertTrue(refreshed['analysis']['stale'])
        self.assertNotEqual(refreshed['analysis']['observed_commit'],self.commit)
        self.assertFalse(any(command[0]=='claude' for command in commands))

    def test_isolated_cli_action_and_split_repo_composition(self):
        import shutil
        other=self.repo.parent/'api';shutil.copytree(self.repo,other)
        conf=project.configure('split',{'repositories':[
            {'id':'web','path':str(self.repo),'refs':{'dev':'HEAD','main':None},'layout':{'backend':None},'api_targets':['api']},
            {'id':'api','path':str(other),'refs':{'dev':'HEAD','main':None},'layout':{'frontend':None}}]})
        for repo in conf['repositories']:
            m=project.empty_map();m.update(repo=repo['path'],commit=self.commit,ref='HEAD')
            project.publish('split',repo['id'],{'dev':m},{'fingerprint':project.fingerprint(repo)})
        binary=self.repo.parent/'bin';binary.mkdir()
        output=self.repo.parent/'ai-output.json';output.write_text(json.dumps(self.data))
        cli=binary/'claude';cli.write_text('#!'+sys.executable+'\nimport os,sys\nfrom pathlib import Path\nassert "Analyze the tracked source" in sys.stdin.read()\nprint(Path(os.environ["FAKE_AI_JSON"]).read_text())\n');cli.chmod(0o755)
        env=dict(os.environ,WHERE_WERE_WE_ROOT=str(self.home),PATH=str(binary)+os.pathsep+os.environ['PATH'],FAKE_AI_JSON=str(output))
        for rid in ('web','api'):
            result=subprocess.run([sys.executable,'-I','-B',str(Path(os.environ['WHERE_WERE_WE_RUNTIME'])/'backend/project.py') if os.environ.get('WHERE_WERE_WE_RUNTIME') else project.__file__,'action','split','ai_extract.py','dev','en','--repository',rid],env=env,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
        m=mapcore.Map('split');request=m.requests('/@web/items')[0]
        self.assertEqual(request['route']['repository'],'api')
        self.assertEqual(request['connection_basis'],'configured')
        self.assertEqual(request['route']['flow']['steps'][0]['file'],'api/server/items.go')
        self.assertEqual(request['route']['evidence'][0]['file'],'api/server/items.go')
        self.assertEqual(request['route']['table_evidence'][0]['file'],'api/server/items.go')
        self.assertEqual(m.m['repositories'][0]['analysis']['dev']['source'],'ai')
        self.assertEqual(m.m['repositories'][0]['analysis']['dev']['stale'],False)

    def test_rules_and_recorded_tests_link_without_another_ai_call(self):
        test=self.repo/'tests/items_test.go';test.parent.mkdir();test.write_text('package tests\nclient.post("/items")\n')
        self.git('add','.');self.git('commit','-qm','Synthetic test')
        def fake(command,**kwargs):return subprocess.CompletedProcess(command,0,json.dumps(self.data),'')
        ai_extract.analyze('demo','dev','en',runner=fake)
        def rules(raw,repo):raw['tests']={'files':['*_test.go'],'calls':['client.<method>("<path>")']}
        project.mutate_tests('demo','service',rules)
        folder=project.repository_folder('demo',self.conf['repositories'][0],project.states('demo'))
        raw=project.raw_bundle(folder)
        ai_extract.refresh_test_links(raw['dev'],mapcore.tests_conf(str(folder)))
        self.assertEqual(raw['dev']['backend_routes'][0]['tests'],['tests/items_test.go'])
        raw['dev']['backend_routes'][0]['tests']=[]
        project.record_test('demo','service','POST /items','tests/items_test.go',2,'client.post("/items")')
        folder=project.repository_folder('demo',self.conf['repositories'][0],project.states('demo'))
        raw=project.raw_bundle(folder)
        ai_extract.refresh_test_links(raw['dev'],mapcore.tests_conf(str(folder)))
        self.assertEqual(raw['dev']['backend_routes'][0]['tests'],['tests/items_test.go'])

    def test_dynamic_http_test_paths_share_static_normalization(self):
        file=self.repo/'tests/test_items.py';file.parent.mkdir();file.write_text('client.get(f"/items/{item_id}")\n')
        self.git('add','.');self.git('commit','-qm','Synthetic dynamic test')
        snapshot={'repo':str(self.repo),'commit':self.git('rev-parse','HEAD').strip(),'analysis':{},
                  'backend_routes':[{'file':'server/items.go','line':4,'method':'GET','path':'/items/{}','function':'read_item'}]}
        ai_extract.refresh_test_links(snapshot,{**mapcore.TESTS_DEFAULT,'records':[]})
        self.assertEqual(snapshot['backend_routes'][0]['tests'],['tests/test_items.py'])

    def test_connected_mcp_agent_can_request_read_and_record_without_claude(self):
        import mcp_server
        real_run=subprocess.run
        def no_cli(command,**kwargs):
            self.assertNotEqual(command[0],'claude','Connected MCP agents must use their own model')
            return real_run(command,**kwargs)
        with patch('subprocess.run',side_effect=no_cli):
            request=json.loads(mcp_server.analyze('demo',repository='service',branch='dev',lang='en'))
            self.assertEqual(request['commit'],self.commit)
            listing=json.loads(mcp_server.analysis_source('demo','service',self.commit))
            self.assertIn('server/items.go',listing['files'])
            source=json.loads(mcp_server.analysis_source('demo','service',self.commit,'server/items.go',2,2))
            self.assertEqual(source['lines'][0],{'line':2,'text':' db.Table("items").Create(item)'})
            args=request['record_arguments'];args['result_json']=json.dumps(self.data)
            message=mcp_server.record_analysis(**args)
            self.assertIn('1 screens',message)
        self.assertEqual(project.read_bundle('demo')['dev']['screens'][0]['source_path'],'/items')

    def seed_tasks(self):
        m,flows=self.normalize()
        project.publish('demo','service',{'dev':m},{'fingerprint':project.fingerprint(self.conf['repositories'][0])})
        return {'file':'server/items.go','line':2,'quote':'db.Table("items").Create(item)'}

    def submit_task(self,task,data,target='',lang='en',branch='dev'):
        import mcp_server
        request=json.loads(mcp_server.request_ai_task('demo',task,'service',branch,lang,target))
        self.assertEqual(request['commit'],self.commit)
        self.assertIn('record_ai_task',request['handoff'])
        self.assertEqual(request['record_arguments']['task'],task)
        mcp_server.record_ai_task(**request['record_arguments'],result_json=json.dumps(data))
        return request

    def test_four_ai_tasks_use_connected_agent_and_existing_scoped_formats(self):
        ev=self.seed_tasks()
        request=self.submit_task('groups',{'groups':[{'name':'Items','description':'Manage items','screens':['/items']}],
             'names':{'/items':'Items'},'request_names':{'server/items.go::SaveItem':'Save item'}})
        self.assertEqual(request['input']['screens'][0]['path'],'/items')
        self.submit_task('steps',{'routes':{'server/items.go::SaveItem':{'name':'Save item','steps':[{**ev,'lane':'저장소','text':'Store item'}]}}},'@routes:["server/items.go::SaveItem"]')
        self.submit_task('system',{'nodes':[{'id':'worker','name':'Worker','kind':'program','code':['server'],'ev':[ev]}],
             'links':[],'externals':[],'others':[],'unknown':[]})
        self.submit_task('jobs',{'jobs':[{'name':'Store item','what':'Store item','starts_when':'Item arrives','trigger':ev,
             'made_by':[{**ev,'routes':['server/items.go::SaveItem']}], 'steps':[{**ev,'lane':'저장소','text':'Store item'}]}]},'worker')
        bundle=project.read_bundle('demo')
        self.assertEqual(bundle['groups']['names']['/@service/items'],'Items')
        self.assertEqual(bundle['dev']['backend_routes'][0]['flow']['steps'][0]['text'],'Store item')
        self.assertEqual(bundle['system']['nodes'][0]['id'],'service::worker')
        job=bundle['jobs']['nodes']['service::worker']['jobs'][0]
        self.assertEqual(job['trigger']['file'],'service/server/items.go')
        self.assertEqual(job['routes'],[{'key':'service/server/items.go::SaveItem','exact':False,'source':'ai'}])

    def test_ai_tasks_reject_bad_evidence_stale_input_and_unknown_targets(self):
        ev=self.seed_tasks()
        request=ai_extract.task_request('demo','system','dev','en','service')
        before=project.states('demo')['service']['generation']
        with self.assertRaisesRegex(ValueError,'evidence'):
            ai_extract.task_record(**request['record_arguments'],result_json=json.dumps({'nodes':[{'id':'bad','ev':[{**ev,'quote':'invented text'}]}]}))
        self.assertEqual(project.states('demo')['service']['generation'],before)
        with self.assertRaisesRegex(ValueError,'target'):ai_extract.task_request('demo','steps','dev','en','service','@routes:["other.go::SaveItem"]')
        with self.assertRaisesRegex(ValueError,'node'):ai_extract.task_request('demo','jobs','dev','en','service','missing')
        self.submit_task('groups',{'groups':[{'name':'First','screens':['/items']}],'names':{},'request_names':{}})
        stale=ai_extract.task_request('demo','groups','dev','en','service')
        self.submit_task('groups',{'groups':[{'name':'Second','screens':['/items']}],'names':{},'request_names':{}})
        with self.assertRaisesRegex(ValueError,'changed'):
            ai_extract.task_record(**stale['record_arguments'],result_json=json.dumps({'groups':[{'name':'Overwrite','screens':['/items']}]}))
        (self.repo/'changed.txt').write_text('changed')
        self.git('add','.');self.git('commit','-qm','Changed head')
        with self.assertRaisesRegex(ValueError,'changed'):
            ai_extract.task_record(**request['record_arguments'],result_json=json.dumps({'nodes':[{'id':'worker','ev':[ev]}]}))

    def test_system_tasks_preserve_human_authored_system(self):
        ev=self.seed_tasks()
        folder=project.repository_folder('demo',self.conf['repositories'][0],project.states('demo'))
        raw=project.raw_bundle(folder);raw['system']={'source':'human','nodes':[{'id':'manual','name':'Manual','ev':[]}]}
        project.publish('demo','service',raw,{'fingerprint':project.fingerprint(self.conf['repositories'][0])})
        self.submit_task('system',{'nodes':[{'id':'worker','name':'Worker','kind':'program','ev':[ev]}]})
        folder=project.repository_folder('demo',self.conf['repositories'][0],project.states('demo'))
        raw=project.raw_bundle(folder)
        self.assertEqual(raw['system']['nodes'][0]['id'],'manual')
        self.assertEqual(project.branch_bundle(raw,'dev')['system.ai']['nodes'][0]['id'],'worker')

    def test_task_outputs_stay_separate_between_branch_roles(self):
        ev=self.seed_tasks()
        conf=project.config('demo');conf['repositories'][0]['refs']['main']='HEAD';project.configure('demo',conf)
        m,_=self.normalize()
        for route in m['backend_routes']:route.pop('source',None)
        project.publish('demo','service',{'dev':m,'main':copy.deepcopy(m)},{'fingerprint':project.fingerprint(project.config('demo')['repositories'][0])})
        for role in ('dev','main'):
            self.submit_task('groups',{'groups':[{'name':role,'screens':['/items']}],'names':{'/items':role}},branch=role)
            self.submit_task('steps',{'routes':{'server/items.go::SaveItem':{'name':role,'steps':[{**ev,'text':role}]}}},'/items',branch=role)
            self.submit_task('system',{'nodes':[{'id':'worker','name':role,'code':['server'],'ev':[ev]}]},branch=role)
            self.submit_task('jobs',{'jobs':[{'name':role,'trigger':ev,'steps':[],'made_by':[]}]},'worker',branch=role)
        for role in ('dev','main'):
            bundle=project.read_bundle('demo',branch=role);model=mapcore.Map('demo',role)
            self.assertEqual(bundle['groups']['names']['/@service/items'],role)
            self.assertEqual(bundle['system']['nodes'][0]['name'],'[service] '+role)
            self.assertEqual(bundle['jobs']['nodes']['service::worker']['jobs'][0]['name'],role)
            self.assertEqual(model.ai_name(model.m['backend_routes'][0]),role)
            self.assertEqual(bundle['branch_details'][role]['groups']['names']['/@service/items'],role)

    def test_system_task_outputs_remain_readable_by_mcp(self):
        import mcp_server
        ev=self.seed_tasks()
        self.submit_task('system',{'nodes':[{'id':'worker','name':'Worker','code':['server'],'ev':[ev],
             'unknown':['Unknown deployment'],'copies':'unsupported extra field'}], 'externals':[{'id':'cloud','ev':[ev]}],
             'links':[],'unknown':['Unknown deployment']})
        # Accepted provider output must be safe for the actual consumers.
        output=mcp_server.overview('demo')
        self.assertIn('Unknown deployment',output)
        model=mapcore.Map('demo')
        self.assertNotIn('copies',model.system['nodes'][0])
        self.assertIsInstance(model.system['unknown'][0],dict)
        self.assertIsInstance(model.system['nodes'][0]['unknown'][0],dict)
        self.assertEqual(model.system['externals'][0]['name'],'cloud')

    def test_four_compatibility_commands_prepare_requests_without_ai(self):
        ev=self.seed_tasks()
        self.submit_task('system',{'nodes':[{'id':'worker','name':'Worker','code':['server'],'ev':[ev]}]})
        base=Path(__file__).resolve().parents[1]
        env=dict(os.environ,WHERE_WERE_WE_ROOT=str(self.home),PATH='/usr/bin:/bin')
        commands=[['group.py','demo','dev'],['steps.py','demo','dev','/items'],
                  ['system.py','demo','--branch','dev'],['jobs.py','demo','worker','--branch','dev']]
        before=project.states('demo')['service']['generation']
        for script,*args in commands:
            result=subprocess.run([sys.executable,'-I','-B',str(base/script),*args,'--repository','service','--lang','en'],env=env,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertIn('record_ai_task',json.loads(result.stdout)['handoff'])
        self.assertEqual(project.states('demo')['service']['generation'],before)

    def test_main_only_task_names_are_available_to_mcp_queries(self):
        import mcp_server
        conf=project.config('demo');conf['repositories'][0]['refs']={'dev':None,'main':'HEAD'};project.configure('demo',conf)
        m,_=self.normalize();m['screens'][0]['heading']=None
        project.publish('demo','service',{'main':m},{'fingerprint':project.fingerprint(project.config('demo')['repositories'][0])})
        self.submit_task('groups',{'groups':[{'name':'Main group','screens':['/items']}],'names':{'/items':'MAIN ONLY LABEL'}},branch='main')
        self.assertIn('MAIN ONLY LABEL',mcp_server.find('MAIN ONLY LABEL','demo','service'))

    def test_standard_mcp_protocol_supports_agent_owned_analysis(self):
        import asyncio
        from mcp import ClientSession,StdioServerParameters
        from mcp.client.stdio import stdio_client
        base=Path(os.environ['WHERE_WERE_WE_RUNTIME'])/'backend' if os.environ.get('WHERE_WERE_WE_RUNTIME') else Path(__file__).resolve().parents[1]
        env=dict(os.environ,WHERE_WERE_WE_ROOT=str(self.home),PATH='/usr/bin:/bin')
        async def exercise():
            params=StdioServerParameters(command=sys.executable,args=['-I','-B',str(base/'mcp_server.py')],env=env,cwd=str(self.repo.parent))
            async with stdio_client(params) as streams:
                async with ClientSession(*streams) as session:
                    await session.initialize()
                    names={tool.name for tool in (await session.list_tools()).tools}
                    self.assertTrue({'analyze','analysis_source','record_analysis','request_ai_task','record_ai_task'}<=names)
                    reply=await session.call_tool('analyze',{'project':'demo','repository':'service','branch':'dev','lang':'en'})
                    self.assertFalse(reply.is_error)
                    request=json.loads(reply.content[0].text)
                    reply=await session.call_tool('analysis_source',{**request['source_arguments'],'file':'server/items.go'})
                    self.assertFalse(reply.is_error)
                    self.assertIn('SaveItem',reply.content[0].text)
                    reply=await session.call_tool('record_analysis',{**request['record_arguments'],'result_json':json.dumps(self.data)})
                    self.assertFalse(reply.is_error,reply.content)
                    ev={'file':'server/items.go','line':2,'quote':'db.Table("items").Create(item)'}
                    tasks=[('groups','',{'groups':[{'name':'Items','screens':['/items']}]}),
                           ('steps','/items',{'routes':{'server/items.go::SaveItem':{'name':'Save item','steps':[{**ev,'text':'Store item'}]}}}),
                           ('system','',{'nodes':[{'id':'worker','name':'Worker','code':['server'],'ev':[ev]}]}),
                           ('jobs','worker',{'jobs':[{'name':'Store item','trigger':ev,'made_by':[],'steps':[]}]})]
                    for task,target,data in tasks:
                        reply=await session.call_tool('request_ai_task',{'project':'demo','repository':'service','branch':'dev','lang':'en','task':task,'target':target})
                        self.assertFalse(reply.is_error,reply.content)
                        request=json.loads(reply.content[0].text)
                        reply=await session.call_tool('record_ai_task',{**request['record_arguments'],'result_json':json.dumps(data)})
                        self.assertFalse(reply.is_error,reply.content)
        asyncio.run(exercise())
        self.assertEqual(project.read_bundle('demo')['dev']['backend_routes'][0]['source'],'ai')

    def test_mcp_submission_rejects_changed_commit_or_configuration(self):
        request=ai_extract.request('demo','dev','en','service')
        before=project.states('demo')['service']['generation']
        (self.repo/'new.txt').write_text('Synthetic change')
        self.git('add','.');self.git('commit','-qm','Moved branch')
        args=request['record_arguments'];args['result_json']=json.dumps(self.data)
        with self.assertRaisesRegex(ValueError,'changed'):ai_extract.record(**args)
        self.assertEqual(project.states('demo')['service']['generation'],before)
        request=ai_extract.request('demo','dev','en','service')
        conf=project.config('demo');conf['repositories'][0]['layout']={'backend':None};project.configure('demo',conf)
        args=request['record_arguments'];args['result_json']=json.dumps(self.data)
        with self.assertRaisesRegex(ValueError,'changed'):ai_extract.record(**args)
        self.assertEqual(project.states('demo')['service']['generation'],before)

    def test_bad_ai_output_preserves_selected_generation(self):
        before=project.states('demo')['service']['generation']
        def bad(command,**kwargs):return subprocess.CompletedProcess(command,0,'not JSON','')
        with self.assertRaises(ValueError):ai_extract.analyze('demo','dev','en',runner=bad)
        self.assertEqual(project.states('demo')['service']['generation'],before)

if __name__=='__main__':unittest.main()
