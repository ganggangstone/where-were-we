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

class GitHubAccounts(TemporaryProject):
    def fake_run(self,args,**kwargs):
        import subprocess
        self.calls.append((args,kwargs))
        env=kwargs.get('env',{})
        if args[0]=='git':out='https://github.com/example/private.git'
        elif args[1:3]==['auth','token']:
            out='test-token-'+args[-1]
        elif args[1:3]==['api','user']:
            out='alice' if env.get('GH_TOKEN')=='test-token-alice' else 'bob'
        elif args[1:3]==['repo','view']:
            return subprocess.CompletedProcess(args,1 if self.denied else 0,'{}','sensitive upstream details')
        else:raise AssertionError(args)
        return subprocess.CompletedProcess(args,0,out+'\n','')

    def setUp(self):
        super().setUp();self.calls=[];self.denied=False
        self.runner=patch('subprocess.run',side_effect=self.fake_run)
        self.runner.start();self.addCleanup(self.runner.stop)

    def test_connect_remembers_account_without_storing_token_or_switching_global_account(self):
        value=project.configure('demo',{'repositories':[{'id':'web','path':'/demo/web'}]})
        self.assertEqual(value['repositories'][0]['github']['account'],'bob')
        self.assertNotIn('test-token', (self.root/'demo/project.json').read_text())
        project.configure('demo',value)
        self.assertFalse(any('switch' in args for args,_ in self.calls))

    def test_collection_uses_remembered_account_for_api_and_https_git_only_in_child(self):
        repo={'path':'/demo/web','refs':{},'layout':{},'github':{'host':'github.com','account':'alice'}}
        with patch.dict(os.environ,{'GH_TOKEN':'other-token','GH_REPO':'other/wrong','GH_DEBUG':'api'}):
            env=project.child_environment(self.root,repo)
            self.assertEqual(os.environ['GH_TOKEN'],'other-token')
        self.assertEqual(env['GH_TOKEN'],'test-token-alice')
        self.assertNotIn('GH_REPO',env);self.assertNotIn('GH_DEBUG',env)
        pairs={env['GIT_CONFIG_KEY_'+str(i)]:env['GIT_CONFIG_VALUE_'+str(i)] for i in range(int(env['GIT_CONFIG_COUNT']))}
        self.assertEqual(pairs['credential.https://github.com.helper'],'!gh auth git-credential')
        self.assertFalse(any('test-token-alice' in str(args) for args,_ in self.calls))

    def test_wrong_identity_is_rejected_without_exposing_token(self):
        repo={'path':'/demo/web','refs':{},'layout':{},'github':{'host':'github.com','account':'charlie'}}
        with self.assertRaisesRegex(ValueError,'GITHUB_ACCESS.*charlie') as error:
            project.child_environment(self.root,repo)
        self.assertNotIn('test-token',str(error.exception))

    def test_account_repair_checks_access_before_saving_and_preserves_map(self):
        project.configure('demo',{'repositories':[{'id':'web','path':'/demo/web'}]})
        repo=project.config('demo')['repositories'][0]
        project.publish('demo','web',{'dev':sample('/demo/web')},{'fingerprint':project.fingerprint(repo)})
        generation=project.states('demo')['web']['generation']
        self.denied=True
        with self.assertRaisesRegex(ValueError,'GITHUB_ACCESS'):
            project.set_github_account('demo','web','alice')
        self.assertEqual(project.config('demo')['repositories'][0]['github']['account'],'bob')
        self.denied=False
        project.set_github_account('demo','web','alice')
        self.assertEqual(project.config('demo')['repositories'][0]['github']['account'],'alice')
        self.assertEqual(project.states('demo')['web']['generation'],generation)

    def test_legacy_refresh_context_remembers_account_for_same_folder(self):
        folder=self.root/'legacy';folder.mkdir()
        project.atomic(folder/'dev.json',sample('/demo/web'))
        repo=project.github_repository('legacy','')
        project.remember_github('legacy',repo)
        remembered=project.github_repository('legacy','')
        self.assertEqual(remembered['github']['account'],'bob')
        project.set_github_account('legacy','','alice')
        adopted=project.configure('legacy',{'repositories':[{'id':'web','path':'/demo/web','legacy':True}]})
        self.assertEqual(adopted['repositories'][0]['github']['account'],'alice')

