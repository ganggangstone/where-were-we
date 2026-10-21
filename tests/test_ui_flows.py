"""User flows in the real UI with fictional bundles in headless Chrome. Native calls are faked; no AI or backend runs."""
import json,re,subprocess,tempfile,unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
CHROME=Path('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome')
# Two fictional projects. First has web+api code with an arbitrary compared ref; Second has one code and no compared version.
BOOTSTRAP=r'''
window.calls=[];window.errors=[];
try{Object.defineProperty(navigator,'clipboard',{value:{writeText:async t=>{window.copied=t;}}});}catch{}
window.addEventListener('error',e=>window.errors.push(String(e.message)));
window.requestAnimationFrame=()=>0;
try{localStorage.setItem('where-were-we.release-auto','false');localStorage.setItem('where-were-we.language',new URLSearchParams(location.search).get('lang')||'ko');}catch{}
function fakeMap(prefix,commit,withNew){
 const route={file:'api/app/items.py',function:'save_item',method:'POST',path:'/items',line:3,tables:['api::items'],externals:[],mounted:true,inputs:[],services:[],tests:['api/tests/test_items.py'],repository:'api',source_file:'app/items.py'};
 const screen=(path,heading)=>({path,heading,file:'web/src/'+heading+'.tsx',line:1,redirect:false,repository:'web',source_path:path.split('::')[1],
  actions:[{kind:'api',label:'Save',api_functions:['saveItem'],file:'web/src/'+heading+'.tsx',line:4,calls:[]}],api_functions:[{name:'saveItem',file:'web/src/api.ts'}]});
 const screens=[screen('web::/items',prefix+' list'),...(withNew?[screen('web::/items/new',prefix+' new')]:[])];
 return {repo:'/fictional',ref:'HEAD',commit,multi_repo:true,repositories:[{id:'web',path:'/fictional/web'},{id:'api',path:'/fictional/api'}],screens,
  api_functions:[{name:'saveItem',file:'web/src/api.ts',calls:[{method:'POST',path:'/items',line:2,backend:[{file:route.file,line:route.line}]}]}],
  backend_routes:[route],backend_routes_without_screen:[],unresolved_calls:[],models:{'api/app/models.py':'api::items'},file_screens:{},
  connection_candidates:[{repository:'web',method:'GET',path:'/health',targets:[{repository:'api'}]}]};
}
function fakeBundle(name){
 const two=name==='First';
 const repos=two?[{id:'web',name:'Web screens',refs:{dev:'HEAD',main:'v1.0'},collected:true,commits:{dev:'aaaaaaaa1111',main:'bbbbbbbb2222'},last_success:'2026-10-01T00:00:00Z',api_targets:[],layout:{}},
   {id:'api',name:'API server',refs:{dev:'HEAD',main:'v1.0'},collected:true,commits:{dev:'cccccccc3333',main:'dddddddd4444'},last_success:'2026-10-01T00:00:00Z',api_targets:[],layout:{}}]
  :[{id:'web',name:'Second web',refs:{dev:'origin/release',main:null},collected:true,commits:{dev:'eeeeeeee5555'},api_targets:[],layout:{}}];
 const system={written:'fictional',checked:'aaaaaaaa',nodes:[{id:'api::worker',name:name+' Worker',what:'Processes items',kind:'program',uses:[],ev:[],unknown:[],code:['api']}],externals:[],links:[],others:[],unknown:[]};
 const details={groups:null,flows:{routes:{}},system,'system.ai':null,jobs:{nodes:{}}};
 return {project:{name,repositories:repos,shared_data:[],selected:''},dev:fakeMap(name,'aaaaaaaa1111',true),main:two?fakeMap(name,'bbbbbbbb2222',false):null,
  status:{open_prs:[{number:42,title:'Item form',url:'https://example.invalid/pull/42',screens:['web::/items'],files:['web/src/x.tsx'],repository:'web',updated_at:'2026-10-01T00:00:00Z'}],merged_prs:[],branches:[],worktrees:[],issues:[]},
  groups:null,flows:{routes:{}},system,jobs:{nodes:{}},changes:{last_refresh:'2026-10-01T00:00:00Z',entries:[]},briefings:{},branch_details:{dev:details,main:details}};
}
window.__TAURI__={core:{invoke:async(command,args)=>{
 window.calls.push({command,args});
 if(command==='analysis_request' && window.holdAnalysis)await window.holdAnalysis;
 if(command==='refresh' && window.holdRefresh)await window.holdRefresh;
 if(command==='read_project' && window.holdRead && args.repository===window.holdRead.repository)await window.holdRead.promise;
 if(command==='refresh' && window.failRefresh)throw Error('web: FAILED: fictional collection error');
 if(command==='refresh')return 'Fictional refresh';
 if(command==='setup_prompt' && window.holdSetup)await window.holdSetup;
 if(command==='setup_prompt')return 'Fictional setup '+args.lang;
 if(command==='connection_diagnose'){if(window.holdDiagnose)await window.holdDiagnose;return JSON.stringify({challenge:'challenge-'+(window.calls.filter(c=>c.command==='connection_diagnose').length),feature:args.feature,handoff:'Fictional repair '+args.lang,fresh_server:{state:'ready'},registration:{state:'not_inspected'},connection:{state:'not_verified'}});}
 if(command==='connection_status' && window.holdStatus)await window.holdStatus;
 if(command==='connection_status')return JSON.stringify(window.liveConnection||{state:'not_verified'});
 if(command==='save_project' && window.githubFail)throw Error(window.githubFail);
 if(command==='github_logins' && window.loginsFail)throw Error(window.loginsFail);
 if(command==='read_settings' && new URLSearchParams(location.search).get('settingsFail'))throw Error('fictional settings read failure');
 if(command==='save_project'){if(window.failSave)throw Error('fictional save failure');(window.savedProjects??=[]).push(args.project);return args.configuration;}
 if(command==='list_projects')return new URLSearchParams(location.search).get('empty')?(window.savedProjects||[]):['First','Second'];
 if(command==='read_project'){const b=window.configuredBundle?.project.name===args.project?structuredClone(window.configuredBundle):fakeBundle(args.project);if(window.noMap){b.dev=null;b.main=null;}return JSON.stringify(b);}
 if(command==='read_settings')return JSON.stringify({open_refresh:false,since:'last_refresh',since_time:''});
 if(command==='app_version')return '0.0.0';
 if(command==='save_settings')return args.json;
 if(command==='app_update_status')return null;
 if(command==='control_poll')return null;
 if(command==='control_focus')return null;
 if(['analysis_request','make_system','suggest_groups'].includes(command))return JSON.stringify({handoff:'Analyze '+args.repository,commit:'aaaaaaaa1111',record_arguments:{repository:args.repository},result_before:command==='analysis_request'?[{task:'analysis',before:null},{task:'system',before:null}]:[{task:'analysis',before:null}]});
 throw Error('Unexpected native action '+command);
}}};
'''
PRELUDE=r'''
window.flowCheck=(async()=>{
 const assert=(v,m)=>{if(!v)throw Error(m);};
 for(let i=0;i<100 && !window.appControlReady;i++)await new Promise(r=>setTimeout(r,20));
 const empty=new URLSearchParams(location.search).get('empty');
 assert(empty || S.project==='First','Fixture project loaded');
 const pane=()=>$('insp').innerText,main=()=>$('map').innerText;
 const wait=(ms=20)=>new Promise(r=>setTimeout(r,ms));
 const outside=el=>{const c=el.cloneNode(true);c.querySelectorAll('details').forEach(d=>d.remove());document.body.append(c);const t=c.innerText;c.remove();return t;};
'''
POSTLUDE=r'''
 assert(!window.errors.length,'Uncaught errors: '+window.errors.join(' | '));
 document.body.dataset.flow='passed';
})().catch(error=>{document.body.dataset.flow='failed';const pre=document.createElement('pre');pre.id='flow-error';pre.textContent=error.stack+' errors:'+window.errors.join(' | ');document.body.append(pre);});
'''

def page(checks,lang='ko',query=''):
    """Return the passed/failed marker and error text after the real index.html, connection.js and control.js run."""
    source=(ROOT/'ui/index.html').read_text()
    html=source.replace('<script>','<script>'+BOOTSTRAP,1)
    for name in ('tokens.css','app.css','vendor/dagre.min.js','connection.js','onboarding.js','control.js'):
        html=html.replace(f'"{name}"','"'+(ROOT/'ui'/name).as_uri()+'"')
    html=html.replace('</body>','<script>'+PRELUDE+checks+POSTLUDE+'</script></body>')
    with tempfile.TemporaryDirectory() as tmp:
        target=Path(tmp)/'flow.html';target.write_text(html)
        result=subprocess.run([str(CHROME),'--headless','--disable-gpu','--no-first-run','--disable-background-networking','--disable-component-update',
            '--no-default-browser-check','--window-size=1280,900','--user-data-dir='+tmp+'/chrome','--virtual-time-budget=6000','--dump-dom',target.as_uri()+'?lang='+lang+query],
            capture_output=True,text=True,timeout=40)
    error=re.findall(r'<pre id="flow-error">(.*?)</pre>',result.stdout,re.S)
    return 'data-flow="passed"' in result.stdout,(error or [result.stdout[-1500:]])[-1][-2000:]

