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

    def test_provider_account_and_charge_before_explicit_start(self):
        self.check_js(r'''
await flush();assert(count('analysis_run_status')===1,'Startup recovers status');
assert(count('analysis_run_start')===0 && count('analysis_providers')===0,'Startup cannot launch or probe a CLI');
await open();
assert($('insp').innerHTML.includes('fictional@example.invalid'),'Account visible before start');
assert($('insp').innerHTML.includes('subscription usage and limits apply'),'Usage visible before start');
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

    def test_entry_points_offer_both_app_run_and_existing_mcp_copy(self):
        self.assertIn('<script src="analysis-run.js"></script>', UI)
        self.assertIn("typeof AnalysisRun!=='undefined'?AnalysisRun.html()", UI)
        self.assertIn('id="cpAgent"', UI)
        self.assertIn('data-analysis-task=', UI)
        for entry in ('remakeSys', 'requestBriefing', 'mk', 'regroup'):
            line = next(line for line in UI.splitlines() if f"$('{entry}').onclick=" in line)
            self.assertIn('openAnalysisPanel(', line)
        self.assertIn("requestAgentAction('analysis_plan',{},true)", UI)


if __name__ == '__main__':
    unittest.main()
