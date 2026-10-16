"""Multi-repository behavior uses synthetic snapshots and temporary homes only."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import mapcore
import project


def sample(path, commit='abc123'):
    return {'repo': path, 'ref': 'origin/dev', 'commit': commit, 'screens': [
        {'path':'/settings','heading':'Settings','file':'src/Settings.tsx','redirect':False,'actions':[], 'api_functions':[]}],
        'api_functions':[], 'backend_routes':[], 'backend_routes_without_screen':[],
        'unresolved_calls':[], 'file_screens':{'src/Settings.tsx':['/settings']}, 'models':{}}

class TemporaryProject(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.patch = patch.object(mapcore, 'ROOT', str(self.root))
        self.patch.start(); self.addCleanup(self.patch.stop)

class Projects(TemporaryProject):
    def test_two_repositories_keep_equal_paths_and_pr_numbers_distinct(self):
        project.configure('studio', {'repositories':[
            {'id':'web','path':'/demo/web'}, {'id':'admin','path':'/demo/admin'}]})
        for rid in ('web','admin'):
            project.publish('studio', rid, {'dev':sample('/demo/'+rid),'main':sample('/demo/'+rid),
                'status':{'open_prs':[{'number':42,'title':'Settings','screens':['/settings'],'files':['src/Settings.tsx']}]}}, {})
        data = project.read_bundle('studio')
        self.assertEqual(len(data['dev']['screens']), 2)
        self.assertEqual(len({s['path'] for s in data['dev']['screens']}), 2)
        self.assertEqual({s['source_path'] for s in data['dev']['screens']}, {'/settings'})
        self.assertEqual({p['repository'] for p in data['status']['open_prs']}, {'web','admin'})
        scoped = project.read_bundle('studio', 'web')
        self.assertEqual(len(scoped['dev']['screens']), 1)
        self.assertEqual(len(scoped['status']['open_prs']), 1)

    def test_legacy_session_fields_are_not_returned_or_migrated_into_project_views(self):
        folder=self.root/'legacy';folder.mkdir()
        (folder/'dev.json').write_text(json.dumps(sample('/demo/old')))
        old=json.dumps({'worktrees':[{'path':'/demo/feature','branch':'feature','uncommitted':['src/Settings.tsx'],
             'screens':['/settings'],'session_count':1,'sessions':[{'id':'old-session','last':'2026-10-01'}]}]})
        (folder/'status.json').write_text(old)
        for adopted in (False,True):
            if adopted:project.configure('legacy',{'repositories':[{'id':'old','path':'/demo/old','legacy':True}]})
            work=project.read_bundle('legacy')['status']['worktrees'][0]
            self.assertNotIn('sessions',work);self.assertNotIn('session_count',work)
            self.assertEqual(work['branch'],'feature')
            self.assertEqual(work['uncommitted'],['src/Settings.tsx'])
        self.assertEqual((folder/'status.json').read_text(),old)

    def test_config_rejects_path_traversal_and_duplicate_ids(self):
        for repositories in ([{'id':'../escape','path':'/demo/a'}],
            [{'id':'web','path':'/demo/a'},{'id':'web','path':'/demo/b'}],
            [{'id':'a','path':'/demo/a'},{'id':'b','path':'/demo/a'}]):
            with self.assertRaises(ValueError):project.configure('studio', {'repositories':repositories})
        with self.assertRaises(ValueError):project.configure('../outside', {'repositories':[]})

    def test_failed_refresh_keeps_last_success(self):
        project.configure('studio', {'repositories':[{'id':'web','path':'/demo/web'}]})
        project.publish('studio','web',{'dev':sample('/demo/web')},{})
        project.failed('studio','web','GitHub unavailable')
        bundle=project.read_bundle('studio')
        self.assertEqual(bundle['dev']['screens'][0]['source_path'],'/settings')
        self.assertIn('GitHub unavailable',bundle['project']['repositories'][0]['error'])
        self.assertTrue(bundle['project']['repositories'][0]['last_success'])

    def test_legacy_adoption_preserves_source_files(self):
        home=self.root/'legacy';home.mkdir()
        text=json.dumps(sample('/demo/old'));(home/'dev.json').write_text(text)
        project.configure('legacy', {'repositories':[{'id':'old','path':'/demo/old','legacy':True}]})
        self.assertEqual((home/'dev.json').read_text(),text)
        self.assertEqual(project.read_bundle('legacy')['dev']['screens'][0]['repository'],'old')

    def test_main_only_legacy_requires_explicit_adoption(self):
        home=self.root/'legacy';home.mkdir()
        original=json.dumps(sample('/demo/old'));(home/'main.json').write_text(original)
        with self.assertRaisesRegex(ValueError,'legacy'):
            project.configure('legacy',{'repositories':[{'id':'new','path':'/demo/new'}]})
        self.assertFalse((home/'project.json').exists())
        self.assertEqual((home/'main.json').read_text(),original)
        project.configure('legacy',{'repositories':[{'id':'old','path':'/demo/old','legacy':True,
                                                   'refs':{'dev':None,'main':'origin/main'}}]})
        self.assertEqual(project.read_bundle('legacy')['main']['screens'][0]['repository'],'old')

class Connections(TemporaryProject):
    def inputs(self):
        project.configure('studio', {'repositories':[
            {'id':'web','path':'/demo/web','api_targets':['api']},
            {'id':'api','path':'/demo/api'}, {'id':'admin','path':'/demo/admin'}, {'id':'worker','path':'/demo/worker'}]})
        web=sample('/demo/web');web['screens'][0]['api_functions']=[{'file':'src/api/client.ts','name':'read_settings'}]
        web['api_functions']=[{'file':'src/api/client.ts','name':'read_settings','calls':[{'method':'GET','path':'/settings','backend':[],'line':1}]}]
        route={'file':'app/main.py','line':3,'function':'read_settings','method':'GET','path':'/settings','mounted':True,'tables':['settings'],'tests':[]}
        api=sample('/demo/api');api['screens']=[];api['backend_routes']=[route];api['models']={'Settings':'settings'}
        worker=sample('/demo/worker');worker['screens']=[];worker['models']={'Settings':'settings'}
        for rid,value in [('web',web),('api',api),('admin',sample('/demo/admin')),('worker',worker)]:
            project.publish('studio',rid,{'dev':value,'main':value},{})
        return web,api

    def test_configured_target_and_unconfigured_candidates(self):
        self.inputs();m=mapcore.Map('studio')
        row=m.requests('/@web/settings')[0]
        self.assertEqual(row['route']['repository'],'api')
        self.assertEqual(row['connection_basis'],'configured')
        self.assertEqual(set(m.m['models'].values()),{'api::settings','worker::settings'})
        conf=project.config('studio');conf['repositories'][0]['api_targets']=[];project.configure('studio',conf)
        m=mapcore.Map('studio')
        self.assertEqual(m.requests('/@web/settings'),[])
        self.assertEqual(m.m['connection_candidates'][0]['targets'][0]['repository'],'api')

    def test_cross_repository_uncommitted_work_is_visible(self):
        web,api=self.inputs()
        folder={'path':'/demo/work','branch':'feature','uncommitted':['app/main.py'],'screens':[]}
        project.publish('studio','api',{'dev':api,'status':{'worktrees':[folder]}},{})
        for scope in ('','web'):
            bundle=project.read_bundle('studio',scope)
            m=mapcore.Map('studio',data=bundle['dev'],bundle=bundle)
            work=m.work_of('/@web/settings')['folders']
            self.assertEqual(len(work),1)
            self.assertEqual(work[0]['repository'],'api')
            self.assertEqual(work[0]['uncommitted'],['app/main.py'])
        self.assertEqual(folder['screens'],[])

    def test_cross_repository_pr_linked_issue_is_visible(self):
        web,api=self.inputs()
        status={'open_prs':[{'number':42,'title':'API','files':['app/main.py'],'screens':[],
                            'issues':[{'number':5}],'refs':[]}],
                'issues':[{'number':5,'title':'Linked','screens':[],'via':'pr','hits':['PR #42']},
                          {'number':6,'title':'Unrelated','screens':[],'via':None,'hits':[]}]}
        project.publish('studio','api',{'dev':api,'status':status},{})
        for scope in ('','web'):
            bundle=project.read_bundle('studio',scope)
            m=mapcore.Map('studio',data=bundle['dev'],bundle=bundle)
            self.assertEqual([i['number'] for i in m.work_of('/@web/settings')['issues']],[5])
        self.assertEqual(status['issues'][0]['screens'],[])

    def test_previous_view_keeps_unchanged_dependency_repository(self):
        web,api=self.inputs()
        project.publish('studio','web',{'dev':web,'dev.prev':web},{})
        bundle=project.read_bundle('studio')
        old=mapcore.Map('studio',data=bundle['dev.prev'],bundle=bundle)
        self.assertEqual(old.requests('/@web/settings')[0]['route']['repository'],'api')

    def test_scope_keeps_dependencies_but_not_unrelated_work(self):
        self.inputs();bundle=project.read_bundle('studio','web')
        with patch.object(mapcore,'_read',side_effect=lambda name,key:bundle.get(key)):
            m=mapcore.Map('studio',data=bundle['dev'],bundle=bundle)
        self.assertEqual(len(m.visible()),1)
        self.assertEqual(m.requests('/@web/settings')[0]['route']['repository'],'api')
        with self.assertRaisesRegex(ValueError,'Ambiguous'):mapcore.Map('studio').find_screen('/settings')

    def test_project_lock_rejects_overlapping_mutations(self):
        self.inputs()
        with project.locked('studio'):
            with self.assertRaisesRegex(ValueError,'already being updated'):project.refresh_project('studio')

    def test_first_failure_is_not_empty_success(self):
        project.configure('new',{'repositories':[{'id':'api','path':'/demo/api'}]})
        project.failed('new','api','fetch denied')
        repo=project.read_bundle('new')['project']['repositories'][0]
        self.assertFalse(repo['collected']);self.assertNotIn('last_success',repo)
        self.assertEqual(repo['error'],'fetch denied')

    def test_mobile_folding_and_shared_data_are_scoped(self):
        self.inputs();raw=sample('/demo/web');raw['screens'].append({**raw['screens'][0],'path':'/m/settings'})
        project.publish('studio','web',{'dev':raw},{})
        m=mapcore.Map('studio');visible=m.visible()
        self.assertEqual(len(visible),2)
        self.assertTrue(next(pair for pair in visible if pair[0]['repository']=='web')[1])
        conf=project.config('studio');conf['shared_data']=[{'id':'workspace','members':[{'repository':'api','table':'settings'},{'repository':'worker','table':'settings'}]}]
        project.configure('studio',conf)
        self.assertEqual(set(mapcore.Map('studio').m['models'].values()),{'shared::workspace'})


# The fake executables only provide git/GitHub inputs. The actual isolated Python
# collector, extractor, parser, snapshot publication and composition run unchanged.
FAKE_CLI = r'''#!PYTHON
import json,os,sys,hashlib
from pathlib import Path
args=sys.argv[1:];repo=os.getcwd()
if '-C' in args:
 i=args.index('-C');repo=args[i+1];args=args[:i]+args[i+2:]
if Path(sys.argv[0]).name=='gh':
 if os.environ.get('FAKE_GH_FAIL'):print('GitHub denied',file=sys.stderr);sys.exit(1)
 print('[]');sys.exit()
sources=json.load(open(os.environ['FAKE_SOURCES']));files={os.path.realpath(k):v for k,v in sources.items()}.get(os.path.realpath(repo),{})
if args[0]=='fetch':
 if Path(repo).name=='broken':print('fetch denied',file=sys.stderr);sys.exit(1)
elif args[0]=='ls-tree':print('\n'.join(files))
elif args[0]=='show':
 file=args[-1].split(':',1)[1]
 if file not in files:sys.exit(1)
 print(files[file],end='')
elif args[0]=='rev-parse':print(hashlib.sha1(json.dumps(files,sort_keys=True).encode()).hexdigest()[:8] if '--short' in args or '--short=8' in args else hashlib.sha1(json.dumps(files,sort_keys=True).encode()).hexdigest())
elif args[0]=='rev-list':print('0')
elif args[0]=='remote':print('https://example.invalid/studio.git')
'''

class Collection(TemporaryProject):
    def environment(self):
        import stat
        sources={}
        for rid in ('web','api','worker','broken'):
            path=self.root/rid;path.mkdir();sources[str(path)]={}
        sources[str(self.root/'web')]={
            'src/App.tsx':"import Settings from './Settings';\n<Route path=\"/settings\" element={<Settings />} />\n",
            'src/Settings.tsx':"import { readSettings } from './api/client';\nexport default function Settings(){ readSettings(); return <h1>Settings</h1>; }\n",
            'src/api/client.ts':"export const readSettings = () => api.get('/settings');\n"}
        sources[str(self.root/'api')]={'app/main.py':'from fastapi import FastAPI\napp = FastAPI()\n@app.get("/settings")\ndef read_settings():\n    return {}\n'}
        sources[str(self.root/'worker')]={'consumer.py':'def consume():\n    return None\n'}
        data=self.root/'sources.json';data.write_text(json.dumps(sources))
        bindir=self.root/'bin';bindir.mkdir()
        for name in ('git','gh'):
            executable=bindir/name;executable.write_text(FAKE_CLI.replace('PYTHON',sys.executable,1));executable.chmod(0o755)
        env=dict(os.environ,PATH=str(bindir)+os.pathsep+os.environ['PATH'],FAKE_SOURCES=str(data),WHERE_WERE_WE_ROOT=str(self.root/'maps'),HOME=str(self.root/'empty-home'))
        return env

    def run_cli(self,env,*args):
        import subprocess
        return subprocess.run([sys.executable,'-I','-B',str(Path(project.__file__)),*args],env=env,capture_output=True,text=True)

    def test_collection_keeps_git_worktrees_without_accessing_agent_sessions(self):
        import contextlib,io,runpy,subprocess
        folder=self.root/'collection';folder.mkdir()
        repo=self.root/'code';repo.mkdir()
        (folder/'dev.json').write_text(json.dumps(sample(str(repo))))
        def command(argv,**kwargs):
            if argv[0]=='gh':output='[]'
            elif 'worktree' in argv:output=f'worktree {repo}\nbranch refs/heads/feature\n\n'
            elif 'status' in argv:output=' M src/Settings.tsx\n'
            elif 'ls-tree' in argv:output='src/Settings.tsx\n'
            else:output=''
            return subprocess.CompletedProcess(argv,0,output,'')
        original=os.path.expanduser
        def no_session_access(path):
            if '/.claude' in str(path) or '/.codex' in str(path):raise AssertionError('Agent session discovery is outside product scope')
            return original(path)
        with patch.object(sys,'argv',['collect.py',str(repo),'collection']),patch.dict(os.environ,{'WHERE_WERE_WE_REFS':json.dumps({'dev':'origin/dev','main':None})}),patch('subprocess.run',side_effect=command),patch('os.path.expanduser',side_effect=no_session_access),contextlib.redirect_stdout(io.StringIO()):
            runpy.run_path(str(Path(project.__file__).parent/'collect.py'),run_name='__main__')
        work=json.loads((folder/'status.json').read_text())['worktrees']
        self.assertEqual(len(work),1)
        self.assertEqual(work[0]['branch'],'feature')
        self.assertEqual(work[0]['uncommitted'],['src/Settings.tsx'])
        self.assertNotIn('sessions',work[0]);self.assertNotIn('session_count',work[0])

    def test_custom_non_python_roots_can_be_collected_before_ai_analysis(self):
        env=self.environment()
        sources=json.loads(Path(env['FAKE_SOURCES']).read_text())
        sources[str(self.root/'web')]={'pages/items.vue':'<template>Items</template>'}
        sources[str(self.root/'api')]={'server/main.go':'package main'}
        Path(env['FAKE_SOURCES']).write_text(json.dumps(sources))
        conf={'repositories':[{'id':'web','path':str(self.root/'web'),'layout':{'frontend':'pages','backend':None}},
                              {'id':'api','path':str(self.root/'api'),'layout':{'frontend':None,'backend':'server'}}]}
        self.assertEqual(self.run_cli(env,'configure','studio',json.dumps(conf)).returncode,0)
        result=self.run_cli(env,'refresh','studio')
        self.assertNotIn('FAILED',result.stdout,result.stdout)
        self.assertIn('web: refreshed',result.stdout)
        self.assertIn('api: refreshed',result.stdout)

    def test_real_isolated_collection_split_sources_and_partial_failure(self):
        env=self.environment()
        conf={'repositories':[
            {'id':'web','path':str(self.root/'web'),'api_targets':['api'],'refs':{'dev':'origin/develop','main':None}},
            {'id':'api','path':str(self.root/'api'),'refs':{'dev':'origin/trunk','main':None}},
            {'id':'worker','path':str(self.root/'worker'),'refs':{'dev':None,'main':'origin/main'}},
            {'id':'broken','path':str(self.root/'broken')}]}
        import subprocess
        created=subprocess.run([sys.executable,'-I','-B',project.__file__,'configure','studio',json.dumps(conf)],env=env,capture_output=True,text=True)
        self.assertEqual(created.returncode,0,created.stderr)
        result=self.run_cli(env,'refresh','studio');self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('web: refreshed',result.stdout,result.stdout)
        self.assertIn('api: refreshed',result.stdout,result.stdout)
        self.assertIn('worker: refreshed',result.stdout,result.stdout)
        self.assertIn('broken: FAILED',result.stdout)
        loaded=self.run_cli(env,'read','studio');self.assertEqual(loaded.returncode,0,loaded.stderr)
        bundle=json.loads(loaded.stdout)
        self.assertEqual(len(bundle['dev']['screens']),1)
        fn=next(f for f in bundle['dev']['api_functions'] if f['name']=='readSettings')
        self.assertEqual(fn['calls'][0]['target_repository'],'api')
        self.assertEqual(len(fn['calls'][0]['backend']),1)
        health={r['id']:r for r in bundle['project']['repositories']}
        self.assertFalse(health['broken']['collected']);self.assertIn('fetch denied',health['broken']['error'])
        before=health['web']['generation']
        failed=self.run_cli(dict(env,FAKE_GH_FAIL='1'),'refresh','studio','--repository','web')
        self.assertIn('FAILED',failed.stdout)
        health={r['id']:r for r in json.loads(self.run_cli(env,'read','studio').stdout)['project']['repositories']}
        self.assertEqual(health['web']['generation'],before)
        self.assertIn('GitHub denied',health['web']['error'])
        worker=json.loads(self.run_cli(env,'read','studio','--repository','worker').stdout)
        self.assertIsNone(worker['dev']);self.assertTrue(worker['main'])

class Recovery(TemporaryProject):
    def init(self):
        project.configure('studio',{'repositories':[{'id':'m','path':'/demo/m'}]})
        repo=project.config('studio')['repositories'][0]
        project.publish('studio','m',{'dev':sample('/demo/m')},{'fingerprint':project.fingerprint(repo)})
        return repo

    def test_mobile_namespace_collision_is_impossible(self):
        self.assertNotEqual(project.qscreen('m','/admin/settings'),project.qscreen('admin','/m/settings'))
        self.assertFalse(project.qscreen('m','/settings').startswith('/m/'))

    def test_test_edits_preserve_collection_health_and_config_guard(self):
        repo=self.init();project.failed('studio','m','offline')
        before=project.states('studio')['m']
        project.mutate_tests('studio','m',lambda raw,r:raw.update(tests={'files':['spec_*.py'],'calls':['<function>(']}))
        after=project.states('studio')['m']
        self.assertEqual(after['error'],'offline');self.assertEqual(after['last_success'],before['last_success'])
        self.assertEqual(after['last_attempt'],before['last_attempt'])
        prompt=mapcore.tests_prompt('studio',lang='en',repository='m');self.assertIn('spec_*.py',prompt)
        conf=project.config('studio');conf['repositories'][0]['refs']['dev']='origin/develop';project.configure('studio',conf)
        with self.assertRaisesRegex(ValueError,'Refresh'):project.action('studio','m','system.py')
        with self.assertRaisesRegex(ValueError,'Refresh'):project.mutate_tests('studio','m',lambda raw,r:None)
        self.assertTrue(project.read_bundle('studio')['project']['repositories'][0]['config_changed'])

    def test_interruption_records_attempt_without_replacing_success(self):
        self.init();before=project.states('studio')['m']['generation']
        with patch.object(project,'_transaction',side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):project.refresh_project('studio')
        repo=project.read_bundle('studio')['project']['repositories'][0]
        self.assertEqual(repo['generation'],before);self.assertIn('interrupted',repo['error'])
        self.assertTrue(repo['last_attempt'])

    def test_atomic_pointer_failure_keeps_selected_generation(self):
        self.init();before=project.states('studio')['m']['generation'];atomic=project.atomic
        def interrupted(path,value):
            if path.name=='repository-state.json':raise OSError('interrupted publication')
            return atomic(path,value)
        with patch.object(project,'atomic',side_effect=interrupted):
            with self.assertRaises(OSError):project.publish('studio','m',{'dev':sample('/demo/m','new')},{})
        self.assertEqual(project.states('studio')['m']['generation'],before)
        self.assertEqual(project.read_bundle('studio')['dev']['screens'][0]['source_path'],'/settings')

    def test_nested_system_evidence_and_background_items_keep_repository(self):
        self.init()
        sy={'nodes':[{'id':'api','name':'API','kind':'program','code':['app'],'uses':[]}],
            'links':[{'from':'api','to':'api','label':'loop','ev':[{'file':'app/main.py','line':1}]}],
            'externals':[],'others':[{'name':'Backup','what':'Archive','ev':[{'file':'backup.py','line':1}]}]}
        project.publish('studio','m',{'dev':sample('/demo/m'),'system':sy,'jobs':{'nodes':{'api':{'jobs':[{'name':'job','routes':[],'steps':[{'file':'consumer.py','line':3}],'made_by':[{'file':'app/main.py','line':5,'quote':'enqueue_job'}]}]}}}},{})
        sy=project.read_bundle('studio')['system']
        self.assertEqual(sy['links'][0]['ev'][0]['file'],'m/app/main.py')
        self.assertEqual(sy['others'][0]['ev'][0]['file'],'m/backup.py')
        job=project.read_bundle('studio')['jobs']['nodes']['m::api']['jobs'][0]
        self.assertEqual(job['made_by'][0]['file'],'m/app/main.py')
        self.assertEqual(job['steps'][0]['file'],'m/consumer.py')

    def test_repository_selection_is_inside_mutation_lock(self):
        self.init();select=project.selected_repository
        def checked(*args):
            self.assertTrue(project.collection_running('studio'))
            return select(*args)
        with patch.object(project,'selected_repository',side_effect=checked):
            project.mutate_tests('studio','m',lambda raw,r:None)

    def test_removed_repository_snapshots_remain_on_disk(self):
        self.init();original=project.repository_folder('studio',project.config('studio')['repositories'][0],project.states('studio'))
        project.configure('studio',{'repositories':[{'id':'new','path':'/demo/new'}]})
        self.assertTrue((original/'dev.json').exists())
        self.assertEqual(len(project.read_bundle('studio')['project']['repositories']),1)



class MCP(TemporaryProject):
    inputs = Connections.inputs
    def setUp(self):
        super().setUp()
        try:import mcp_server
        except ImportError:self.skipTest('Run with the bundled MCP interpreter for MCP integration checks')
        self.server=mcp_server

    def test_mcp_scoped_raw_paths_calls_and_test_writes(self):
        self.inputs()
        text=self.server.impact('app/main.py','studio',repository='api')
        self.assertIn('api/app/main.py',text)
        self.assertIn('web',text)
        self.assertIn('read_settings',self.server.impact('/settings','studio',repository='web'))
        self.assertIn('read_settings',self.server.impact('/@web/settings','studio',repository='web'))
        self.assertIn('read_settings',self.server.impact('Settings','studio',repository='web'))
        text=self.server.impact('GET /settings','studio',repository='api')
        self.assertIn('read_settings',text)
        with self.assertRaisesRegex(ValueError,'Choose a repository'):
            self.server.set_test_rules(['spec_*.py'],['<function>('],'studio')
        self.server.set_test_rules(['spec_*.py'],['<function>('],'studio',repository='api')
        self.assertIn('spec_*.py',mapcore.tests_prompt('studio',lang='en',repository='api'))
        self.assertNotIn('spec_*.py',mapcore.tests_prompt('studio',lang='en',repository='web'))

    def test_http_impact_includes_connected_work(self):
        web,api=self.inputs()
        project.publish('studio','api',{'dev':api,'status':{'open_prs':[
            {'number':42,'title':'API change','author':'demo','files':['app/main.py'],'screens':[]}]}},{})
        text=self.server.impact('GET /settings','studio',repository='api')
        self.assertIn('PR #42',text)
        self.assertIn('API change',text)

    def test_backend_only_impact_includes_file_work(self):
        project.configure('studio',{'repositories':[{'id':'api','path':'/demo/api'}]})
        api=sample('/demo/api');api['screens']=[];api['file_screens']={};api['models']={'Settings':'settings'}
        api['backend_routes']=[{'file':'app/main.py','line':3,'function':'read_settings',
            'method':'GET','path':'/settings','mounted':True,'tables':['settings'],'tests':[]}]
        project.publish('studio','api',{'dev':api,'status':{'open_prs':[
            {'number':42,'title':'API change','author':'demo','files':['app/main.py'],'screens':[]}]}},{})
        for target in ('GET /settings','app/main.py','settings'):
            self.assertIn('PR #42',self.server.impact(target,'studio',repository='api'))

    def test_mcp_reports_configuration_change_and_collection_times(self):
        conf=project.configure('studio',{'repositories':[{'id':'web','path':'/demo/old'}]})
        project.publish('studio','web',{'dev':sample('/demo/old')},
                        {'fingerprint':project.fingerprint(conf['repositories'][0])})
        state=project.states('studio')['web']
        conf['repositories'][0]['path']='/demo/new';project.configure('studio',conf)
        for text in (self.server.projects(),self.server.overview('studio'),
                     self.server.impact('/settings','studio',repository='web')):
            self.assertIn('configuration changed; refresh required',text)
            self.assertIn(state['last_success'],text)
            self.assertIn(state['last_attempt'],text)

    def test_mcp_main_only_repository(self):
        project.configure('studio',{'repositories':[{'id':'only','path':'/demo/only','refs':{'dev':None,'main':'origin/main'}}]})
        project.publish('studio','only',{'main':sample('/demo/only')},{})
        text=self.server.find('Settings','studio',repository='only')
        self.assertIn('Settings',text);self.assertIn('only',text)

if __name__=='__main__':unittest.main()