ESCAPE_DRIVER=r'''
import {spawn} from 'node:child_process';import fs from 'node:fs';import os from 'node:os';import path from 'node:path';
const dir=fs.mkdtempSync(path.join(os.tmpdir(),'ww-escape-'));
const chrome=spawn('CHROME',['--headless','--disable-gpu','--no-first-run','--disable-background-networking','--remote-debugging-port=0','--user-data-dir='+dir,'PAGE?empty=1']);
const delay=ms=>new Promise(r=>setTimeout(r,ms));let ws;
try{
 for(let i=0;i<200&&!fs.existsSync(dir+'/DevToolsActivePort');i++)await delay(50);
 const port=fs.readFileSync(dir+'/DevToolsActivePort','utf8').split('\n')[0];
 const tabs=await(await fetch('http://localhost:'+port+'/json')).json();
 ws=new WebSocket(tabs.find(t=>t.type==='page').webSocketDebuggerUrl);await new Promise(r=>ws.onopen=r);
 let seq=0;const jobs=new Map();ws.onmessage=e=>{const m=JSON.parse(e.data);if(m.id){jobs.get(m.id)?.(m);jobs.delete(m.id);}};
 const call=(method,params={})=>new Promise(r=>{const id=++seq;jobs.set(id,r);ws.send(JSON.stringify({id,method,params}));});
 const run=async expression=>{const r=await call('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.result.exceptionDetails)throw Error(JSON.stringify(r.result.exceptionDetails));return r.result.result.value;};
 const escape=async()=>{await call('Input.dispatchKeyEvent',{type:'keyDown',key:'Escape',code:'Escape',windowsVirtualKeyCode:27});await call('Input.dispatchKeyEvent',{type:'keyUp',key:'Escape',code:'Escape',windowsVirtualKeyCode:27});await delay(100);};
 const state=()=>run('({guide:$("guide").open,project:$("project-dialog").open,marker:guideMarker(),step:G.step})');
 await run('(async()=>{while(!window.appControlReady)await new Promise(r=>setTimeout(r,20));guideStep(2);$("guideCreate").click();$("projectName").focus();})()');
 await escape();const editor=await state();
 await run('(()=>{const s=document.createElement("input");s.id="probeInput";$("guide").querySelector(".guide-step").append(s);s.focus();})()');
 await escape();const input=await state();
 await run('$("guideTitle").focus()');await escape();const guide=await state();
 console.log(JSON.stringify({editor,input,guide}));
}finally{ws?.close();chrome.kill();}
'''

