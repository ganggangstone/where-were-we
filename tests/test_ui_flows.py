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
 if(command==='refresh')return window.refreshOutput || 'Fictional refresh';
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
 if(command==='read_project' && window.failRead)throw Error('fictional read failure');
 if(command==='read_project'){const b=window.configuredBundle?.project.name===args.project?structuredClone(window.configuredBundle):fakeBundle(args.project);if(window.noMap){b.dev=null;b.main=null;}if(window.mutateBundle)window.mutateBundle(b);return JSON.stringify(b);}
 if(command==='read_settings')return JSON.stringify({open_refresh:false,since:'last_refresh',since_time:''});
 if(command==='app_version')return '0.0.0';
 if(command==='save_settings')return args.json;
 if(command==='app_update_status')return null;
 if(command==='control_poll')return null;
 if(command==='control_focus')return null;
 if(command==='analysis_plan'){if(window.holdPlan)await window.holdPlan;if(window.failPlan)throw Error('fictional plan failure');return JSON.stringify(window.planResult||{tasks:[],blocked:[],requirements:[],handoff:'',up_to_date:true});}
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

# Saved AI results as the stored project reports them; analyzeAll() makes the next read_project return them.
ANALYZED=r"""
 const saved=(r,lang,over={})=>({version:'v1',commit:r.commits.dev,language:lang,stale:false,configuration:'c',...over});
 const analyzeAll=(lang=S.lang,over={},only=null,parts=['analysis','system'])=>{window.mutateBundle=b=>{for(const r of b.project.repositories){if(only&&!only.includes(r.id))continue;r.results={dev:Object.fromEntries(parts.map(k=>[k,saved(r,lang,over)])),main:{}};}};};
 const reads=()=>window.calls.filter(c=>c.command==='read_project').length;
 const analysisRail=()=>$('guide').querySelector('.guide-rail li:nth-child(4) .dot.ok');
 const awaitRequest=()=>{G.copied=true;G.await={lang:S.lang,base:S.project,project:S.project,branch:S.branch};};
 const finishReading=async()=>{await guideReadSaved(true);for(let i=0;i<50 && G.reading;i++)await wait();await wait(20);};
 const openAnalysisStep=async()=>{await loadProject('First');$('guideOpen').click();G.step=3;renderGuide();};
"""

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
 assert($('guideMapState').textContent.includes(tr('기본 지도는 준비됐지만 첫 AI 분석은 아직 없습니다.')),'Existing basic map is ready but not analyzed');
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
 assert(window.calls.filter(c=>c.command==='refresh').length===1 && !$('guideRefresh') && $('guideAnalysis') && !$('guideFinish'),'One explicit refresh makes the basic map ready, not the first analysis');
 $('guideAnalysis').click();await wait();
 assert(!$('guide').open && !window.calls.some(c=>c.command==='analysis_request'),'Analysis opens the request panel without running');
 assert($('insp').textContent.includes(tr('AI로 자세한 지도 만들기')),'The existing analysis panel is shown');
""")

    def test_copy_step_explains_one_request_and_ai_cost_before_copying(self):
        self.check(r"""
 $('guideNext').click();
 const step=$('guide').querySelector('.guide-step'),text=step.innerText;
 const once=tr('같은 요청 하나로 연결·코드 확인·첫 지도·첫 AI 분석까지 이어집니다.'),cost=tr('첫 AI 분석은 연결한 AI의 요금과 사용 한도를 씁니다.'),button=tr('AI에게 보낼 요청 복사');
 assert(text.includes(once),'Says one request does everything');
 assert(text.includes(cost),'Says the AI cost before copying');
 assert(text.indexOf(cost)<text.indexOf(button),'Cost is stated before the copy button');
 if(S.lang==='en')assert(!/[가-힣]/.test(text),'English step has no Korean: '+text);
 assert(!window.calls.some(c=>['refresh','analysis_plan','save_project'].includes(c.command)),'Reading the step runs nothing');
""",query='&empty=1')

    def test_last_stage_is_the_first_analysis_and_a_basic_map_alone_is_not_done(self):
        self.check(ANALYZED+r"""
 await openAnalysisStep();
 assert($('guideTitle').textContent===tr('첫 분석') && $('guide').querySelector('.guide-rail li:nth-child(4)').textContent.includes(tr('첫 분석')),'Last stage is the first analysis');
 assert(guideHasMap() && !$('guideFinish') && !analysisRail(),'A connected basic map is not a finished first run');
 assert($('guideMapState').textContent.includes(tr('기본 지도는 준비됐지만 첫 AI 분석은 아직 없습니다.')),'Says the analysis is missing');
 assert($('guideReadNow') && $('guideAnalysis'),'Recovery: read again, and the manual request stays reachable');
 const before=reads();analyzeAll();$('guideReadNow').click();for(let i=0;i<50 && !$('guideFinish');i++)await wait();
 assert(reads()===before+1 && $('guideFinish') && analysisRail(),'Saved current analysis for every code and no remaining plan finishes it');
 const asked=window.calls.filter(c=>c.command==='analysis_plan');
 assert(asked.length===1 && asked[0].args.project==='First' && asked[0].args.branch==='dev' && asked[0].args.lang===S.lang && !asked[0].args.repository,'The authoritative plan is read once for exactly this project, version and language');
 assert($('guide').querySelectorAll('li[data-guide-code]').length===2,'Each code is listed');
 if(S.lang==='en')assert(!/[가-힣]/.test($('guide').querySelector('.guide-step').innerText),'English step has no Korean');
 $('guideFinish').click();await wait();
 assert(!$('guide').open && S.view==='sys' && guideMarker()==='done','Result viewing opens the analyzed structure, not the basic map');
 assert(!window.calls.some(c=>['refresh','analysis_request','make_system'].includes(c.command)),'Viewing does not run anything');
""")

    def test_partial_stale_wrong_language_and_missing_system_never_look_complete(self):
        self.check(ANALYZED+r"""
 const other=S.lang==='ko'?'en':'ko',cases=[
  ['partial one code',()=>analyzeAll(S.lang,{},['web']),tr('일부 코드만 분석이 저장됐습니다.')],
  ['other language',()=>analyzeAll(other),tr('다른 언어로 저장된 분석입니다.')],
  ['stale',()=>analyzeAll(S.lang,{stale:true}),tr('코드가 바뀌어 최신이 아닌 분석입니다.')],
  ['old commit',()=>analyzeAll(S.lang,{commit:'ffffffff9999'}),tr('코드가 바뀌어 최신이 아닌 분석입니다.')],
  ['saved but plan unread',()=>analyzeAll(),tr('저장된 결과를 읽어 남은 분석이 있는지 확인하세요.')],
  ['empty commit',()=>analyzeAll(S.lang,{commit:''}),tr('코드가 바뀌어 최신이 아닌 분석입니다.')]];
 for(const [name,make,message] of cases){
  make();await openAnalysisStep();
  assert(!$('guideFinish') && !analysisRail(),name+': not finished');
  assert($('guideMapState').textContent.includes(message),name+': says why ('+$('guideMapState').textContent+')');
  assert($('guideAnalysis') && $('guideReadNow'),name+': recovery offered');
  if(S.lang==='en')assert(!/[가-힣]/.test($('guide').querySelector('.guide-step').innerText),name+': English');
  closeGuide();
 }
 window.mutateBundle=null;await loadProject('First');$('guideOpen').click();G.step=3;renderGuide();
 S.branch='main';renderGuide();assert(!$('guideFinish'),'Results saved for another version do not count');S.branch='dev';
""")

    def test_saved_results_are_read_when_the_app_regains_focus_only_while_awaiting_the_request(self):
        self.check(ANALYZED+r"""
 await openAnalysisStep();let n=reads();
 window.dispatchEvent(new Event('focus'));await wait(60);assert(reads()===n,'A guide that was never asked to wait reads nothing on focus');
 awaitRequest();analyzeAll();window.dispatchEvent(new Event('focus'));for(let i=0;i<50 && !$('guideFinish');i++)await wait();
 assert(reads()===n+1 && $('guideFinish'),'After the request was copied, focus reads the saved result');
 window.dispatchEvent(new Event('focus'));await wait(60);assert(reads()===n+1,'Nothing more is read once it is done');
 closeGuide();awaitRequest();window.mutateBundle=null;window.dispatchEvent(new Event('focus'));await wait(60);assert(reads()===n+1,'A closed guide reads nothing');
 const sent=window.calls.map(c=>c.command);
 assert(!sent.some(c=>['refresh','analysis_request','make_system','suggest_groups','briefing_request'].includes(c)),'Reading never starts a collection or analysis');
 assert(sent.filter(c=>c==='analysis_plan').length===1,'Only the one read-only plan check ran');
""")

    def test_reading_saved_results_never_overlaps_and_failures_are_shown_and_recoverable(self):
        self.check(ANALYZED+r"""
 await openAnalysisStep();awaitRequest();let release;window.holdRead={repository:'',promise:new Promise(r=>release=r)};const n=reads();
 for(let i=0;i<4;i++){window.dispatchEvent(new Event('focus'));guideReadSaved();}
 await wait(30);assert(reads()===n+1,'One read in flight; the rest are dropped');
 release();window.holdRead=null;await wait(60);
 window.failRead=true;window.dispatchEvent(new Event('focus'));await wait(60);
 assert($('guide').querySelector('[role=alert]') && !$('guideFinish') && !analysisRail(),'A failed read is shown, not treated as done');
 assert($('guide').querySelector('[role=alert]').textContent.includes(tr('저장된 결과를 읽지 못했습니다.')),'Says the read failed');
 window.failRead=false;analyzeAll();$('guideReadNow').click();for(let i=0;i<50 && !$('guideFinish');i++)await wait();
 assert($('guideFinish') && !$('guide').querySelector('[role=alert]'),'Reading again recovers');