class RefreshSettings(TemporaryProject):
    def test_program_details_show_saved_jobs_and_empty_state_without_request_button(self):
        import shutil,subprocess
        node=shutil.which('node')
        if not node:self.skipTest('Node is required for UI behavior checks')
        script=r'''
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const html=fs.readFileSync('ui/index.html','utf8');
const js=html.slice(html.indexOf('<script>')+8,html.lastIndexOf('</script>'));
global.window={__TAURI__:{core:{invoke:()=>{throw Error('Viewing details must not invoke analysis');}}}};
global.localStorage={getItem:()=>null};
vm.runInThisContext(js.slice(0,js.indexOf("$('q').oninput"))+`
S.system={nodes:[{id:'service::backend',name:'API server',kind:'program',code:['service/server'],uses:[]}],links:[],externals:[]};
S.node='service::backend';S.jobs={nodes:{}};S.status={};
let view=sysInspector({});
assert.ok(view.includes('아직 하는 일이 분석되지 않았습니다.'));
assert.ok(!view.includes('mkJobs'));assert.ok(!view.includes('요청을 복사'));
S.jobs.nodes[S.node]={jobs:[{name:'Store item',what:'Save the submitted item',starts_when:'On submit',routes:[]}]};
view=sysInspector({});assert.ok(view.includes('Store item'));assert.ok(view.includes('Save the submitted item'));
assert.ok(!view.includes('mkJobs'));assert.ok(!view.includes('요청을 복사'));
S.jobs.nodes[S.node]={jobs:[]};S.lang='en';view=sysInspector({});
assert.ok(view.includes('No jobs were established from the code.'));assert.ok(!view.includes('mkJobs'));
S.jobs.nodes={};view=sysInspector({});assert.ok(view.includes('Program jobs have not been analyzed yet.'));
`);
'''
        result=subprocess.run([node,'-e',script],cwd=Path(project.__file__).parent,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_settings_round_trip_and_validation_preserve_saved_value(self):
        self.assertFalse(mapcore.settings()['open_refresh'])
        wanted={'open_refresh':True,'since':'time','since_time':'2026-10-01T18:30'}
        mapcore.save_settings(wanted)
        self.assertEqual(mapcore.settings(),wanted)
        with self.assertRaises(ValueError):mapcore.save_settings({**wanted,'since_time':''})
        self.assertEqual(mapcore.settings(),wanted)

    def test_comparison_baselines_and_repository_specific_author(self):
        from datetime import datetime, timezone, timedelta
        now=datetime(2026,10,19,12,tzinfo=timezone.utc)
        last=now-timedelta(days=2)
        self.assertEqual(mapcore.since_of('/demo/a',last,now)[0],last)
        self.assertEqual(mapcore.since_of('/demo/a',None,now)[0],now-timedelta(days=1))
        mapcore.save_settings({'open_refresh':False,'since':'time','since_time':'2026-10-01T18:30+09:00'})
        self.assertEqual(mapcore.since_of('/demo/a',last,now)[0].isoformat(),'2026-10-01T18:30:00+09:00')
        mapcore.save_settings({'open_refresh':False,'since':'my_commit','since_time':''})
        import subprocess
        calls=[]
        def git(args,**kwargs):
            calls.append(args)
            output='demo@example.invalid\n' if 'config' in args else '2026-10-10T19:00:00+09:00\n'
            return subprocess.CompletedProcess(args,0,output,'')
        with patch('subprocess.run',side_effect=git):
            baseline,_=mapcore.since_of('/demo/a',last,now)
        self.assertEqual(baseline.isoformat(),'2026-10-10T19:00:00+09:00')
        self.assertTrue(all(args[:3]==['git','-C','/demo/a'] for args in calls))
        with patch('subprocess.run',return_value=subprocess.CompletedProcess([],1,'','missing')):
            self.assertEqual(mapcore.since_of('/demo/a',last,now)[0],last)

    def test_child_collection_reads_same_settings_as_app(self):
        mapcore.save_settings({'open_refresh':False,'since':'time','since_time':'2026-10-01T18:30'})
        child=self.root/'staging'
        env=project.child_environment(child,{'refs':{},'layout':{}})
        with patch.dict(os.environ,env),patch.object(mapcore,'ROOT',str(child)):
            self.assertEqual(mapcore.settings()['since'],'time')

    def test_refresh_uses_selected_time_for_commits_and_pr_collection(self):
        self.run_refresh_case(False)

    def test_refresh_never_compares_static_baseline_against_retained_ai_map(self):
        self.run_refresh_case(True)

    def run_refresh_case(self, ai):
        import runpy, subprocess
        folder=self.root/'legacy';folder.mkdir()
        current=sample('/demo/repo','bbbbbbbb')
        current['extractor']=mapcore.extractor_id(str(folder))
        if ai:
            current['commit']='cccccccc'
            current['analysis']={'source':'ai'}
        (folder/'dev.json').write_text(json.dumps(current))
        (folder/'status.json').write_text(json.dumps({'merged_prs':[]}))
        (folder/'changes.json').write_text(json.dumps({'last_refresh':'2026-10-18T00:00:00+00:00','entries':[]}))
        mapcore.save_settings({'open_refresh':False,'since':'time','since_time':'2026-10-01T18:30+09:00'})
        calls=[]
        def run(args,**kwargs):
            args=list(map(str,args));calls.append(args)
            if args[0]=='git':
                output=''
                if 'rev-parse' in args:output='bbbbbbbb' if '--short' in args else 'b'*40
                if 'rev-list' in args:output='a'*40
            else:
                output=''
                if any(a.endswith('extract.py') for a in args):
                    previous=sample('/demo/repo','aaaaaaaa');previous['screens']=[]
                    Path(args[-1]).write_text(json.dumps(previous))
            return subprocess.CompletedProcess(args,0,output,'')
        with patch.object(sys,'argv',['refresh.py','legacy','/demo/repo','7']), \
             patch.dict(os.environ,{'WHERE_WERE_WE_REFS':'{"dev":"origin/dev"}'}), \
             patch('subprocess.run',side_effect=run):
            runpy.run_path(str(Path(project.__file__).with_name('refresh.py')),run_name='__main__')
            first=json.loads((folder/'changes.json').read_text())
            saved=mapcore.settings()
            runpy.run_path(str(Path(project.__file__).with_name('refresh.py')),run_name='__main__')
        changes=json.loads((folder/'changes.json').read_text())
        self.assertEqual(changes['last_result']['since'],'2026-10-01T18:30:00+09:00')
        self.assertEqual(changes['last_result']['since'],first['last_result']['since'])
        self.assertGreater(changes['last_refresh'],first['last_refresh'])
        self.assertEqual(mapcore.settings(),saved)
        if ai:
            self.assertEqual(changes['entries'],[])
            self.assertEqual(json.loads((folder/'dev.json').read_text())['commit'],'cccccccc')
        else:self.assertEqual(changes['entries'][0]['branches']['dev']['from'],'aaaaaaaa')
        self.assertTrue(any('--before=2026-10-01T18:30:00+09:00' in a for args in calls for a in args))
        collect=next(args for args in calls if any(a.endswith('collect.py') for a in args))
        self.assertGreater(int(collect[-1]),7)

    def test_project_preserves_each_repository_latest_comparison_result(self):
        project.configure('studio',{'repositories':[{'id':'web','path':'/demo/web'},{'id':'api','path':'/demo/api'}]})
        for rid in ('web','api'):
            project.publish('studio',rid,{'dev':sample('/demo/'+rid),'changes':{'entries':[],
                'last_result':{'at':'2026-10-19T00:00:00+00:00','since':'2026-10-01T00:00:00+00:00','changed':False}}},{})
        results=project.read_bundle('studio')['changes']['last_results']
        self.assertEqual({r['repository'] for r in results},{'web','api'})
        self.assertTrue(all(r['changed'] is False for r in results))

    def test_settings_ui_save_language_and_optional_open_refresh(self):
        import shutil, subprocess
        node=shutil.which('node')
        if not node:self.skipTest('Node is required for UI behavior checks')
        script=r'''
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const html=fs.readFileSync('ui/index.html','utf8');
const js=html.slice(html.indexOf('<script>')+8,html.lastIndexOf('</script>'));
const elements={}, calls=[];let chosen='last_refresh',rejectSave=false;
const element=id=>elements[id] ||= {innerHTML:'',value:'',checked:false,disabled:false,
  querySelector:()=>({value:chosen}),querySelectorAll:()=>[],close(){this.open=false;}};
global.document={getElementById:element,querySelectorAll:()=>[]};
global.window={__TAURI__:{core:{invoke:async(name,args)=>{
  calls.push([name,args]);
  if(name==='read_project')return JSON.stringify({dev:{repo:'/demo',screens:[]},main:null});
  if(name==='save_settings'){if(rejectSave)throw Error('disk full');return args.json;}
  if(name==='refresh')return '';
  throw Error(name);
}}}};
global.localStorage={getItem:()=>null};
const source=js.slice(0,js.indexOf("$('q').oninput"));
const settings=js.slice(js.indexOf('function renderSettings()'),js.indexOf("$('settings').onclick"));
vm.runInThisContext(source+'\n'+settings+`\n(async()=>{
  render=()=>{};
  await loadProject('demo',true);
  assert.equal(calls.filter(c=>c[0]==='refresh').length,0);
  S.settings.open_refresh=true;await loadProject('demo',true);
  assert.equal(calls.filter(c=>c[0]==='refresh').length,1);
  await loadProject('demo',false);
  assert.equal(calls.filter(c=>c[0]==='refresh').length,1);
  renderSettings();assert.ok(element('settings-dialog').innerHTML.includes('서비스를 열 때 새로고침'));
  S.lang='en';renderSettings();assert.ok(element('settings-dialog').innerHTML.includes('Refresh when opening a service'));
  chosen='time';element('sinceTime').value='';await element('saveSt').onclick();
  assert.equal(calls.filter(c=>c[0]==='save_settings').length,0);
  element('sinceTime').value='2026-10-01T18:30';element('openRefresh').checked=false;
  rejectSave=true;await element('saveSt').onclick();assert.equal(S.settings.open_refresh,true);
  rejectSave=false;await element('saveSt').onclick();
  assert.deepEqual(S.settings,{open_refresh:false,since:'time',since_time:'2026-10-01T18:30'});
  S.changes={entries:[],last_results:[{repository:'api',at:'2026-10-19T00:00:00Z',since:'2026-10-01T00:00:00Z',changed:false,scope:'basic'}]};
  const view=changesView({});assert.ok(view.includes('No changes since the selected baseline'));assert.ok(view.includes('api'));assert.ok(!view.includes('이후'));
})().catch(error=>{console.error(error);process.exitCode=1;});`);
'''
        result=subprocess.run([node,'-e',script],cwd=Path(project.__file__).parent,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)

class Registration(TemporaryProject):
    def test_real_browser_connects_code_without_manual_ids_and_preserves_existing_settings(self):
        import html as html_module,subprocess
        chrome=Path('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome')
        if not chrome.is_file():self.skipTest('Chrome is required for the real registration-form check')
        source=(Path(project.__file__).parent/'ui/index.html').read_text()
        script=source.split('<script>',1)[1].split('</script>',1)[0].split("$('q').oninput",1)[0]
        script+=source[source.index('function renderAgentPrompt() {'):source.index("$('agent').onclick")]
        bootstrap=r'''
const saved=[],accountChanges=[],backendCalls=[];let accountFailure=false,analysisBundle=null,resultReadFailure=false,delayedResult=null;
window.__TAURI__={core:{invoke:async(command,args)=>{
  backendCalls.push(command);
  if(command==='read_project'){if(delayedResult)return delayedResult;if(resultReadFailure)throw Error('Cannot read saved result');return JSON.stringify(analysisBundle);}
  if(command==='make_system')return JSON.stringify({handoff:'Analyze pinned code',commit:'abc',record_arguments:{repository:'web'},result_before:[{task:'system',before:null}]});
  if(command==='make_steps')return JSON.stringify({handoff:'Read '+args.repository,commit:'abc',record_arguments:{repository:args.repository},result_before:[{task:'steps',key:'server.py::Save',before:null}]});
  if(command==='save_project'){saved.push(JSON.parse(args.configuration));return '';}
  if(command==='list_projects')return ['demo'];
  if(command==='github_accounts')return JSON.stringify({accounts:['alice','bob'],selected:'bob'});
  if(command==='use_github_account'){accountChanges.push(args);if(accountFailure)throw Error('GITHUB_ACCESS|github.com|bob|repository');return '';}
  throw Error('Unexpected command: '+command);
}}};
'''
        checks=r'''
(async()=>{
  const assert=(ok,message)=>{if(!ok)throw Error(message);};
  loadProject=async()=>{};
  const field=(i,key)=>document.querySelector(`[data-repository-row="${i}"] [data-field="${key}"]`);
  const change=(i,key,value)=>{field(i,key).value=value;field(i,key).dispatchEvent(new Event('change'));};
  S.project='demo';S.maps={};S.projectInfo={repositories:[],shared_data:[]};
  editProject(true);$('projectName').value='demo';
  assert(field(0,'id').type==='hidden','The user must not enter an internal repository ID');
  change(0,'path','/demo/web');
  assert(field(0,'name').value==='web','A missing display name should use the folder name');
  $('addRepository').click();
  change(1,'name','API Server');change(1,'path','/demo/api');
  const apiId=field(1,'id').value;
  const target=document.querySelector(`[data-repository-row="0"] [data-api-target][value="${apiId}"]`);
  assert(target && target.parentElement.textContent.includes('API Server'),'Choose server code by display name');
  target.checked=true;
  change(1,'name','API Backend');
  assert(target.isConnected && target.checked,'Renaming code must preserve server checkboxes and pending selection');
  $('addSharedData').click();
  let member=document.querySelector('[data-shared-member]');
  member.querySelector('[data-member-repo]').value=field(0,'id').value;
  member.querySelector('[data-member-table]').value='users';
  document.querySelector('[data-add-member]').click();
  member=document.querySelectorAll('[data-shared-member]')[1];
  member.querySelector('[data-member-repo]').value=apiId;
  member.querySelector('[data-member-table]').value='users';
  await $('saveProject').onclick();
  const created=saved.at(-1);
  assert(created.repositories[0].id==='web','The folder should supply the ID');
  assert(created.repositories[1].id==='api-server','The display name should supply the ID');
  assert(created.repositories[0].refs.dev==='HEAD' && created.repositories[0].refs.main===null,'New code should not require a dev branch');
  assert(created.repositories[0].api_targets[0]===apiId,'Server identity must survive the UI selection');
  assert(created.shared_data[0].id && created.shared_data[0].members.length===2,'Shared-data IDs are automatic and members survive');
  const existing={repositories:[{id:'custom-id',name:'Web',path:'/demo/old',refs:{dev:'origin/release',main:'v1.0'},
    layout:{frontend:null,backend:'app'},api_targets:['server-key'],legacy:true},
    {id:'server-key',name:'Server',path:'/demo/server',refs:{dev:'HEAD',main:null},layout:{},api_targets:[]}],
    shared_data:[{id:'existing-data',members:[{repository:'custom-id',table:'users'},{repository:'server-key',table:'users'}]}]};
  S.projectInfo=structuredClone(existing);editProject(false);change(0,'name','Renamed Web');
  await $('saveProject').onclick();
  const updated=saved.at(-1);
  assert(updated.repositories[0].id==='custom-id' && updated.repositories[0].legacy,'Existing identity and legacy flag must stay');
  assert(updated.repositories[0].refs.dev==='origin/release' && updated.repositories[0].refs.main==='v1.0','Existing branch/tag refs must stay');
  assert(updated.repositories[0].layout.frontend===null && updated.repositories[0].layout.backend==='app','Existing source-root settings must stay');
  assert(updated.shared_data[0].id==='existing-data','Existing shared-data identity must stay');
  assert(updated.repositories[0].api_targets[0]==='server-key','Existing server connection must stay');
  assert(updated.shared_data[0].members.length===2,'Existing shared members must stay');
  assert(S.projectInfo.repositories[0].name==='Web','Editing must not mutate the loaded project before saving');
  S.projectInfo={repositories:[],shared_data:[]};S.maps={main:{repo:'/demo/legacy'}};
  editProject(false);await $('saveProject').onclick();
  const legacy=saved.at(-1).repositories[0];
  assert(legacy.legacy && legacy.id==='original' && legacy.refs.dev===null && legacy.refs.main==='origin/main','Main-only legacy maps must remain main-only');
  S.lang='en';S.maps={};editProject(true);
  assert(!/[가-힣]/.test($('project-dialog').innerText),'English form must not show untranslated interface text');
  const shownError=registrationError('ValueError: Use an absolute repository folder path');assert(shownError.startsWith('Enter the full path to the folder containing the code.') && shownError.includes('Use an absolute repository folder path</pre>'),'Use plain English errors and keep the original in details');
  S.projectInfo={repositories:[{id:'vue',name:'Web',collected:true,commits:{dev:'demo'},
    analysis_scope:{dev:{source:'basic',frontend:'needs_analysis',backend:'disabled'}}}]};
  S.branch='dev';renderRepositories();
  assert($('repository-bar').textContent.includes('Not identified by basic collection'),'A successful collection must not look like complete analysis');
  assert($('repository-bar').textContent.includes('Excluded from analysis'),'Disabled areas must be distinct from missing analysis');
  const screen=(path,file,via)=>({path,file,actions:[],api_functions:[{file:'src/api.ts',name:'load',via}]});
  assert(!commonVia({screens:[screen('/one','src/One.tsx','src/Child.tsx')]}).has('src/Child.tsx'),'A component used on one screen is not shared');
  assert(!commonVia({screens:[screen('/one','src/One.tsx','src/One.tsx')]}).has('src/One.tsx'),'Direct screen requests must stay visible');
  assert(commonVia({screens:[screen('/one','src/One.tsx','src/Header.tsx'),screen('/two','src/Two.tsx','src/Header.tsx')]}).has('src/Header.tsx'),'Shared headers still count as shared');
  S.project='demo';S.repository='';S.projectInfo={repositories:[{id:'web',name:'Web',collected:true,commits:{dev:'abc'},error:'GITHUB_ACCESS|github.com|bob|repository'}]};
  S.lang='en';renderRepositories();
  assert(document.querySelector('[data-github-repair]'),'Offer account repair only on authentication-related failure');
  const folded=$('repository-bar').cloneNode(true);folded.querySelectorAll('details').forEach(d=>d.remove());
  assert(folded.textContent.includes('@bob') && !folded.textContent.includes('GITHUB_ACCESS'),'Use readable account-aware errors');
  assert([...$('repository-bar').querySelectorAll('details')].some(d=>d.textContent.includes('GITHUB_ACCESS|github.com|bob|repository')),'The original error stays in details');
  await editGitHubAccount('web');
  assert($('githubAccount').value==='bob','Preselect the remembered account');
  assert(!/[가-힣]/.test($('project-dialog').innerText),'Account repair is translated');
  accountFailure=true;await $('saveGithub').onclick();
  assert($('project-dialog').open && $('githubError').textContent.includes('@bob'),'Preserve the dialog on access failure');
  accountFailure=false;$('githubAccount').value='alice';let retried=0;doRefresh=async()=>{retried++;};
  await $('saveGithub').onclick();
  assert(accountChanges.at(-1).repository==='web' && accountChanges.at(-1).account==='alice' && retried===1,'Save only the chosen code account and retry collection');
  S.projectInfo.repositories[0].error=null;renderRepositories();
  assert(!document.querySelector('[data-github-repair]'),'Normal collection should not add an account selector');
  S.lang='ko';await editGitHubAccount('');
  assert($('project-dialog').innerText.includes('선택한 계정은 이 코드에만 사용합니다.'),'Legacy repair should use the same plain guidance');
  $('project-dialog').close();
  S.lang='en';S.project='demo';S.repository='web';S.branch='dev';S.loadToken=5;
  S.desiredProject='demo';S.desiredRepository='web';S.maps={dev:{repo:'/demo/web',screens:[]}};
  S.projectInfo={repositories:[{id:'web',results:{dev:{system:null}}}]};
  const changes={last_refresh:'fixed',entries:[{at:'retained'}]},settings={since:'time',since_time:'2026-10-01T18:30'};
  S.changes=changes;S.settings=settings;S.chi=2;S.view='sys';S.node='web::worker';
  render=()=>{if(S.agentPrompt)renderAgentPrompt();};
  Object.defineProperty(navigator,'clipboard',{value:{writeText:async()=>{}},configurable:true});
  await requestAgentAction('make_system');
  assert($('insp').textContent.includes('1. Copy the request') && $('insp').textContent.includes('3. Check results'),'Use the chosen existing-pane sequence');
  await $('cpAgent').onclick();
  assert(!$('analysisResultState').textContent.includes('saved a new result'),'Copying must not imply saved or running analysis');
  analysisBundle={project:{repositories:[{id:'web',results:{dev:{system:null}}}]},dev:{repo:'/demo/web',screens:[]},main:null,changes:{last_refresh:'must-not-replace'},branch_details:{}};
  const beforeChecks=backendCalls.length;
  await $('checkAnalysisResults').onclick();
  assert($('analysisResultState').textContent.includes('No new result yet'),'Missing results need an explicit state');
  assert(S.changes===changes && S.chi===2 && S.settings===settings,'Checking results must preserve change history, selected entry and comparison settings');
  assert(backendCalls.slice(beforeChecks).every(c=>c==='read_project'),'Result checks must only read saved data');
  analysisBundle.project.repositories[0].results.dev.system={version:'new',commit:'abc',stale:false};
  await $('checkAnalysisResults').onclick();
  assert($('analysisResultState').textContent.includes('saved a new result'),'Completion requires a saved matching result');
  analysisBundle.project.repositories[0].results.dev.system={version:'old',commit:'different',stale:false};
  await $('checkAnalysisResults').onclick();
  assert($('analysisResultState').textContent.includes('different code version'),'A stale saved result must be distinct from a new result');
  const mapBefore=S.maps.dev;resultReadFailure=true;await $('checkAnalysisResults').onclick();
  assert(S.maps.dev===mapBefore && S.changes===changes,'A failed result read must preserve the displayed map and changes');
  resultReadFailure=false;S.lang='ko';renderAgentPrompt();
  assert($('insp').textContent.includes('3. 결과 확인'),'Korean shows the same result-only path');
  S.lang='en';
  assert(tr('AI에게 보낼 요청만 만듭니다. 앱에서 바로 분석하지 않습니다.').includes('Nothing is analyzed in the app'),'Step requests must not retain old automatic-analysis wording');
  analysisBundle.project.repositories[0].results.dev.system={version:'proposal',commit:'abc',stale:false,proposal:true};
  await $('checkAnalysisResults').onclick();
  assert($('analysisResultState').textContent.includes('saved separately') && $('viewAnalysisResults').textContent==='View AI proposal','A saved AI proposal is offered as the proposal, not as the old manual map');
  S.analysisRequest.requirements[0].before={version:'proposal'};await $('checkAnalysisResults').onclick();
  assert($('analysisResultState').textContent.includes('earlier AI proposal') && $('viewAnalysisResults').textContent==='View AI proposal','An earlier AI proposal is offered as the proposal too');
  S.repository='';S.projectInfo={repositories:[{id:'api-a'},{id:'api-b'}]};
  requests=()=>['api-a','api-b'].map(repository=>({route:{repository,file:repository+'/server.py',function:'Save'}}));
  await requestAgentAction('make_steps',{screen:'/items'});
  assert(S.analysisRequest.requirements.length===2,'A cross-code screen requires each server result');
  analysisBundle={project:{repositories:[{id:'api-a',results:{dev:{steps:{'server.py::Save':{version:'a-new',commit:'abc'}}}}},
    {id:'api-b',results:{dev:{steps:{}}}}]},dev:{repo:'/demo',screens:[]},main:null,branch_details:{},changes:{last_refresh:'do-not-use'}};
  await $('checkAnalysisResults').onclick();
  assert($('analysisResultState').textContent.includes('Some results'),'One saved server is partial completion');
  analysisBundle.project.repositories[1].results.dev.steps['server.py::Save']={version:'b-new',commit:'abc'};
  await $('checkAnalysisResults').onclick();
  assert($('analysisResultState').textContent.includes('saved a new result'),'All server results must be saved before completion');
  let resolveRead;delayedResult=new Promise(resolve=>{resolveRead=resolve;});
  const originalMap=S.maps.dev,pendingCheck=$('checkAnalysisResults').onclick();
  S.branch='main';resolveRead(JSON.stringify({...analysisBundle,dev:{repo:'/wrong'}}));await pendingCheck;
  assert(S.maps.dev===originalMap,'A late result check must not apply to another branch');
  assert(S.changes===changes && S.chi===2 && S.settings===settings,'All result paths preserve change history and baseline');
  document.body.dataset.registrationTest='passed';
  const output=document.createElement('pre');output.id='registration-result';output.textContent=JSON.stringify(saved);document.body.append(output);
})().catch(error=>{document.body.dataset.registrationTest='failed';const output=document.createElement('pre');output.textContent=error.stack;document.body.append(output);});
'''
        page=source.split('<script>',1)[0]+'<script>'+bootstrap+script+checks+'</script></body></html>'
        page=page.replace('href="tokens.css"','href="'+(Path(project.__file__).parent/'ui/tokens.css').as_uri()+'"')
        page=page.replace('href="app.css"','href="'+(Path(project.__file__).parent/'ui/app.css').as_uri()+'"')
        target=self.root/'registration-check.html';target.write_text(page)
        result=subprocess.run([str(chrome),'--headless','--disable-gpu','--no-first-run','--disable-background-networking',
            '--disable-component-update','--no-default-browser-check','--user-data-dir='+str(self.root/'chrome'),
            '--virtual-time-budget=1000','--dump-dom',target.as_uri()],capture_output=True,text=True,timeout=40)
        self.assertEqual(result.returncode,0,result.stderr[-1200:])
        self.assertTrue('data-registration-test="passed"' in result.stdout,result.stdout[-2000:])
        import re
        match=re.search(r'<pre id="registration-result">(.*?)</pre>',result.stdout,re.S)
        self.assertIsNotNone(match)
        configurations=json.loads(html_module.unescape(match.group(1)))
        for value in configurations:project.validate(value)

    def test_repository_identifiers_are_generated_without_renaming_existing_ones(self):
        import shutil,subprocess
        node=shutil.which('node')
        if not node:self.skipTest('Node is required for UI behavior checks')
        script=r'''
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const html=fs.readFileSync('ui/index.html','utf8');
const js=html.slice(html.indexOf('<script>')+8,html.lastIndexOf('</script>'));
global.window={__TAURI__:{core:{invoke:async()=>[]}}};global.localStorage={getItem:()=>null};
vm.runInThisContext(js.slice(0,js.indexOf("$('q').oninput"))+`
assert.equal(newRepositoryId('Web app','/demo/web',[]),'web-app');
assert.equal(newRepositoryId('웹 화면','/demo/frontend/',[]),'frontend');
assert.equal(newRepositoryId('Web','/demo/web',['web']),'web-2');
assert.equal(newRepositoryId('Web','/demo/web',['web','web-2']),'web-3');
assert.equal(newRepositoryId('2026 app','/demo/app',[]),'repo-2026-app');
assert.equal(newRepositoryId('한글','/demo/한글',[]),'repository');
const name='x'.repeat(80),first=newRepositoryId(name,'/demo',[]),second=newRepositoryId(name,'/demo',[first]);
assert.ok(first.length<=48 && second.length<=48);assert.notEqual(first,second);
const existing=[{id:'original',name:'Renamed',path:'/demo/web'},{id:'custom-key',name:'Other',path:'/demo/other'},
 {id:'',name:'Web',path:'/demo/new'},{id:'',name:'Web',path:'/demo/another'}];
ensureRepositoryIds(existing);
assert.deepEqual(existing.map(r=>r.id),['original','custom-key','web','web-2']);
ensureRepositoryIds(existing);assert.deepEqual(existing.map(r=>r.id),['original','custom-key','web','web-2']);
`);
'''
        result=subprocess.run([node,'-e',script],cwd=Path(project.__file__).parent,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)

class Projects(TemporaryProject):
    def test_collection_success_distinguishes_unrecognized_analysis_from_disabled_roles(self):
        project.configure('studio',{'repositories':[{'id':'web','path':'/demo/web','layout':{'frontend':'pages','backend':None}}]})
        raw=sample('/demo/web');raw['screens']=[];raw['coverage']={'frontend':False,'backend':False}
        project.publish('studio','web',{'dev':raw},{})
        scope=project.read_bundle('studio')['project']['repositories'][0]['analysis_scope']['dev']
        self.assertEqual(scope['frontend'],'needs_analysis')
        self.assertEqual(scope['backend'],'disabled')
        self.assertEqual(scope['source'],'basic')
        folder=self.root/'legacy';folder.mkdir()
        (folder/'dev.json').write_text(json.dumps(raw))
        self.assertEqual(project.read_bundle('legacy')['project']['analysis_scope']['dev']['frontend'],'needs_analysis')

    def test_ai_empty_results_and_legacy_missing_coverage_stay_unverified(self):
        snapshot=sample('/demo/web');snapshot['screens']=[]
        self.assertEqual(project.analysis_scope(snapshot,{})['frontend'],'unknown')
        snapshot['analysis']={'source':'ai','unknown':['Navigation was not established']}
        scope=project.analysis_scope(snapshot,{})
        self.assertEqual(scope['frontend'],'not_established')
        self.assertEqual(scope['unknown'],['Navigation was not established'])

    def test_common_components_require_multiple_screens_and_keep_direct_requests(self):
        pages=[]
        for path in ('/one','/two','/three'):
            page=sample('/demo/web')['screens'][0];page['path']=path;page['file']='src/'+path[1:]+'.tsx'
            page['api_functions']=[{'file':'src/api.ts','name':'load','via':'src/Header.tsx'}]
            pages.append(page)
        snapshot=sample('/demo/web');snapshot['screens']=pages
        self.assertIn('src/Header.tsx',mapcore.Map('unused',data=snapshot,bundle={}).common)
        single={**snapshot,'screens':[pages[0]]}
        self.assertNotIn('src/Header.tsx',mapcore.Map('unused',data=single,bundle={}).common)
        pages[0]['api_functions'][0]['via']=pages[0]['file']
        self.assertNotIn(pages[0]['file'],mapcore.Map('unused',data=snapshot,bundle={}).common)

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
 if os.environ.get('FAKE_GITHUB'):
  active=Path(os.environ['FAKE_ACTIVE']).read_text().strip()
  account=os.environ.get('GH_TOKEN','test-token-'+active).removeprefix('test-token-')
  if args[:2]==['auth','token']:print('test-token-'+args[-1]);sys.exit()
  if args[:2]==['auth','git-credential']:
   sys.stdin.read();print('username='+account+'\npassword='+os.environ.get('GH_TOKEN','')+'\n');sys.exit()
  if args[:2]==['api','user']:print(account);sys.exit()
  if args[:2]==['auth','status']:print(json.dumps(['alice','bob']));sys.exit()
  if account!='alice' or os.environ.get('FAKE_GH_DENY'):print('access failed',file=sys.stderr);sys.exit(1)
  if args[:2]==['repo','view']:print('{}');sys.exit()
 if os.environ.get('FAKE_GH_FAIL'):print('GitHub denied',file=sys.stderr);sys.exit(1)
 if os.environ.get('FAKE_GITHUB_DATA'):
  data=json.load(open(os.environ['FAKE_GITHUB_DATA']))
  if args[:2]==['pr','list']:print(json.dumps(data.get('merged',[]) if args[args.index('--state')+1]=='merged' else []));sys.exit()
  if args[:2]==['issue','view']:print(json.dumps(data['linked'][args[2]]));sys.exit()
  if args[:2]==['issue','list']:print('[]');sys.exit()
 print('[]');sys.exit()
sources=json.load(open(os.environ['FAKE_SOURCES']));files={os.path.realpath(k):v for k,v in sources.items()}.get(os.path.realpath(repo),{})
if args[0]=='fetch':
 if os.environ.get('FAKE_GITHUB') and os.environ.get('GH_TOKEN')!='test-token-alice':print('wrong Git credential',file=sys.stderr);sys.exit(1)
 if Path(repo).name=='broken':print('fetch denied',file=sys.stderr);sys.exit(1)
elif args[0]=='ls-tree':print('\n'.join(files))
elif args[0]=='show':
 file=args[-1].split(':',1)[1]
 if file not in files:sys.exit(1)
 print(files[file],end='')
elif args[0]=='rev-parse':print(hashlib.sha1(json.dumps(files,sort_keys=True).encode()).hexdigest()[:8] if '--short' in args or '--short=8' in args else hashlib.sha1(json.dumps(files,sort_keys=True).encode()).hexdigest())
elif args[0]=='rev-list':print('0')
elif args[0]=='remote':print('https://github.com/example/studio.git' if os.environ.get('FAKE_GITHUB') else 'https://example.invalid/studio.git')
'''

class Collection(TemporaryProject):
    def test_real_collection_preserves_pr_and_closed_issue_evidence_for_briefing(self):
        from datetime import datetime,timedelta,timezone
        env=self.environment();now=datetime.now(timezone.utc);merged=(now-timedelta(hours=1)).isoformat()
        issue_url='https://github.com/example/web/issues/9'
        pr={'number':7,'title':'Reuse a job','body':'Before retries duplicated jobs. After the change retries reuse one job.',
            'url':'https://github.com/example/web/pull/7','headRefName':'fix/retry','baseRefName':'main','author':{'login':'demo'},
            'createdAt':merged,'updatedAt':merged,'mergedAt':merged,
            'files':[{'path':'src/Settings.tsx'}]+[{'path':f'src/item{i}.tsx'} for i in range(99)],
            'closingIssuesReferences':[{'number':9,'title':'Retry creates duplicates','url':issue_url}]}
        payload=self.root/'github-data.json';payload.write_text(json.dumps({'merged':[pr],'linked':{issue_url:{'number':9,'title':'Retry creates duplicates','url':issue_url,'body':'Repeating a request creates duplicate jobs.','state':'CLOSED'}}}))
        env['FAKE_GITHUB_DATA']=str(payload)
        configured=self.run_cli(env,'configure','studio',json.dumps({'repositories':[{'id':'web','path':str(self.root/'web')}]}))
        self.assertEqual(configured.returncode,0,configured.stderr)
        (Path(env['WHERE_WERE_WE_ROOT'])/'settings.json').write_text(json.dumps({'since':'time','since_time':(now-timedelta(hours=2)).isoformat(),'open_refresh':False}))
        collected=self.run_cli(env,'refresh','studio');self.assertNotIn('FAILED',collected.stdout,collected.stderr)
        state=json.loads((Path(env['WHERE_WERE_WE_ROOT'])/'studio/repository-state.json').read_text())
        folder=Path(env['WHERE_WERE_WE_ROOT'])/'studio/repositories/web/snapshots'/state['web']['generation']
        frozen=json.loads((folder/'changes.json').read_text())['last_result']['evidence']
        self.assertEqual(frozen['prs'][0]['body'],pr['body'])
        self.assertEqual(frozen['issues'][0]['body'],'Repeating a request creates duplicate jobs.')
        self.assertTrue(frozen['collection']['pr_files']['possibly_truncated'])
        import subprocess
        result=subprocess.run([sys.executable,'-I','-B',str(Path(project.__file__).with_name('briefing.py')),'request','studio','--lang','en'],env=env,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        request=json.loads(result.stdout)
        self.assertEqual(request['input']['prs'][0]['number'],7)
        self.assertTrue(any(w['code']=='collection_limited' for w in request['input']['warnings']))

    def test_real_git_credential_protocol_uses_child_account(self):
        import shutil,subprocess
        gh=shutil.which('gh')
        if not gh:self.skipTest('GitHub CLI is required for the local credential protocol check')
        env=self.environment();active=self.root/'active-account';active.write_text('bob')
        env.update(FAKE_GITHUB='1',FAKE_ACTIVE=str(active))
        repo={'path':str(self.root/'web'),'refs':{},'layout':{},'github':{'host':'github.com','account':'alice'}}
        with patch.dict(os.environ,env):child=project.child_environment(self.root/'maps',repo)
        child.update(GIT_CONFIG_NOSYSTEM='1',GIT_CONFIG_GLOBAL=os.devnull)
        # Only the preflight uses fake gh. Real git and real gh exchange the fake
        # token through the local credential protocol without a network request.
        child['PATH']=str(Path(gh).parent)+os.pathsep+child['PATH']
        child['GH_CONFIG_DIR']=str(self.root/'empty-gh-config')
        result=subprocess.run(['/usr/bin/git','credential','fill'],input='protocol=https\nhost=github.com\n\n',env=child,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('username=x-access-token',result.stdout);self.assertIn('password=test-token-alice',result.stdout)
        self.assertEqual(active.read_text(),'bob')

    def test_account_switch_and_access_failure_use_real_isolated_collection(self):
        env=self.environment();active=self.root/'active-account';active.write_text('alice')
        env.update(FAKE_GITHUB='1',FAKE_ACTIVE=str(active))
        configured=self.run_cli(env,'configure','studio',json.dumps({'repositories':[{'id':'web','path':str(self.root/'web')}]}))
        self.assertEqual(configured.returncode,0,configured.stderr)
        self.assertEqual(json.loads(configured.stdout)['repositories'][0]['github']['account'],'alice')
        active.write_text('bob')
        success=self.run_cli(env,'refresh','studio')
        self.assertEqual(success.returncode,0,success.stderr);self.assertNotIn('FAILED',success.stdout)
        before=json.loads(self.run_cli(env,'read','studio').stdout)['project']['repositories'][0]
        self.assertTrue(before['collected'])
        denied=self.run_cli(dict(env,FAKE_GH_DENY='1'),'refresh','studio')
        self.assertIn('GITHUB_ACCESS|github.com|alice|repository',denied.stdout)
        after=json.loads(self.run_cli(env,'read','studio').stdout)['project']['repositories'][0]
        self.assertEqual(before['generation'],after['generation'])
        self.assertNotIn('test-token',json.dumps(after))
        self.assertEqual(active.read_text(),'bob')
        self.assertEqual(json.loads(self.run_cli(env,'github-accounts','studio','--repository','web').stdout)['accounts'],['alice','bob'])

    def test_legacy_account_switch_and_failure_preserve_successful_files(self):
        import subprocess
        env=self.environment();active=self.root/'active-account';active.write_text('alice')
        env.update(FAKE_GITHUB='1',FAKE_ACTIVE=str(active))
        folder=Path(env['WHERE_WERE_WE_ROOT'])/'legacy';folder.mkdir(parents=True)
        (folder/'dev.json').write_text(json.dumps(sample(str(self.root/'web'))))
        def refresh(extra=None):
            return subprocess.run([sys.executable,'-I','-B',str(Path(project.__file__).with_name('refresh.py')),'legacy',str(self.root/'web')],env={**env,**(extra or {})},capture_output=True,text=True)
        first=refresh();self.assertEqual(first.returncode,0,first.stderr)
        active.write_text('bob')
        second=refresh();self.assertEqual(second.returncode,0,second.stderr)
        previous={n:(folder/n).read_bytes() for n in ('dev.json','main.json','status.json','changes.json')}
        denied=refresh({'FAKE_GH_DENY':'1'})
        self.assertNotEqual(denied.returncode,0);self.assertIn('GITHUB_ACCESS|github.com|alice|repository',denied.stderr)
        self.assertEqual(previous,{n:(folder/n).read_bytes() for n in previous})
        sources=Path(env['FAKE_SOURCES']);changed=json.loads(sources.read_text())
        changed[str(self.root/'web')]['src/Settings.tsx']+='\n// changed after successful collection\n'
        sources.write_text(json.dumps(changed))
        late_failure=refresh({'FAKE_GH_FAIL':'1'})
        self.assertNotEqual(late_failure.returncode,0);self.assertIn('GITHUB_ACCESS',late_failure.stderr)
        self.assertEqual(previous,{n:(folder/n).read_bytes() for n in previous})
        self.assertEqual(active.read_text(),'bob')

    def environment(self):
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

    def test_react_fastapi_sqlalchemy_screen_request_table_chain_is_preserved(self):
        env=self.environment();sources=json.loads(Path(env['FAKE_SOURCES']).read_text())
        sources[str(self.root/'api')]={
            'app/main.py':'from fastapi import FastAPI\nfrom app.models.settings import Setting\napp = FastAPI()\n@app.get("/settings")\ndef read_settings():\n    return session.query(Setting).all()\n',
            'app/models/settings.py':'class Setting(Base):\n    __tablename__ = "settings"\n'}
        Path(env['FAKE_SOURCES']).write_text(json.dumps(sources))
        conf={'repositories':[{'id':'web','path':str(self.root/'web'),'api_targets':['api']},
                              {'id':'api','path':str(self.root/'api')}]}
        self.assertEqual(self.run_cli(env,'configure','studio',json.dumps(conf)).returncode,0)
        result=self.run_cli(env,'refresh','studio');self.assertNotIn('FAILED',result.stdout,result.stdout)
        bundle=json.loads(self.run_cli(env,'read','studio').stdout)
        screen=bundle['dev']['screens'][0]
        self.assertEqual(screen['source_path'],'/settings')
        model=mapcore.Map('studio',data=bundle['dev'],bundle=bundle)
        route=model.requests(screen['path'])[0]['route']
        self.assertEqual((route['method'],route['path']),('GET','/settings'))
        self.assertEqual(route['tables'],['api::settings'])
        self.assertEqual(bundle['dev']['models']['api/Setting'],'api::settings')

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

    def test_mcp_reports_unrecognized_basic_collection_instead_of_complete_analysis(self):
        project.configure('studio',{'repositories':[{'id':'web','path':'/demo/web','layout':{'backend':None}}]})
        raw=sample('/demo/web');raw['screens']=[];raw['coverage']={'frontend':False,'backend':False}
        project.publish('studio','web',{'dev':raw},{})
        for output in (self.server.overview('studio'),self.server.find('missing','studio')):
            self.assertIn('frontend=needs_analysis',output)
            self.assertIn('backend=disabled',output)

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