class Guide(unittest.TestCase):
    """The full-window first-run guide driven through its real buttons."""
    def setUp(self):
        if not CHROME.exists():self.skipTest('Chrome is required')
    def check(self,checks,query=''):
        for lang in ('ko','en'):
            with self.subTest(lang=lang):
                ok,error=page(checks,lang,query);self.assertTrue(ok,error)

    def test_agent_registration_keeps_guide_and_shows_each_code_without_claiming_empty_map_ready(self):
        self.check(r"""
 $('guideNext').click();
 const configuration={repositories:[{id:'web',name:'Lumen Web',path:'/fictional/web',refs:{dev:'HEAD',main:null},layout:{},api_targets:[]},{id:'api',name:'Lumen API',path:'/fictional/api',refs:{dev:'HEAD',main:null},layout:{},api_targets:[]}],shared_data:[]};
 window.configuredBundle=fakeBundle('Lumen');window.configuredBundle.project.repositories=configuration.repositories.map(r=>({...r,collected:false,commits:{}}));
 window.configuredBundle.dev={...fakeMap('Lumen','',false),screens:[],backend_routes:[]};window.configuredBundle.main=null;
 const result=await applyAppCommand({action:'configure',arguments:{project:'Lumen',configuration}});await wait();
 assert(result.ok && $('guide').open && G.step===1,'Confirmed agent registration leaves guide available');
 assert(!window.calls.some(c=>c.command==='refresh'),'Existing local configure does not implicitly move the baseline');
 $('guideLater').click();
 assert($('guideProjectState').textContent.includes('Lumen') && $('guide').textContent.includes('Lumen Web') && $('guide').textContent.includes('Lumen API'),'Shows the service and both saved code connections');
 $('guideNext').click();assert(!$('guideFinish') && $('guideRefresh'),'An empty composed map is not reported ready');
""",query='&empty=1')

    def test_empty_workspace_offers_agent_handoff_after_guide_is_closed(self):
        self.check(r"""
 $('guideSkip').click();assert($('startWithAI') && $('startProject'),'Both methods remain reachable');
 $('startWithAI').click();assert($('guide').open && $('guideCopySetup') && !$('project-dialog').open,'Default path goes straight to the AI request');
""",query='&empty=1')

    def test_agent_reconfiguring_another_saved_service_does_not_refresh_its_existing_code(self):
        self.check(r"""
 const bundle=fakeBundle('Second');bundle.project.repositories[0].url='https://github.com/example/lumen-web.git';
 bundle.project.repositories[0].collected=true;window.configuredBundle=bundle;
 const configuration={repositories:structuredClone(bundle.project.repositories),shared_data:[]};
 assert(S.project==='First','A different service is selected');
 const result=await applyAppCommand({action:'configure',arguments:{project:'Second',configuration}});await wait();
 assert(result.ok && S.project==='Second','Existing target service was configured');
 assert(!window.calls.some(c=>c.command==='refresh'),'Saving existing code must not move its comparison baseline');
""")

    def test_first_action_hands_service_connection_to_agent_before_manual_project_setup(self):
        self.check(r"""
 $('guideNext').click();
 assert($('guideCopySetup'),'First action copies the service connection request');
 assert(!$('projectName') && !$('guideProjectState'),'No project form or project checkpoint before agent handoff');
 assert($('guideCreate') && !$('guideCreate').classList.contains('primary'),'Manual setup is secondary');
 $('guideCopySetup').click();await wait();
 assert(window.calls.some(c=>c.command==='setup_prompt' && c.args.onboarding===true),'Use the onboarding-specific request');
 assert(!window.calls.some(c=>['save_project','refresh'].includes(c.command)),'Copy does not register or collect code');
 $('guideLater').click();
 assert($('guideProjectState') && !$('guideCopySetup'),'Check connected service after handoff');
""",query='&empty=1')

    def test_new_install_opens_the_guide_and_skip_is_remembered_and_reopenable(self):
        self.check(r"""
 const g=$('guide');assert(g.open,'A new install with no projects opens the guide');
 assert(g.querySelector('[aria-current="step"]').textContent.includes(tr('시작')),'Current step is announced');
 assert(document.activeElement===$('guideTitle'),'Focus moves into the guide');
 $('q').focus();assert(document.activeElement!==$('q'),'Workspace behind the guide is not reachable');
 $('guideNext').click();assert($('guideProgress').textContent.includes('2 / 4'),'Visible progress');
 $('guideBack').click();assert(document.activeElement===$('guideTitle') && $('guideProgress').textContent.includes('1 / 4'),'Back returns and keeps focus');
 $('guideSkip').click();assert(!g.open && guideMarker()==='skipped','Skip closes and is remembered');
 assert(localStorage.getItem('where-were-we.onboarding')==='skipped','Marker is stored per install');
 $('guideOpen').click();assert(g.open && G.step===0,'Menu reopens the guide');
 closeGuide('done');assert(guideMarker()==='done','Completion is recorded');
 assert(!window.calls.some(c=>['refresh','save_project'].includes(c.command)),'Opening and closing changes nothing');
""",query='&empty=1')

    def test_existing_users_keep_their_workspace_and_reopening_changes_nothing(self):
        self.check(r"""
 assert(!$('guide').open,'Existing projects do not open the guide');
 $('view').querySelector('[data-v=sys]').click();const before=JSON.stringify([S.project,S.repository,S.view,S.branch,S.chi,S.settings]),calls=window.calls.length;
 $('guideOpen').click();assert($('guide').open,'Menu opens the guide');
 assert($('guideProjectState')===null && G.step===0,'Starts at the first step');
 $('guideNext').click();$('guideLater').click();assert($('guideProjectState').textContent.includes('First'),'Shows the current project as saved');
 $('guideNext').click();
 assert($('guideMapState').textContent.includes(tr('지도가 준비됐습니다.')),'Existing map is ready');
 $('guideSkip').click();await wait();
 assert(JSON.stringify([S.project,S.repository,S.view,S.branch,S.chi,S.settings])===before,'Project, code, view, history and settings are preserved');
 assert(!window.calls.slice(calls).some(c=>['refresh','read_project','save_project','analysis_request'].includes(c.command)),'No implicit refresh or reload');
 assert(document.activeElement===$('menuButton'),'Focus returns to the menu');
""")

    def test_project_step_reports_cancel_failure_and_multi_code_success_honestly(self):
        self.check(r"""
 $('guideNext').click();$('guideLater').click();$('guideCreate').click();const d=$('project-dialog');assert(d.open && $('guide').open,'Existing editor opens above the guide');
 d.close();await wait();assert($('guide').open && $('guideProjectState').textContent.includes(tr('아직 연결된 서비스가 없습니다. AI 채팅에서 연결을 마친 뒤 돌아오세요.')),'Cancel leaves no saved project and keeps the guide');
 $('guideCreate').click();$('projectName').value='Lumen';$('addRepository').click();
 const paths=[...d.querySelectorAll('[data-field="path"]')];assert(paths.length===2,'Two code rows');paths[0].value='/fictional/web';paths[1].value='/fictional/api';
 window.failSave=true;$('saveProject').click();await wait(60);
 assert(d.open && $('projectError').textContent && !S.project,'A failed save stays open with its error');
 d.close();await wait();assert(!$('guide').querySelector('.guide-rail li:nth-child(3) .dot'),'Failed save is not marked done');
 window.failSave=false;$('guideCreate').click();$('projectName').value='Lumen';$('addRepository').click();
 [...d.querySelectorAll('[data-field="path"]')].forEach((input,i)=>input.value=['/fictional/web','/fictional/api'][i]);
 $('saveProject').click();for(let i=0;i<50 && S.project!=='Lumen';i++)await wait();await wait();
 const saved=window.calls.filter(c=>c.command==='save_project');assert(JSON.parse(saved.at(-1).args.configuration).repositories.length===2,'One project holds both code folders');
 assert(!d.open && $('guideProjectState').textContent.includes('Lumen'),'Saved project is reported');
 assert($('guide').querySelector('.guide-rail li:nth-child(3) .dot.ok'),'Rail marks the saved project');
 assert(!window.calls.some(c=>c.command==='refresh'),'Local folders are not collected without an explicit refresh');
""",query='&empty=1')

    def test_agent_step_is_verified_only_by_the_live_connection_and_keeps_its_challenge_across_languages(self):
        self.check(r"""
 $('guideNext').click();
 $('guideCopySetup').click();await wait();assert(window.copied==='Fictional setup '+S.lang,'Setup instructions follow the app language');
 assert($('guideCopyState').textContent,'Copy is acknowledged');
 assert(!$('guide').querySelector('.guide-rail li:nth-child(2) .dot'),'Copying does not verify the agent');
 $('guideDiagnose').click();await wait(60);
 assert($('guideConnection').textContent.includes(connectionMessage('not_verified')),'A fresh diagnostic is not verified');
 assert($('guideLater').className.includes('plain'),'Next is not highlighted before verification');
 assert($('guide').querySelectorAll('.guide-step .btn.primary').length===1 && $('guide-copyConnectionRequest').classList.contains('primary'),'One main action: copy the repair request first');
 assert(!$('guideConnection').querySelector('h2') && $('guide-copyConnectionRequest') && $('guide-runConnectionDiagnostic'),'No nested title; repair and rerun stay available');
 const challenge=G.connection.challenge;assert(challenge,'Diagnostic prepared a challenge');
 assert(!S.agentPrompt && $('insp').textContent.indexOf(tr('연결 진단'))<0,'The inspector is not taken over');
 const other=S.lang==='ko'?'en':'ko';$('guide').querySelector(`[data-guide-lang="${other}"]`).click();await wait();
 assert(S.lang===other && G.connection.challenge===challenge && $('guideCopyState').textContent,'Language change keeps the prepared challenge and copy state');
 $('guideCopySetup').click();await wait();assert(window.copied==='Fictional setup '+other,'Copy again uses the new language');
 window.liveConnection={state:'verified'};$('guide-checkCurrentConnection').click();await wait(60);
 assert($('guideConnection').textContent.includes(connectionMessage('verified')),'Live confirmation is shown');
 assert($('guide').querySelector('.guide-rail li:nth-child(2) .dot.ok') && $('guideLater').className.includes('primary'),'Only the live state marks the agent');
 assert(!$('guideConnection').querySelector('[id$="backToMap"]'),'Inspector-only controls stay out of the guide');
""",query='&empty=1')

    def test_late_diagnostic_after_skip_does_not_reopen_or_overwrite(self):
        self.check(r"""
 let release;window.holdDiagnose=new Promise(r=>release=r);
 $('guideNext').click();$('guideDiagnose').click();await wait();
 const inspector=$('insp').innerHTML;$('guideSkip').click();release();await wait(60);
 assert(!$('guide').open && $('insp').innerHTML===inspector && !S.agentPrompt,'A late result is dropped');
""",query='&empty=1')

    def test_first_map_needs_an_explicit_refresh_and_analysis_only_prepares(self):
        self.check(r"""
 window.noMap=true;await loadProject('First');$('guideOpen').click();G.step=3;renderGuide();
 assert($('guideMapState').textContent.includes(tr('아직 지도를 가져오지 않았습니다.')),'Missing map is reported');
 assert(!window.calls.some(c=>c.command==='refresh'),'No refresh before the user asks');
 window.noMap=false;$('guideRefresh').click();for(let i=0;i<50 && !$('guideFinish');i++)await wait();
 assert(window.calls.filter(c=>c.command==='refresh').length===1 && $('guideFinish'),'One explicit refresh makes the map ready');
 $('guideAnalysis').click();await wait();
 assert(!$('guide').open && !window.calls.some(c=>c.command==='analysis_request'),'Analysis opens the request panel without running');
 assert($('insp').textContent.includes(tr('AI에게 알아보기')),'The existing analysis panel is shown');
""")

    def test_blocked_storage_keeps_the_skip_for_the_session(self):
        self.check(r"""
 for(const store of ['localStorage','sessionStorage'])Object.defineProperty(window,store,{get(){throw Error('blocked');}});
 guideMemory=null;assert(guideMarker()===null,'Nothing stored yet');
 $('guideSkip').click();assert(!$('guide').open && guideMarker()==='skipped','Skip still holds without storage');
""",query='&empty=1')

    def test_finishing_reveals_the_map_and_agent_navigation_is_not_hidden_by_the_guide(self):
        self.check(r"""
 $('guideOpen').click();G.step=3;renderGuide();$('guideFinish').click();await wait();
 assert(!$('guide').open && S.view==='map' && $('map').querySelector('[data-scr]'),'Open the map shows an actual screen map');
 $('guideOpen').click();const r=await applyAppCommand({action:'navigate',arguments:{project:'First',repository:'',branch:'dev',view:'sys'}});
 assert(!$('guide').open && S.view==='sys','Agent navigation closes the covering guide');
 assert(guideMarker()==='done','Agent navigation does not overwrite the recorded choice');
 $('guideOpen').click();localStorage.removeItem('where-were-we.onboarding');guideMemory=null;
 const target=controlTargets().find(t=>t.kind==='screen');
 await applyAppCommand({action:'select',arguments:{project:'First',repository:'',branch:'dev',revision:await controlRevision(),target:target.id}});
 assert(!$('guide').open && S.sel && guideMarker()===null,'Select closes the guide without marking it skipped or done');
 $('guideOpen').click();await applyAppCommand({action:'select',arguments:{project:'First',repository:'',branch:'dev',revision:'stale',target:target.id}}).catch(()=>{});
 assert($('guide').open,'A rejected select leaves the guide open');closeGuide();
""")

    def test_late_setup_prompt_and_duplicate_ids_do_not_leak_between_places(self):
        self.check(r"""
 await startConnectionDiagnostic('detail');assert($('liveConnectionState'),'Inspector diagnostic shown');
 $('guideOpen').click();$('guideNext').click();$('guideDiagnose').click();await wait(60);
 const ids=[...document.querySelectorAll('[id]')].map(e=>e.id);assert(new Set(ids).size===ids.length,'No duplicate IDs: '+ids.filter((x,i)=>ids.indexOf(x)!==i));
 assert(S.connectionDiagnostic!==G.connection && $('liveConnectionState').closest('#insp'),'Each place keeps its own report');
 let release;window.holdSetup=new Promise(r=>release=r);$('guideCopySetup').click();await wait();
 $('guideBack').click();release();await wait(60);
 assert(!G.copied && !G.setup && !window.copied && G.step===0,'A late setup prompt after leaving the step is dropped');
 window.holdSetup=new Promise(r=>release=r);$('guideNext').click();$('guideCopySetup').click();await wait();
 const other=S.lang==='ko'?'en':'ko';setLanguage(other);release();await wait(60);
 assert(!G.copied && !window.copied,'A late setup prompt from the previous language is not copied');
 window.holdSetup=null;$('guideCopySetup').click();await wait();assert(window.copied==='Fictional setup '+other,'Copy works after the switch');
 closeGuide();
""")

    def test_escape_on_the_project_editor_closes_only_the_editor(self):
        self.check(r"""
 $('guideNext').click();$('guideLater').click();$('guideCreate').click();const d=$('project-dialog');
 if(d.requestClose)d.requestClose();else d.close();await wait();
 assert(!d.open && $('guide').open && guideMarker()===null,'Closing the editor keeps the guide');
 if($('guide').requestClose){$('guide').requestClose();await wait();assert(!$('guide').open && guideMarker()==='skipped','Escape on the guide skips it');}
""",query='&empty=1')

    def test_late_copy_and_diagnostic_results_only_land_in_the_run_that_started_them(self):
        self.check(r"""
 const reset=()=>{closeGuide();window.holdSetup=null;window.holdDiagnose=null;G.setup=null;G.copied=false;G.connection=null;window.copied=null;};
 const clip=navigator.clipboard.writeText;
 // setup_prompt failure after close and reopen
 $('guideOpen').click();guideStep(1);let reject;window.holdSetup=new Promise((r,j)=>reject=j);$('guideCopySetup').click();await wait();
 closeGuide();openGuide();guideStep(1);reject(Error('old'));await wait(60);assert(!$('guideCopyState').textContent,'Old setup failure painted a new run');reset();
 // setup_prompt failure after a language switch
 $('guideOpen').click();guideStep(1);window.holdSetup=new Promise((r,j)=>reject=j);$('guideCopySetup').click();await wait();
 setLanguage(S.lang==='ko'?'en':'ko');await wait();reject(Error('old'));await wait(60);assert(!$('guideCopyState').textContent,'Old-language failure painted');setLanguage(S.lang==='ko'?'en':'ko');reset();
 // clipboard failure after leaving and returning to the step
 $('guideOpen').click();guideStep(1);navigator.clipboard.writeText=()=>new Promise((r,j)=>reject=j);$('guideCopySetup').click();await wait();
 guideStep(2);guideStep(1);reject(Error('old'));await wait(60);assert(!$('guideCopyState').textContent,'Old clipboard failure painted a new step');navigator.clipboard.writeText=clip;reset();
 // shared repair-request clipboard success after close and reopen
 $('guideOpen').click();guideStep(1);$('guideDiagnose').click();await wait(60);let release;navigator.clipboard.writeText=()=>new Promise(r=>release=r);
 $('guide-copyConnectionRequest').click();await wait();closeGuide();openGuide();guideStep(1);release();await wait(60);
 assert(!G.connection?.copied,'Old repair copy marked a new run');navigator.clipboard.writeText=clip;reset();
 // shared clipboard failure after a language switch keeps the challenge but paints nothing old
 $('guideOpen').click();guideStep(1);$('guideDiagnose').click();await wait(60);const challenge=G.connection.challenge;navigator.clipboard.writeText=()=>new Promise((r,j)=>reject=j);
 $('guide-copyConnectionRequest').click();await wait();setLanguage(S.lang==='ko'?'en':'ko');await wait();reject(Error('old'));await wait(60);
 assert(!$('guide-connectionCopyStatus').textContent && G.connection.challenge===challenge,'Old failure painted, or the challenge was lost');setLanguage(S.lang==='ko'?'en':'ko');navigator.clipboard.writeText=clip;reset();
 // a diagnostic finishing while on another step leaves a usable result
 $('guideOpen').click();guideStep(1);window.holdDiagnose=new Promise(r=>release=r);$('guideDiagnose').click();await wait();guideStep(2);release();await wait(60);guideStep(1);
 assert(G.connection && !G.connection.busy && !$('guide-runConnectionDiagnostic').disabled,'Diagnostic stuck busy after returning');reset();
 // a live check still running at close does not leave Check current connection disabled
 $('guideOpen').click();guideStep(1);$('guideDiagnose').click();await wait(60);window.holdStatus=new Promise(r=>release=r);window.liveConnection={state:'verified'};
 $('guide-checkCurrentConnection').click();await wait();closeGuide();openGuide();guideStep(1);release();await wait(60);
 assert(!G.connection.checking && !$('guide-checkCurrentConnection').disabled && G.connection.connection.state!=='verified','Check stuck, or a result from the closed run landed');window.liveConnection=null;reset();
""",query='&empty=1')

    def test_agent_navigation_is_blocked_while_the_project_editor_is_open_over_the_guide(self):
        self.check(r"""
 openGuide();guideStep(2);editProject(true);$('projectName').value='Draft';
 const before=[S.project,S.view];let code=null;
 try{await applyAppCommand({action:'navigate',arguments:{view:'sys'}});}catch(e){code=e.code;}
 assert(code==='guide_dialog_open' && $('project-dialog').open && $('guide').open && $('projectName').value==='Draft' && S.view===before[1],'Navigate is refused and the draft stays');
 code=null;try{await applyAppCommand({action:'select',arguments:{project:'First',repository:'',branch:'dev',revision:'x',target:'x'}});}catch(e){code=e.code;}
 assert(code==='guide_dialog_open','Select is refused before changing context');
 $('project-dialog').close();await applyAppCommand({action:'navigate',arguments:{project:'First',repository:'',branch:'dev',view:'sys'}});
 assert(!$('guide').open && S.view==='sys' && guideMarker()===null,'Guide alone still closes without a marker');
""")

    def test_one_trusted_escape_closes_only_the_top_editor(self):
        """Real key events through the Chrome DevTools protocol; node is only a driver, no new dependency."""
        import shutil
        node=shutil.which('node')
        if not node:self.skipTest('node is required for the DevTools driver')
        source=(ROOT/'ui/index.html').read_text().replace('<script>','<script>'+BOOTSTRAP,1)
        for name in ('tokens.css','app.css','vendor/dagre.min.js','connection.js','onboarding.js','control.js'):
            source=source.replace(f'"{name}"','"'+(ROOT/'ui'/name).as_uri()+'"')
        with tempfile.TemporaryDirectory() as tmp:
            html=Path(tmp)/'escape.html';html.write_text(source)
            driver=Path(tmp)/'escape.mjs';driver.write_text(ESCAPE_DRIVER.replace('PAGE',html.as_uri()).replace('CHROME',str(CHROME)))
            result=subprocess.run([node,str(driver)],capture_output=True,text=True,timeout=60)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        steps=json.loads(result.stdout.strip().splitlines()[-1])
        self.assertEqual(steps['editor'],{'guide':True,'project':False,'marker':None,'step':2},steps)
        self.assertEqual(steps['input'],{'guide':True,'project':False,'marker':None,'step':2},steps)
        self.assertEqual(steps['guide'],{'guide':False,'project':False,'marker':'skipped','step':2},steps)