""")

    def test_a_reopened_guide_can_read_again_once_the_previous_run_settles(self):
        self.check(ANALYZED+r"""
 await openAnalysisStep();awaitRequest();let release;window.holdRead={repository:'',promise:new Promise(r=>release=r)};
 window.dispatchEvent(new Event('focus'));await wait(30);closeGuide();openGuide();guideStep(3);
 assert($('guideReadNow').disabled,'The old read still holds the one-in-flight guard');
 release();window.holdRead=null;await wait(60);
 assert($('guide').open && G.step===3 && !$('guideReadNow').disabled,'Once the old read settles the reopened guide can read again');
 assert(!S.projectInfo.repositories[0].results,'The old read is still not applied');
""")

    def test_completion_needs_the_authoritative_plan_and_survives_no_failed_read(self):
        self.check(ANALYZED+r"""
 analyzeAll();await openAnalysisStep();awaitRequest();
 assert(!$('guideFinish') && !window.calls.some(c=>c.command==='analysis_plan'),'Saved results alone are not done, and opening the step asks nothing');
 window.planResult={tasks:[{repository:'web',task:'groups',target:'',commit:'aaaaaaaa1111'}],blocked:[],requirements:[],up_to_date:false};
 await finishReading();
 assert(!$('guideFinish') && !analysisRail() && $('guideMapState').textContent.includes(tr('첫 분석은 저장됐지만 남은 분석이 있습니다.')),'Remaining planned analysis is not complete');
 assert($('guide').querySelector('[data-plan]') && $('guideAnalysis'),'The remaining work is named and can be requested');
 window.planResult={tasks:[],blocked:[{repository:'api',task:'analysis',reason:'Refresh first'}],requirements:[],up_to_date:false};
 await finishReading();assert(!$('guideFinish'),'A blocked analysis is not complete');
 window.planResult=null;await finishReading();assert($('guideFinish') && analysisRail(),'No remaining and no blocked plan completes it');
 window.failRead=true;await finishReading();
 assert(!$('guideFinish') && !analysisRail() && $('guide').querySelector('[role=alert]'),'A failed current read withdraws completion');
 window.failRead=false;window.failPlan=true;await finishReading();
 assert(!$('guideFinish') && $('guide').querySelector('[role=alert]'),'A failed plan read is not completion');
 closeGuide();
""")

    def test_awaiting_is_bound_to_the_context_that_copied_the_request(self):
        self.check(ANALYZED+r"""
 await openAnalysisStep();awaitRequest();analyzeAll();let n=reads();
 const other=S.lang==='ko'?'en':'ko';setLanguage(other);window.dispatchEvent(new Event('focus'));await wait(60);
 assert(reads()===n,'A language change ends the wait');setLanguage(other==='ko'?'en':'ko');
 S.branch='main';window.dispatchEvent(new Event('focus'));await wait(60);assert(reads()===n,'Another version ends the wait');S.branch='dev';
 closeGuide();openGuide();G.step=3;renderGuide();window.dispatchEvent(new Event('focus'));await wait(60);assert(reads()===n,'Closing and reopening ends the wait');
 // a read still in flight when the guide closes or the language changes is dropped before it touches the app state
 awaitRequest();let release;window.holdRead={repository:'',promise:new Promise(r=>release=r)};
 window.dispatchEvent(new Event('focus'));await wait(30);closeGuide();release();window.holdRead=null;await wait(60);
 assert(!S.projectInfo.repositories[0].results,'A late read from a closed guide is not applied');
 openGuide();G.step=3;renderGuide();awaitRequest();window.holdRead={repository:'',promise:new Promise(r=>release=r)};
 window.dispatchEvent(new Event('focus'));await wait(30);setLanguage(S.lang==='ko'?'en':'ko');release();window.holdRead=null;await wait(60);
 assert(!S.projectInfo.repositories[0].results && !$('guide').querySelector('[role=alert]'),'A late read in another language is neither applied nor reported as a failure');
""")

    def test_copying_follows_the_request_to_the_first_analysis_without_clicking_through(self):
        self.check(ANALYZED+r"""
 $('guideNext').click();$('guideCopySetup').click();await wait();
 assert(G.step===1 && G.copied,'Copying alone stays on the copy step while no service exists');
 const configuration={repositories:[{id:'web',name:'Lumen Web',path:'/fictional/web',refs:{dev:'HEAD',main:null},layout:{},api_targets:[]}],shared_data:[]};
 window.configuredBundle=fakeBundle('Lumen');window.configuredBundle.project.repositories=configuration.repositories.map(r=>({...r,collected:true,commits:{dev:'aaaaaaaa1111'}}));
 const result=await applyAppCommand({action:'configure',arguments:{project:'Lumen',configuration}});await wait(60);
 assert(result.ok && G.step===3 && $('guideTitle').textContent===tr('첫 분석'),'The service the AI connected moves the guide to the first analysis by itself');
 assert($('guide').innerText.includes(tr('AI가 분석을 마치면 앱으로 돌아올 때 저장된 결과를 자동으로 읽습니다.')) && !$('guideFinish'),'It waits for the saved analysis; a connection is not the result');
 guideStep(1);await wait();assert(G.step===1,'The user can still go back; it moves only once');
 guideStep(3);const reads0=reads();
 // the AI prepares the whole-project request, runs it, and the saved results arrive while the app is in the background
 await applyAppCommand({action:'prepare_analysis',arguments:{project:'Lumen',repository:'',branch:'dev',task:'all'}});
 analyzeAll();window.dispatchEvent(new Event('focus'));for(let i=0;i<60 && !$('guideFinish');i++)await wait();
 assert($('guideFinish') && reads()>reads0 && S.project==='Lumen','Returning to the app reads the saved analysis and the result becomes viewable');
 assert(!window.calls.some(c=>c.command==='refresh'),'Nothing was collected by the guide');
""",query='&empty=1')

    def test_result_view_opens_the_ai_proposal_and_the_manual_request_does_not_mark_the_guide_done(self):
        self.check(ANALYZED+r"""
 analyzeAll();const base=window.mutateBundle;
 window.mutateBundle=b=>{base(b);b.branch_details.dev['system.ai']={...b.system,source:'ai',nodes:b.system.nodes.map(n=>({...n,name:'Proposed Worker'}))};};
 await openAnalysisStep();await finishReading();$('guideFinish').click();await wait();
 assert(S.view==='sys' && S.showProposal && $('map').innerText.includes('Proposed Worker'),'The new AI structure is shown, not the older written one');
 openGuide();window.mutateBundle=null;await loadProject('First');G.step=3;renderGuide();localStorage.removeItem('where-were-we.onboarding');guideMemory=null;
 $('guideAnalysis').click();await wait();
 assert(!$('guide').open && guideMarker()===null,'Opening the manual request before any result does not record the guide as done');
""")

    def test_whole_project_decides_the_first_analysis_whatever_code_is_selected(self):
        self.check(ANALYZED+r"""
 analyzeAll(S.lang,{},['web']);await loadProject('First',false,'web');
 assert(S.repository==='web','One code is selected');$('guideOpen').click();G.step=3;renderGuide();awaitRequest();
 await finishReading();
 assert(S.repository==='web' && !$('guideFinish') && !analysisRail(),'The selected code being analyzed does not finish the project');
 const lines=[...$('guide').querySelectorAll('li[data-guide-code]')].map(li=>li.textContent);
 assert(lines.length===2 && lines.some(t=>t.includes('API server') && t.includes(tr('아직 분석 없음'))),'The unanalyzed code is named: '+lines.join(' / '));
 assert(window.calls.filter(c=>c.command==='analysis_plan').every(c=>!c.args.repository),'The plan is asked for the whole project');
 // an uncollected code also keeps the map from being ready, even while another code is selected
 const base=window.mutateBundle;window.mutateBundle=b=>{base(b);b.project.repositories[1].collected=false;b.project.repositories[1].commits={};};
 await finishReading();assert(!guideHasMap() && !$('guideFinish'),'An uncollected code is not hidden by the selection');
 analyzeAll();await finishReading();assert(S.repository==='web' && $('guideFinish') && analysisRail(),'All codes saved finishes it without changing the selection');
 // a code without the shown version is not eligible and cannot block it
 const all=window.mutateBundle;window.mutateBundle=b=>{all(b);const api=b.project.repositories[1];api.refs.dev=null;delete api.results;};
 await finishReading();assert($('guideFinish'),'A code that has no such version is skipped');
 closeGuide();
