"""Cross-platform run UI checks. Native calls and timers are fake; no AI runs."""
import json
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which('node')
UI = (ROOT / 'ui/index.html').read_text()
RELOAD = UI[UI.index('async function reloadAnalysisOnly('):UI.index('// Manual, automatic and MCP reads')]
HARNESS = r'''
const assert = (value, message) => { if (!value) throw Error(message); };
const calls = [], elements = {}, timers = new Map(), listeners = {};
let timerId = 0, native = null, reads = 0;
const S = {project:'First',repository:'',branch:'dev',lang:'en',loadToken:1,
  agentPurpose:null,agentPrompt:null,view:'map',changes:{entries:['keep']},chi:3,settings:{since:'keep'}};
const baseline = S.changes, settings = S.settings;
const document = {hidden:false,addEventListener:(name,fn)=>listeners[name]=fn};
const window = {addEventListener:(name,fn)=>listeners[name]=fn};
const setTimeout = (fn,ms) => { const id=++timerId;timers.set(id,{fn,ms});return id; };
const clearTimeout = id => timers.delete(id);
function element(id) {
  return {id,onclick:null,disabled:false,textContent:'',_html:'',
    get innerHTML(){return this._html;},set innerHTML(html){
      this._html=html;
      for(const id of Object.keys(elements))if(!['insp','analyzeMap'].includes(id))delete elements[id];
      for(const hit of html.matchAll(/<[^>]*\bid="([^"]+)"[^>]*>/g)){
        elements[hit[1]]=element(hit[1]);elements[hit[1]].disabled=/\bdisabled\b/.test(hit[0]);
      }
    }};
}
elements.insp=element('insp');elements.analyzeMap=element('analyzeMap');
const $ = id => elements[id] || null;
const esc = value => String(value).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;');
const PLAN_NAMES = {analysis:'상세 지도',system:'서비스 구성 보기'};
const connectionDisplayName = id => 'Repository '+id;
const analysisButtonText = () => AnalysisRun.stateLabel();
elements.insp.querySelectorAll=selector=>{
 const hits=[...elements.insp.innerHTML.matchAll(/data-overview-feature="([^"]+)"/g)];
 globalThis.featureButtons=hits.map(hit=>({dataset:{overviewFeature:hit[1].replaceAll('&quot;','"')}}));return featureButtons;
};
function renderAgentPrompt(){elements.insp.innerHTML=AnalysisRun.html();AnalysisRun.bind();}
function render(){AnalysisRun.syncScope();if(S.agentPrompt!=null && S.agentPurpose==='analysis')renderAgentPrompt();}
const account = {auth_method:'claude.ai',email:'fictional@example.invalid',subscription_type:'pro'};
const available = {providers:[{provider:'claude',available:true,authenticated:true,account}]};
const runRecord = (state='running',extra={}) => ({id:'run-1',project:S.project,repository:S.repository,branch:S.branch,lang:S.lang,
  state,tasks:[{task:'analysis'}],completed_tasks:[],current_task:{task:'analysis'},error:null,cancel_requested:false,...extra});
let status = null, provider = available;
async function invoke(command,args){
  calls.push({command,args:JSON.parse(JSON.stringify(args||{}))});
  if(native){const result=await native(command,args);if(result!==undefined)return JSON.stringify(result);}
  if(command==='analysis_run_status')return JSON.stringify(status);
  if(command==='analysis_providers')return JSON.stringify(provider);
  if(command==='analysis_run_start'){status=runRecord('preparing');return JSON.stringify(status);}
  if(command==='analysis_run_cancel'){status={...status,state:'cancelled',cancel_requested:true};return JSON.stringify(status);}
  if(command==='analysis_run_retry'){status=runRecord('preparing',{id:'retry-2'});return JSON.stringify(status);}
  if(command==='read_project'){reads++;return JSON.stringify({project:{},dev:{},main:null,briefings:{},branch_details:{},groups:null,flows:null,system:null,jobs:null});}
  throw Error('Unexpected native command '+command);
}
const flush = async()=>{for(let i=0;i<15;i++)await Promise.resolve();};
const tick = async()=>{const batch=[...timers.values()];timers.clear();for(const item of batch)await item.fn();await flush();};
const open = async()=>{S.agentPurpose='analysis';S.agentPrompt='';renderAgentPrompt();AnalysisRun.open();await flush();};
const count = name=>calls.filter(c=>c.command===name).length;
'''


