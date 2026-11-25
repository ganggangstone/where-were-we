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
 const unit=/^\[data-(unit-[a-z]+)\]$/.exec(selector);
 if(unit){
  const key=unit[1].replace(/-([a-z])/g,(_,c)=>c.toUpperCase());
  const found=[...elements.insp.innerHTML.matchAll(new RegExp('data-'+unit[1]+'="([^"]*)"','g'))].map(hit=>({dataset:{[key]:hit[1]},onclick:null}));
  (globalThis.unitHandles||(globalThis.unitHandles={}))[unit[1]]=found;return found;
 }
 if(selector==='input[name="mapCoverage"]'){
  const found=[...elements.insp.innerHTML.matchAll(/<input type="radio" name="mapCoverage" value="([^"]+)"/g)].map(hit=>({value:hit[1],onchange:null}));
  globalThis.coverageHandles=found;return found;
 }
 const hits=[...elements.insp.innerHTML.matchAll(/data-overview-feature="([^"]+)"/g)];
 globalThis.featureButtons=hits.map(hit=>({dataset:{overviewFeature:hit[1].replaceAll('&quot;','"')}}));return featureButtons;
};
function renderAgentPrompt(){elements.insp.innerHTML=AnalysisRun.html()+AnalysisRun.boardHtml();AnalysisRun.bind();}
function render(){AnalysisRun.syncScope();if(S.agentPrompt!=null && S.agentPurpose==='analysis')renderAgentPrompt();}
const account = {auth_method:'claude.ai',email:'fictional@example.invalid',subscription_type:'pro'};
const available = {providers:[{provider:'claude',available:true,authenticated:true,account}]};
const runRecord = (state='running',extra={}) => ({id:'run-1',project:S.project,repository:S.repository,branch:S.branch,lang:S.lang,
  intent:{task:'overview',targets:[]},state,tasks:[{task:'overview'}],completed_tasks:[],current_task:{task:'overview'},error:null,cancel_requested:false,...extra});
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

    BOARD = r"""
const unitBoard=(extra={})=>({repositories:[{repository:'service',units:[
 ['route:/orders','route','/orders',3,'saved','new'],
 ['route:/reports','route','/reports',6,'working',''],
 ['folder:lib','folder','lib',9,'pending',''],
 ['folder:tools','folder','tools',3,'failed',''],
 ['folder:jobs','folder','jobs',2,'named','','Runs the jobs']],
 coverage:{tracked:20,in_units:15,indexed:15,excluded:{secret:1,binary:2},truncated:true}}],
 totals:{units:5,saved:1,named:1,working:1,pending:1,failed:1},calls:{rules:0,labeling:2,structure:1,unit:0,total:3},...extra});
const serve=(extra)=>{native=(command,args)=>command==='analysis_run_status'&&args.view==='units'?unitBoard(extra):undefined;};
"""

    def test_idle_board_shows_cost_scope_gaps_and_starts_only_after_a_click(self):
        self.check_js(self.BOARD + r"""
serve();status=null;await open();await AnalysisRun.check();await flush();
const html=$('insp').innerHTML;
assert(!html.includes('Full code analysis') && html.includes('Detailed 1') && html.includes('Named 2'),'No second heading; named counts include the detailed unit');
assert(html.includes('Paths<b>1/2</b><small>Detailed 1</small>') && html.includes('Folders<b>1/3</b></span>'),'A lane counts named units out of units sent to AI and adds detailed ones apart');
assert(!html.includes('checkFullAccount'),'No account button beside the start when the account works');
assert(html.includes('Analyze · 3 calls') && html.includes('Map summary sent to Claude') && html.includes('AI interpretations of a map summary only'),'Call count, what is sent and what the AI reads before the click');
assert(html.includes('Excluded 3') && html.includes('Index limit reached') && html.includes('Files 15/20') && html.includes('Credential files'),'Scope gaps, index limit and exclusion reasons');
assert(html.includes('Analyzing') && html.includes('No explanation') && html.includes('Failed') && html.includes('Detailed explanation') && html.includes('Named and described'),'Named units are not shown as queued');
assert(count('analysis_run_start')===0,'Showing the board costs no model call');
await $('startFullAnalysis').onclick();await flush();
const intent=calls.find(c=>c.command==='analysis_run_start').args.scope.intent;
assert(intent.task==='full' && !('max_calls' in intent),'The start asks for no cap confirmation');
""")

    def test_full_analysis_is_the_main_action_and_has_no_separate_overview_button(self):
        self.check_js(self.BOARD + r"""
serve();status=null;await open();await AnalysisRun.check();await flush();
let html=$('insp').innerHTML;
assert(/class="btn primary" id="startFullAnalysis"/.test(html),'Full analysis is the primary button');
assert(!html.includes('id="startAppAnalysis"') && !html.includes('Create initial overview'),'No separate overview button when the full board is ready');
await AnalysisRun.check();await flush();
assert(/class="btn primary" id="startFullAnalysis"/.test($('insp').innerHTML) && count('analysis_run_start')===0,'No model call before the click');
""")

    def test_units_show_first_while_the_local_file_check_finishes_and_start_waits_for_the_exact_count(self):
        self.check_js(self.BOARD + r"""
let release;const gate=new Promise(r=>release=r);
const pending=unitBoard({calls:{rules:1,labeling:1,structure:0,unit:0,total:2},signals:'pending'});
const ready=unitBoard({calls:{rules:1,labeling:1,structure:0,unit:0,total:2},signals:'ready'});
let units=0;
native=async(command,args)=>{
 if(command!=='analysis_run_status')return undefined;
 if(args.view==='signals'){await gate;return {ready:true,repositories:[]};}
 if(args.view==='units'){units++;return units===1?pending:ready;}
};
status=null;await open();await AnalysisRun.check();await flush();
let html=$('insp').innerHTML;
assert(html.includes('/orders') && html.includes('Detailed 1'),'The unit list shows before the scan ends');
assert(html.includes('Checking files') && /id="startFullAnalysis" disabled/.test(html) && !html.includes('2 calls'),'No call count and no start until the file check ends');
assert(count('analysis_run_start')===0,'Waiting costs no model call');
release();await flush();await flush();await flush();
html=$('insp').innerHTML;
assert(!html.includes('Checking files') && html.includes('Analyze · 2 calls') && !/id="startFullAnalysis" disabled/.test(html),'The exact count replaces the waiting note');
assert(calls.filter(c=>c.args && c.args.view==='signals').length===1 && units===2,'One scan request, then the board is read again');
""")

    def test_legend_counts_detailed_units_apart_from_saved_map_rows_and_adds_up(self):
        self.check_js(self.LOCAL_BOARD + r"""
const mixed=()=>({repositories:[{repository:'service',units:[
 ['route:/a','route','/a',3,'saved',''],['route:/b','route','/b',2,'saved',''],['route:/c','route','/c',2,'named',''],['route:/d','route','/d',2,'pending',''],
 ['groups','groups','groups',1,'saved',''],['system','system','system',1,'saved','']]}],
 totals:{units:6,saved:4,named:1,pending:1},calls:{rules:0,labeling:0,structure:0,unit:0,total:0}});
const legend=()=>[...$('insp').innerHTML.matchAll(/data-unit-filter="(\w+)"[^>]*>(?:<i[^>]*><\/i>)?([^<]*)</g)].map(m=>m[2].trim());
native=(command,args)=>command==='analysis_run_status'&&args.view==='units'?mixed():undefined;
status=null;await open();await AnalysisRun.check();await flush();
const first=legend();
assert(first.includes('All 6') && first.includes('Detailed explanation 2') && first.includes('Saved 2') && first.includes('Named and described 1') && first.includes('No explanation 1'),'Legend labels: '+first);
assert(first.slice(1).reduce((n,x)=>n+Number(x.match(/(\d+)$/)[1]),0)===6,'Legend rows add up to the unit total');
unitHandles['unit-filter'].find(b=>b.dataset.unitFilter==='explained').onclick();
assert(($('insp').innerHTML.match(/data-unit-card=/g) || []).length===2,'The detailed legend row filters the two detailed units');
await open();await AnalysisRun.check();await flush();
assert(JSON.stringify(legend())===JSON.stringify(first),'Same legend after reopening');
""")

    def test_running_board_filters_opens_saved_units_and_cancels(self):
        self.check_js(self.BOARD + r"""
await open();
status=runRecord('running',{intent:{task:'full',targets:[]},unit_board:unitBoard({announced:{total:3},used:{labeling:1}}),input_stats:{calls:1,bytes:10}});
await AnalysisRun.check();await flush();
assert($('cancelFullAnalysis') && !$('startFullAnalysis') && $('insp').innerHTML.includes('AI calls 1/3'),'Run strip with cancel and live call count');
unitHandles['unit-filter'].find(b=>b.dataset.unitFilter==='pending').onclick();
assert($('insp').innerHTML.includes('data-unit-card="2"') && !$('insp').innerHTML.includes('data-unit-card="0"'),'Filter keeps only queued units');
unitHandles['unit-filter'].find(b=>b.dataset.unitFilter==='all').onclick();
native=(command,args)=>command==='analysis_run_status'&&args.view==='unit'?{repository:'service',commit:'abcd1234ef',configuration:'pin',resource:'/orders',files:['api.py'],items:[{name:'List orders',description:'Returns the orders',file:'api.py',line:1,quote:'def orders'}],format:'overview-v1'}:undefined;
unitHandles['unit-open'].find(b=>b.dataset.unitOpen==='0').onclick();await flush();
const read=calls.filter(c=>c.command==='analysis_run_status'&&c.args.view==='unit').at(-1);
assert(read && read.args.resource==='route:/orders' && $('insp').innerHTML.includes('List orders'),'A saved unit opens its explanation on demand');
const before=calls.length;
unitHandles['unit-open'].find(b=>b.dataset.unitOpen==='1').onclick();await flush();
assert(calls.length===before,'A unit still being prepared reads nothing');
await $('cancelFullAnalysis').onclick();await flush();
assert(count('analysis_run_cancel')===1,'Cancel reaches the backend');
""")

    LOCAL_BOARD = r"""
const localBoard=(extra={})=>({repositories:[{repository:'service',units:[
 ['route:/a','route','/a',3,'saved',''],['route:/b','route','/b',2,'saved',''],['route:/c','route','/c',2,'pending',''],
 ['folder:local:docs','folder','docs',5,'local','']],
 links:[[0,1,2],[2,0,1]],
 coverage:{tracked:20,in_units:12,local:5,excluded:{binary:2}},map_coverage:{files:18,windows:3,whole:1,local:1,docs:5,support:0,text_bytes:100,sent_bytes:50}}],
 totals:{units:4,saved:2,pending:1,local:1},calls:{rules:0,labeling:4,structure:0,unit:0,total:4},...extra});
const serveLocal=(extra)=>{native=(command,args)=>command==='analysis_run_status'&&args.view==='units'?localBoard(extra):command==='analysis_run_status'&&args.view==='unit'?{local:true,commit:'abcd1234',files:['docs/a.md'],file_count:5,kinds:{doc:5}}:undefined;};
"""

    def test_local_units_links_and_the_start_sends_the_board_count(self):
        self.check_js(self.LOCAL_BOARD + r"""
serveLocal();status=null;await open();await AnalysisRun.check();await flush();
let html=$('insp').innerHTML;
assert(html.includes('Detailed 2') && html.includes('Checked locally 1') && html.includes('data-state="local"'),'Saved AI units over AI units, local counted apart');
assert(html.includes('Read locally 18') && html.includes('AI range 7') && html.includes('Local only 5'),'Scope chips come from coverage');
assert(!$('renewFullAnalysis') && html.includes('Analyze · 4 calls'),'One start button with the board count');
await $('startFullAnalysis').onclick();await flush();
const intent=calls.find(c=>c.command==='analysis_run_start').args.scope.intent;
assert(!('max_calls' in intent) && !('renew' in intent),'The start sends no cap');
""")

    def test_a_completed_run_with_unread_parts_says_so(self):
        self.check_js(self.LOCAL_BOARD + r"""
serveLocal();status=runRecord('completed',{intent:{task:'full',targets:[],},map_gaps:true});await open();await AnalysisRun.check();await flush();
assert($('insp').innerHTML.includes('Completed · some parts unconfirmed'),'A run that closed batches is not shown as plainly complete');
""")

    def test_open_card_shows_link_chips_marks_cells_and_local_card_lists_files(self):
        self.check_js(self.LOCAL_BOARD + r"""
serveLocal();status=null;await open();await AnalysisRun.check();await flush();
unitHandles['unit-open'].find(b=>b.dataset.unitOpen==='0').onclick();await flush();
let html=$('insp').innerHTML;
assert(html.includes('Uses →') && html.includes('data-unit-link="1"') && html.includes('← Used by') && html.includes('data-unit-link="2"'),'Both link rows');
assert((html.match(/data-linked="1"/g) || []).length===2,'Linked cells are marked in the map');
unitHandles['unit-open'].find(b=>b.dataset.unitOpen==='3').onclick();await flush();
html=$('insp').innerHTML;
assert(html.includes('docs/a.md') && html.includes('Documents 5') && html.includes('AI did not read it'),'Local card lists files and kinds');
unitHandles['unit-filter'].find(b=>b.dataset.unitFilter==='local').onclick();
assert($('insp').innerHTML.includes('data-unit-card="3"') && !$('insp').innerHTML.includes('data-unit-card="0"'),'Local legend filter');
""")

    def test_card_is_the_only_detail_place_and_asks_one_unit_at_a_time(self):
        self.check_js(self.LOCAL_BOARD + r"""
serveLocal();status=null;await open();await AnalysisRun.check();await flush();
let html=$('insp').innerHTML;
for(const id of ['startAppAnalysis','viewAppAnalysis','chooseResourceBatch','openBatchSaved','checkAppAnalysis'])assert(!$(id),'Removed button '+id);
assert(!html.includes('Create initial overview') && !html.includes('Units added later') && !html.includes('Unit packs'),'No overview button and no zero parts');
assert(html.includes('Analyze · 4 calls') && html.includes('Map summary sent to Claude') && /<details class="unit-calls" data-read-scope>/.test(html),'One action with decision facts and a collapsed reading range');
const before=calls.length;
unitHandles['unit-open'].find(b=>b.dataset.unitOpen==='2').onclick();await flush();
html=$('insp').innerHTML;
assert(count('analysis_run_start')===0 && html.includes('AI explanation · 1 call') && html.includes('data-unit-explain="2"'),'Opening a card starts nothing and offers one request');
assert(!calls.slice(before).some(c=>c.command==='analysis_run_start'),'Card open makes no run');
await unitHandles['unit-explain'].find(b=>b.dataset.unitExplain==='2').onclick();await flush();
const intent=calls.find(c=>c.command==='analysis_run_start').args.scope.intent;
assert(intent.task==='full' && !('max_calls' in intent) && JSON.stringify(intent.only)===JSON.stringify([{repository:'service',target:'route:/c'}]) && !intent.renew,'The card sends the only intent with 2 calls');
status=runRecord('running',{intent,unit_board:localBoard()});await AnalysisRun.check();await flush();
assert(!$('startFullAnalysis') && !$('insp').innerHTML.includes('data-unit-explain') || /data-unit-explain="2" disabled/.test($('insp').innerHTML),'Buttons are off while a run is active');
""")

    def test_saved_card_has_no_ask_button_and_a_stale_one_asks_again(self):
        self.check_js(self.LOCAL_BOARD + r"""
serveLocal();status=null;await open();await AnalysisRun.check();await flush();
native=(command,args)=>command==='analysis_run_status'&&args.view==='units'?localBoard():command==='analysis_run_status'&&args.view==='unit'?{repository:'service',commit:'abcd1234ef',configuration:'pin',resource:'/a',files:['a.py'],items:[{name:'List',description:'Lists',file:'a.py',line:1,quote:'def a'}],format:'overview-v1'}:undefined;
unitHandles['unit-open'].find(b=>b.dataset.unitOpen==='0').onclick();await flush();
let html=$('insp').innerHTML;
assert(html.includes('List') && !html.includes('data-unit-explain="0"'),'A saved explanation replaces the button');
""")

    def test_live_card_run_board_has_no_calls_or_modes_and_keeps_the_static_numbers(self):
        self.check_js(self.LOCAL_BOARD + r"""
serveLocal();status=null;await open();await AnalysisRun.check();await flush();
await unitHandles['unit-open'].find(b=>b.dataset.unitOpen==='2').onclick();await flush();
await unitHandles['unit-explain'].find(b=>b.dataset.unitExplain==='2').onclick();await flush();
const intent=calls.find(c=>c.command==='analysis_run_start').args.scope.intent;
assert(intent.only.length===1 && intent.renew===undefined && !('max_calls' in intent),'No renew and no cap with only');
const live=localBoard({calls:{rules:0,labeling:0,structure:0,unit:0,total:0},announced:{total:1},used:{unit:1}});live.repositories[0].units[2][4]='working';
status=runRecord('running',{intent,unit_board:live,input_stats:{calls:1,bytes:5}});await AnalysisRun.check();await flush();
let html=$('insp').innerHTML;
assert($('cancelFullAnalysis') && !$('startFullAnalysis') && html.includes('Analyzing') && !html.includes('max 0'),'Live card run shows working and no empty limit');
status=runRecord('completed',{intent,unit_board:localBoard()});await AnalysisRun.check();await flush();await flush();
html=$('insp').innerHTML;
assert($('startFullAnalysis') && html.includes('Analyze · 4 calls'),'After it ends the main action reads the static board again');
""")

    MAP_BOARD = r"""
const mapBoard=(extra={})=>({repositories:[{repository:'service',units:[
 ['route:/orders','route','/orders',3,'saved','new'],
 ['folder:lib','folder','lib',9,'saved',''],
 ['task:analysis','map','analysis',0,'partial','3/8'],
 ['task:system','system','system',0,'pending',''],
 ['task:groups','groups','groups',0,'unavailable','no screens']],
 coverage:{tracked:30,in_units:26,plain:11,indexed:15,excluded:{secret:1,generated:3},truncated:false}}],
 totals:{units:5,saved:2,partial:1,pending:1,unavailable:1},calls:6,map_calls:4,time_limit_seconds:3600,...extra});
const serveMap=(extra)=>{native=(command,args)=>command==='analysis_run_status'&&args.view==='units'?mapBoard(extra):undefined;};
"""

    def test_board_tolerates_other_responses_and_asks_for_a_refresh(self):
        self.check_js(self.BOARD + r"""
status=null;await open();await AnalysisRun.check();await flush();
assert(!$('insp').innerHTML.includes('unit-board'),'A response that is not a board renders nothing');
native=(command,args)=>{if(command==='analysis_run_status'&&args.view==='units')throw Error('Refresh the local structure before analyzing every unit');};
S.loadToken++;AnalysisRun.syncScope();await open();await AnalysisRun.check();await flush();
assert($('insp').innerHTML.includes('Units are calculated after one refresh') && $('insp').innerHTML.includes('does not call AI') && !$('startFullAnalysis'),'No start before the structure exists');
assert($('refreshForUnits') && $('insp').innerHTML.includes('Refresh and calculate units'),'A plain refresh action is offered');
let refreshed=0;elements.refresh={click(){refreshed++;}};
AnalysisRun.bind();$('refreshForUnits').onclick();assert(refreshed===1,'The action presses the normal refresh');
assert(!calls.some(c=>['analysis_run_start','analysis_request'].includes(c.command)),'Refreshing never starts AI work');
""")

    def test_board_loads_on_first_open_before_the_account_answers_and_when_the_window_shows(self):
        self.check_js(self.BOARD + r"""
serve();status=null;let answer;native=(command,args)=>command==='analysis_providers'?new Promise(r=>answer=r):command==='analysis_run_status'&&args.view==='units'?unitBoard():undefined;
await open();await flush();
assert($('insp').innerHTML.includes('/orders'),'The first open shows the board while the account check is pending');
answer(available);await flush();
document.hidden=true;S.loadToken=2;render();await flush();
const before=calls.filter(c=>c.args && c.args.view==='units').length;
assert(!$('insp').innerHTML.includes('/orders'),'A hidden window reads nothing for the new scope');
document.hidden=false;listeners.visibilitychange();await flush();await flush();
assert(calls.filter(c=>c.args && c.args.view==='units').length===before+1 && $('insp').innerHTML.includes('/orders'),'Showing the window loads the board');
""")

    def test_open_panel_notices_a_run_started_elsewhere_and_shows_its_saved_result(self):
        self.check_js(self.BOARD + r"""
serve();status=null;await open();await AnalysisRun.check();await flush();
assert($('insp').innerHTML.includes('Analyze · 3 calls'),'Idle board before the outside run');
const full=(state,extra)=>({...runRecord(state),intent:{task:'full',targets:[]},repository:'',...extra});
status=full('running',{unit_board:unitBoard({announced:{total:3},used:{labeling:1}})});
await tick();await flush();
assert(calls.some(c=>c.args && c.args.view==='latest'),'The idle panel reads only the latest run id and state');
assert($('insp').innerHTML.includes('cancelFullAnalysis') && $('insp').innerHTML.includes('AI calls 1/3'),'The run started elsewhere shows as running');
status=full('completed',{unit_board:unitBoard({calls:{total:0}})});native=(command,args)=>command==='analysis_run_status'&&args.view==='units'?unitBoard({calls:{total:0}}):undefined;
for(let i=0;i<3;i++)await tick();
assert($('insp').innerHTML.includes('Nothing left to analyze') && !$('insp').innerHTML.includes('Analyze · 3 calls'),'After it finishes, the board shows the saved result');
""")

    def test_a_board_load_for_an_earlier_scope_does_not_block_the_new_one(self):
        self.check_js(self.BOARD + r"""
status=null;let hold=true;const pending=[];
native=(command,args)=>command==='analysis_run_status'&&args.view==='units'?(hold?new Promise(r=>pending.push(r)):unitBoard()):undefined;
await open();await flush();
hold=false;S.lang='ko';S.loadToken=2;render();AnalysisRun.open();await flush();await flush();
pending.forEach(r=>r(unitBoard()));await flush();await flush();
assert($('insp').innerHTML.includes('/orders'),'The new language loads its own board while the old load is still out');
""")

    def test_account_problem_replaces_the_start_and_zero_detailed_is_not_shown(self):
        self.check_js(self.BOARD + r"""
const named=()=>({repositories:[{repository:'service',units:[['folder:a','folder','a',2,'named',''],['folder:b','folder','b',2,'local','']]}],totals:{units:2,named:1,local:1},calls:{rules:0,labeling:1,structure:0,unit:0,total:1}});
native=(command,args)=>command==='analysis_run_status'&&args.view==='units'?named():undefined;
provider={providers:[{provider:'claude',available:false,error_code:'CLI_NOT_INSTALLED'}]};status=null;await open();await flush();
let html=$('insp').innerHTML;
assert(!html.includes('startFullAnalysis') && html.includes('checkFullAccount') && html.includes('Install Claude Code'),'An account problem shows its message and the check in place of the start');
assert(html.includes('Named 1') && !html.includes('Detailed') && html.includes('Folders<b>1/1</b></span>'),'Zero detailed explanations are not shown');
provider=available;$('checkFullAccount').onclick();await flush();
html=$('insp').innerHTML;
assert(html.includes('id="startFullAnalysis"') && !html.includes('checkFullAccount'),'After the account works there is one button');
""")

    def test_short_state_says_reanalysis_when_units_are_outdated(self):
        self.check_js(self.BOARD + r"""
native=(command,args)=>command==='analysis_run_status'&&args.view==='units'?unitBoard({totals:{units:5,saved:1,named:1,working:1,pending:1,stale:1}}):undefined;
status=null;assert(AnalysisRun.shortState()==='','No state before any run');
await open();await flush();
assert(AnalysisRun.shortState()==='Reanalysis needed','Outdated units ask for a new analysis');
native=(command,args)=>command==='analysis_run_status'&&args.view==='units'?unitBoard({totals:{units:5,saved:4,stale:1},calls:{rules:0,labeling:0,structure:0,unit:0,total:0}}):undefined;
await AnalysisRun.check();await flush();
assert(AnalysisRun.shortState()==='','An outdated detailed explanation alone is not a reason to run the analysis again');
""")

    def test_korean_board_uses_plain_labels_without_banned_endings(self):
        self.check_js(self.BOARD + r"""
S.lang='ko';serve();status=null;await open();await AnalysisRun.check();await flush();
const html=$('insp').innerHTML;
for(const word of ['분석 중','설명 없음','자세한 설명 있음','이름·설명 있음','분석하기 · 호출 3회','색인 한도 도달','제외 3'])assert(html.includes(word),'Korean label '+word);
assert(!/해요|이에요|예요|할게요/.test(html),'No informal ending');
""")

    def test_saved_task_and_input_calls_are_distinct_and_intent_is_not_reused(self):
        self.check_js(r'''
const briefing={task:'briefing',targets:[]};S.analysisChoice={task:'briefing_request'};
await flush();status=runRecord('running',{intent:briefing,completed_tasks:[{task:'briefing'}],input_stats:{calls:4,bytes:12000}});
await open();await AnalysisRun.check();await flush();
assert($('insp').innerHTML.includes('1/2 tasks saved'),'Saved task count');
assert($('insp').innerHTML.includes('Input calls: 4'),'Input calls are not saved tasks');
status=runRecord('failed',{intent:briefing});
S.analysisChoice={task:'resource_batch',maxCalls:1};AnalysisRun.open();await flush();
assert($('startAppAnalysis') && !$('retryAppAnalysis'),'Another intent is not offered as this request’s retry');
await $('startAppAnalysis').onclick();await flush();
const args=calls.filter(c=>c.command==='analysis_run_start').at(-1).args;
assert(args.scope.intent.task==='resources' && args.scope.intent.max_calls===1,'The chosen intent reaches native bridge');
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
S.analysisChoice={task:'resource_batch',detailTarget:'',maxCalls:2};await open();await flush();
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
await AnalysisRun.check();assert($('insp').innerHTML.includes('Path groups saved: 2 · Remaining: 1'),'Compact counts without a separate result button');
assert(calls.at(-1).args.view==='progress' && calls.at(-1).args.runId==='run-1','Routine poll only asks for compact progress');
native=(command,args)=>command==='analysis_run_status'?runRecord('completed',{intent,completed_tasks:3,tasks:0}):undefined;
await AnalysisRun.check();assert(calls.filter(c=>c.command==='analysis_run_status' && !String(c.args.view).startsWith('units') && c.args.view!=='signals').at(-1).args.view==='catalog','Terminal transition reads the saved catalog');
''')

    def test_initial_overview_and_full_analysis_have_distinct_explicit_buttons(self):
        self.check_js(r'''
await open();
assert(!$('startFullAnalysis') && $('insp').innerHTML.includes('1 AI call') && $('insp').innerHTML.includes('Create initial overview'),'Scope and call bound visible');
await $('startAppAnalysis').onclick();await flush();
assert(calls.filter(c=>c.command==='analysis_run_start').at(-1).args.scope.intent.task==='overview','Default button requests the bounded overview');
status=null;await AnalysisRun.check();
for(const task of ['analysis_plan','analysis_request','make_system','suggest_groups']){
 S.analysisChoice={task};AnalysisRun.open();await flush();
 assert(!$('startAppAnalysis'),'The map, groups and service structure start only from the board: '+task);
}
''')

    def test_provider_account_and_charge_before_explicit_start(self):
        self.check_js(r'''
await flush();assert(count('analysis_run_status')===1,'Startup recovers status');
assert(count('analysis_run_start')===0 && count('analysis_providers')===0,'Startup cannot launch or probe a CLI');
await open();
assert($('insp').innerHTML.includes('fictional@example.invalid'),'Account visible before start');
assert($('insp').innerHTML.includes('subscription limit'),'Usage visible before start');
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
AnalysisRun.checkAccount();await flush();assert($('startAppAnalysis').disabled,'Signed out cannot start');
S.lang='ko';AnalysisRun.syncScope();renderAgentPrompt();
assert($('insp').innerHTML.includes('구독 계정에 로그인'),'Korean sign-in guidance');
assert(!calls.some(c=>['analysis_run_start','analysis_run_retry'].includes(c.command)),'Account check never starts a run');
''')

    def test_progress_completion_uses_existing_read_without_moving_history(self):
        self.check_js(r'''
const intent={task:'briefing',targets:[]};S.analysisChoice={task:'briefing_request'};
await open();await $('startAppAnalysis').onclick();await flush();
status=runRecord('saving',{intent,completed_tasks:[{task:'overview'}],tasks:[{task:'briefing'}],current_task:{task:'briefing'}});
await tick();assert($('insp').innerHTML.includes('1/2'),'Completed plus pending task count');
assert($('insp').innerHTML.includes('Saving…'),'Saving is visible');
status=runRecord('completed',{intent,tasks:[],completed_tasks:[{task:'overview'},{task:'briefing'}],current_task:null});
await tick();assert(reads===1,'Completion reads saved results once');
assert([...timers.values()].every(t=>t.ms>=4000),'Completed runs stop polling; only the slow check for a run started elsewhere stays');
assert(S.changes===baseline && S.settings===settings && S.chi===3,'Existing read preserves history, comparison and selection');
assert($('viewAppAnalysis'),'A single-task result keeps its one way to open');
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
 S.lang='en';AnalysisRun.checkAccount();await flush();
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
assert([...timers.values()].every(t=>t.ms>=4000),'Cancelled run stops polling; only the slow check for a run started elsewhere stays');
provider={providers:[{provider:'claude',available:true,authenticated:true,account:{...account,email:'new@example.invalid'}}]};
AnalysisRun.checkAccount();await flush();
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

    def test_saved_partial_overview_reopens_after_cancel_and_hides_stale_configuration(self):
        self.check_js(r'''
await open();
const group={repository:'service',commit:'abcd1234ef',configuration:'pin',files:['src/cli'],items:[{name:'Save',file:'src/cli',line:3,quote:'<save>'}]};
S.projectInfo={repositories:[{id:'service',fingerprint:'pin',commits:{dev:'abcd1234'}}]};
status=runRecord('cancelled',{saved_overviews:[group],cancel_requested:true});
await AnalysisRun.check();
assert($('savedOverview0') && !$('viewAppAnalysis'),'Partial sample is available without completing a map task');
await $('savedOverview0').onclick();
assert($('insp').innerHTML.includes('Sampled files 1') && $('insp').innerHTML.includes('&lt;save>'),'Scoped coverage and escaped evidence');
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
await AnalysisRun.check();assert(!$('insp').innerHTML.includes('<b>GET /runs</b>'),'Grouped evidence starts collapsed');featureButtons[0].onclick();const grouped=$('insp').innerHTML;
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

    def test_entry_points_offer_both_app_run_and_existing_mcp_copy(self):
        self.assertIn('<script src="analysis-run.js"></script>', UI)
        self.assertIn('id="automaticAnalysis"', UI)
        self.assertLess(UI.index("AnalysisRun.overviewHtml()"),UI.index('id="automaticAnalysis"'))
        self.assertIn('id="cpAgent"', UI)
        self.assertIn('data-analysis-task=', UI)
        for entry in ('requestBriefing', 'mk'):
            line = next(line for line in UI.splitlines() if f"$('{entry}').onclick=" in line)
            self.assertIn('openAnalysisPanel(', line)
        self.assertIn("requestAgentAction('analysis_plan',{},true)", UI)


if __name__ == '__main__':
    unittest.main()