""")

    def test_reading_results_reports_the_actual_state_per_code_to_the_agent(self):
        self.check(ANALYZED+r"""
 const pin=(id,commit)=>({commit,configuration:'c'}),task=(repository,commit)=>({repository,task:'analysis',target:'',before:null,commit,configuration:'c'});
 const tasks=[task('web','aaaaaaaa1111'),task('api','cccccccc3333')],pins={web:pin('web','aaaaaaaa1111'),api:pin('api','cccccccc3333')};
 window.planResult={tasks,blocked:[],requirements:tasks,pins,up_to_date:false,handoff:'plan'};
 const prepared=await applyAppCommand({action:'prepare_analysis',arguments:{project:'First',repository:'',branch:'dev',task:'all'}});
 assert(prepared.output.prepared && !prepared.output.executed,'Preparing runs nothing');
 // only the web code is saved; the plan still lists the api code
 analyzeAll(S.lang,{},['web']);window.planResult={tasks:[tasks[1]],blocked:[],requirements:[],pins,up_to_date:false};
 const part=await applyAppCommand({action:'read_results',arguments:{}});
 assert(part.output.state==='partial' && part.output.scope.project==='First' && part.output.scope.repository==='' && part.output.scope.branch==='dev','Partial state and scope are returned');
 assert(part.output.codes.saved.join()==='web' && part.output.codes.waiting.join()==='api','Per-code saved and waiting are returned');
 assert(part.output.remaining.length===1 && part.output.remaining[0].repository==='api' && Array.isArray(part.output.blocked) && part.output.pins.web.commit==='aaaaaaaa1111','Remaining, blocked and pins are returned');
 window.planResult={tasks:[],blocked:[],requirements:[],pins,up_to_date:true};analyzeAll();
 const full=await applyAppCommand({action:'read_results',arguments:{}});
 assert(full.output.state==='saved' && full.output.codes.waiting.length===0 && full.output.codes.saved.length===2 && full.output.remaining.length===0,'Everything saved is reported as saved');
 window.failRead=true;let code=null;try{await applyAppCommand({action:'read_results',arguments:{}});}catch(e){code=e.code;}
 assert(code==='result_read_failed','A failed read is an error, not a saved state');window.failRead=false;
 S.analysisRequest=null;const none=await applyAppCommand({action:'read_results',arguments:{}});
 assert(none.output.state==='no_request' && none.output.scope.project==='First','Without a prepared request nothing is claimed');
""")

    def test_a_service_connected_only_on_its_main_version_is_awaited_on_that_version(self):
        self.check(ANALYZED+r"""
 $('guideNext').click();$('guideCopySetup').click();await wait();
 const repositories=[{id:'web',name:'Lumen Web',path:'/fictional/web',refs:{dev:null,main:'HEAD'},layout:{},api_targets:[]}];
 const bundle=fakeBundle('Lumen');bundle.project.repositories=repositories.map(r=>({...r,collected:true,commits:{main:'bbbbbbbb2222'}}));
 bundle.main=fakeMap('Lumen','bbbbbbbb2222',true);bundle.dev=null;window.configuredBundle=bundle;
 await applyAppCommand({action:'configure',arguments:{project:'Lumen',configuration:{repositories,shared_data:[]}}});await wait(60);
 assert(S.branch==='main' && G.step===3,'The guide follows the service to the version it was collected on');
 window.mutateBundle=b=>{for(const r of b.project.repositories)r.results={dev:{},main:{analysis:saved({...r,commits:{dev:r.commits.main}},S.lang),system:saved({...r,commits:{dev:r.commits.main}},S.lang)}};};
 const n=reads();window.dispatchEvent(new Event('focus'));for(let i=0;i<60 && !$('guideFinish');i++)await wait();
 assert(reads()>n && $('guideFinish'),'Saved results on that version are read without a manual click');
 S.branch='dev';n2=reads();window.dispatchEvent(new Event('focus'));await wait(60);
""".replace("S.branch='dev';n2=reads();window.dispatchEvent(new Event('focus'));await wait(60);\n","")+r"""
 closeGuide();
""",query='&empty=1')

    def test_a_finished_plan_is_not_reused_by_a_reopened_guide(self):
        self.check(ANALYZED+r"""
 analyzeAll();await openAnalysisStep();awaitRequest();await finishReading();
 assert($('guideFinish'),'Finished after reading');
 closeGuide();openGuide();G.step=3;renderGuide();
 assert(!$('guideFinish') && $('guideReadNow'),'A reopened guide must read the plan again before it can finish');
 window.failRead=true;awaitRequest();await finishReading();window.failRead=false;closeGuide();openGuide();G.step=3;renderGuide();
 assert(!$('guide').querySelector('[role=alert]'),'A new session does not inherit an old read failure');
""")

    def test_a_poll_runs_only_the_guarded_read(self):
        source=(ROOT/'ui/onboarding.js').read_text()
        self.assertEqual(source.count('setInterval('),1)
        self.assertIn('setInterval(guideReadSaved',source)
        self.assertNotIn('doRefresh',source[source.index('async function guideReadSaved'):source.index('function guideSync')])

    def test_blocked_storage_keeps_the_skip_for_the_session(self):
        self.check(r"""
 for(const store of ['localStorage','sessionStorage'])Object.defineProperty(window,store,{get(){throw Error('blocked');}});
 guideMemory=null;assert(guideMarker()===null,'Nothing stored yet');
 $('guideSkip').click();assert(!$('guide').open && guideMarker()==='skipped','Skip still holds without storage');
