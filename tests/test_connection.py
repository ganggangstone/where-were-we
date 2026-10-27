"""Connection diagnostics use temporary registrations and fake server identities."""
import copy,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import mapcore

class Connection(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.root=Path(self.tmp.name);p=patch.object(mapcore,'ROOT',str(self.root));p.start();self.addCleanup(p.stop)
 def test_onboarding_prompt_connects_service_before_any_manual_project_setup(self):
  with patch.object(mapcore,'projects',return_value=[]):
   for lang in ('ko','en'):
    prompt=mapcore.setup_prompt(lang,onboarding=True)
    for token in ('app_control','catalog','configure','app_command_result','completed','repositories','api_targets'):
     self.assertIn(token,prompt)
    self.assertNotIn('extract a project first',prompt)
    self.assertNotIn('앱에서 프로젝트를 먼저',prompt)
    self.assertIn('confirm' if lang=='en' else '확인',prompt)
    from tests.reply_language import assert_reply_language
    assert_reply_language(self,prompt,lang)

 def test_onboarding_prompt_is_one_request_that_ends_at_the_first_analysis_result(self):
  # One copied request: connect, confirm, collect, then analyze only after explicit consent, and finish by reading the saved results.
  with patch.object(mapcore,'projects',return_value=[]):
   for lang in ('ko','en'):
    prompt=mapcore.setup_prompt(lang,onboarding=True)
    for token in ('prepare_analysis','task=all','analysis_plan','pins','read_results','app_command_result'):
     self.assertIn(token,prompt,(lang,token))
    for token in (('pricing','limits','permission','second') if lang=='en' else ('요금','한도','허락','다시 복사')):
     self.assertIn(token,prompt,(lang,token))
    # Consent for the paid analysis is part of the same confirmation as the repositories and first collection.
    confirm=prompt.index('Ask me to confirm' if lang=='en' else '내 확인을 받아')
    self.assertLess(confirm,prompt.index('prepare_analysis'))
    consent=prompt[confirm:prompt.index('prepare_analysis')]
    self.assertTrue(('pricing' in consent) if lang=='en' else ('요금' in consent))
    self.assertIn('read_results',prompt[prompt.index('prepare_analysis'):])
    # The result is read from the app command, never by refreshing to display it.
    self.assertIn('Do not call refresh' if lang=='en' else 'refresh를 실행하지',prompt)
 def test_onboarding_prompt_explains_source_structure_discovery_without_a_framework_choice(self):
  # The request says how screens and server code are found: by reading the code, not by asking me for a framework or source roots.
  with patch.object(mapcore,'projects',return_value=[]):
   en=mapcore.setup_prompt('en',onboarding=True);ko=mapcore.setup_prompt('ko',onboarding=True)
  for token in ('framework','layout','reading the code'):self.assertIn(token,en)
  for token in ('프레임워크','layout','코드를 읽어'):self.assertIn(token,ko)
 def test_onboarding_prompt_states_the_cost_without_unmeasured_warnings(self):
  with patch.object(mapcore,'projects',return_value=[]):
   self.assertNotIn('long time',mapcore.setup_prompt('en',onboarding=True))
   self.assertNotIn('오래 걸리',mapcore.setup_prompt('ko',onboarding=True))
 def test_onboarding_prompt_stops_honestly_and_keeps_saved_work(self):
  with patch.object(mapcore,'projects',return_value=[]):
   en=mapcore.setup_prompt('en',onboarding=True);ko=mapcore.setup_prompt('ko',onboarding=True)
  for token in ('new session','stop','saved','Do not claim'):self.assertIn(token,en)
  for token in ('새 세션','멈춰','저장된','말하지 마'):self.assertIn(token,ko)
 def test_onboarding_check_requires_the_tools_the_onboarding_request_uses(self):
  import connection
  needed=connection.required('onboarding')
  for tool in ('projects','app_control','app_command_result','app_state','server_info','confirm_connection'):self.assertIn(tool,needed)
  challenge=connection.begin(self.identity(),'onboarding')
  self.assertEqual(connection.confirm(challenge,self.identity(),list(connection.required('detail')))['state'],'missing_tools')
  self.assertEqual(connection.confirm(challenge,self.identity(),needed)['state'],'verified')
  # The first-run request also runs the planned analysis, so a connection missing those tools is not ready.
  for tool in ('analysis_plan','analyze','analysis_source','record_analysis','request_ai_task','record_ai_task','request_briefing','briefing_source','record_briefing'):self.assertIn(tool,needed)
  without=[t for t in needed if t!='analysis_plan']
  self.assertEqual(connection.confirm(connection.begin(self.identity(),'onboarding'),self.identity(),without)['state'],'missing_tools')
 def test_detail_check_requires_the_unified_plan_tool(self):
  import connection
  older=[t for t in connection.required('detail') if t!='analysis_plan']+['request_briefing','briefing_source','record_briefing']
  challenge=connection.begin(self.identity(),'detail')
  self.assertEqual(connection.confirm(challenge,self.identity(),older)['state'],'missing_tools')
 def identity(self):
  return {'python':'/Applications/Example.app/python3','server':'/Applications/Example.app/mcp_server.py','digest':'new','pid':11,'started_at':'2026-10-19T10:00:00+00:00','app_version':'0.3.0'}
 def test_fresh_server_is_not_evidence_that_current_agent_reconnected(self):
  import connection
  expected=self.identity()
  with patch.object(connection,'snapshot',return_value=expected),patch.object(connection,'probe',return_value={'identity':expected,'tools':list(connection.required('detail'))}):
   result=connection.diagnose('detail','en')
  self.assertEqual(result['connection']['state'],'not_verified')
  self.assertEqual(connection.check(result['challenge'])['state'],'not_verified')
  self.assertIn('confirm_connection',result['handoff'])
 def test_handoff_replies_in_conversation_language(self):
  import connection
  from reply_language import assert_reply_language
  expected=self.identity()
  for lang in ('ko','en'):
   with patch.object(connection,'snapshot',return_value=expected),patch.object(connection,'probe',return_value={'identity':expected,'tools':list(connection.required('detail'))}):
    result=connection.diagnose('detail',lang)
   assert_reply_language(self,result['handoff'],lang)
 def test_running_old_code_is_rejected_even_if_path_and_version_are_unchanged(self):
  import connection
  challenge=connection.begin(self.identity(),'detail');old=dict(self.identity(),digest='old')
  result=connection.confirm(challenge,old,list(connection.required('detail')))
  self.assertEqual(result['state'],'running_old_server')
  self.assertNotEqual(connection.check(challenge)['state'],'verified')
 def test_only_actual_capabilities_of_matching_server_confirm_connection(self):
  import connection
  challenge=connection.begin(self.identity(),'detail')
  result=connection.confirm(challenge,self.identity(),['projects'])
  self.assertEqual(result['state'],'missing_tools');self.assertIn('analysis_source',result['missing'])
  result=connection.confirm(challenge,self.identity(),list(connection.required('detail')))
  self.assertEqual(result['state'],'verified');self.assertEqual(connection.check(challenge)['state'],'verified')
 def test_registration_diagnostics_redact_environment_and_custom_arguments(self):
  import connection
  server=self.root/'old/mcp_server.py';server.parent.mkdir();server.write_text('old')
  python=self.root/'python3';python.write_text('fake')
  raw={'command':str(python),'args':['-u',str(server),'--token','SUPERSECRET'],'env':{'TOKEN':'SUPERSECRET'},'other':'preserve'}
  before=copy.deepcopy(raw);value=connection.registration(raw,self.identity())
  self.assertEqual(value['state'],'different_path');self.assertNotIn('SUPERSECRET',json.dumps(value));self.assertEqual(raw,before)
  value=connection.registration({'command':'/old/Example.app/python3','args':['/old/Example.app/mcp_server.py']},self.identity())
  self.assertEqual(value['state'],'app_moved_or_missing')
 def test_confirmed_result_is_invalidated_by_app_update_or_expired_challenge(self):
  import connection
  expected=self.identity();challenge=connection.begin(expected,'detail')
  connection.confirm(challenge,expected,list(connection.required('detail')))
  self.assertEqual(connection.check(challenge,dict(expected,digest='next'))['state'],'app_changed')
  with patch('time.time',return_value=10**12):self.assertEqual(connection.check(challenge)['state'],'expired')
  with self.assertRaises(ValueError):connection.check('../outside')
 def test_same_install_location_can_update_without_rewriting_custom_registration(self):
  import connection
  expected=self.identity();raw={'command':expected['python'],'args':['-I','-B',expected['server']],'env':{'PRIVATE':'unchanged'}}
  with patch.object(Path,'is_file',return_value=True):value=connection.registration(raw,dict(expected,digest='updated'))
  self.assertEqual(value['state'],'matches_app');self.assertEqual(raw['env']['PRIVATE'],'unchanged')

 def test_changed_fresh_server_cannot_be_reported_ready(self):
  import connection
  expected=self.identity()
  for identity,state in [(dict(expected,digest='other'),'app_changed'),(dict(expected,server='/other/mcp_server.py'),'different_server'),(None,'server_info_unavailable')]:
   with self.subTest(state=state),patch.object(connection,'snapshot',return_value=expected),patch.object(connection,'probe',return_value={'identity':identity,'tools':connection.required('detail')}):
    self.assertEqual(connection.diagnose()['fresh_server']['state'],state)
 def test_real_stdio_confirms_reconnected_server_and_rejects_same_path_old_process(self):
  import asyncio,os,shutil,connection
  from mcp import ClientSession,StdioServerParameters
  from mcp.client.stdio import stdio_client
  backend=self.root/'backend';backend.mkdir()
  for name in connection.BACKEND_FILES:shutil.copyfile(Path(connection.__file__).with_name(name),backend/name)
  params=StdioServerParameters(command=sys.executable,args=['-I','-B',str(backend/'mcp_server.py')],env={'HOME':str(self.root),'PATH':'/usr/bin:/bin','WHERE_WERE_WE_ROOT':str(self.root)})
  async def read(session,name,args={}):
   result=await session.call_tool(name,args)
   self.assertFalse(result.is_error,str(result));return json.loads(result.content[0].text)
  async def exercise():
   with open(os.devnull,'w') as errors:
    async with stdio_client(params,errlog=errors) as streams:
     async with ClientSession(*streams) as old:
      await old.initialize();old_info=await read(old,'server_info')
      # Emulate an update at the SAME installation path while old MCP stays alive.
      with (backend/'jobs.py').open('a') as f:f.write('\n# synthetic update\n')
      async with stdio_client(params,errlog=errors) as next_streams:
       async with ClientSession(*next_streams) as new:
        await new.initialize();new_info=await read(new,'server_info')
        self.assertEqual(old_info['server'],new_info['server']);self.assertNotEqual(old_info['digest'],new_info['digest'])
        self.assertEqual((await read(old,'server_info'))['digest'],old_info['digest'])
        self.assertTrue(set(connection.required('detail'))<=set(new_info['tools']))
        challenge=connection.begin(new_info,'detail')
        self.assertEqual(connection.check(challenge)['state'],'not_verified')
        result=await read(old,'confirm_connection',{'challenge':challenge})
        self.assertEqual(result['state'],'running_old_server')
        raw={'command':sys.executable,'args':['-I','-B',str(backend/'mcp_server.py')],'env':{'TOKEN':'SECRET'}}
        result=await read(new,'confirm_connection',{'challenge':challenge,'registration_json':json.dumps(raw)})
        self.assertEqual(result['state'],'verified');self.assertEqual(result['registration']['state'],'matches_app')
        self.assertNotIn('SECRET',json.dumps(connection.load(challenge)))
        self.assertEqual(connection.check(challenge)['state'],'verified')
  asyncio.run(exercise())
 def test_browser_guided_repair_keeps_changes_and_requires_live_confirmation(self):
  import re,subprocess
  chrome=Path('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome')
  if not chrome.exists():self.skipTest('Chrome is required')
  folder=Path(__file__).resolve().parents[1];source=(folder/'ui/index.html').read_text()
  script=source.split('<script>',1)[1].split('</script>',1)[0].split("$('q').oninput",1)[0]
  script+=source[source.index('function renderAgentPrompt() {'):source.index("$('agent').onclick")]
  script+=(folder/'ui/connection.js').read_text()
  bootstrap=r'''
const calls=[];let live={state:'not_verified'},waitNext=false,finishNext;
const report=()=>({challenge:'abc',handoff:'Synthetic repair request',app:{python:'/Example.app/python3',server:'/Example.app/mcp_server.py',app_version:'test'},fresh_server:{state:'ready'},registration:{state:'not_inspected'},connection:{state:'not_verified'}});
window.__TAURI__={core:{invoke:async(command,args)=>{calls.push({command,args});
 if(command==='connection_diagnose')return waitNext?await new Promise(resolve=>{finishNext=()=>resolve(JSON.stringify(report()));}):JSON.stringify(report());
 if(command==='connection_status')return JSON.stringify(live);
 throw Error('Unexpected native call '+command);
}}};
Object.defineProperty(navigator,'clipboard',{value:{writeText:async text=>{window.copied=text;}}});
'''
  checks=r'''
(async()=>{
 const assert=(v,m)=>{if(!v)throw Error(m);};
 S.lang='ko';S.changes={entries:[{name:'Keep this'}]};S.chi=3;const changes=S.changes,settings=JSON.stringify(S.settings);
 S.agentPurpose='setup';S.agentPrompt='Synthetic setup';renderAgentPrompt();assert($('openConnectionDiagnostic'),'Setup offers diagnostics');
 await startConnectionDiagnostic();assert($('liveConnectionState').textContent.includes('아직'),'Fresh server is not the current connection');
 await $('copyConnectionRequest').onclick();assert(window.copied==='Synthetic repair request','Repair request copied');
 assert($('liveConnectionState').textContent.includes('아직'),'Copying is not verification');
 live={state:'running_old_server',registration:{state:'different_path',command:'/old/python3',server:'/old/mcp_server.py'}};
 await checkCurrentConnection();assert($('liveConnectionState').textContent.includes('이전 연결'),'Old live server is distinct');
 assert($('registeredConnectionState').textContent.includes('다른 경로'),'Actual registration is separate');
 live={state:'verified',registration:{state:'matches_app'}};await checkCurrentConnection();assert($('liveConnectionState').textContent.includes('확인했습니다'),'Live MCP confirmation becomes verified');
 live={state:'app_changed'};await checkCurrentConnection();assert($('copyConnectionRequest').disabled,'An app update invalidates the request');
 for(const state of ['expired','app_changed']){live={state};await checkCurrentConnection();assert($('copyConnectionRequest').disabled,'Invalidated requests cannot be reused');}
 S.lang='en';await startConnectionDiagnostic('app');assert($('insp').textContent.includes('Connection diagnostics'),'English heading');
 assert(!/[가-힣]/.test($('insp').textContent),'English pane has no untranslated Korean');
 for(const state of Object.keys(connectionMessages))assert(!/[가-힣]/.test(connectionMessage(state)),'Translated status '+state);
 assert(tr('업데이트 뒤 AI 연결을 다시 확인하세요.').startsWith('Check'),'Translated update guidance');
 // Two feature requests resolve in reverse order; stale responses cannot replace the newer one.
 waitNext=true;const first=startConnectionDiagnostic('detail');const oldFinish=finishNext;
 waitNext=false;await startConnectionDiagnostic('maps');oldFinish();await first;
 assert(S.connectionDiagnostic.feature==='maps','Latest feature wins');
 waitNext=true;const closing=startConnectionDiagnostic('detail');S.agentPurpose='setup';S.agentPrompt='Other pane';$('insp').innerHTML='Other pane';finishNext();await closing;
 assert($('insp').textContent==='Other pane','Late diagnostics do not reopen a closed pane');
 S.agentPurpose='connection';S.agentPrompt='connection';S.connectionDiagnostic={feature:'detail',fresh_server:{state:'missing_runtime'},connection:{state:'not_verified'}};renderConnectionDiagnostic();
 assert($('copyConnectionRequest').disabled,'Broken runtime is not offered as a repair target');
 assert(S.changes===changes&&S.chi===3&&JSON.stringify(S.settings)===settings,'Diagnostics preserve changes, selection and comparison settings');
 assert(calls.every(c=>['connection_diagnose','connection_status'].includes(c.command)),'No refresh, install or config write');
 document.body.dataset.connectionTest='passed';
})().catch(error=>{document.body.dataset.connectionTest='failed';const p=document.createElement('pre');p.textContent=error.stack;document.body.append(p);});
'''
  page=re.sub(r'<script>.*?</script>',lambda m:'<script>'+bootstrap+script+checks+'</script>',source,count=1,flags=re.S)
  page=re.sub(r'<script src="[^\"]+"></script>','',page)
  target=self.root/'connection-check.html';target.write_text(page)
  syntax=subprocess.run(['/opt/homebrew/bin/node','--check'],input=bootstrap+script+checks,capture_output=True,text=True)
  self.assertEqual(syntax.returncode,0,syntax.stderr)
  result=subprocess.run([str(chrome),'--headless','--disable-gpu','--no-first-run','--disable-background-networking','--disable-component-update','--no-default-browser-check','--user-data-dir='+str(self.root/'chrome'),'--virtual-time-budget=5000','--dump-dom',target.as_uri()],capture_output=True,text=True,timeout=30)
  self.assertIn('data-connection-test="passed"',result.stdout,str(re.findall(r'<pre>(.*?)</pre>',result.stdout,re.S))[-2000:])
