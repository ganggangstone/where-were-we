"""Live control checks use fake native actions and synthetic maps, never AI."""
import json
import socket
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import mapcore
import app_control

class Control(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        p=patch.object(mapcore,'ROOT',str(self.root));p.start();self.addCleanup(p.stop)
    def test_closed_app_is_explicit_and_cannot_report_success(self):
        self.assertEqual(app_control.command('state')['status'],'app_closed')
    def test_real_socket_protocol_returns_applied_state_and_does_not_resubmit_for_outcome(self):
        path='/tmp/www-control-test-'+self.root.name
        server=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);server.bind(path);server.listen()
        self.addCleanup(lambda:Path(path).unlink(missing_ok=True));self.addCleanup(server.close)
        (self.root/'.app-control.json').write_text(json.dumps({'protocol':1,'socket':path,'instance':'fixture'}));calls=[]
        def serve():
            for index in range(3):
                conn,_=server.accept()
                with conn:
                    with conn.makefile('rb') as f:args=json.loads(f.readline())
                    calls.append(args)
                    result={'id':args.get('id') or args.get('command',{}).get('id'),'status':'queued' if index==0 else 'completed','result':{'ok':True,'state':{'selection':['screen:upload']}}}
                    conn.sendall((json.dumps(result)+'\n').encode())
        thread=threading.Thread(target=serve,daemon=True);thread.start()
        value=app_control.command('select',{'target':'screen:upload','revision':'synthetic'},wait=1)
        self.assertEqual(value['status'],'completed');self.assertEqual(value['result']['state']['selection'],['screen:upload'])
        self.assertEqual(app_control.outcome(value['id'])['status'],'completed');thread.join(2)
        self.assertEqual([x['op'] for x in calls],['submit','result','result'])
    def test_real_browser_controls_synthetic_map_and_reads_mouse_selection(self):
        import subprocess,re
        chrome=Path('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome')
        if not chrome.exists():self.skipTest('Chrome is required')
        folder=Path(__file__).resolve().parents[1];source=(folder/'ui/index.html').read_text()
        script=source.split('<script>',1)[1].split('</script>',1)[0].split("$('q').oninput",1)[0]
        script+=source[source.index('function renderAgentPrompt() {'):source.index("$('agent').onclick")]
        controller=(folder/'ui/control.js').read_text()
        bootstrap=r'''
const calls=[];
// Hidden native webviews can suspend animation frames.
window.requestAnimationFrame=()=>0;
window.__TAURI__={core:{invoke:async(command,args)=>{
 calls.push({command,args});
 if(command==='control_focus')return;
 if(command==='save_settings')return args.json;
 if(command==='read_project')return JSON.stringify(bundle);
 if(command==='refresh')return 'web: refreshed';
 if(command==='make_system')return JSON.stringify({handoff:'Read synthetic code',requirements:[]});
 if(command==='app_update_status')return {phase:'idle'};
 throw Error('Unexpected native action '+command);
}}};
'''
        checks=r'''
(async()=>{
 const assert=(v,m)=>{if(!v)throw Error(m);};
 const route={file:'web/server.py',function:'upload',method:'POST',path:'/upload',flow:{name:'Upload request',steps:[{lane:'서버',text:'Validate upload',file:'web/server.py',line:2,quote:'validate(upload)'}]},tables:['web::uploads'],externals:[],line:2,tests:[],services:[],mounted:true,repository:'web'};
 const screen={path:'web::/upload',heading:'Upload',file:'web/src/Upload.tsx',actions:[],api_functions:[],redirect:false,repository:'web'};
 const m={repo:'/synthetic',commit:'synthetic1',screens:[screen,{...screen,path:'api::/upload',repository:'api',file:'api/src/Upload.tsx'}],api_functions:[],backend_routes:[route],backend_routes_without_screen:[route],models:{'web/models.py':'web::uploads'},file_screens:{},unresolved_calls:[],coverage:{}};
 const system={nodes:[{id:'web::server',name:'Upload',kind:'program',uses:[],copies:[],origin:'repo',what:'Handles uploads',code:['web'],tables:['web::uploads'],externals:[],unknown:[],ev:[]},{id:'api::worker',name:'Upload',kind:'program',uses:[],copies:[],origin:'repo',what:'Processes uploads',code:['api'],tables:[],externals:[],unknown:[],ev:[]}],links:[{from:'web::server',to:'api::worker',label:'Queues uploads',sure:'code',ev:[]}],externals:[],unknown:[],others:[]};
 const jobs={nodes:{'api::worker':{jobs:[{name:'Retry upload',trigger:'queue',what:'Retries failed uploads',routes:[],steps:[],ev:[]}]}}};
 const bundle={dev:m,main:{...m,commit:'synthetic2'},project:{name:'demo',repositories:[{id:'web',name:'Web',collected:true,commits:{dev:'synthetic1'},generation:'gen1'},{id:'api',name:'API',collected:true,commits:{dev:'synthetic1'},generation:'gen1'}],shared_data:[]},status:{},groups:{names:{},request_names:{},groups:[]},system,jobs,flows:{routes:{}},changes:{entries:[]},branch_details:{dev:{system,jobs,groups:{names:{},request_names:{},groups:[]},flows:{routes:{}}}},briefings:{}};
 window.bundle=bundle;
 S.project='demo';S.repository='';S.branch='dev';S.maps={dev:bundle.dev,main:bundle.main};S.projectInfo=bundle.project;S.system=system;S.jobs=jobs;S.groups=bundle.groups;S.flows=bundle.flows;S.changes=bundle.changes;S.status={};S.view='map';
 // Existing renderer and mouse handlers run; only graph layout is irrelevant here.
 drawWires=()=>{};render();
 const targets=await applyAppCommand({action:'targets',arguments:{query:'Upload'}});
 assert(targets.output.targets.filter(t=>t.kind==='program').length===2,'Duplicate names remain disambiguated');
 const select=async(kind,predicate=()=>true)=>{const t=(await applyAppCommand({action:'targets',arguments:{}})).output.targets.find(t=>t.kind===kind && predicate(t));assert(t,'Missing '+kind);return applyAppCommand({action:'select',arguments:{project:'demo',repository:'',branch:'dev',target:t.id,revision:(await controlState()).revision}});};
 await select('screen',t=>t.key==='web::/upload');assert(S.sel==='web::/upload' && S.view==='focus','Screen selection and relations');
 await select('feature');assert(S.view==='feat' && S.feat===0,'Actual visible feature groups use stable IDs');
 await select('program',t=>t.key==='api::worker');assert(S.node==='api::worker' && S.view==='sys','Program selection');
 await select('job');assert(document.querySelector('[data-control-detail]')?.textContent.includes('Retry upload'),'Job details are visible');
 await select('connection');assert(document.querySelector('[data-control-detail]')?.textContent.includes('Queues uploads'),'Connection details are visible');
 await select('data');assert(S.focus.id==='web::uploads','Data relationships');
 await select('request');await applyAppCommand({action:'step',arguments:{index:1}});assert(document.querySelector('.step.cur')?.textContent.includes('Validate upload'),'Request step and source evidence are visible');assert(S.focus.t==='route' && document.getElementById('insp').textContent.includes('/upload'),'Orphan request is visible');
 const before=await controlState();m.commit='changed';
 const oldIDs=controlTargets().map(t=>t.id);system.nodes.reverse();assert(JSON.stringify(controlTargets().map(t=>t.id).sort())===JSON.stringify(oldIDs.sort()),'Reordering nodes preserves target IDs');
 let stale=false;try{await applyAppCommand({action:'select',arguments:{project:'demo',repository:'',branch:'dev',target:before.selection[0],revision:before.revision}});}catch(e){stale=e.code==='stale_revision';}assert(stale,'Stale revision is explicit');
 let missing=false;try{await applyAppCommand({action:'select',arguments:{project:'demo',repository:'',branch:'dev',target:'absent',revision:(await controlState()).revision}});}catch(e){missing=e.code==='missing_target';}assert(missing,'Missing target is explicit');
 await applyAppCommand({action:'navigate',arguments:{project:'demo',repository:'',branch:'dev',view:'map'}});
 document.querySelector('[data-scr="api::/upload"]').click();
 const actual=await applyAppCommand({action:'state',arguments:{}});assert(actual.state.selection.some(id=>id.includes('api::/upload')),'Read actual mouse selection');
 const changes=JSON.stringify(S.changes);
 const branch=await applyAppCommand({action:'targets',arguments:{branch:'main'}});assert(branch.state.branch==='main' && document.querySelector('#branch [data-b=main]').classList.contains('on'),'Branch change is actually rendered');
 await applyAppCommand({action:'navigate',arguments:{branch:'dev',view:'map'}});
 let noUpdate=false;try{await applyAppCommand({action:'start_update',arguments:{}});}catch(e){noUpdate=e.code==='no_update_available';}assert(noUpdate,'No update must not report successful installation');
 const prepared=await applyAppCommand({action:'prepare_analysis',arguments:{project:'demo',repository:'web',branch:'dev',task:'system'}});assert(prepared.output.prepared && !prepared.output.executed,'Preparing a request is not executing analysis');
 S.analysisRequest=null;S.chi=3;const previousChanges=S.changes;
 await applyAppCommand({action:'read_results',arguments:{}});assert(S.chi===3 && S.changes===previousChanges,'Result reads keep change history and selected entry');
 await applyAppCommand({action:'language',arguments:{lang:'en'}});assert(S.lang==='en','Language uses existing action');
 await applyAppCommand({action:'settings',arguments:{value:{open_refresh:false,since:'time',since_time:'2026-10-01T18:30'}}});assert(S.settings.since==='time','Comparison settings saved');
 assert(JSON.stringify(S.changes)===changes,'Setting state does not silently refresh changes');
 await applyAppCommand({action:'clear',arguments:{}});assert((await controlState()).selection.length===0,'Clear highlighting');
 assert(!calls.some(c=>c.command==='refresh'),'Navigation and selections never refresh');
 document.body.dataset.controlTest='passed';
})().catch(error=>{document.body.dataset.controlTest='failed';const p=document.createElement('pre');p.textContent=error.stack;document.body.append(p);});
'''
        page=re.sub(r'<script>.*?</script>',lambda m:'<script>'+bootstrap+script+controller+checks+'</script>',source,count=1,flags=re.S)
        target=self.root/'control-check.html';target.write_text(page)
        syntax=subprocess.run(['/opt/homebrew/bin/node','--check'],input=bootstrap+script+controller+checks,capture_output=True,text=True)
        self.assertEqual(syntax.returncode,0,syntax.stderr)
        result=subprocess.run([str(chrome),'--headless','--disable-gpu','--no-first-run','--disable-background-networking','--disable-component-update','--no-default-browser-check','--user-data-dir='+str(self.root/'chrome'),'--virtual-time-budget=8000','--dump-dom',target.as_uri()],capture_output=True,text=True,timeout=30)
        self.assertTrue('data-control-test="passed"' in result.stdout,str(re.findall(r'<pre>(.*?)</pre>',result.stdout,re.S))[-2000:])

    def test_standard_mcp_tools_are_vendor_independent_and_closed_app_is_not_completed(self):
        import asyncio,os
        from mcp import ClientSession,StdioServerParameters
        from mcp.client.stdio import stdio_client
        async def exercise():
            params=StdioServerParameters(command=sys.executable,args=['-I','-B',str(Path(app_control.__file__).with_name('mcp_server.py'))],env=dict(os.environ,WHERE_WERE_WE_ROOT=str(self.root),PATH='/usr/bin:/bin'))
            async with stdio_client(params) as streams:
                async with ClientSession(*streams) as session:
                    await session.initialize()
                    names={t.name for t in (await session.list_tools()).tools}
                    self.assertTrue({'app_state','app_targets','app_control','app_command_result'}<=names)
                    result=await session.call_tool('app_control',{'action':'catalog'})
                    self.assertFalse(result.is_error);catalog=json.loads(result.content[0].text)
                    self.assertTrue({'select','configure','settings','prepare_analysis','refresh','start_update'}<=catalog.keys())
                    result=await session.call_tool('app_state',{})
                    self.assertEqual(json.loads(result.content[0].text)['status'],'app_closed')
                    result=await session.call_tool('app_control',{'action':'select','arguments_json':'[]'})
                    self.assertEqual(json.loads(result.content[0].text)['status'],'invalid_arguments')
        asyncio.run(exercise())