""",query='&empty=1')

    def test_finishing_reveals_the_analysis_and_agent_navigation_is_not_hidden_by_the_guide(self):
        self.check(ANALYZED+r"""
 analyzeAll();await openAnalysisStep();await finishReading();$('guideFinish').click();await wait();
 assert(!$('guide').open && S.view==='sys' && $('map').innerText.includes('First Worker'),'Opening the result shows the analyzed structure');
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

    def test_unified_result_check_keeps_target_and_original_pins(self):
        self.check(r'''
 window.planResult={tasks:[{repository:'web',task:'groups',commit:'old',configuration:'layout-a'}],requirements:[],pins:{web:{commit:'old',configuration:'layout-a'}},blocked:[],handoff:'one request'};
 await requestAgentAction('analysis_plan',{repository:'web'});
 window.planResult={tasks:[],blocked:[],pins:{web:{commit:'new',configuration:'layout-a'}},up_to_date:true};
 await checkAnalysisResults();
 assert(S.analysisRequest.state==='stale','A newer code result is not the requested result');
 assert(calls.filter(c=>c.command==='analysis_plan').at(-1).args.repository==='web','Check only the originally requested code');
 window.planResult.pins.web.commit='old';await checkAnalysisResults();
 assert(S.analysisRequest.state==='saved','Original pinned results can complete');
 const request=S.analysisRequest;window.planResult.pins.web.commit='new';window.holdPlan=new Promise(r=>window.releasePlan=r);
 const checking=checkAnalysisResults();await wait();setLanguage(S.lang==='ko'?'en':'ko');
 window.releasePlan();await checking;
 assert(request.state==='saved' && !activeAnalysis(),'A language change does not apply the old request and does not leave it checking: '+request.state);
''')

    def test_failed_collection_does_not_prepare_or_overwrite_failure(self):
        self.check(r'''
 window.refreshOutput='web: FAILED: unavailable';
 await doRefresh();await wait();
 assert(!calls.some(c=>c.command==='analysis_plan'),'Failed collection does not prepare an analysis');
 assert($('status').textContent.includes(tr('최신 지도를 가져오지 못했습니다. 오류 내용을 확인하세요.')),'Keep the collection failure visible');
''')

    def test_all_code_is_explained_and_one_code_keeps_its_configured_server_links(self):
        self.check(r'''
 const note=()=>$('repository-bar').querySelector('[data-code-scope]')?.textContent || '';
 assert(note()===tr('모든 코드: 연결한 코드 전체를 한 지도로 봅니다.'),'All code is explained beside the selector: '+note());
 $('repository').value='web';$('repository').dispatchEvent(new Event('change'));for(let i=0;i<50 && S.repository!=='web';i++)await wait();await wait();
 assert(note()===tr('이 코드의 화면만 봅니다. 지정한 서버 연결은 그대로 이어집니다.'),'One code says what stays linked: '+note());
 window.mutateBundle=b=>{b.project.repositories=b.project.repositories.slice(0,1);};await loadProject('Second',false,'');await wait();
 assert(!$('repository-bar').querySelector('[data-code-scope]'),'One connected code needs no scope note');
''')

    def test_manual_connection_leads_into_the_analysis_request_and_later_refreshes_stay_quiet(self):
        self.check(r'''
 window.planResult={tasks:[{repository:'web',task:'analysis',commit:'aaaaaaaa1111'}],blocked:[],requirements:[{repository:'web',task:'analysis',before:null,commit:'aaaaaaaa1111'}],handoff:'First request',up_to_date:false};
 // Outside the first-run guide (which has its own First analysis step), a GitHub address is collected on save and the prepared request opens by itself.
 if($('guide').open)closeGuide('skipped');editProject(true);$('projectName').value='Lumen';document.querySelector('[data-field="path"]').value='https://github.com/example/web';
 window.configuredBundle=null;$('saveProject').click();for(let i=0;i<80 && S.agentPurpose!=='analysis';i++)await wait();await wait();
 assert(S.project==='Lumen' && window.calls.some(c=>c.command==='refresh'),'GitHub code was collected on save');
 assert(S.agentPurpose==='analysis' && S.analysisRequest?.handoff==='First request' && pane().includes(tr('1. 요청 복사')),'The analysis request is shown right after connecting');
 assert(window.copied===undefined,'Nothing is copied or run by itself');
 // A local folder is not collected on save: the status names the next step, and that first refresh opens the request.
 S.agentPrompt=null;S.agentPurpose=null;render();
 window.mutateBundle=b=>{if(b.project.name==='Local'){b.project.repositories.forEach(r=>{r.collected=false;r.commits={};});b.dev=null;b.main=null;}};
 editProject(true);$('projectName').value='Local';document.querySelector('[data-field="path"]').value='/fictional/local';
 $('saveProject').click();for(let i=0;i<80 && S.project!=='Local';i++)await wait();await wait();
 assert($('status').textContent===tr('연결을 저장했습니다. 새로고침으로 첫 지도를 가져오면 AI에게 보낼 분석 요청이 준비됩니다.'),'Status says how the first map leads to the request: '+$('status').textContent);
 assert(S.agentPurpose!=='analysis','No request before the first map');
 // The plan now lists the first tasks of the code that was just added, under the id the editor gave it.
 window.planResult={...window.planResult,tasks:[{repository:S.openRequestFor.ids[0],task:'analysis',commit:'aaaaaaaa1111'}]};
 window.mutateBundle=null;await doRefresh();await wait();
 assert(S.agentPurpose==='analysis' && pane().includes(tr('1. 요청 복사')),'The first refresh of a new connection opens the request');
 S.agentPrompt=null;S.agentPurpose=null;render();await doRefresh();await wait();
 assert(S.agentPurpose!=='analysis' && S.analysisRequest?.handoff==='First request','Later refreshes prepare quietly as before');
''',query='&empty=1')

    def test_added_code_opens_the_request_only_when_its_own_first_tasks_appear(self):
        self.check(r'''
 if($('guide').open)closeGuide('skipped');
 // First already has web and api collected; a third local folder is added and is not collected on save.
 const extra={id:'extra',name:'Extra worker',refs:{dev:'HEAD',main:null},collected:false,commits:{},api_targets:[],layout:{}};
 window.mutateBundle=b=>{if(b.project.name==='First')b.project.repositories.push(structuredClone(extra));};
 editProject(false);$('addRepository').click();[...document.querySelectorAll('[data-field="path"]')].at(-1).value='/fictional/extra';
 window.planResult={tasks:[],blocked:[],requirements:[],handoff:'',up_to_date:true};
 $('saveProject').click();for(let i=0;i<80 && $('project-dialog').open;i++)await wait();await wait();
 assert(S.projectInfo.repositories.some(r=>r.id==='extra') && S.openRequestFor?.ids?.includes('extra'),'The added code is remembered: '+JSON.stringify(S.openRequestFor));
 assert($('status').textContent===tr('연결을 저장했습니다. 새로고침으로 첫 지도를 가져오면 AI에게 보낼 분석 요청이 준비됩니다.'),'The next step is named: '+$('status').textContent);
 // Refreshing only the already collected web code (up to date) must not use up the handoff.
 $('repository').value='web';$('repository').dispatchEvent(new Event('change'));for(let i=0;i<50 && S.repository!=='web';i++)await wait();await wait();
 S.agentPrompt=null;S.agentPurpose=null;render();await doRefresh();await wait();
 assert(S.agentPurpose!=='analysis' && S.openRequestFor?.ids?.includes('extra'),'An unrelated up-to-date refresh keeps the marker');
 // The refresh that collects the new code lists its first tasks: the request opens once.
 extra.collected=true;extra.commits={dev:'ffffffff6666'};
 window.planResult={tasks:[{repository:'extra',task:'analysis',commit:'ffffffff6666'}],blocked:[],requirements:[{repository:'extra',task:'analysis',before:null,commit:'ffffffff6666'}],handoff:'Extra request',up_to_date:false};
 $('repository').value='';$('repository').dispatchEvent(new Event('change'));for(let i=0;i<50 && S.repository!=='';i++)await wait();await wait();
 await doRefresh();await wait();
 assert(S.agentPurpose==='analysis' && S.analysisRequest?.handoff==='Extra request' && pane().includes(tr('1. 요청 복사')),'The new code\'s first tasks open the request');
 assert(!S.openRequestFor,'The marker is consumed once');
 S.agentPrompt=null;S.agentPurpose=null;render();await doRefresh();await wait();
 assert(S.agentPurpose!=='analysis','The next refresh stays quiet');
''')

    def test_stale_button_names_are_not_shown(self):
        self.check(r'''
 window.mutateBundle=b=>{b.project.repositories=[];b.dev=null;b.main=null;};await loadProject('Second',false,'');await wait();
 await doRefresh();assert($('status').textContent===tr('연결된 코드가 없습니다. 코드 추가·수정에서 GitHub 주소나 코드 폴더를 추가하세요.'),'No-code status names the real button: '+$('status').textContent);
 window.mutateBundle=null;await loadProject('Second',false,'');await wait();
 assert($('branch').querySelector('[data-b=main]').title===tr('비교할 버전을 코드 추가·수정에서 지정할 수 있습니다.'),'Version fallback names the real button: '+$('branch').querySelector('[data-b=main]').title);
 const table=[...Object.keys(UI_EN),...Object.values(UI_EN)].join('\n');
 assert(!/코드 연결에서|AI에게 알아보기에서|in Connect code|in Ask your AI/.test(table),'No stale button references remain in the dictionary');
''')

    def test_entry_actions_say_their_purpose_and_the_service_name_defaults_to_the_first_code(self):
        self.check(r'''
 if($('guide').open)closeGuide('skipped');
 // One first entry: explore my code. Both ways are explained, and nothing runs AI by itself.
 assert(main().includes(tr('내 코드 살펴보기')) && main().includes(tr('어떤 코드를 살펴볼까요?')),'The empty workspace asks which code to explore: '+main());
 assert(main().includes(tr('앱이 AI를 직접 실행하지는 않습니다.')),'No automatic AI execution is stated');
 assert($('startWithAI').textContent===tr('작업하던 AI에게 맡기기') && $('startProject').textContent===tr('코드 위치를 직접 입력'),'The two ways name what each one does');
 assert($('newProject').title===tr('다른 서비스 추가'),'The header plus adds another service');
 $('startProject').click();const d=$('project-dialog');assert(d.open && d.querySelector('h2').textContent===tr('살펴볼 코드 추가'),'The editor is about code to explore');
 assert(d.textContent.includes(tr('서비스 이름은 함께 살펴볼 코드를 묶는 이름입니다.')) && d.textContent.includes(tr('비워 두면 첫 코드의 이름을 씁니다.')),'Service name is explained as a grouping name with a default');
 assert($('saveProject').textContent===tr('저장'),'Saving is called saving');
 document.querySelector('[data-field="path"]').value='/fictional/lumen-web';
 $('saveProject').click();for(let i=0;i<80 && !S.project;i++)await wait();await wait();
 assert(S.project==='lumen-web' && window.savedProjects.includes('lumen-web'),'An empty service name falls back to the first code name: '+S.project);
 assert($('manageRepositories').textContent===tr('코드 추가·수정'),'The code bar button says add or edit code');
 $('manageRepositories').click();assert(d.querySelector('h2').textContent===tr('살펴보는 코드') && !d.textContent.includes(tr('비워 두면 첫 코드의 이름을 씁니다.')),'Editing names the explored code without the default hint');d.close();
 assert($('analyzeMap').textContent.startsWith(tr('AI로 자세한 지도 만들기')),'The AI button says what the AI makes: '+$('analyzeMap').textContent);
 $('analyzeMap').click();assert(pane().includes(tr('AI로 자세한 지도 만들기')) && pane().includes(tr('AI에게 보낼 요청만 만듭니다. 앱에서 바로 분석하지 않습니다.')),'The panel keeps the explicit handoff');
''',query='&empty=1')

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
 S.view='sys';S.system=null;S.branchDetails=null;render();$('remakeSys').click();await new Promise(r=>setTimeout(r,20));
 assert(!$('status').textContent && calls.some(c=>c.command==='analysis_plan' && c.args.repository===''),'Contextual buttons request all connected code without forcing a code choice');
 $('analysisTarget').value='*';$('analysisTarget').dispatchEvent(new Event('change'));
 document.querySelector('[data-analysis-task="make_system"]').click();await new Promise(r=>setTimeout(r,20));
 assert(['web','api'].every(id=>calls.some(c=>c.command==='make_system' && c.args.repository===id)),'Explicit re-analysis still prepares one request per code');