class Flows(unittest.TestCase):
    def setUp(self):
        if not CHROME.exists():self.skipTest('Chrome is required')
    def check(self,checks,query=''):
        for lang in ('ko','en'):
            with self.subTest(lang=lang):
                ok,error=page(checks,lang,query);self.assertTrue(ok,error)

    def test_dictionary_has_no_duplicate_interface_keys(self):
        source=(ROOT/'ui/index.html').read_text();table=source[source.index('const UI_EN = {'):source.index('const UI_PATTERN')]
        keys=re.findall(r'''(?:^|[{,\s])(?:'((?:[^'\\]|\\.)*)'|"((?:[^"\\]|\\.)*)")\s*:''',table)
        seen=[a or b for a,b in keys];duplicates=sorted({k for k in seen if seen.count(k)>1})
        self.assertGreater(len(seen),300);self.assertEqual(duplicates,[])

    def test_code_buttons_name_the_code_and_keep_the_existing_selection(self):
        self.check(r'''
 const bar=$('branch');assert(bar.getAttribute('aria-label')===tr('지도에 표시할 버전'),'Code selector has a plain label');
 assert(bar.previousElementSibling.textContent===tr('지도에 표시할 버전'),'Label is visible beside the buttons');
 assert(bar.querySelector('[data-b=dev]').textContent==='HEAD','First button names its actual ref');
 assert(bar.querySelector('[data-b=main]').textContent==='v1.0','Second button names its actual ref');
 S.projectInfo.repositories[1].refs.dev='origin/next';renderRepositories();
 assert($('branch').querySelector('[data-b=dev]').textContent==='HEAD · origin/next','Mixed code refs stay visible');
 assert($('branch').querySelector('[data-b=dev]').title.includes('API server: origin/next'),'Tooltip identifies each code');
 const changes=S.changes,settings=JSON.stringify(S.settings);
 $('branch').querySelector('[data-b=main]').click();
 assert(S.branch==='main'&&$('branch').querySelector('[data-b=main]').getAttribute('aria-pressed')==='true','Second code is selected');
 assert(S.changes===changes&&JSON.stringify(S.settings)===settings,'Viewing another code does not move the comparison start');
 assert(!window.calls.some(c=>c.command==='refresh'),'Selection does not collect again');
''')

    def test_switching_version_keeps_rendering_when_the_selected_screen_is_missing(self):
        self.check(r'''
 setFocus('screen|web::/items/new');assert(S.view==='focus','Connections of an analysis-only screen are open');
 document.querySelector('#branch [data-b=main]').click();
 assert(S.branch==='main','Compared version is selected');
 assert(!window.errors.length,'Switching versions must not throw: '+window.errors.join(' | '));
 assert(main().includes(tr('이 버전에는 선택한 화면이 없습니다.')),'Explain that the selection is absent in this version');
 document.querySelector('#branch [data-b=dev]').click();assert(S.branch==='dev' && !window.errors.length,'Switch back');
''')

    def test_agent_navigation_to_another_project_updates_the_visible_project_name(self):
        self.check(r'''
 const result=await applyAppCommand({action:'navigate',arguments:{project:'Second',repository:'',branch:'dev',view:'sys'}});
 assert(result.state.project==='Second','Agent moved to Second');
 assert($('project').value==='Second','Header shows the project whose data is displayed');
 assert(main().includes('Second Worker'),'Second data is rendered');
''')

    def test_search_finds_items_from_every_view_and_reports_no_results(self):
        self.check(r'''
 for(const view of ['changes','sys','feat','focus']){
  S.view=view;S.focus=null;render();
  $('q').value='First Worker';$('q').dispatchEvent(new Event('input'));
  const hit=document.querySelector('[data-search-result]');
  assert(hit && hit.innerText.includes('First Worker'),'Search shows a result list in '+view);
  $('q').value='zz-no-such-thing';$('q').dispatchEvent(new Event('input'));
  assert(document.body.innerText.includes(tr('찾은 것이 없습니다.')),'Empty search is explicit in '+view);
 }
 $('q').value='First Worker';$('q').dispatchEvent(new Event('input'));
 document.querySelector('[data-search-result]').click();
 assert(S.view==='sys' && S.node==='api::worker','Choosing a result opens it');
 $('q').value='#42';$('q').dispatchEvent(new Event('input'));
 assert([...document.querySelectorAll('[data-search-result]')].some(x=>x.innerText.includes('First list')),'PR numbers find linked screens');
''')

    def test_all_code_analysis_asks_which_code_instead_of_failing(self):
        self.check(r'''
 assert(S.repository==='' && S.projectInfo.repositories.length===2,'All code is selected');
 $('analyzeMap').click();await new Promise(r=>setTimeout(r,0));
 assert(!$('status').textContent,'No selection error: '+$('status').textContent);
 const target=$('analysisTarget');assert(target,'Choose the code to analyze');
 assert(target.textContent.includes('Web screens') && target.textContent.includes('API server'),'Display names are used');
 target.value='web';target.dispatchEvent(new Event('change'));
 document.querySelector('[data-analysis-task="analysis_request"]').click();await new Promise(r=>setTimeout(r,20));
 assert(calls.some(c=>c.command==='analysis_request' && c.args.repository==='web'),'Request goes to the chosen code');
 assert(pane().includes(tr('1. 요청 복사')),'The prepared request is shown');
 S.view='sys';S.system=null;S.branchDetails=null;render();$('remakeSys').click();await new Promise(r=>setTimeout(r,0));
 assert(!$('status').textContent && $('analysisTarget'),'Contextual analysis buttons also offer the code choice');
 $('analysisTarget').value='*';$('analysisTarget').dispatchEvent(new Event('change'));
 document.querySelector('[data-analysis-task="make_system"]').click();await new Promise(r=>setTimeout(r,20));
 assert(['web','api'].every(id=>calls.some(c=>c.command==='make_system' && c.args.repository===id)),'All code prepares one request per code');
''')

    def test_prepared_analysis_can_be_reopened_after_browsing(self):
        self.check(r'''
 S.repository='web';S.projectInfo.repositories=S.projectInfo.repositories.slice(0,1);render();
 $('analyzeMap').click();document.querySelector('[data-analysis-task="analysis_request"]').click();await new Promise(r=>setTimeout(r,20));
 assert($('checkAnalysisResults'),'Result check is offered');
 document.querySelector('#view [data-v="sys"]').click();
 assert(!$('checkAnalysisResults'),'Browsing replaced the panel');
 assert($('analyzeMap').innerText.includes(tr('결과 확인 대기')),'The waiting request stays visible');
 $('analyzeMap').click();
 assert($('checkAnalysisResults') && pane().includes(tr('1. 요청 복사')),'The same request reopens with the result check');
''')

    def test_versions_show_the_configured_refs_instead_of_production_or_development(self):
        self.check(r'''
 const text=$('branch').innerText;
 assert(text.includes('HEAD') && text.includes('v1.0'),'Configured refs are shown: '+text);
 assert(!/운영|개발|Production|Development/.test(text),'No deployment wording: '+text);
 S.view='map';render();
 assert(!/운영|개발|Production|Development/.test(main()),'Map badges use version wording');
 await applyAppCommand({action:'navigate',arguments:{project:'Second',repository:'',branch:'dev',view:'map'}});
 assert($('branch').innerText.includes('origin/release'),'Single compared ref');
 assert(document.querySelector('#branch [data-b=main]').disabled,'A missing compared version cannot be chosen');
''')

    def test_every_screen_and_state_reads_in_one_language_with_consistent_terms(self):
        self.check(r'''
 const hangul=/[가-힣]/,visible=()=>[document.querySelector('header'),$('status'),$('repository-bar'),$('map'),$('insp'),...document.querySelectorAll('dialog[open]')].map(e=>{const c=e.cloneNode(true);c.querySelectorAll('[lang]').forEach(x=>x.remove());document.body.append(c);const t=c.innerText;c.remove();return t;}).join('\n');
 const checkText=(where)=>{const text=visible();
  if(S.lang==='en'){const line=text.split('\n').find(l=>hangul.test(l));assert(!line,'Korean in English UI at '+where+': '+line);}
  else{assert(!/레포|저장소/.test(text),'Use 코드 for repositories and 데이터 for tables at '+where+': '+(text.match(/.{0,30}(레포|저장소).{0,30}/)||[''])[0]);}
 };
 $('menu').open=true;checkText('menu');$('menu').open=false;
 for(const view of ['sys','feat','map','focus','changes']){S.view=view;S.focus=null;S.sel=null;render();checkText(view);}
 S.view='map';render();document.querySelector('[data-scr="web::/items"]').click();checkText('screen inspector');
 document.querySelector('[data-req]').click();checkText('request detail');
 for(const sel of ['!orphans','!unres']){selectScreen(sel);checkText(sel);}
 setFocus('table|api::items');checkText('data focus');setFocus('screen|web::/items');checkText('screen focus');
 S.view='sys';render();document.querySelector('[data-node]').click();checkText('program');
 $('analyzeMap').click();checkText('analysis panel');
 $('q').value='Worker';$('q').dispatchEvent(new Event('input'));checkText('search');$('q').value='zz-none';$('q').dispatchEvent(new Event('input'));checkText('empty search');$('q').value='';$('q').dispatchEvent(new Event('input'));
 renderSettings();$('settings-dialog').showModal();checkText('settings');$('settings-dialog').close();
 editProject(false);checkText('code connections');$('project-dialog').close();
 editProject(true);checkText('new project');$('project-dialog').close();
 renderUpdates();$('release-dialog').showModal();checkText('updates');$('release-dialog').close();
''')

    def test_three_questions_lead_navigation_and_keep_the_five_views(self):
        self.check(r'''
 const top=[...document.querySelectorAll('#view button')].map(b=>b.dataset.v);
 assert(JSON.stringify(top)===JSON.stringify(['sys','work','changes']),'Three top views: '+top);
 document.querySelector('#view [data-v="work"]').click();
 assert(['feat','map','focus'].includes(S.view) && !$('subview').hidden,'What it does opens with its sub views');
 for(const v of ['feat','map','focus']){document.querySelector('#subview [data-v="'+v+'"]').click();assert(S.view===v,'Sub view '+v);}
 document.querySelector('#view [data-v="changes"]').click();assert($('subview').hidden,'Sub views only belong to What it does');
 document.querySelector('#view [data-v="work"]').click();assert(S.view==='focus','Returns to the last used sub view');
 assert(document.querySelector('#view [data-v="work"]').getAttribute('aria-pressed')==='true','Selected view is announced');
 assert($('menu').contains($('settings')) && $('menu').contains($('language')) && $('menu').contains($('updates')) && $('menu').contains($('agent')),'Rare tools live in the menu');
''')

    def test_map_items_work_from_the_keyboard(self):
        self.check(r'''
 S.view='map';render();
 const card=document.querySelector('[data-scr="web::/items"]');
 assert(card.tabIndex===0 && card.getAttribute('role')==='button','Cards are focusable buttons');
 card.focus();card.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true}));
 assert(S.sel==='web::/items','Enter selects a screen');
 const row=document.querySelector('[data-req]');row.focus();row.dispatchEvent(new KeyboardEvent('keydown',{key:' ',bubbles:true}));
 assert(S.open,'Space opens a request');
 $('q').value='Worker';$('q').dispatchEvent(new Event('input'));
 $('q').dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true}));
 assert(S.view==='sys' && S.node==='api::worker','Enter in search opens the first result');
''')

    def test_every_clickable_item_has_press_feedback_and_links_are_tabbable(self):
        # headless cannot hold :active, so check that each rendered clickable item matches a press rule from app.css with :active removed
        css=re.sub(r'/\*.*?\*/','',(ROOT/'ui/app.css').read_text(),flags=re.S)
        pressed=[sel.strip().replace(':active','') for sels,body in re.findall(r'([^{}]+)\{([^}]*)\}',css)
                 if 'transform:var(--press)' in body or 'background:var(--color-bg-control)' in body
                 for sel in re.split(r',(?![^(]*\))',sels) if ':active' in sel]
        self.assertTrue(pressed)
        self.check('const PRESSED='+repr(pressed)+';'+r'''
 const need=(sel,what)=>{const el=document.querySelector(sel);assert(el,what+' is rendered');assert(PRESSED.some(s=>el.matches(s)),what+' has press feedback');return el;};
 S.view='map';render();
 need('.card[data-scr]','Screen card').click();
 need('.row[data-req]','Request row').click();
 const link=document.querySelector('a.lnk[data-url]');assert(link,'Code link is rendered');
 assert(link.tabIndex===0 && link.getAttribute('role')==='link','Code link without href is reachable with Tab');
 const sent=window.calls.length;link.focus();link.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true}));
 assert(window.calls.slice(sent).some(c=>c.command==='open_url' && c.args.url.startsWith('zed://')),'Enter on the code link opens it');
 need('.pill.click[data-f]','Data pill').click();
 need('.card[data-f]','Focus card');
 const a=document.createElement('a');a.href='https://example.invalid';a.dataset.url='x';document.body.append(a);keyboardTargets();
 assert(!a.hasAttribute('role') && a.tabIndex===0,'Links with href keep native semantics');a.remove();
''')

    def test_first_run_offers_the_next_step(self):
        self.check(r'''
 assert(!S.project,'No project exists');
 const start=$('startProject');assert(start && $('startWithAI') && main().includes(tr('직접 연결하기')),'Empty app offers AI handoff and a manual alternative');
 start.click();assert($('project-dialog').open,'Start opens project creation');
''',query='&empty=1')

    def test_unlinked_code_and_candidates_lead_to_the_connection_setting(self):
        self.check(r'''
 assert($('linkCode'),'Two codes without server connections are pointed out');
 $('linkCode').click();assert($('project-dialog').open,'Opens code connections');
 const box=document.querySelector('[data-repository-row="0"] [data-api-target]');
 assert(box && box.offsetParent!==null,'Server choice is visible without opening advanced options');
 $('project-dialog').close();
 $('reviewCandidates').click();
 const confirm=document.querySelector('[data-confirm-link]');assert(confirm,'Candidates can be confirmed');
 const h=[...$('insp').querySelectorAll('h2,h4')];assert(h[0].tagName==='H2','Title comes before sub headings');
 confirm.click();assert($('project-dialog').open && document.querySelector('[data-repository-row="0"] [data-api-target][value="api"]').checked,'Confirming pre-checks the server');
''')

    def test_names_proposals_history_settings_and_recovery_paths(self):
        self.check(r'''
 S.view='map';render();
 assert(!/\[(web|api)\]/.test(main()) && main().includes('First list [Web screens]'),'Screens show the connection display name, not the internal ID');
 document.querySelector('[data-scr="web::/items"]').click();
 assert(!pane().includes('· web') && pane().includes('Web screens'),'Inspector uses the display name');
 const reqRow=document.querySelector('[data-req]');assert(reqRow.innerText.includes(tr('테스트 연결 ')+'1'),'Tests are named, not a colour dot');
 const proposal={...S.system,nodes:[{...S.system.nodes[0],name:'Proposed worker'}]};
 S.branchDetails.dev['system.ai']=proposal;S.view='sys';render();
 assert(main().includes('First Worker') && !main().includes('Proposed worker'),'Written structure stays the default');
 document.querySelector('[data-proposal="1"]').click();
 assert(main().includes('Proposed worker') && main().includes(tr('AI 제안 · 기존 서비스 구성은 바뀌지 않았습니다')),'The AI proposal is viewable and labelled');
 document.querySelector('[data-proposal="0"]').click();assert(main().includes('First Worker'),'Back to the written structure');
 S.changes={last_refresh:'2026-10-01T00:00:00Z',entries:Array.from({length:14},(_,i)=>({at:'2026-09-'+String(10+i).padStart(2,'0')+'T00:00:00Z',since:'2026-09-01T00:00:00Z',repository:'api',branches:{},prs:[]}))};
 S.view='changes';render();
 assert($('olderChanges') && main().includes('API server'),'Older records are reachable and named');
 $('olderChanges').value='13';$('olderChanges').dispatchEvent(new Event('change'));assert(S.chi===13,'Choosing an older record');
 let refreshed=0;const original=doRefresh;doRefresh=async()=>{refreshed++;};
 renderSettings();$('settings-dialog').showModal();await $('saveRefresh').onclick();
 assert(refreshed===1 && !$('settings-dialog').open,'Save and refresh in one step');doRefresh=original;
 U.latest={version:'9.9.9',newer:true,notes:'',url:''};renderUpdates();
 assert(!$('startBannerUpdate'),'The banner never starts an update directly');
 $('viewRelease').click();assert($('release-dialog').open && $('installUpdate'),'The update starts from the dialog that explains the restart');$('release-dialog').close();
 S.agentPurpose='connection';S.agentPrompt='connection';S.connectionDiagnostic={feature:'detail',challenge:'x',fresh_server:{state:'ready'},registration:{state:'matches_app'},connection:{state:'verified'},handoff:'repair'};
 renderConnectionDiagnostic();assert($('backToMap') && $('copyConnectionRequest').className.includes('quiet'),'A verified connection leads back to the map');
 $('backToMap').click();assert(!$('backToMap') && S.agentPrompt===null,'Back to the map');
''')

    def test_analysis_code_choice_follows_the_current_project_and_code_scope(self):
        self.check(r'''
 const fb=fakeBundle;fakeBundle=n=>{const b=fb(n);if(n==='Second')b.project.repositories=[{...b.project.repositories[0],id:'web',name:'Second web'},{id:'pay',name:'Pay API',refs:{dev:'origin/release'},collected:true,commits:{dev:'eeeeeeee5555'},api_targets:[],layout:{}}];return b;};
 const choose=id=>{$('analyzeMap').click();$('analysisTarget').value=id;$('analysisTarget').dispatchEvent(new Event('change'));};
 choose('web');
 await applyAppCommand({action:'navigate',arguments:{project:'Second',repository:'',branch:'dev',view:'sys'}});
 $('analyzeMap').click();
 assert($('analysisTarget').value==='','A code chosen in another project is not carried over');
 assert(document.querySelector('[data-analysis-task="analysis_request"]').disabled,'Nothing can be requested before choosing a code here');
 calls.length=0;
 const prepared=await applyAppCommand({action:'prepare_analysis',arguments:{task:'analysis'}}).catch(e=>e.code);
 assert(prepared==='analysis_request_failed' && !calls.some(c=>c.command==='analysis_request'),'No request is sent with the previous project code');
 await applyAppCommand({action:'navigate',arguments:{project:'First',repository:'',branch:'dev',view:'sys'}});
 choose('web');await loadProject('First',false,'api');await loadProject('First',false,'');$('analyzeMap').click();
 assert($('analysisTarget').value==='','Changing the code scope clears the choice');
 choose('api');S.projectInfo.repositories=S.projectInfo.repositories.filter(r=>r.id!=='api');S.projectInfo.repositories.push({id:'ops',name:'Ops'});$('analyzeMap').click();
 assert($('analysisTarget').value==='' && document.querySelector('[data-analysis-task="analysis_request"]').disabled,'A code that is no longer connected cannot stay chosen');
''')

    def test_code_chips_show_why_they_need_attention_and_how_to_reanalyze(self):
        self.check(r'''
 const r=S.projectInfo.repositories;r[0].analysis={dev:{stale:true,unknown:['auth flow unread']}};render();
 const chips=$('repository-bar').querySelector('.chips');
 assert(chips.innerText.includes(tr('AI 재분석 필요')),'Stale analysis is named on the chip: '+chips.innerText);
 assert(chips.innerText.includes(tr('모르는 것 ')+'1') && chips.innerHTML.includes('auth flow unread'),'Unknowns are counted on the chip and listed in its tooltip');
 const again=document.querySelector('[data-reanalyze="web"]');
 assert(again && outside($('repository-bar')).includes(again.innerText),'The re-analysis action is outside the folded details');
 again.click();
 assert($('analysisTarget').value==='web' && document.querySelector('[data-analysis-task="analysis_request"]').className.includes('primary'),'It opens code analysis for that code');
''')

    def test_registration_problems_stay_visible_in_connection_diagnostics(self):
        self.check(r'''
 S.agentPurpose='connection';S.agentPrompt='connection';
 S.connectionDiagnostic={feature:'detail',challenge:'x',fresh_server:{state:'ready'},registration:{state:'app_moved_or_missing',command:'/old/python',server:'/old/mcp_server.py'},connection:{state:'different_server',missing:['impact']},handoff:'repair'};
 renderConnectionDiagnostic();
 assert(outside($('insp')).includes(connectionMessage('app_moved_or_missing')),'The registered path problem is not folded away');
 assert(outside($('insp')).includes(tr('AI 연결에 필요한 기능이 빠져 있습니다')),'Missing capability is not folded away');
 assert([...$('insp').querySelectorAll('details')].some(d=>d.textContent.includes('impact')),'Actual tool names stay in details');
 S.connectionDiagnostic={feature:'detail',challenge:'x',fresh_server:{state:'ready'},registration:{state:'different_path',command:'/a',server:'/b/mcp_server.py'},connection:{state:'verified'},handoff:'repair'};
 renderConnectionDiagnostic();
 assert(outside($('insp')).includes(connectionMessage('different_path')),'A different registered path is shown even when the live connection works');
 S.connectionDiagnostic.registration={state:'matches_app'};renderConnectionDiagnostic();
 assert(!outside($('insp')).includes(connectionMessage('matches_app')),'A matching registration adds no warning');
''')

    def test_app_generated_text_is_localized_but_user_data_is_not(self):
        self.check(r'''
 const links=[{from:'api::worker',to:'web::repository',label:'Configured API destination',sure:'doc',ev:[]},{from:'web::repository',to:'api::worker',label:'Configured API destination',sure:'code',ev:[{file:'x',line:1}]}];
 S.branchDetails.dev.system={...S.system,nodes:[...S.system.nodes,{id:'web::repository',name:'[Web screens] Web screens',kind:'repository',origin:'repo',what:'Repository · 3 screens',uses:[],ev:[],unknown:[]},{id:'web::copy',name:'Copy',kind:'program',what:'Repository · 9 screens',uses:[],ev:[],unknown:[]}],links};
 S.view='sys';render();
 const text=main();
 if(S.lang==='ko'){assert(!text.includes('Repository · 3 screens') && text.includes('코드 · 화면 3개'),'The generated code box is described in Korean');
  assert(text.split('Configured API destination').length===2 && text.includes('지정한 서버 연결'),'Only the generated connection label is translated');}
 else assert(text.includes('Code · screens: 3'),'The generated code box is described in English');
 assert(text.includes('Repository · 9 screens'),'User or AI written text is not rewritten');
 $('q').value=tr('지정한 서버 연결');$('q').dispatchEvent(new Event('input'));
 assert(document.querySelector('[data-search-result]'),'Search finds the translated connection label');
 $('q').value='';$('q').dispatchEvent(new Event('input'));
 S.changes={last_refresh:'2026-10-01T00:00:00Z',entries:[{at:'2026-10-01T00:00:00Z',since:'2026-09-24T00:00:00Z',repository:'web',branches:{},prs:[
  {number:7,title:'Docs',url:'https://example.invalid/7',base:'dev',kinds:[],screens:[],groups:['배포·CI'],programs:[],issues:[],files:1,author:'a',merged_at:'2026-10-01T00:00:00Z'},
  {number:8,title:'Items',url:'https://example.invalid/8',base:'dev',kinds:[],screens:[],groups:[],programs:['[api] Worker'],issues:[],files:1,author:'a',merged_at:'2026-10-01T00:00:00Z'}]}]};
 S.view='changes';render();
 assert(main().includes('[API server] Worker') && !main().includes('[api]'),'PR group names use code display names');
 if(S.lang==='en')assert(!/[가-힣]/.test(main()),'App-made PR places are translated: '+(main().split('\n').find(l=>/[가-힣]/.test(l))));
''')

    def test_branches_ahead_name_the_analyzed_version_instead_of_development(self):
        self.check(r'''
 S.status.branches=[{name:'feature/items',ahead_of_dev:3,author:'alice',age_days:2,screens:['web::/items']}];
 S.view='map';render();document.querySelector('[data-scr="web::/items"]').click();
 const line=[...$('insp').querySelectorAll('.row')].find(r=>r.innerText.includes('feature/items'))?.innerText || '';
 assert(line && !/개발|[Dd]evelopment/.test(line),'No development wording: '+line);
 assert(line.includes(versionName('dev')) && line.includes('3'),'The analyzed version is named: '+line);
''')

    def test_search_shows_data_by_display_and_code_names_without_changing_ids(self):
        self.check(r'''
 for(const query of ['API server','items · API','api::items']){
  $('q').value=query;$('q').dispatchEvent(new Event('input'));
  const hit=[...document.querySelectorAll('[data-search-result]')].map((el,i)=>[el,S._search[i]]).find(([,t])=>t.kind==='data');
  assert(hit,'Data is found by '+query);
  assert(hit[0].querySelector('.t').innerText==='items · API server','Data shows its display name: '+hit[0].innerText);
 }
 assert(controlTargets().some(t=>t.id==='data:api::items' && t.key==='api::items'),'App control IDs stay the same');
''')

    def test_request_names_are_not_cut_off_by_badges(self):
        self.check(r'''
 M().screens[0].actions[0].label='Cancel the reservation for the selected item';S.status.open_prs[0].files=['api/app/items.py'];
 S.view='map';render();document.querySelector('[data-scr="web::/items"]').click();
 const row=document.querySelector('[data-req]'),name=row.querySelector('.t');
 assert(row.querySelectorAll('.pill').length>=2,'The row has badges');
 assert(name.scrollWidth<=name.clientWidth+1,'The request name is fully visible at 1280: '+name.scrollWidth+'>'+name.clientWidth);
''')

    def test_structure_choice_resets_per_project_and_matches_app_control(self):
        self.check(r'''
 const fb=fakeBundle;fakeBundle=n=>{const b=fb(n);const proposal={...b.system,nodes:[{...b.system.nodes[0],name:n+' proposed'}]};b.branch_details.dev={...b.branch_details.dev,'system.ai':proposal};return b;};
 await loadProject('First',false,'');S.view='sys';render();
 document.querySelector('[data-proposal="1"]').click();
 let result=await applyAppCommand({action:'targets',arguments:{query:'proposed'}});
 assert(result.state.structure==='ai_proposal','App state says the AI proposal is shown');
 assert(result.output.targets.some(t=>t.kind==='program' && t.name==='First proposed'),'Targets come from the shown structure');
 assert(main().includes('First proposed'),'Reading targets keeps the shown structure');
 result=await applyAppCommand({action:'navigate',arguments:{project:'Second',repository:'',branch:'dev',view:'sys'}});
 assert(result.state.structure==='written' && main().includes('Second Worker') && !main().includes('Second proposed'),'Another project starts with its written structure');
 result=await applyAppCommand({action:'targets',arguments:{query:'Worker'}});
 assert(result.output.targets.some(t=>t.name==='Second Worker'),'Targets follow the written structure');
''')

    def test_partial_results_say_which_code_is_saved_and_which_is_waiting(self):
        # Like ai_extract.py, each code's analysis request expects both the map (analysis) and the structure (system).
        self.check(r'''
 $('analyzeMap').click();$('analysisTarget').value='*';$('analysisTarget').dispatchEvent(new Event('change'));
 document.querySelector('[data-analysis-task="analysis_request"]').click();await wait();
 assert(S.analysisRequest.requirements.length===4,'Two requirements per code');
 const fb=fakeBundle,saved={version:'new',commit:'aaaaaaaa1111'};let results={};
 fakeBundle=n=>{const b=fb(n);for(const r of b.project.repositories)r.results={dev:results[r.id] || {}};return b;};
 const shown=async()=>{await checkAnalysisResults();const p=$('analysisResultState').nextElementSibling;return p?.dataset.codes!==undefined?[...p.children].map(c=>c.textContent).join('\n'):'';};
 const line=(text,label)=>(text.split('\n').find(l=>l.startsWith(tr(label))) || '').slice(tr(label).length);
 results={web:{analysis:saved}};let text=await shown();
 assert(S.analysisRequest.state==='partial','The map of one code is saved');
 assert(!line(text,'결과가 저장된 코드: ') && line(text,'일부 결과만 저장된 코드: ')==='Web screens' && line(text,'결과를 기다리는 코드: ')==='API server','A code is never both saved and waiting: '+text);
 results={web:{analysis:saved,system:saved}};text=await shown();
 assert(line(text,'결과가 저장된 코드: ')==='Web screens' && !line(text,'일부 결과만 저장된 코드: ') && line(text,'결과를 기다리는 코드: ')==='API server','One code is complete: '+text);
 results={web:{analysis:saved,system:{...saved,proposal:true}},api:{analysis:{commit:'aaaaaaaa1111'}}};text=await shown();
 assert(S.analysisRequest.state==='proposal_partial' && line(text,'결과가 저장된 코드: ')==='Web screens' && line(text,'결과를 기다리는 코드: ')==='API server','A proposal and an earlier result keep their states: '+text);
 results={web:{analysis:saved,system:saved},api:{analysis:saved,system:{...saved,proposal:true}}};text=await shown();
 assert(S.analysisRequest.state==='proposal' && !line(text,'결과를 기다리는 코드: ') && $('viewAnalysisResults'),'Everything saved shows the result: '+text);
 results={web:{analysis:{commit:'aaaaaaaa1111'},system:{commit:'aaaaaaaa1111'}},api:{analysis:{commit:'aaaaaaaa1111'},system:{commit:'aaaaaaaa1111'}}};await shown();
 assert(S.analysisRequest.state==='previous','Only earlier results are not reported as new');
''')

    def test_progress_status_is_neutral_and_cleared_when_the_scope_changes(self):
        self.check(r'''
 setStatus('boom',true);
 let release;window.holdAnalysis=new Promise(r=>release=r);
 const pending=requestAgentAction('analysis_request',{repository:'web'});await wait();
 assert($('status').textContent===tr('분석 요청을 준비하는 중…') && !$('status').classList.contains('error'),'Progress is not shown in the error colour: '+$('status').textContent+' '+$('status').className);
 document.querySelector('#branch [data-b=main]').click();release();await pending;await wait();
 assert(!$('status').textContent,'Progress for an abandoned scope is cleared: '+$('status').textContent);
''')

    def test_finishing_a_refresh_keeps_a_newer_code_selection(self):
        self.check(r'''
 let finishRefresh,finishRead;window.holdRefresh=new Promise(r=>finishRefresh=r);window.holdRead={repository:'api',promise:new Promise(r=>finishRead=r)};
 const refreshing=doRefresh();await wait();
 $('repository').value='api';$('repository').dispatchEvent(new Event('change'));await wait();
 finishRefresh();await wait();finishRead();await refreshing;await wait(50);
 assert(S.repository==='api' && $('repository').value==='api','The code chosen while refreshing stays selected: '+S.repository);
''')

    def test_a_failed_read_does_not_block_refreshing_the_shown_project(self):
        self.check(r'''
 const fb=fakeBundle,reads=()=>calls.filter(c=>c.command==='read_project' && c.args.project==='First').length;
 fakeBundle=n=>{if(n==='Second')throw Error('fictional read failure');return fb(n);};
 $('project').value='Second';$('project').dispatchEvent(new Event('change'));await wait();
 assert(S.project==='First' && $('status').classList.contains('error'),'The failed read is reported and First stays shown');
 assert($('project').value==='First','The project menu returns to the shown project: '+$('project').value);
 let before=reads();await doRefresh();await wait();
 assert(reads()>before && !$('status').textContent,'Refreshing the shown project reloads it and clears the progress: '+$('status').textContent);
 fakeBundle=n=>{if(window.failRead)throw Error('fictional code read failure');return fb(n);};
 window.failRead=true;$('repository').value='api';$('repository').dispatchEvent(new Event('change'));await wait();
 assert(S.repository==='' && $('repository').value==='','The code menu returns to the shown code: '+$('repository').value);
 window.failRead=false;before=reads();await doRefresh();await wait();
 assert(reads()>before && !$('status').textContent,'A failed code read does not block refreshing either: '+$('status').textContent);
''')

    def test_request_detail_names_shared_data_by_display_name(self):
        self.check(r'''
 S.branchDetails.dev.system.nodes[0].tables=['api::items'];S.view='map';render();
 document.querySelector('[data-scr="web::/items"]').click();document.querySelector('[data-req]').click();
 const line=[...$('insp').querySelectorAll('.empty')].map(e=>e.innerText).find(t=>t.includes('First Worker')) || '';
 assert(line.includes('items · API server') && !line.includes('api::items'),'Directly accessed data uses its display name: '+line);
''')

    def test_a_failed_refresh_keeps_the_version_buttons_labelled(self):
        self.check(r'''
 window.failRefresh=true;await doRefresh();
 assert($('status').classList.contains('error') && $('error-detail').textContent.includes('fictional collection error'),'The failure is shown with its original text');
 const labels=[...document.querySelectorAll('#branch button')].map(b=>b.textContent);
 assert(labels.length===2 && labels[0].includes('HEAD') && labels[1].includes('v1.0'),'Version buttons keep their names: '+JSON.stringify(labels));
''')

