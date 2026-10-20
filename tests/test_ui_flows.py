"""User flows in the real UI with fictional bundles in headless Chrome. Native calls are faked; no AI or backend runs."""
import re,subprocess,tempfile,unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
CHROME=Path('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome')
# Two fictional projects. First has web+api code with an arbitrary compared ref; Second has one code and no compared version.
BOOTSTRAP=r'''
window.calls=[];window.errors=[];
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
 if(command==='list_projects')return new URLSearchParams(location.search).get('empty')?[]:['First','Second'];
 if(command==='read_project')return JSON.stringify(fakeBundle(args.project));
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
    for name in ('tokens.css','app.css','vendor/dagre.min.js','connection.js','control.js'):
        html=html.replace(f'"{name}"','"'+(ROOT/'ui'/name).as_uri()+'"')
    html=html.replace('</body>','<script>'+PRELUDE+checks+POSTLUDE+'</script></body>')
    with tempfile.TemporaryDirectory() as tmp:
        target=Path(tmp)/'flow.html';target.write_text(html)
        result=subprocess.run([str(CHROME),'--headless','--disable-gpu','--no-first-run','--disable-background-networking','--disable-component-update',
            '--no-default-browser-check','--window-size=1280,900','--user-data-dir='+tmp+'/chrome','--virtual-time-budget=6000','--dump-dom',target.as_uri()+'?lang='+lang+query],
            capture_output=True,text=True,timeout=40)
    error=re.findall(r'<pre id="flow-error">(.*?)</pre>',result.stdout,re.S)
    return 'data-flow="passed"' in result.stdout,(error or [result.stdout[-1500:]])[-1][-2000:]

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
 const start=$('startProject');assert(start && main().includes(tr('프로젝트 만들기')),'Empty app shows how to start');
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
 const reqRow=document.querySelector('[data-req]');assert(reqRow.innerText.includes(tr('테스트 ')+'1'),'Tests are named, not a colour dot');
 const proposal={...S.system,nodes:[{...S.system.nodes[0],name:'Proposed worker'}]};
 S.branchDetails.dev['system.ai']=proposal;S.view='sys';render();
 assert(main().includes('First Worker') && !main().includes('Proposed worker'),'Written structure stays the default');
 document.querySelector('[data-proposal="1"]').click();
 assert(main().includes('Proposed worker') && main().includes(tr('AI 제안 · 직접 작성한 구조는 바뀌지 않았습니다')),'The AI proposal is viewable and labelled');
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
 assert(outside($('insp')).includes('impact'),'Missing tools are not folded away');
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
 assert($('status').classList.contains('error') && $('status').textContent.includes('fictional collection error'),'The failure is shown in the status line');
 const labels=[...document.querySelectorAll('#branch button')].map(b=>b.textContent);
 assert(labels.length===2 && labels[0].includes('HEAD') && labels[1].includes('v1.0'),'Version buttons keep their names: '+JSON.stringify(labels));
''')

if __name__=='__main__':unittest.main()