''')

    def test_every_request_button_prepares_one_unified_request(self):
        self.check(r'''
 const blocked=[{repository:'api',task:'analysis',reason:'Refresh after configuration changes first'}];
 const plan={tasks:[{repository:'web',task:'analysis',commit:'aaaaaaaa1111'},{repository:'web',task:'groups',commit:'aaaaaaaa1111'},{repository:'',task:'briefing',commit:'h'}],blocked,
  requirements:[{repository:'web',task:'analysis',before:null,commit:'aaaaaaaa1111'},{repository:'web',task:'groups',before:null,commit:'aaaaaaaa1111'},{repository:'',task:'briefing',before:null,commit:'h'}],handoff:'Unified handoff',up_to_date:false};
 window.planResult=plan;
 S.view='feat';render();$('regroup').click();await wait();
 assert(calls.filter(c=>c.command==='analysis_plan').length===1 && !calls.some(c=>c.command==='suggest_groups'),'Grouping uses the unified request');
 assert(pane().includes(tr('1. 요청 복사')) && S.analysisRequest.handoff==='Unified handoff','One handoff is shown');
 assert(pane().includes(tr('요청할 분석: ')) && pane().includes(tr('요청하지 못한 분석: ')) && pane().includes(tr('설정이 바뀌었거나 코드가 바뀌었습니다. 먼저 새로고침하세요.')),'Queued, blocked and refresh-needed work is listed');
 assert($('insp').textContent.includes('Refresh after configuration changes first'),'The raw reason stays available');
 await $('cpAgent').onclick();assert(window.copied==='Unified handoff','Only an explicit copy writes the clipboard');
 window.planResult={tasks:[{repository:'web',task:'steps',target:'@routes:["app/items.py::save_item"]',commit:'aaaaaaaa1111'}],blocked,requirements:[],handoff:'x',up_to_date:false};
 await $('checkAnalysisResults').onclick();
 assert(S.analysisRequest.state==='partial' && pane().includes(tr('남은 분석: ')) && pane().includes(tr('동작 과정')),'Targets that appeared after the map was saved are still needed');
 window.planResult={tasks:[],blocked,requirements:[],handoff:'',up_to_date:false};
 await $('checkAnalysisResults').onclick();
 assert(S.analysisRequest.state==='partial' && S.analysisRequest.codes.waiting.includes('api') && pane().includes(tr('결과를 기다리는 코드: ')),'A blocked code keeps the request partial');
 window.planResult={tasks:[],blocked:[],requirements:[],handoff:'',up_to_date:true};
 await $('checkAnalysisResults').onclick();
 assert(S.analysisRequest.state==='saved','Only nothing left completes it');
 assert(!calls.some(c=>c.command==='refresh'),'Checking results never refreshes');
 S.view='sys';render();$('remakeSys').click();await wait();
 assert(pane().includes(tr('모든 분석 결과가 최신입니다. 새로 요청할 것이 없습니다.')) && !$('cpAgent'),'Nothing to do reports up to date without a copy step');
 $('analysisTarget').value='*';$('analysisTarget').dispatchEvent(new Event('change'));
 document.querySelector('[data-analysis-task="analysis_plan"]').click();await wait();
 assert(calls.filter(c=>c.command==='analysis_plan').every(c=>c.args.repository!=='*'),'The advanced selector never sends a wildcard to the plan');
''')

    def test_action_steps_use_the_unified_request_and_unknown_steps_settle(self):
        self.check(r'''
 window.planResult={tasks:[{repository:'api',task:'steps',target:'@routes:["app/items.py::save_item"]',commit:'cccccccc3333'}],blocked:[],requirements:[{repository:'api',task:'steps',before:null,commit:'cccccccc3333'}],handoff:'Steps handoff',up_to_date:false};
 S.view='screen';S.sel='web::/items';render();
 const mk=$('mk') || document.querySelector('[data-mk]');assert(mk,'A steps request is offered while steps are missing');
 mk.click();await wait();
 assert(calls.some(c=>c.command==='analysis_plan') && !calls.some(c=>c.command==='make_steps'),'Steps use the unified request');
 S.agentPrompt=null;S.agentPurpose=null;S.maps.dev.backend_routes[0].flow={steps:[],unknown:'Fictional handler is generated'};render();
 assert(!$('mk'),'An explicit unknown is a finished analysis');
 document.querySelector('[data-req]').click();await wait();
 assert(document.body.textContent.includes('Fictional handler is generated') && !document.querySelector('[data-mk]'),'The reason is shown without another request button: '+S.open);
''')

    def test_refresh_prepares_the_request_quietly_and_never_applies_an_old_project(self):
        self.check(r'''
 window.planResult={tasks:[{repository:'web',task:'analysis',commit:'aaaaaaaa1111'}],blocked:[],requirements:[{repository:'web',task:'analysis',before:null,commit:'aaaaaaaa1111'}],handoff:'After refresh',up_to_date:false};
 S.agentPrompt=null;render();await doRefresh();await wait();
 assert(calls.filter(c=>c.command==='analysis_plan').length===1 && S.analysisRequest?.handoff==='After refresh','Refresh prepares the same unified request once');
 assert(window.copied===undefined && S.agentPurpose!=='analysis','No clipboard write and no panel opened');
 assert($('analyzeMap').innerText.includes(tr('결과 확인 대기')),'The prepared request is visible on the button');
 S.analysisRequest={...S.analysisRequest,copied:true,scope:{...S.analysisRequest.scope,project:'Second'},handoff:'Other project'};
 let before=calls.filter(c=>c.command==='analysis_plan').length;
 await applyAppCommand({id:'app-refresh-1',action:'refresh',arguments:{}});await wait();
 assert(calls.filter(c=>c.command==='analysis_plan').length===before+1 && S.analysisRequest.handoff==='After refresh','App-control refresh prepares it too; another project copied request does not block it');
 window.failPlan=true;S.analysisRequest=null;await doRefresh();await wait();
 assert($('status').textContent===tr('새로고침은 끝났지만 분석 요청을 준비하지 못했습니다.') && !S.githubFailure,'A preparation error is not a refresh failure');
 window.failPlan=false;S.analysisRequest=null;
 let release;window.holdPlan=new Promise(r=>release=r);
 $('analyzeMap').click();document.querySelector('[data-analysis-task="analysis_plan"]').click();await wait();
 $('project').value='Second';$('project').dispatchEvent(new Event('change'));await wait(60);
 release();window.holdPlan=null;await wait();
 assert(S.project==='Second' && !S.analysisRequest,'A request prepared for the previous project is discarded');
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
 const start=$('startProject');assert(start && $('startWithAI') && main().includes(tr('코드 위치를 직접 입력')),'Empty app offers AI handoff and a manual alternative');
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
 assert($('registeredConnectionState').getAttribute('role')==='status' && !$('insp').querySelector('[role=alert]'),'Matching registration is a status, not a warning');
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