class UxWriting(unittest.TestCase):
    '''Regressions for the 2026-10-21 novice UX writing review: behaviour, not individual labels.'''
    def setUp(self):
        if not CHROME.exists():self.skipTest('Chrome is required')
    def check(self,checks,query=''):
        for lang in ('ko','en'):
            with self.subTest(lang=lang):
                ok,error=page(checks,lang,query);self.assertTrue(ok,error)

    def test_briefing_shows_problem_and_change_and_counts_unknown_fields_separately_from_both_periods(self):
        self.check(r'''
 const value=(t,u=false)=>({text:t,unknown:u,evidence:[]});
 const card={title:'Fictional change',merge:'merged',prs:[{repository:'web',number:42,url:'https://example.invalid/pull/42',branch:'feature/a',base:'main',issues:[]}],terms:[{term:'Ref',explanation:value('Fictional term')}]};
 for(const k of ['problem','why','before','after','resolution','impact','recovery','remaining'])card[k]=value('Known '+k);
 card.why=value('Unknown why',true);card.remaining=value('Unknown remaining',true);
 S.briefings={dev:{[S.lang]:{state:'saved',warnings:[],result:{cards:[card],pr_count:1,branch:'dev',unknown:[],input:{repositories:[{id:'web',since:'2026-09-01T00:00:00Z',at:'2026-09-20T00:00:00Z',refs:{dev:'HEAD'},commits:{from:'aaaa1111',to:'bbbb2222'}}]}}}}};
 S.changes={last_refresh:'2026-10-01T00:00:00Z',entries:[{at:'2026-10-01T00:00:00Z',since:'2026-09-24T00:00:00Z',repository:'web',branches:{},prs:[]}]};
 S.view='changes';render();
 const text=outside($('map')),summaries=[...$('map').querySelectorAll('summary')];
 assert(text.includes('Known problem') && text.includes('Known after'),'Problem and what changed are shown by default');
 assert(!text.includes('Unknown why') && !text.includes('Unknown remaining') && !text.includes('Known before'),'Other fields are folded');
 const unknown=summaries.find(s=>s.textContent.includes(tr('확인이 필요한 내용')));
 assert(unknown && unknown.textContent.includes('2') && unknown.parentElement.textContent.includes('Unknown remaining') && !unknown.parentElement.textContent.includes('Known before'),'Unknown fields have their own visible count');
 const more=summaries.find(s=>s.textContent.includes(tr('자세한 변경 내용')));
 assert(more && more.parentElement.textContent.includes('Known before') && !more.parentElement.textContent.includes('Unknown why'),'Known details are separate');
 assert(summaries.some(s=>s.textContent.includes(tr('용어 풀이')) && s.parentElement.textContent.includes('Fictional term')),'Terms are separate');
 assert(text.includes(tr('설명 구간')) && text.includes(when('2026-09-01T00:00:00Z')) && text.includes(when('2026-09-20T00:00:00Z')),'Explanation period is visible: '+text);
 assert(text.includes(tr('새로고침 기록 구간')) && text.includes(when('2026-09-24T00:00:00Z')),'Selected refresh history period is shown separately');
 assert(!text.includes('aaaa1111'),'Commit provenance stays folded');
''')

    def test_connection_repair_copy_leads_until_copied_then_the_check_and_details_hold_tools(self):
        self.check(r'''
 S.agentPurpose='connection';S.agentPrompt='connection';
 S.connectionDiagnostic={feature:'detail',challenge:'x',fresh_server:{state:'ready'},registration:{state:'not_inspected'},connection:{state:'not_verified'},handoff:'repair'};
 renderConnectionDiagnostic();
 assert($('liveConnectionState').textContent===tr('AI 연결을 아직 확인하지 않았습니다.'),'Unchecked is not reported as disconnected');
 assert($('copyConnectionRequest').classList.contains('primary') && !$('checkCurrentConnection').classList.contains('primary'),'Copying the repair request comes first');
 assert($('connectionFeature').closest('details'),'The feature choice is an advanced detail');
 await $('copyConnectionRequest').onclick();
 assert(!$('copyConnectionRequest').classList.contains('primary') && $('checkCurrentConnection').classList.contains('primary'),'After copying, checking is the main action');
 assert($('checkCurrentConnection').textContent===tr('연결됐는지 확인'),'Check names what it does');
 S.connectionDiagnostic.connection={state:'missing_tools',missing:['impact']};renderConnectionDiagnostic();
 assert(outside($('insp')).includes(tr('AI 연결에 필요한 기능이 빠져 있습니다')) && !outside($('insp')).includes('impact'),'Missing capability is stated plainly');
 assert([...$('insp').querySelectorAll('details')].some(d=>d.textContent.includes('impact')),'Actual tool names stay in details');
 $('guideOpen').click();guideStep(1);$('guideDiagnose').click();await wait(60);
 assert(window.calls.some(c=>c.command==='connection_diagnose' && c.args.feature==='onboarding'),'The guide checks the tools onboarding actually needs');
 assert($('guide-copyConnectionRequest').classList.contains('primary'),'The guide also leads with copying');
 closeGuide();
''')

    def test_guide_edits_the_connected_service_and_names_each_code_and_its_map(self):
        self.check(r'''
 const repos=S.projectInfo.repositories;repos[0].url='https://github.com/example/web';repos[1].path='/fictional/api';repos[1].collected=false;repos[1].commits={};
 $('guideOpen').click();guideStep(2);
 assert($('guideCreate').textContent===tr('연결한 코드 수정'),'An existing service is edited, not recreated');
 const text=$('guide').innerText;
 assert(text.includes('https://github.com/example/web') && text.includes('/fictional/api'),'Each code shows where it comes from');
 assert(text.includes(tr('지도 준비됨')) && text.includes(tr('아직 지도 없음')),'Each code shows its own map state: '+text);
 $('guideCreate').click();
 assert($('project-dialog').open && $('projectName').disabled && $('projectName').value==='First','The editor opens the shown service');
 $('project-dialog').close();await wait();guideStep(1);
 assert($('guideCreate').textContent===tr('연결한 코드 수정'),'Same on the AI step');
 repos[0].config_changed=true;guideStep(2);
 assert($('guide').innerText.includes(tr('설정 변경 · 지도 갱신 필요')) && !guideHasMap(),'Changed settings are not reported as a ready map');
 repos[0].config_changed=false;repos[1].collected=true;repos[1].commits={dev:'cccccccc3333'};assert(guideHasMap(),'Refreshed code is ready again');
 S.projectInfo.repositories=[];guideStep(2);
 assert($('guide').innerText.includes('/fictional') && $('guide').innerText.includes(tr('지도 준비됨')),'A legacy single-folder service shows its folder and map');
 closeGuide();
''')

    def test_guide_offers_manual_copy_only_when_instructions_exist(self):
        self.check(r'''
 $('guideNext').click();
 const clip=navigator.clipboard.writeText;navigator.clipboard.writeText=async()=>{throw Error('denied');};
 $('guideCopySetup').click();await wait(60);
 assert($('guideCopyState').textContent===tr('복사하지 못했습니다. 다시 시도하거나 안내를 열어 직접 복사하세요.') && $('guide').querySelector('pre.prompt'),'Manual copy is offered with the instructions');
 navigator.clipboard.writeText=clip;G.setup=null;window.holdSetup=Promise.reject(Error('no prompt'));window.holdSetup.catch(()=>{});
 $('guideCopySetup').click();await wait(60);
 assert($('guideCopyState').textContent===tr('안내를 만들지 못했습니다. 다시 시도하세요.') && !$('guide').querySelector('pre.prompt'),'No manual copy without instructions');
''',query='&empty=1')

    def test_search_explains_why_it_is_unavailable_without_a_map(self):
        self.check(r'''
 assert($('q').disabled && $('q').title===tr('서비스를 연결하고 지도를 가져오면 찾을 수 있습니다.'),'No service: search is disabled with a reason');
''',query='&empty=1')
        self.check(r'''
 assert(!$('q').disabled && $('q').placeholder===tr('화면·기능·프로그램·데이터·PR·이슈 찾기'),'With a map search is available');
 window.noMap=true;await loadProject('First');
 assert($('q').disabled && $('q').title===tr('서비스를 연결하고 지도를 가져오면 찾을 수 있습니다.'),'No map: search is disabled with a reason');
''')

    def test_errors_are_explained_and_keep_the_original_text_in_details(self):
        self.check(r'''
 window.failRefresh=true;await doRefresh();
 assert($('status').classList.contains('error') && !$('status').textContent.includes('fictional collection error'),'The status line explains the failure: '+$('status').textContent);
 const raw=$('error-detail');
 assert(!raw.hidden && raw.textContent.includes('fictional collection error') && raw.querySelector('[data-copy-error]'),'The original error stays in copyable details');
 assert(!/SSH/.test(githubErrorText('GITHUB_ACCESS|github.com|me|download|web')) && !/SSH/.test(githubErrorText('GITHUB_ACCESS|github.com|me|fetch|web')),'Download failures do not blame SSH keys');
 assert(githubErrorText('GITHUB_ACCESS|github.com|me|unknown_code|web').indexOf(tr('로그인 상태와 인터넷 연결을 확인해 주세요.'))<0,'Unknown failures do not blame login');
 editProject(false);window.failSave=true;$('saveProject').click();await wait(60);
 const box=$('project-dialog');
 assert(box.querySelector('#projectError').innerText.startsWith(tr('연결을 저장하지 못했습니다. 입력과 연결 상태를 확인하세요.')) && [...box.querySelectorAll('details')].some(d=>d.textContent.includes('fictional save failure')),'Save failure keeps its original text in details');
 assert(box.querySelector('#projectError details'),'Error details stay inside the alert');
 box.close();window.failSave=false;
 window.githubFail='GITHUB_ACCESS|github.com|me|login|web';window.loginsFail='fictional login listing failure';
 editProject(false);$('saveProject').click();await wait(80);
 assert([...$('project-dialog').querySelectorAll('[data-registration-account] details')].some(d=>d.textContent.includes('fictional login listing failure')),'Account listing failure keeps its own original error');
 $('project-dialog').close();window.githubFail=null;window.loginsFail=null;
 S.analysisRequest={scope:{project:S.project,repository:S.repository,branch:S.branch},command:'analysis_request',state:'error',error:'fictional read failure',handoff:'x'};S.agentPurpose='analysis';S.agentPrompt='x';renderAgentPrompt();
 assert($('analysisResultState').querySelector('details')?.textContent.includes('fictional read failure'),'Result read errors keep details inside the status');
 U.latest={version:'9.9.9',newer:true,notes:'',url:''};
 const cause=e=>{U.job={stage:'failed',version:'9.9.9',error:e};return updateMessage();};
 assert(!$('updateConnectionDiagnostic'),'No reconnect step without a completed update');
 assert(cause('The previous update was interrupted. Recovery copy: /safe/recovery')===tr('이전 업데이트가 중간에 멈췄습니다. 오류 내용의 복구 방법을 확인하세요.'),'A preserved recovery copy is not a failed restore');
 assert(cause('Could not reopen the updated app: x; disk full. Recovery copy: /b')===tr('이전 버전으로 자동 복구하지 못했습니다. 오류 내용의 복구 위치를 확인하세요.'),'A failed rollback is named');
 assert(cause('Open the Homebrew-installed app to update it here')===tr('Homebrew로 설치한 앱에서만 여기서 업데이트할 수 있습니다. 직접 업데이트하기의 명령을 쓰세요.'),'Install origin precondition');
 assert(cause('Another app update is already running')===tr('이미 업데이트가 진행 중입니다.'),'Busy update');
 assert(cause('Could not copy the app for recovery')===tr('새 버전을 설치하지 못했습니다.')+' '+tr('업데이트하지 못했습니다. 오류 내용을 확인한 뒤 다시 시도하세요.'),'A failed backup before installing is not a failed restore');
 assert(cause('Could not restore app: busy. Preserved files: /p')===tr('이전 버전으로 자동 복구하지 못했습니다. 오류 내용의 복구 위치를 확인하세요.'),'Explicit restore failure');
 assert(cause('Wait for collection or AI work to finish before updating')===tr('새로고침이나 AI 작업이 끝난 뒤 다시 시도하세요.'),'Busy precondition');
 assert(cause('Homebrew does not have the requested stable version yet')===tr('Homebrew에 새 버전이 아직 올라오지 않았습니다. 잠시 뒤 다시 시도하세요.'),'Version not ready');
 U.job={stage:'failed',version:'9.9.9',error:'Could not restore app: busy. Preserved files: /private/tmp/recovery-1'};renderUpdates();
 const update=$('updateStatus');
 assert(!update.textContent.includes('/private/tmp/recovery-1') && update.textContent && update.textContent!==tr('업데이트가 완료되었습니다.'),'Recovery failure is explained without claiming success');
 assert([...$('release-dialog').querySelectorAll('details')].some(d=>d.textContent.includes('/private/tmp/recovery-1')),'The recovery location stays available');
 assert(!$('release-dialog').textContent.includes(tr('업데이트 뒤 AI 연결을 다시 확인하세요.')),'Reconnect guidance waits for a completed update');
 U.job={stage:'completed',version:'9.9.9',error:null};renderUpdates();
 assert($('release-dialog').textContent.includes(tr('업데이트 뒤 AI 연결을 다시 확인하세요.')) && $('updateConnectionDiagnostic'),'Completed updates ask to check the AI connection');
''')

    def test_settings_read_failure_keeps_the_original_error(self):
        self.check(r'''
 assert($('status').classList.contains('error') && $('status').textContent===tr('설정을 읽지 못했습니다. 오류 내용을 확인하세요.') && $('error-detail').textContent.includes('fictional settings read failure'),'Settings read failure is explained with its original text');
''',query='&settingsFail=1')

    def test_baseline_notice_only_for_since_previous_refresh_and_names_the_next_refresh(self):
        self.check(r'''
 const notice=tr('지난 새로고침 이후를 선택하면 다음 새로고침은 이번 시각 이후부터 비교합니다. 시작점을 고정하려면 날짜·시각을 지정하세요.');
 S.settings={open_refresh:false,since:'last_refresh',since_time:''};renderHeader();
 assert($('refresh').title.includes(notice),'Refresh explains the next comparison start');
 S.settings={open_refresh:false,since:'time',since_time:'2026-09-01T00:00'};renderHeader();
 assert(!$('refresh').title.includes(notice),'A fixed time has no moving-start notice');
 renderSettings();$('settings-dialog').showModal();
 const shown=()=>{const n=$('baselineNotice');return !!n && !n.hidden;};
 assert(!shown(),'Fixed time hides the notice');
 const last=$('settings-dialog').querySelector('input[value=last_refresh]');last.checked=true;last.dispatchEvent(new Event('change'));
 assert(shown() && $('baselineNotice').textContent===notice,'Choosing previous refresh shows it');
 assert($('settings-dialog').textContent.includes(tr('서비스를 열 때 새로고침')),'Automatic refresh names service switches too');
 $('settings-dialog').close();
 const save=async since=>{renderSettings();$('settings-dialog').showModal();const r=$('settings-dialog').querySelector('input[value='+since+']');r.checked=true;r.dispatchEvent(new Event('change'));$('sinceTime').value='2026-09-01T00:00';await $('saveSt').onclick();};
 await save('last_refresh');assert($('refresh').title.includes(notice),'Saving previous refresh updates the refresh button');
 await save('time');assert(!$('refresh').title.includes(notice),'Saving a fixed time removes the notice without another render');
 assert(!window.calls.some(c=>c.command==='refresh'),'Saving alone does not refresh');
''')

    def test_copied_requests_name_the_buttons_the_app_shows(self):
        source=(ROOT/'ui/index.html').read_text()+(ROOT/'ui/connection.js').read_text()
        prompts=''.join((ROOT/name).read_text() for name in ('ai_extract.py','briefing.py','connection.py'))
        for ko,en in (('결과 확인','Check results'),('연결됐는지 확인','Check the connection')):
            self.assertRegex(source,'["\']'+re.escape(ko)+'["\']\\s*:\\s*["\']'+re.escape(en)+'["\']')
            self.assertIn(f'‘{ko}’',prompts);self.assertIn(en,prompts)
        for old in ('저장된 결과 확인','Check saved results','‘현재 연결 확인’','Check current connection'):
            self.assertNotIn(old,prompts)

if __name__=='__main__':unittest.main()