@unittest.skipUnless(NODE, 'Node is required for fake native UI checks')
class AnalysisRunUI(unittest.TestCase):
    def check_js(self, checks):
        source = HARNESS + '\n' + RELOAD + '\n' + (ROOT / 'ui/analysis-run.js').read_text()
        runner = f'''const vm=require('vm');const context=vm.createContext({{}});
vm.runInContext({json.dumps(source)},context);
Promise.resolve(vm.runInContext({json.dumps('(async()=>{'+checks+'})()')},context)).catch(e=>{{console.error(e.stack);process.exitCode=1;}});'''
        result = subprocess.run([NODE], input=runner, text=True, capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_saved_task_and_input_progress_are_distinct_and_intent_is_not_reused(self):
        self.check_js(r'''
await flush();status=runRecord('running',{intent:{task:'all',targets:[]},completed_tasks:[{task:'analysis'}],input_stats:{calls:4,bytes:12000},batch_progress:{task:'system',completed:2,total:7}});
await open();await AnalysisRun.check();await flush();
assert($('insp').innerHTML.includes('1/2 tasks saved'),'Saved task count');
assert($('insp').innerHTML.includes('Input calls: 4') && $('insp').innerHTML.includes('Current task input units: 2/7'),'Input units are not saved tasks');
status.batch_progress={task:'analysis',completed:4,total:4,discovering:true};
await AnalysisRun.check();await flush();
assert($('insp').innerHTML.includes('Initial input units reviewed: 4 · Total not yet known') && !$('insp').innerHTML.includes('4/4'),'Initial batch is not a whole-run denominator');
S.lang='ko';
assert(AnalysisRun.html().includes('먼저 살펴본 입력 조각 4개 · 전체 개수 집계 전'),'Korean initial progress');
S.lang='en';
status=runRecord('failed',{intent:{task:'all',targets:[]}});
S.analysisChoice={task:'suggest_groups'};AnalysisRun.open();await flush();
assert($('startAppAnalysis') && !$('retryAppAnalysis'),'Another intent is not offered as this request’s retry');
await $('startAppAnalysis').onclick();await flush();
const args=calls.filter(c=>c.command==='analysis_run_start').at(-1).args;
assert(args.scope.intent.task==='groups' && args.scope.intent.targets.length===0,'Explicit grouping intent reaches native bridge');
''')

    def test_explicit_local_scope_sends_only_selected_resource(self):
        self.check_js(r'''
S.analysisChoice={task:'scope_overview',target:'backend',detailTarget:'/work'};
await open();await flush();
assert(count('analysis_run_start')===0 && !$('startFullAnalysis'),'Only direct confirmation starts the bounded request');
await $('startAppAnalysis').onclick();
const started=calls.find(c=>c.command==='analysis_run_start').args;
assert(started.scope.repository==='backend' && started.scope.intent.task==='overview' && JSON.stringify(started.scope.intent.targets)===JSON.stringify([{repository:'backend',target:'/work'}]),'Only the selected repository and path reach the backend');
''')

    def test_batch_requires_separate_confirmation_and_discloses_fixed_call_limit(self):
        self.check_js(r'''
S.maps={dev:{structure_indexes:[{repository:'web',service_flow:{feature_groups:[{resource:'/one'},{resource:'/two'}]}}]}};
await open();await flush();$('chooseResourceBatch').onclick();
assert(count('analysis_run_start')===0 && $('insp').innerHTML.includes('Path groups: 2 · Up to 2 AI calls'),'The batch shows its cost boundary before starting');
S.maps.dev.structure_indexes[0].service_flow.feature_groups.push({resource:'/three'});
await $('startAppAnalysis').onclick();
const args=calls.find(c=>c.command==='analysis_run_start').args;
assert(args.scope.intent.task==='resources' && args.scope.intent.max_calls===2,'Confirmation cannot widen when the live map changes');
const one={task:'overview',repository:'web',target:'/one'},two={...one,target:'/two'};
status=runRecord('running',{intent:args.scope.intent,current_task:two,tasks:[one,two],completed_tasks:[one]});
await AnalysisRun.check();
assert($('insp').innerHTML.includes('Path groups saved: 1 · Remaining: 1') && $('insp').innerHTML.includes('/two') && $('cancelAppAnalysis'),'Current path and remaining count with cancel');
status.state='cancelled';await AnalysisRun.check();assert($('retryAppAnalysis'),'Cancelled batch can resume');
''')

    def test_active_poll_uses_progress_then_recovers_terminal_catalog(self):
        self.check_js(r'''
await flush();S.analysisChoice={task:'resource_batch',maxCalls:3};await open();await flush();
await $('startAppAnalysis').onclick();const intent=calls.find(c=>c.command==='analysis_run_start').args.scope.intent;
native=(command,args)=>{
 if(command==='analysis_run_status' && args.view==='progress')return runRecord('running',{intent,completed_tasks:2,tasks:1});
};
await AnalysisRun.check();assert($('insp').innerHTML.includes('Path groups saved: 2 · Remaining: 1') && $('refreshSavedBatch'),'Compact counts with an on-demand result catalog');
assert(calls.at(-1).args.view==='progress' && calls.at(-1).args.runId==='run-1','Routine poll only asks for compact progress');
native=(command,args)=>command==='analysis_run_status'?runRecord('completed',{intent,completed_tasks:3,tasks:0}):undefined;
await AnalysisRun.check();assert(calls.filter(c=>c.command==='analysis_run_status').at(-1).args.view==='catalog','Terminal transition reads the saved catalog');
''')

    def test_initial_overview_and_full_analysis_have_distinct_explicit_buttons(self):
        self.check_js(r'''
await open();
assert($('startFullAnalysis') && $('insp').innerHTML.includes('1 AI call maximum') && $('insp').innerHTML.includes('Analyze full codebase (beta)'),'Scope and call bound visible');
await $('startAppAnalysis').onclick();await flush();
assert(calls.filter(c=>c.command==='analysis_run_start').at(-1).args.scope.intent.task==='overview','Default button requests the bounded overview');
status=null;await AnalysisRun.check();
await $('startFullAnalysis').onclick();await flush();
assert(calls.filter(c=>c.command==='analysis_run_start').at(-1).args.scope.intent.task==='all','Full button requests the complete plan');
''')

    def test_provider_account_and_charge_before_explicit_start(self):
        self.check_js(r'''
await flush();assert(count('analysis_run_status')===1,'Startup recovers status');
assert(count('analysis_run_start')===0 && count('analysis_providers')===0,'Startup cannot launch or probe a CLI');
await open();
assert($('insp').innerHTML.includes('fictional@example.invalid'),'Account visible before start');
assert($('insp').innerHTML.includes('Subscription usage limits apply'),'Usage visible before start');
assert(!$('startAppAnalysis').disabled,'Authenticated subscription enables explicit start');
assert(count('analysis_run_start')===0,'Opening the panel cannot start AI');
await $('startAppAnalysis').onclick();await flush();
assert(count('analysis_run_start')===1,'Exactly one explicit run');
assert(calls.find(c=>c.command==='analysis_run_start').args.expectedAccount.email===account.email,'Displayed account pinned to explicit start');
assert($('cancelAppAnalysis'),'Preparing run can be cancelled');
assert(timers.size===1,'Only active run polls');
assert(!calls.some(c=>['refresh','save_settings'].includes(c.command)),'No refresh or baseline writes');
''')

    def test_missing_cli_and_signed_out_subscription_disable_paid_actions(self):
        self.check_js(r'''
provider={providers:[{provider:'claude',available:false,authenticated:false,error_code:'CLI_NOT_INSTALLED'}]};
await open();assert($('startAppAnalysis').disabled,'Missing CLI cannot start');
assert($('insp').innerHTML.includes('Install Claude Code'),'Missing CLI has an actionable message');
await $('startAppAnalysis').onclick();assert(count('analysis_run_start')===0,'Guard works even if disabled handler called');
provider={providers:[{provider:'claude',available:true,authenticated:false,error_code:'CLI_NOT_AUTHENTICATED'}]};
await $('checkAppAnalysis').onclick();await flush();assert($('startAppAnalysis').disabled,'Signed out cannot start');
S.lang='ko';AnalysisRun.syncScope();renderAgentPrompt();
assert($('insp').innerHTML.includes('구독 계정에 로그인'),'Korean sign-in guidance');
assert(!calls.some(c=>['analysis_run_start','analysis_run_retry'].includes(c.command)),'Account check never starts a run');
''')

    def test_progress_completion_uses_existing_read_without_moving_history(self):
        self.check_js(r'''
await open();await $('startAppAnalysis').onclick();await flush();
status=runRecord('saving',{completed_tasks:[{task:'analysis'}],tasks:[{task:'system'}],current_task:{task:'system'}});
await tick();assert($('insp').innerHTML.includes('1/2'),'Completed plus pending task count');
assert($('insp').innerHTML.includes('Saving…'),'Saving is visible');
status=runRecord('completed',{tasks:[],completed_tasks:[{task:'analysis'},{task:'system'}],current_task:null});
await tick();assert(reads===1,'Completion reads saved results once');
assert(timers.size===0,'Completed runs stop polling');
assert(S.changes===baseline && S.settings===settings && S.chi===3,'Existing read preserves history, comparison and selection');
assert($('viewAppAnalysis'),'Saved results can be opened');
await AnalysisRun.check();assert(reads===1,'Repeated status does not repeatedly reload results');
assert(!calls.some(c=>c.command==='refresh'),'Result reads never collect');
''')

    def test_account_usage_and_auth_errors_are_localized_and_actionable(self):
        self.check_js(r'''
await open();
for(const [code,en,ko] of [
 ['CLI_ACCOUNT_UNIDENTIFIED','identify the Claude Code account','계정을 확인할 수 없습니다'],
 ['CLI_USAGE_LIMIT','usage limit was reached','사용 한도에 도달'],
 ['CLI_AUTH','sign-in expired or was rejected','로그인이 만료됐거나 거부'],
 ['CANCELLED','Analysis was cancelled','분석이 취소']
]){
 provider={providers:[{provider:'claude',available:false,authenticated:false,error_code:code}]};
 S.lang='en';await $('checkAppAnalysis').onclick();await flush();
 assert($('insp').innerHTML.includes(en),'English error '+code);
 S.lang='ko';renderAgentPrompt();assert($('insp').innerHTML.includes(ko),'Korean error '+code);
 assert($('startAppAnalysis').disabled,'Failure cannot enable paid run '+code);
}
assert(count('analysis_run_start')===0 && count('analysis_run_retry')===0,'Reading errors never starts AI');
''')

    def test_scope_switch_discards_late_start_and_status_responses(self):
        self.check_js(r'''
await open();let release;
native=(command,args)=>command==='analysis_run_start'?new Promise(resolve=>release=resolve):undefined;
const pending=$('startAppAnalysis').onclick();await flush();
S.project='Second';S.repository='web';S.loadToken++;AnalysisRun.syncScope();await flush();
release({id:'old',project:'First',repository:'',branch:'dev',lang:'en',state:'completed',tasks:[],completed_tasks:[{}]});await pending;await flush();
assert(reads===0,'Late completion from previous code cannot load results');
assert(!AnalysisRun.stateLabel(),'Late previous scope cannot paint status');
let releaseStatus;
native=(command,args)=>command==='analysis_run_status'?new Promise(resolve=>releaseStatus=resolve):undefined;
const reading=AnalysisRun.check();await flush();
S.branch='main';AnalysisRun.syncScope();await flush();
releaseStatus(null);await flush();
assert(!calls.some(c=>c.command==='refresh'),'Switching scopes never collects');
''')

    def test_interruption_distinguishes_possible_redelivery_before_explicit_retry(self):
        self.check_js(r'''
status=runRecord('failed',{error:{code:'interrupted'},input_stats:{calls:1}});
await flush();await AnalysisRun.check();await open();assert($('retryDeliveryWarning') && $('retryAppAnalysis') && $('insp').innerHTML.includes('aria-describedby="retryDeliveryWarning"') && $('insp').innerHTML.includes('Retrying may send it again.'),'Provider delivery uncertainty accompanies retry');
S.lang='ko';status.lang=S.lang;AnalysisRun.syncScope();await flush();assert($('insp').innerHTML.includes('같은 요청이 재전송될 수 있습니다.'),'Korean warning');
status.state='cancelled';status.error=null;await AnalysisRun.check();assert(!$('retryDeliveryWarning'),'Manual cancellation has no lost-worker warning');
status.state='failed';status.error={code:'interrupted'};status.input_stats.calls=0;await AnalysisRun.check();assert(!$('retryDeliveryWarning'),'Startup before a model attempt has no duplicate-delivery warning');
status.error={code:'invalid_result'};status.input_stats.calls=1;await AnalysisRun.check();assert(!$('retryDeliveryWarning') && !count('analysis_run_retry'),'A different error or viewing warnings cannot retry');
''')

    def test_cancel_retry_interrupted_recovery_and_new_account_snapshot(self):
        self.check_js(r'''
status=runRecord('failed',{error:{code:'interrupted',message:'stopped'},tasks:[],completed_tasks:[{task:'analysis'}]});
await flush();await AnalysisRun.check();await open();
assert($('insp').innerHTML.includes('Analysis was interrupted'),'Interrupted run recovered on status read');
assert(count('analysis_run_retry')===0,'Recovery cannot automatically retry');
await $('retryAppAnalysis').onclick();await flush();
assert(count('analysis_run_retry')===1,'Retry is explicit');
assert(calls.find(c=>c.command==='analysis_run_retry').args.expectedAccount.email===account.email,'Retry pins visible account');
await $('cancelAppAnalysis').onclick();await flush();assert(AnalysisRun.stateLabel()==='Cancelled','Cancel state is shown');
assert(timers.size===0,'Cancelled run stops polling');
provider={providers:[{provider:'claude',available:true,authenticated:true,account:{...account,email:'new@example.invalid'}}]};
await $('checkAppAnalysis').onclick();await flush();
native=(command,args)=>{if(command==='analysis_run_retry')throw JSON.stringify({error:{code:'CLI_ACCOUNT_CHANGED'}});};
await $('retryAppAnalysis').onclick();await flush();
assert($('insp').innerHTML.includes('account changed'),'Account race has actionable guidance');
assert(calls.filter(c=>c.command==='analysis_run_retry').at(-1).args.expectedAccount.email==='new@example.invalid','Rechecked account is the next explicit snapshot');
''')

    def test_hidden_window_stops_polling_and_return_only_reads_status(self):
        self.check_js(r'''
await open();await $('startAppAnalysis').onclick();await flush();
document.hidden=true;listeners.visibilitychange();assert(timers.size===0,'Hidden app stops polling');
const paid=count('analysis_run_start');document.hidden=false;listeners.visibilitychange();await flush();
assert(timers.size===1,'Return resumes active selected scope polling');
assert(count('analysis_run_start')===paid,'Returning cannot start paid work');
''')

    def test_project_wide_active_run_shows_actual_scope_and_only_allows_cancel(self):
        self.check_js(r'''
await flush();
status=runRecord('running',{repository:'api',branch:'main',lang:'ko',completed_tasks:[{task:'analysis'}]});
await AnalysisRun.check();await open();
assert($('insp').innerHTML.includes('Repository api · main · ko'),'Conflicting run scope is visible');
assert($('cancelAppAnalysis') && !$('startAppAnalysis') && !$('retryAppAnalysis'),'Only cancellation offered for other scope');
status={...status,state:'completed',tasks:[]};await tick();
assert(reads===0,'Other-scope saved results cannot reload the selected view');
assert(!$('viewAppAnalysis') && !$('retryAppAnalysis'),'No hidden cross-scope read or retry');
assert($('startAppAnalysis'),'Selected scope can be explicitly started after the other run finishes');
''')

    def test_verified_preview_opens_before_save_and_is_scoped_to_this_commit(self):
        self.check_js(r'''
await flush();
for(const [lang,title] of [['en','Features verified so far'],['ko','분석 중 확인한 기능']]){
 S.lang=lang;AnalysisRun.syncScope();
 status=runRecord('running',{current_task:{task:'analysis',repository:'',commit:'a1b2c3d4'},
   preview:{repository:'',commit:'a1b2c3d4',items:[{kind:'request',name:'Save <items>',file:'handlers/save',line:21,quote:'<save items>'}]}});
 await open();await AnalysisRun.check();await flush();
 assert($('analysisPreview0') && $('insp').innerHTML.includes(title),'Scope and translated preview');
 await $('analysisPreview0').onclick();
 assert($('insp').innerHTML.includes('handlers/save:21') && $('insp').innerHTML.includes('&lt;save items>'),'Escaped source and line are readable');
 assert(count('analysis_run_start')===0 && reads===0,'Opening preview is local');
 await AnalysisRun.check();
 assert($('insp').innerHTML.includes('handlers/save:21'),'Expanded source survives polling');
 status={...status,preview:{...status.preview,commit:'wrong'}};
 await AnalysisRun.check();assert(!$('analysisPreview0'),'No evidence from another commit');
}
''')

    def test_saved_partial_overview_reopens_after_cancel_and_hides_stale_configuration(self):
        self.check_js(r'''
await open();
const group={repository:'service',commit:'abcd1234ef',configuration:'pin',files:['src/cli'],items:[{name:'Save',file:'src/cli',line:3,quote:'<save>'}]};
S.projectInfo={repositories:[{id:'service',fingerprint:'pin',commits:{dev:'abcd1234'}}]};
status=runRecord('cancelled',{saved_overviews:[group],cancel_requested:true});
await AnalysisRun.check();
assert($('savedOverview0') && !$('viewAppAnalysis'),'Partial sample is available without completing a map task');
await $('savedOverview0').onclick();
assert($('insp').innerHTML.includes('Files sampled: 1') && $('insp').innerHTML.includes('&lt;save>'),'Scoped coverage and escaped evidence');
await AnalysisRun.check();assert($('insp').innerHTML.includes('src/cli:3'),'Expanded overview survives polling');
S.projectInfo.repositories[0].fingerprint='changed';renderAgentPrompt();
assert(!$('savedOverview0'),'Hide a sample from previous settings');
assert(count('analysis_run_start')===0,'Reopening costs no model call');
''')

    def test_legacy_overview_requires_server_validated_live_git_pins(self):
        self.check_js(r'''
await open();S.maps={dev:{commit:'older-map'}};
const group={repository:'',commit:'current-head',configuration:'config',files:['app'],items:[{name:'Start',description:'Runs the app',file:'app',line:2,quote:'run_command()'}],format:'overview-v1'};
status=runRecord('completed',{intent:{task:'overview',targets:[]},saved_overviews:[group]});
await AnalysisRun.check();assert(!$('savedOverview0'),'Missing live pin hides results');
status.current_legacy_pin={commit:group.commit,configuration:group.configuration};
await AnalysisRun.check();assert($('savedOverview0') && $('insp').innerHTML.includes('Runs the app'),'Verified current legacy result opens despite an old basic map');
const html=$('insp').innerHTML;
assert(html.includes('Feature diagram by source file') && /<li><code>app<\/code><ul><li><b>Start<\/b>/.test(html),'Verified feature is a child of its cited file');
assert(html.includes('app:2') && html.includes('run_command()'),'Diagram node retains the pinned evidence');

group.connections=[{method:'GET',path:'/runs',client:{file:'client.ts',line:7,quote:'fetch("/runs")'},server:{file:'app.py',line:21,quote:'@app.get("/runs")'}}];
await AnalysisRun.check();
const flow=$('insp').innerHTML;
assert(flow.includes('GET /runs') && flow.includes('client.ts:7') && flow.includes('app.py:21'),'Both pinned sides reopen with the request');
group.connections[0].basis='path_template';group.connections[0].server_path='/runs/:id';
await AnalysisRun.check();
assert($('insp').innerHTML.includes('If the path pattern matches') && $('insp').innerHTML.includes('/runs/:id'),'A parameterized match stays conditional when reopened');
group.connections[0].id=1;
group.connections.push({...group.connections[0],id:2,path:'/other'});
group.feature_groups=[{name:'Manage <runs>',connection_ids:[1]}];
group.items.push({description:'Fetch the current runs',file:'client.ts',line:7,name:'Load',quote:'fetch("/runs")'});
await AnalysisRun.check();assert(!$('insp').innerHTML.includes('GET /runs'),'Grouped evidence starts collapsed');featureButtons[0].onclick();const grouped=$('insp').innerHTML;
assert(grouped.includes('Manage &lt;runs>') && grouped.indexOf('Manage &lt;runs>')<grouped.indexOf('GET /runs') && grouped.indexOf('Other requests')<grouped.indexOf('GET /other'),'Named features precede both linked requests and ungrouped requests');
assert(grouped.includes('Fetch the current runs') && grouped.includes('Evidence by file') && grouped.includes('If the path pattern matches'),'Grounded descriptions, original file evidence and conditions remain available');
globalThis.flowActions=()=>'';
globalThis.flowDataSteps=(steps,evidence)=>steps ? evidence('models.py',9) : '';
const step={...group.connections[0],data_steps:[{operation:'read',model:'Run'}]};
S.maps.dev.structure_index={commit:group.commit,service_flow:{connections:[step]}};
await AnalysisRun.check();assert($('insp').innerHTML.includes('models.py:9'),'Matching pinned endpoints add storage evidence to saved features');
S.maps.dev.structure_index.commit='moved';await AnalysisRun.check();assert(!$('insp').innerHTML.includes('models.py:9'),'Never join data stages from a different snapshot');
status.current_legacy_pin.configuration='changed';await AnalysisRun.check();
assert(!$('savedOverview0'),'Configuration mismatch hides the sample');
''')

    def test_completed_program_evidence_matches_saved_repository_commit(self):
        self.check_js(r'''
await open();
const hash='aecb78901234',group={repository:'service',commit:hash,items:[{kind:'program',name:'CLI command',file:'shell',line:2,quote:'run command'}]};
status=runRecord('completed',{completed_tasks:[],program_observations:[group],pins:{service:{commit:hash}}});
native=command=>command==='read_project'?{project:{repositories:[{id:'service',commits:{dev:hash.slice(0,8)}}]},dev:{},main:null,branch_details:{}}:undefined;
await AnalysisRun.check();renderAgentPrompt();
await $('analysisPreview0').onclick();
assert($('insp').innerHTML.includes('shell:2') && $('insp').innerHTML.includes('Verified programs'),'Completed program can be inspected');
S.projectInfo.repositories[0].commits.dev='another';renderAgentPrompt();
assert(!$('analysisPreview0'),'Program from a previous commit is hidden');
''')

    def test_entry_points_offer_both_app_run_and_existing_mcp_copy(self):
        self.assertIn('<script src="analysis-run.js"></script>', UI)
        self.assertIn('id="automaticAnalysis"', UI)
        self.assertLess(UI.index("AnalysisRun.overviewHtml()"),UI.index('id="automaticAnalysis"'))
        self.assertIn('id="cpAgent"', UI)
        self.assertIn('data-analysis-task=', UI)
        for entry in ('remakeSys', 'requestBriefing', 'mk', 'regroup'):
            line = next(line for line in UI.splitlines() if f"$('{entry}').onclick=" in line)
            self.assertIn('openAnalysisPanel(', line)
        self.assertIn("requestAgentAction('analysis_plan',{},true)", UI)


if __name__ == '__main__':
    unittest.main()