# Repeated analysis requests: returning to the app reads the copied request's saved results by itself. Reads are faked; no AI runs.
AUTO=r"""
 const reads=()=>window.calls.filter(c=>c.command==='read_project').length,plans=()=>window.calls.filter(c=>c.command==='analysis_plan').length;
 const back=async(ms=80)=>{window.dispatchEvent(new Event('focus'));await wait(ms);};
 const pins={web:{commit:'aaaaaaaa1111',configuration:'c'}},tasks=[{repository:'web',task:'analysis',before:null,commit:'aaaaaaaa1111'}];
 const pending=()=>{window.planResult={tasks,blocked:[],requirements:tasks,pins,up_to_date:false,handoff:'plan'};};
 const done=()=>{window.planResult={tasks:[],blocked:[],requirements:[],pins,up_to_date:true};};
 const copied=async()=>{pending();await requestAgentAction('analysis_plan');await $('cpAgent').onclick();assert(S.analysisRequest.copied && S.analysisRequest.state==='prepared','A copied request is pending');};
 RESULT_RETRY_MS=30;
"""
class AutoRead(unittest.TestCase):
    def setUp(self):
        if not CHROME.exists():self.skipTest('Chrome is required')
    def check(self,checks):
        for lang in ('ko','en'):
            with self.subTest(lang=lang):
                ok,error=page(AUTO+checks,lang);self.assertTrue(ok,error)

    def test_returning_to_the_app_reads_the_copied_request_without_clicking(self):
        self.check(r"""
 await copied();const n=reads();done();
 await back();
 assert(S.analysisRequest.state==='saved' && reads()===n+1,'Focus read the saved result: '+S.analysisRequest.state);
 assert(pane().includes(tr('새 결과가 저장된 것을 확인했습니다.')) && $('viewAnalysisResults'),'The panel shows the saved state and the result button');
 assert($('checkAnalysisResults'),'The manual check stays as a recovery path');
 await back();assert(reads()===n+1,'A saved request is not read again');
 document.dispatchEvent(new Event('visibilitychange'));await wait(60);assert(reads()===n+1,'Nor on visibility');
 assert(!window.calls.some(c=>['refresh','analysis_request','make_system','suggest_groups','briefing_request'].includes(c.command)),'Reading never collects or analyzes');
""")

    def test_manual_automatic_and_control_reads_of_one_request_do_not_overlap(self):
        self.check(r"""
 await copied();const n=reads();done();
 window.holdRead={repository:S.repository,promise:new Promise(r=>window.releaseRead=r)};
 const manual=checkAnalysisResults();await wait();
 window.dispatchEvent(new Event('focus'));document.dispatchEvent(new Event('visibilitychange'));
 const control=applyAppCommand({action:'read_results',arguments:{}});await wait(40);
 assert(reads()===n+1 && S.analysisRequest.state==='checking','One read serves every caller while it runs');
 window.releaseRead();window.holdRead=null;await manual;const report=await control;
 assert(S.analysisRequest.state==='saved' && report.output.state==='saved' && reads()===n+1,'All callers see the one finished read');
""")

    def test_nothing_is_read_without_a_copied_pending_request_in_the_same_context(self):
        self.check(r"""
 pending();await requestAgentAction('analysis_plan');let n=reads();
 await back();assert(reads()===n,'A request that was not copied is not read');
 await $('cpAgent').onclick();done();
 setLanguage(S.lang==='ko'?'en':'ko');await back();assert(reads()===n,'Another language is not this request');setLanguage(S.lang==='ko'?'en':'ko');
 S.branch='main';await back();assert(reads()===n,'Another version is not this request');S.branch='dev';
 S.analysisRequest.state='stale';await back();assert(reads()===n,'A stale request is never read');
 S.analysisRequest.state='up_to_date';await back();assert(reads()===n,'Nothing to wait for');
 S.analysisRequest.state='blocked';await back();assert(reads()===n,'A blocked request waits for a new one');
 S.analysisRequest=null;await back();assert(reads()===n,'No request, no read');
""")

    def test_reading_on_return_keeps_the_view_the_user_moved_to(self):
        self.check(r"""
 await copied();done();
 document.querySelector('#view [data-v="sys"]').click();assert(S.view==='sys' && !$('checkAnalysisResults'),'The user browsed elsewhere');
 await back();
 assert(S.analysisRequest.state==='saved','The result was still read');
 assert(S.view==='sys' && !$('checkAnalysisResults') && !pane().includes(tr('1. 요청 복사')),'The right panel was not taken over');
 assert($('analyzeMap').innerText.includes(tr('결과 저장됨')),'The header reports the saved result');
""")

    def test_a_late_read_after_a_context_change_is_dropped_and_does_not_leave_the_request_checking(self):
        self.check(r"""
 await copied();const request=S.analysisRequest;done();
 window.holdPlan=new Promise(r=>window.releasePlan=r);
 await back(30);assert(request.state==='checking','The second plan read is in flight');
 const other=S.lang==='ko'?'en':'ko';setLanguage(other);window.releasePlan();window.holdPlan=null;await wait(60);
 assert(request.state!=='saved' && request.state!=='checking','A read that outlived its context applies nothing and does not stay checking: '+request.state);
 setLanguage(other==='ko'?'en':'ko');const n=reads();
 await back();assert(S.analysisRequest===request && request.state==='saved' && reads()===n+1,'Back in its context the request can be read again');
""")

    def test_errors_partial_results_and_changed_code_keep_their_state_and_stop_retrying(self):
        self.check(r"""
 await copied();done();window.failRead=true;
 await back();const n=reads();
 assert(S.analysisRequest.state==='error' && pane().includes(tr('결과를 읽지 못했습니다. 오류 내용을 확인하세요.')) && $('checkAnalysisResults') && !$('checkAnalysisResults').disabled,'A failed read shows the error with the manual retry');
 await wait(200);assert(reads()===n,'No timed retry after an error');
 window.failRead=false;pending();
 await back();const m=reads();
 assert(S.analysisRequest.state==='missing','The AI has not saved yet');
 await wait(300);assert(reads()>m && reads()<=m+RESULT_RETRIES,'A few timed retries while waiting, then they stop: '+(reads()-m));
 const after=reads();await wait(150);assert(reads()===after,'Retries are bounded');
 done();await back();assert(S.analysisRequest.state==='saved','The next return completes it');
 await copied();window.planResult={tasks:[],blocked:[],requirements:[],pins:{web:{commit:'newer',configuration:'c'}},up_to_date:true};
 await back();assert(S.analysisRequest.state==='stale','Changed code is stale, never saved');
 const s=reads();await wait(150);assert(reads()===s,'A stale request is not retried');
""")

    def test_the_general_reader_stays_out_of_the_first_run_guide(self):
        self.check(r"""
 await copied();done();
 $('guideOpen').click();assert($('guide').open,'The guide is open');const n=reads();
 await back();await wait(100);
 assert(reads()===n && S.analysisRequest.state==='prepared','While the guide is open only its own reader may read');
 closeGuide();await back();assert(S.analysisRequest.state==='saved','After the guide closes the request is read');
""")

    def test_a_control_read_reports_only_the_request_of_the_current_language(self):
        self.check(r"""
 await copied();done();await back();assert(S.analysisRequest.state==='saved','Saved in the first language');
 const other=S.lang==='ko'?'en':'ko';setLanguage(other);
 const report=await applyAppCommand({action:'read_results',arguments:{}});
 assert(report.output.state==='no_request' && report.output.scope.lang===other,'A saved request of another language is not reported as current: '+JSON.stringify(report.output));
 setLanguage(other==='ko'?'en':'ko');await copied();window.holdPlan=new Promise(r=>window.releasePlan=r);
 const control=applyAppCommand({action:'read_results',arguments:{}});await wait(30);
 setLanguage(other);window.releasePlan();window.holdPlan=null;
 let code=null;try{await control;}catch(e){code=e.code;}
 assert(code==='context_changed' && S.analysisRequest.state==='prepared','A language switch during the read is a context change, not a saved state: '+code);
 setLanguage(other==='ko'?'en':'ko');done();await back();assert(S.analysisRequest.state==='saved','Back in its language the request is still readable');
""")

    def test_a_control_read_that_outlives_a_project_reload_is_a_context_change(self):
        self.check(r"""
 await copied();done();window.holdPlan=new Promise(r=>window.releasePlan=r);
 const control=applyAppCommand({action:'read_results',arguments:{}});await wait(30);
 await loadProject('Second');await loadProject('First');
 window.releasePlan();window.holdPlan=null;
 let code=null;try{await control;}catch(e){code=e.code;}
 assert(code==='context_changed' && S.analysisRequest.state!=='saved','A read started before reloading does not confirm a saved state: '+code+' '+S.analysisRequest.state);
""")

    def test_a_failed_automatic_read_updates_the_header_without_taking_over_the_view(self):
        self.check(r"""
 await copied();done();
 document.querySelector('#view [data-v="sys"]').click();assert(S.view==='sys' && S.agentPrompt==null,'The user browsed elsewhere');
 window.failRead=true;await back();const n=reads();
 assert(S.analysisRequest.state==='error','The read failed');
 assert($('analyzeMap').innerText.includes(tr('결과 읽기 실패')),'The header reports the failed read: '+$('analyzeMap').innerText);
 assert(S.view==='sys' && S.agentPrompt==null && !$('checkAnalysisResults'),'The view and the right panel are kept');
 await wait(200);assert(reads()===n,'No retry storm after the error');
""")


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
 assert(text.includes(tr('확인이 필요한 내용')+' 2'),'Unknown fields have a visible count');
 const more=$('map').querySelector('.change-details');
 assert(more && more.textContent.includes('Known before') && more.textContent.includes('Unknown remaining') && more.textContent.includes('Fictional term'),'Details, unknown fields and terms retained together');
 assert(!$('map').querySelector('details details'),'Details and evidence never require nested disclosures');
 assert(text.includes(tr('설명 구간')) && text.includes(when('2026-09-01T00:00:00Z')) && text.includes(when('2026-09-20T00:00:00Z')),'Explanation period is visible: '+text);
 assert(text.includes(tr('새로고침 기록 구간')) && text.includes(when('2026-09-24T00:00:00Z')),'Selected refresh history period is shown separately');
 assert(!text.includes('aaaa1111'),'Commit provenance stays folded');
 S.changes.last_results=[{repository:'web',at:'2026-10-27T01:47:00Z',since:'2026-10-26T00:00:00Z',changed:false,scope:'basic'}];render();assert(outside($('map')).includes(when('2026-10-27T01:47:00Z')) && outside($('map')).includes(tr('선택한 기준 이후 달라진 것 없음')),'Latest no-change refresh remains visible beside historical records');
''')

    def test_connection_repair_copy_leads_until_copied_then_the_check_and_details_hold_tools(self):
        self.check(r'''
 S.agentPurpose='connection';S.agentPrompt='connection';
 S.connectionDiagnostic={feature:'detail',challenge:'x',fresh_server:{state:'ready'},registration:{state:'not_inspected'},connection:{state:'not_verified'},handoff:'repair'};
 renderConnectionDiagnostic();
 assert($('liveConnectionState').textContent===tr('AI 연결을 아직 확인하지 않았습니다.'),'Unchecked is not reported as disconnected');
 assert($('copyConnectionRequest').classList.contains('primary') && !$('checkCurrentConnection').classList.contains('primary'),'Copying the repair request comes first');
 assert(!$('connectionFeature').closest('details') && $('connectionFeature').closest('.section-heading'),'Scope choice stays alongside the diagnostic action');
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
 assert(shown() && $('baselineNotice').textContent===tr('새로고침마다 시작점 이동') && $('baselineNotice').title===notice,'Moving baseline has a short visible label and full accessible title');
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
        # Connection repair still ends with the user pressing the app's own button.
        self.assertIn('‘연결됐는지 확인’',prompts);self.assertIn('Check the connection',prompts)
        # Saved analysis results are read when the user returns to the app; prompts no longer require a manual check.
        self.assertIn('앱으로 돌아가라고 안내하세요',prompts);self.assertIn('return to the app',prompts)
        for old in ('저장된 결과 확인','Check saved results','‘현재 연결 확인’','Check current connection','‘결과 확인’을 누르도록','select Check results'):
            self.assertNotIn(old,prompts)

# Fictional feature fixture: two AI groups (Items with two screens, Orders with one) and work linked by
# the collected status shapes (repository-tagged PRs, branches, worktrees, issues). Two PRs share #42 in different repositories.
FEATURE=r'''
 const items=['web::/items','web::/items/new'];
 const featureBundle=b=>{
  const add=(m,path,heading)=>{const s=structuredClone(m.screens[0]);s.path=path;s.heading=heading;s.source_path=path.split('::')[1];m.screens.push(s);};
  add(b.dev,'web::/orders','First orders');
  b.dev.backend_routes.push({...structuredClone(b.dev.backend_routes[0]),file:'api/app/orders.py',function:'list_orders',method:'GET',path:'/orders',line:5,tables:['api::orders'],tests:[]});
  const groups={groups:[{name:'Items',description:'Item screens',screens:items},{name:'Orders',description:'Order screens',screens:['web::/orders']}],names:{},request_names:{}};
  for(const k of ['dev','main'])b.branch_details[k].groups=groups;b.groups=groups;
  const u='https://example.invalid/',t='2026-10-01T00:00:00Z';
  b.status={open_prs:[{number:42,title:'Item form',url:u+'web/42',repository:'web',screens:['web::/items'],files:['web/src/x.tsx'],updated_at:t,author:'a'},
    {number:42,title:'[API server] Item API',url:u+'api/42',repository:'api',screens:['web::/items/new'],files:[],updated_at:t,author:'b'},
    {number:7,title:'Shared form',url:u+'web/7',repository:'web',screens:items,files:[],updated_at:t,author:'a'},
    {number:100,title:'Order fix',url:u+'web/100',repository:'web',screens:['web::/orders'],files:[],updated_at:t,author:'c'}],
   merged_prs:[{number:5,title:'Merged item',url:u+'web/5',repository:'web',screens:items,files:[],merged_at:t}],
   branches:[{name:'feature/items',repository:'web',ahead_of_dev:2,stale:false,has_open_pr:false,author:'b',age_days:1,screens:['web::/items/new'],files:[]}],
   worktrees:[{path:'/fictional/wt-items',repository:'web',branch:'feature/items',uncommitted:['a'],screens:items}],
   issues:[{number:9,title:'Item bug',url:u+'web/issues/9',repository:'web',via:'pr',hits:['PR #7'],screens:['web::/items']}]};
 };
 window.mutateBundle=featureBundle;await loadProject('First');
 const featureCard=name=>[...document.querySelectorAll('[data-feat]')].find(c=>c.innerText.includes(name));
 const openFeature=async name=>{S.view='feat';render();featureCard(name).click();await wait();};
 const itemsId=()=>targetID('feature',[...items].sort());
 const hangul=text=>S.lang==='en' && /[가-힣]/.test(text);
'''

class FeatureContext(unittest.TestCase):
    """A chosen feature stays visible across the full screen map and the existing screen/action detail."""
    def setUp(self):
        if not CHROME.exists():self.skipTest('Chrome is required')
    def check(self,checks):
        for lang in ('ko','en'):
            with self.subTest(lang=lang):
                ok,error=page(FEATURE+checks,lang);self.assertTrue(ok,error)

    def test_full_map_stays_and_only_member_screens_are_highlighted_while_structure_is_unchanged(self):
        self.check(r'''
 S.view='sys';S.node=null;render();const sysBefore=$('map').innerHTML;
 await openFeature('Items');
 assert(S.feat===itemsId(),'Selection stores the stable feature ID, not an index: '+S.feat);
 assert(featureCard('Items').classList.contains('sel') && !featureCard('Orders').classList.contains('sel'),'Features graph marks the chosen feature');
 $('featMap').click();await wait();
 assert(S.view==='map' && !S.sel && S.feat===itemsId(),'Opening the map keeps the feature without picking a screen');
 const cards=[...$('map').querySelectorAll('.card[data-scr]')].map(c=>c.dataset.scr);
 for(const p of [...items,'web::/orders','!orphans','!unres','!issues'])assert(cards.includes(p),'Full map keeps '+p);
 assert(!$('map').querySelector('.card.dim'),'Nothing is filtered or dimmed');
 const featured=[...$('map').querySelectorAll('.col.featured')];
 assert(featured.length===1,'One highlighted feature column');
 assert(JSON.stringify([...featured[0].querySelectorAll('.card[data-scr]')].map(c=>c.dataset.scr).sort())===JSON.stringify([...items].sort()),'Highlighted column holds exactly the member screens');
 assert(featured[0].innerText.includes(tr('선택한 기능')),'The highlight is labelled');
 assert($('insp').innerText.includes('Items') && $('featClear'),'Inspector shows the feature overview with a clear path');
 assert(!hangul($('insp').innerText+featured[0].innerText),'English feature context: '+$('insp').innerText);
 assert(S.repository==='' && S.branch==='dev','No implicit code or version change');
 S.view='sys';render();assert($('map').innerHTML===sysBefore,'Structure diagram is unchanged by feature selection');
 assert(!window.calls.some(c=>['refresh','save_project','analysis_plan'].includes(c.command)),'Highlighting never refreshes, saves or prepares analysis');
''')

    def test_member_action_keeps_the_feature_context_with_back_switch_and_clear(self):
        self.check(r'''
 await openFeature('Items');
 const actions=$('insp').querySelectorAll('[data-goact]'),action=actions[0];
 assert(actions.length===1 && action.innerText.includes('Save') && items.includes(action.dataset.goact),'Overview lists each action once with a member screen');
 action.click();await wait();
 assert(S.view==='map' && S.sel===action.dataset.goact && S.open===action.dataset.key && S.feat===itemsId(),'Action opens in the screen map with the feature kept');
 const strip=()=>$('insp').querySelector('.feature-context');
 assert(strip() && strip()===$('insp').firstElementChild && strip().innerText.includes('Items') && strip().innerText.includes(tr('이 기능에 속한 화면입니다.')),'Compact member context above the detail');
 assert($('insp').querySelector('.detail') && $('insp').querySelector('[data-copy]') && $('copyS'),'Existing action detail, copy and code links stay reachable');
 assert($('map').querySelector('.col.featured .card.sel[data-scr="'+action.dataset.goact+'"]'),'Selected member card sits inside the highlight');
 assert(!hangul($('insp').innerText),'English strip and detail');
 $('featBack').click();await wait();
 assert(!S.sel && !S.open && S.view==='map' && $('insp').querySelector('[data-goact]') && $('map').querySelector('.col.featured'),'Back returns to the feature overview on the full map');
 $('map').querySelector('[data-scr="web::/orders"]').click();await wait();
 assert(S.sel==='web::/orders' && strip().innerText.includes(tr('선택한 기능 밖의 화면입니다.')) && !strip().innerText.includes(tr('이 기능에 속한 화면입니다.')),'An outside screen is never called a member');
 assert(!$('map').querySelector('.col.featured [data-scr="web::/orders"]'),'Outside card stays outside the highlight');
 $('featSwitch').click();await wait();
 assert(S.feat===targetID('feature',['web::/orders']) && $('map').querySelector('.col.featured [data-scr="web::/orders"]') && strip().innerText.includes(tr('이 기능에 속한 화면입니다.')),'Switch anchors the screen own feature');
 $('map').querySelector('[data-scr="!orphans"]').click();await wait();
 assert(strip().innerText.includes(tr('선택한 기능 밖의 화면입니다.')) && !$('featSwitch'),'Items outside every feature only offer back and clear');
 $('featClear').click();await wait();
 assert(S.feat===null && !$('map').querySelector('.col.featured') && !strip() && S.sel==='!orphans','Clear removes only the feature context');
''')

    def test_feature_work_is_the_deduplicated_union_of_member_screens_and_unknown_is_not_none(self):
        self.check(r'''
 await openFeature('Items');const text=$('insp').innerText,count=s=>text.split(s).length-1;
 assert(count('#7 ')===1,'A PR linked to two member screens is counted once: '+count('#7 '));
 assert(count('#42 ')===2,'The same number in two repositories stays distinct');
 assert(count('wt-items')===1 && text.includes('feature/items') && count('#5 ')===1 && count('#9 ')===1,'Branch, folder, merged PR and issue are shown once');
 assert(!text.includes('Order fix'),'Work of screens outside the feature is excluded');
 assert(text.includes(tr('이 기능과 이어진 작업 ')+'6'),'Heading counts open PRs, branches, folders and issues once');
 $('insp').querySelector('[data-goscr="web::/items"]').click();await wait();
 const screen=$('insp').innerText;assert(screen.split('#42 ').length-1===1 && screen.split('#7 ').length-1===1,'A member screen keeps its own work list');
 window.mutateBundle=b=>{featureBundle(b);b.status=null;};await loadProject('First',false,'');S.view='feat';render();
 assert(S.feat===itemsId() && $('insp').innerText.includes(tr('작업 정보를 아직 수집하지 않았습니다.')) && !$('insp').innerText.includes(tr('수집된 작업 중 이 기능의 화면과 이어진 것이 없습니다.')),'Uncollected work is not reported as none');
 window.mutateBundle=b=>{featureBundle(b);b.status.open_prs=b.status.open_prs.filter(p=>p.number===100);for(const k of ['merged_prs','branches','worktrees','issues'])b.status[k]=[];};await loadProject('First',false,'');render();
 assert($('insp').innerText.includes(tr('수집된 작업 중 이 기능의 화면과 이어진 것이 없습니다.')),'Collected but unlinked work says so');
''')

    def test_copy_holds_only_the_feature_context_and_screen_copy_is_unchanged(self):
        self.check(r'''
 await openFeature('Items');$('copyF').click();await wait();const c=window.copied;
 assert(c.includes(itemsId()),'Copy names the feature target ID: '+c);
 for(const p of items)assert(c.includes(p),'Copy lists member screen '+p);
 assert(c.includes('POST /items') && c.includes('api/app/items.py:3'),'Copy keeps the action and server code pointers');
 assert(c.split('#7 ').length-1===1 && c.includes('web#42') && c.includes('api#42'),'Linked work is deduplicated with its repository');
 assert(!c.includes('web::/orders') && !c.includes('Order fix') && !c.includes('First orders'),'No unrelated feature data');
 assert(c.includes(tr('기준: ')) && c.includes(tr('AI가 붙인 이름')),'Version and the AI-name indicator are kept');
 assert(!hangul(c),'English copy');
 $('insp').querySelector('[data-goscr="web::/items"]').click();await wait();$('copyS').click();await wait();
 assert(window.copied.startsWith(tr('화면: ')) && !window.copied.includes('feature:'),'Screen copy stays screen-only');
 assert(!window.calls.some(x=>['analysis_plan','analysis_request','suggest_groups','make_system'].includes(x.command)),'Copy never calls AI');
''')

    def test_app_control_selects_the_same_feature_and_reports_drilldown_honestly(self):
        self.check(r'''
 const feature=(await applyAppCommand({action:'targets',arguments:{}})).output.targets.find(t=>t.kind==='feature' && t.name==='Items');
 assert(feature && feature.id===itemsId(),'Feature target ID is the selection ID');
 await applyAppCommand({action:'select',arguments:{project:'First',repository:'',branch:'dev',target:feature.id,revision:(await controlState()).revision}});
 assert(S.view==='feat' && S.feat===feature.id && featureCard('Items').classList.contains('sel'),'Agent selection shows the same feature');
 assert(JSON.stringify((await controlState()).selection)===JSON.stringify([feature.id]),'State reports the feature');
 $('featMap').click();await wait();
 assert((await controlState()).selection[0]===feature.id,'Feature overview on the map still reports the feature');
 $('map').querySelector('[data-scr="web::/items"]').click();await wait();let st=await controlState();
 assert(st.selection[0]==='screen:web::/items' && st.feature_context?.id===feature.id && st.feature_context.member===true,'Drilldown reports the screen with the feature as context: '+JSON.stringify(st.feature_context));
 $('map').querySelector('[data-scr="web::/orders"]').click();await wait();st=await controlState();
 assert(st.selection[0]==='screen:web::/orders' && st.feature_context.member===false,'Outside screen is not reported as a member');
 await applyAppCommand({action:'clear',arguments:{}});st=await controlState();
 assert(S.feat===null && !st.feature_context && !st.selection.length,'Clear removes the feature context');
 S.q='Item screens';render();const hit=[...document.querySelectorAll('[data-search-result]')].find(b=>S._search[+b.dataset.searchResult].kind==='feature');
 hit.click();await wait();assert(S.view==='feat' && S.feat===feature.id,'Search opens the same feature');
''')

    def test_context_is_revalidated_by_identity_and_cleared_on_scope_change(self):
        self.check(r'''
 await openFeature('Items');const id=S.feat,lang=S.lang;
 setLanguage(lang==='ko'?'en':'ko');assert(S.feat===id && featureCard('Items').classList.contains('sel'),'Language change keeps the same feature');setLanguage(lang);
 await loadProject('First',false,'');assert(S.feat===id,'Reloading the same service keeps a feature whose screens are unchanged');
 window.mutateBundle=b=>{featureBundle(b);const g={groups:[{name:'Orders',description:'',screens:['web::/orders','web::/items/new']},{name:'Items',description:'',screens:['web::/items']}],names:{},request_names:{}};for(const k of ['dev','main'])b.branch_details[k].groups=g;};
 await loadProject('First',false,'');render();
 assert(S.feat===null && !document.querySelector('[data-feat].sel'),'Changed membership clears instead of reusing the array index');
 S.view='map';render();assert(!$('map').querySelector('.col.featured'),'No highlight after the membership change');
 window.mutateBundle=featureBundle;await loadProject('First',false,'');await openFeature('Items');
 await loadProject('First',false,'web');assert(S.feat===null,'Another code connection clears the feature');
 await loadProject('First',false,'');await openFeature('Items');
 document.querySelector('#branch [data-b=main]').click();await wait();
 assert(S.feat===null && !document.querySelector('[data-feat].sel'),'Another version without the same screens clears the feature');
 document.querySelector('#branch [data-b=dev]').click();await wait();await openFeature('Items');
 await applyAppCommand({action:'targets',arguments:{branch:'main'}});assert(S.feat===null,'Agent version change clears');
 await applyAppCommand({action:'navigate',arguments:{branch:'dev',view:'feat'}});await openFeature('Items');
 await loadProject('Second');assert(S.feat===null,'Another service clears');
''')

    def test_choosing_a_feature_replaces_an_open_request_panel_but_keeps_the_request(self):
        self.check(r"""
 window.planResult={tasks:[{repository:'web',task:'groups',commit:'old',configuration:'layout-a'}],requirements:[],pins:{web:{commit:'old',configuration:'layout-a'}},blocked:[],handoff:'one request'};
 S.view='feat';render();await requestAgentAction('analysis_plan');await wait();
 const request=S.analysisRequest;assert(S.agentPrompt && request && $('insp').querySelector('.request-steps'),'The request panel is open');
 featureCard('Items').click();await wait();
 assert($('copyF') && $('featMap') && !$('insp').querySelector('.request-steps'),'Choosing a feature shows its overview instead of the old request');
 assert(S.analysisRequest===request && JSON.stringify(controlSelection())===JSON.stringify([itemsId()]),'The prepared request is kept and the feature is the selection');
 S.sel='web::/orders';render();assert((await controlState()).feature_context.member===null,'A screen left from another view is not the Features view target');
""")

    def test_feature_context_continues_into_connections_with_honest_relations(self):
        self.check(r"""
 S.view='sys';S.node=null;render();const sysBefore=$('map').innerHTML;
 const strip=()=>$('insp').querySelector('.feature-context'),said=t=>strip()?.innerText.includes(tr(t));
 await openFeature('Items');$('insp').querySelector('[data-goact]').click();await wait();
 $('insp').querySelector('.detail [data-f^="route|"]').click();await wait();
 let st=await controlState();
 assert(S.view==='focus' && S.focus.t==='route' && strip() && said('선택한 기능의 화면이 쓰는 대상입니다.') && !said('이 기능에 속한 화면입니다.'),'A route used by member screens keeps the feature with neutral wording');
 assert(st.feature_context?.id===itemsId() && st.feature_context.member===null && st.feature_context.relation==='used','State does not claim a member screen for a route: '+JSON.stringify(st.feature_context));
 $('insp').querySelector('[data-f^="table|"]').click();await wait();st=await controlState();
 assert(S.focus.t==='table' && said('선택한 기능의 화면이 쓰는 대상입니다.') && st.feature_context.relation==='used','Data reached from member screens keeps the anchor');
 setFocus('route|api/app/orders.py::list_orders');st=await controlState();
 assert(said('선택한 기능의 화면에서 이어진 것을 찾지 못했습니다.') && st.feature_context.member===null && st.feature_context.relation==='unlinked','A route no member screen calls is not linked to the feature');
 setFocus('screen|web::/orders');st=await controlState();
 assert(said('선택한 기능 밖의 화면입니다.') && $('featSwitch') && st.feature_context.member===false,'An outside screen in Connections is outside');
 assert(!hangul($('insp').innerText),'English focus strip');
 $('featBack').click();await wait();
 assert(S.view==='map' && !S.sel && S.feat===itemsId() && $('copyF') && $('map').querySelectorAll('.col.featured').length===1 && $('map').querySelector('[data-scr="web::/orders"]'),'Back returns to the same feature on the full map');
 S.view='sys';render();assert($('map').innerHTML===sysBefore,'Structure is unchanged');
""")

    def test_actions_beyond_the_first_eight_can_be_opened_from_the_overview(self):
        self.check(r"""
 window.mutateBundle=b=>{featureBundle(b);const s=b.dev.screens.find(x=>x.path==='web::/items/new');s.api_functions=[...s.api_functions];
  for(let k=0;k<9;k++){const r={...structuredClone(b.dev.backend_routes[0]),file:'api/app/extra.py',function:'extra_'+k,path:'/extra/'+k,line:10+k};b.dev.backend_routes.push(r);
   b.dev.api_functions.push({name:'extra'+k,file:'web/src/api.ts',calls:[{method:'POST',path:'/extra/'+k,line:20+k,backend:[{file:r.file,line:r.line}]}]});s.api_functions.push({name:'extra'+k,file:'web/src/api.ts'});}};
 await loadProject('First',false,'');await openFeature('Items');
 const rows=[...$('insp').querySelectorAll('[data-goact]')];
 assert(rows.length===10,'All ten actions are reachable from the overview: '+rows.length);
 const more=$('insp').querySelector('details.more-actions');
 assert(more && !more.open && more.querySelectorAll('[data-goact]').length===2 && more.querySelector('summary').innerText.includes('2'),'The first eight show and the rest sit behind one disclosure');
 more.open=true;const last=more.querySelectorAll('[data-goact]')[1];last.click();await wait();
 assert(S.view==='map' && S.sel===last.dataset.goact && S.open===last.dataset.key && $('insp').querySelector('.feature-context') && $('insp').querySelector('.detail'),'A hidden action opens directly in its detail');
""")

    def test_merged_prs_beyond_the_first_five_stay_openable_in_the_feature_and_screen(self):
        self.check(r"""
 window.mutateBundle=b=>{featureBundle(b);for(let k=0;k<6;k++)b.status.merged_prs.push({number:60+k,title:'Merged extra '+k,url:'https://example.invalid/web/'+(60+k),repository:'web',screens:items,files:[],merged_at:'2026-10-01T00:00:00Z'});};
 await loadProject('First',false,'');await openFeature('Items');
 const more=$('insp').querySelector('details.more-merged');
 assert(more && !more.open && more.querySelectorAll('.row[data-url]').length===2 && more.querySelector('summary').innerText.includes('2'),'Merged PRs past five sit behind one disclosure');
 more.open=true;more.querySelectorAll('.row[data-url]')[1].click();await wait();
 assert(window.calls.some(c=>c.command==='open_url' && c.args.url==='https://example.invalid/web/65') && S.feat===itemsId(),'A hidden merged PR opens and the feature stays');
 $('insp').querySelector('[data-goscr="web::/items"]').click();await wait();
 assert($('insp').querySelector('details.more-merged .row[data-url]'),'The screen work list uses the same disclosure');
""")

if __name__=='__main__':unittest.main()
