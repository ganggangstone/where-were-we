"""Exercise stored and fresh maps with a detached WebKit view and fake native calls."""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from test_ui_flows import BOOTSTRAP, ROOT


@unittest.skipUnless(sys.platform == 'darwin' and shutil.which('swiftc'), 'Requires Swift and WebKit')
class RefreshFirstWebKit(unittest.TestCase):
    def test_local_first_and_optional_evidenced_ai(self):
        checks = r"""
(async()=>{
 const check=(value,why)=>{if(!value)throw Error(why)};
 for(let i=0;i<100&&!window.appControlReady;i++)await new Promise(r=>setTimeout(r,20));
 const pin='aaaaaaaa1111', file='worker.cjs';
 const index={repository:'web',commit:pin,version:11,project_description:{text:'Build <small> modules.',file:'README.md',line:3},coverage:{indexed_files:1,candidate_files:1,languages:{javascript:{indexed_files:1,candidate_files:1}}},
   files:[{file,language:'javascript',declarations:[{kind:'function',name:'work',line:1}]}],imports:[],
   service_flow:{connections:[],coverage:{requests:0,routes:0},feature_groups:[]}};
 // These checks read the structure lists, which the screen folds under 「자세한 목록」.
 S.listsOpen=true;
 window.mutateBundle=b=>{b.dev.structure_indexes=[index];b.project.repositories[0].fingerprint='pin'};
 await doRefresh();
 const purpose=()=>$('map').querySelector('[data-project-purpose]');
 check(purpose().querySelector('summary').textContent==='Build <small> modules.' && !purpose().querySelector('small') && !purpose().open,'Document text is shown verbatim before source details');
 purpose().querySelector('summary').click();check(purpose().innerText.includes('README.md:3') && purpose().innerText.includes(pin),'The literal description retains its pinned citation');
 check(S.view==='sys' && $('moduleDetails') && !$('moduleDetails').open,'Module connections stay collapsed without groups');$('moduleDetails').open=true;check($('map').innerText.includes('work'),'A CLI refresh must open local declarations');
 check(!$('map').querySelector('[data-http-flow]') && !$('automaticAnalysis'),'Empty HTTP graph and optional AI stay hidden');
 check(!calls.some(c=>['analysis_run_start','analysis_plan','analysis_providers'].includes(c.command)),'Refresh must not prepare AI');
 S.project=null;S.view='changes';await loadProject('First');
 check(S.view==='sys' && !$('moduleDetails').open,'Module connections are collapsed');$('moduleDetails').open=true;check($('map').innerText.includes('worker.cjs'),'Opening a saved local map shows its structure');
 const crossMap=M();const serverPin='bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb',clientPin='aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
 crossMap.repositories=[{id:'web',path:'/fictional/web'},{id:'api',path:'/fictional/service'}];
 crossMap.cross_repository_connections=[{method:'GET',path:'/cross',basis:'configured',client:{repository:'web',commit:clientPin,file:'src/shared file.js',line:4},server:{repository:'api',commit:serverPin,file:'src/shared file.js',line:8,function:'serve'}}];
 render();const cross=$('map').querySelector('[data-cross-connection]');cross.open=true;
 const anchors=[...cross.querySelectorAll('a')];check(cross.querySelector('code[title="'+serverPin+'"]') && cross.querySelector('code[title="'+clientPin+'"]'),'Each side of a cross-repository match carries its own pin');
 check(anchors[0].dataset.url==='zed://file/fictional/web/src/shared%20file.js:4' && anchors[1].dataset.url==='zed://file/fictional/service/src/shared%20file.js:8','Identically named paths resolve under their own repository');
 anchors[1].dispatchEvent(new MouseEvent('click',{bubbles:true,cancelable:true}));check(calls.at(-1).command==='open_url' && calls.at(-1).args.url===anchors[1].dataset.url,'Server proof opens its own working path');
 delete crossMap.cross_repository_connections;
 const wsIndex=crossMap.structure_indexes[0];wsIndex.workspace_packages=[{name:'@sample/core',directory:'packages/core',file:'packages/core/package.json',line:2,description:'Main <package>.',description_line:3,workspace:{file:'pnpm-workspace.yaml',line:4}}];
 wsIndex.workspace_packages.push(...Array.from({length:8},(_,i)=>({...wsIndex.workspace_packages[0],name:'lib'+i})));
 wsIndex.workspace_dependencies=[{source:'@sample/core',target:'lib7',kind:'devDependencies',specifier:'workspace:*',file:'packages/core/package.json',line:12}];
 wsIndex.coverage.workspace_manifests_matched=12;
 const inventories=crossMap.inventories;crossMap.inventories=[{repository:wsIndex.repository,commit:wsIndex.commit,paths:['packages/core/package.json'],files:1}];render();
 check($('map').querySelector('[data-workspace-packages] h2').innerText.endsWith('9/12'),'Partial verified workspaces include the manifest candidate count');
 const w=$('map').querySelector('[data-workspace-packages] details');check(w && !w.open && w.innerText.includes('Main <package>.'),'Workspace summary uses literal package metadata');
 w.open=true;check(w.innerText.includes('pnpm-workspace.yaml:4') && w.innerText.includes('packages/core/package.json:2'),'Membership and package declaration have their own citations');
 const deps=w.querySelector('details');check(deps && !deps.open,'Dependency evidence starts collapsed');
 deps.open=true;check(deps.innerText.includes('devDependencies · workspace:*') && deps.innerText.includes('packages/core/package.json:12'),'Dependency manifest declaration stays distinct from runtime calls');
 deps.querySelector('[data-package-target]').click();const destination=$('map').querySelector('[data-workspace-package="lib7"]');check(destination.open && document.activeElement===destination.querySelector('summary'),'Dependency opens and focuses its package across pages');
 destination.querySelector('[data-package-folder]').click();check($('map').querySelector('[data-inspect-directory="packages/core"]'),'Package folder opens in the existing repository inventory');
 delete wsIndex.workspace_packages;crossMap.inventories=inventories;
 index.files=Array.from({length:160},(_,i)=>({file:'module'+i+'.cjs',language:'javascript',declarations:[]}));
 index.imports=[{file:'module0.cjs',target:'module150.cjs',line:1},{file:'module45.cjs',target:'module150.cjs',line:3}];
 index.commit='bbbbbbbb2222';await doRefresh();
 check($('moduleFile').value==='module150.cjs' && $('moduleFile').options.length<=64,'Large maps open a highly referenced module with a bounded picker');
 $('moduleRange').selectedIndex=0;$('moduleRange').dispatchEvent(new Event('change'));
 check($('moduleFile').value==='module0.cjs','Other ranges remain reachable');
 $('map').querySelector('[data-module-neighbor]').click();
 check($('moduleFile').value==='module150.cjs' && $('moduleRange').selectedIndex===2,'Import navigation crosses ranges without losing the destination');
 index.commit=pin;
 index.cli_entries=[{command:'alpha',kind:'python_script',file:'pyproject.toml',line:8,target:'tool/cli.py',symbol:'main',target_line:14},
    ...Array.from({length:12},(_,i)=>({command:'tool-'+i,kind:'npm_bin',file:'package.json',target:'bin/tool.js'})),{command:'alpha run',kind:'cobra_subcommand',description:'Run <task>',description_line:17,handler_line:22,file:'parent.go',line:9,target:'child.go',target_line:16}];
 await doRefresh();
 const cli=()=>$('map').querySelector('[data-cli-entries]');
 check(cli().querySelectorAll('details').length===12 && !$('moduleDetails').open,'CLI commands precede module internals');
 check(!$('map').querySelector('[data-readme-features]'),'No empty section on snapshots without feature documentation');
 index.documented_features=[{text:'Lists <entries>.',file:'README.md',line:12}];await doRefresh();
 const documented=$('map').querySelector('[data-readme-features]');
 check(documented && !documented.open && cli().compareDocumentPosition(documented) & Node.DOCUMENT_POSITION_FOLLOWING,'Documented features come after verified CLI commands');
 documented.querySelector('summary').click();check(documented.innerText.includes('Lists <entries>.') && !documented.querySelector('entries') && documented.innerText.includes('README.md:12') && documented.innerText.includes(index.commit.slice(0,12)),'README wording, exact source and commit remain available');
 const firstCommand=cli().querySelector('details');firstCommand.querySelector('summary').click();
 check(firstCommand.innerText.includes('pyproject.toml:8') && firstCommand.innerText.includes('tool/cli.py:14') && firstCommand.innerText.includes('main'),'Python command shows actual registration and callable');
 cli().querySelector('[data-cli-page="1"]').click();const npm=cli().querySelector('details');npm.querySelector('summary').click();
 check(npm.innerText.includes('tool-11') && npm.querySelectorAll('a')[1].dataset.url.endsWith('/bin/tool.js') && !npm.innerText.includes('undefined'),'Missing locations remain file-only');
 const cobra=cli().querySelectorAll('details')[1];cobra.open=true;
 check(cobra.innerText.includes('Run <task>') && !cobra.querySelector('task') && ['parent.go:9','child.go:16','child.go:17','child.go:22'].every(p=>cobra.innerText.includes(p)),'Cobra source, child declaration and literal description have independent evidence');
 check(!calls.some(c=>c.command==='analysis_run_start'),'Command inspection has no model call');
 index.cli_entries=[];
 index.cli_entries=[];index.files=[{file:'main.go',language:'go',declarations:[]},{file:'pkg/a.go',language:'go',declarations:[]}];index.imports=[];index.commit='go-edges';
 index.package_imports=[{file:'main.go',line:4,package:'example.org/pkg',directory:'pkg',members:['pkg/a.go','pkg/b.go'],member_count:3}];
 await doRefresh();$('moduleDetails').open=true;const pkg=$('map').querySelector('[data-go-package]');pkg.querySelector('summary').click();
 check(pkg.innerText.includes('2/3') && pkg.innerText.includes('main.go:4') && pkg.innerText.includes('pkg/b.go'),'Source import and bounded package membership are separate');
 check(pkg.querySelector('a[data-url$="/pkg/b.go"]'),'Unindexed package members point to their working files without fake line numbers');
 pkg.querySelector('[data-module-neighbor]').click();check($('moduleFile').value==='pkg/a.go','Indexed package member opens its module');
 index.package_imports=[];index.commit=pin;
 const client={file:'client.js',line:5,quote:'fetch("/items")'},server={file:'api.py',line:9,quote:'@router.get("/items")',function:'items'};
 const edge={id:1,method:'GET',path:'/items',client,server,data_steps:[{operation:'read',model:'Item',file:'api.py',line:11,evidence:[]}]};
 index.service_flow={connections:[edge,{...edge,path:'/profiles',data_steps:[]}],feature_groups:[{resource:'/items',connection_indexes:[0]},{resource:'/profiles',connection_indexes:[1]}],coverage:{requests:2,routes:2,unresolved_requests:0}};
 await doRefresh();check($('map').querySelector('[data-local-resource]'),'Local resource groups appear first');
 $('map').querySelector('[data-local-resource="/items"]').click();
 const trace=$('map').querySelector('.flow-trace');
 check([...trace.children].map(e=>e.dataset.traceStage).join(',')==='client,request,server,data' && trace.lastElementChild.innerText.includes('Item'),'Only evidenced stages appear and repeated model reads share a node');
 index.service_flow.registered_routes=[{...edge},...Array.from({length:9},(_,i)=>({method:'GET',path:'/internal/'+i,framework:i===8?'next_app_router':undefined,server:{file:i===8?'app/api/internal/route.ts':'api.py',function:'handler'+i,line:20+i},mounts:i===8?[{file:'package.json',line:26}]:[]}))];
 index.service_flow.coverage.routes=10;await doRefresh();
 const routes=()=>$('registeredRoutes');routes().open=true;
 check(!$('routeArea'),'Short route lists omit the area picker');
 const registered=index.service_flow.registered_routes;
 index.service_flow.registered_routes=[...registered,...Array.from({length:10},(_,i)=>({method:'GET',path:'/api/v2/teams/'+i,server:{file:'teams.py',line:i+5,function:'list'}}))];
 index.service_flow.registered_route_groups=Array.from({length:10},(_,i)=>({resource:'/api/v2/teams/'+i,registered_route_indexes:[registered.length+i]}));
 await doRefresh();const chooseArea=value=>{const menu=$('routeArea');menu.value=value;menu.dispatchEvent(new Event('change'));};
 check($('routeArea').value==='' && [...$('routeArea').options].some(o=>o.text.endsWith('/api/v2/teams · 10')),'Versioned prefix and distinct standalone count');
 check(!routes().querySelector('[data-route-page]') && routes().querySelector('[data-route-area="/api/v2/teams"] summary').textContent.endsWith('· 10'),'Long route lists group by area with counts instead of pages');
 chooseArea('/api/v2/teams');check(routes().querySelectorAll('[data-registered-route]').length===10 && routes().innerText.includes('/api/v2/teams/9'),'One area lists all its routes');
 $('explainRouteArea').click();
 check(S.analysisChoice.area.resources.length===10 && S.analysisChoice.area.commit===index.commit && S.analysisChoice.maxCalls===10 && $('resourceLimits').innerText.includes('10') && !$('chooseResourceBatch') && !calls.some(c=>c.command==='analysis_run_start'),'Area preview binds all pages, commit and cost before any model call');
 S.agentPrompt=null;S.analysisChoice=null;S.agentPurpose=null;index.service_flow.registered_route_groups=[];AnalysisRun.syncScope();
 chooseArea('');check(routes().querySelector('[data-route-area="/internal"]') && !routes().querySelector('[data-route-area][open]'),'All areas return to the closed groups');
 index.service_flow.registered_routes=registered;await doRefresh();routes().open=true;
 check(routes().querySelectorAll('[data-registered-route]').length===9 && !routes().innerText.includes('/items'),'Registered routes page omits already connected endpoints');
 const route=[...routes().querySelectorAll('[data-registered-route]')].at(-1);
 check(route.querySelector('[data-trace-stage="server"]').textContent==='handler8' && !route.querySelector('[data-trace-stage="client"]') && route.innerText.includes('app/api/internal/route.ts:28'),'A standalone server handler has its own source and no invented client');
 check(route.innerText.includes(tr('Next.js 파일 경로')) && route.innerText.includes('package.json:26') && route.innerText.split('app/api/internal/route.ts:28').length===2,'Filesystem provenance identifies the route file and supporting package evidence once');
 window.runningAnalysis={id:'saved',state:'completed',project:'First',repository:'',branch:'dev',lang:S.lang,intent:{task:'overview',targets:[]},completed_tasks:[],tasks:[],saved_overviews:[{
  repository:'web',configuration:'pin',commit:pin,format:'overview-v1',files:[client.file,server.file],
  scope_coverage:{selected:['/items'],total:2},items:[{name:'Browse',description:'Read stored items.',...client}],connections:[edge],feature_groups:[{name:'Saved items',connection_ids:[1]}]}]};
 Object.defineProperty(document,'hidden',{configurable:true,value:false});
 S.agentPurpose='analysis';S.agentPrompt='';renderAgentPrompt();await AnalysisRun.check();
 check(!$('automaticAnalysis').open && $('insp').innerText.includes('Saved items'),'Optional saved group appears without opening AI controls');
 $('toggleAutomaticAnalysis').click();S.analysisChoice={task:'resource_batch',detailTarget:'',maxCalls:2};AnalysisRun.syncScope();renderAgentPrompt();
 check($('automaticAnalysis').open && $('resourceLimits').innerText.includes('2') && !calls.some(c=>c.command==='analysis_run_start'),'Explicit batch preview is visible before any model call');
 S.analysisChoice=null;S.automaticPanelOpen=false;AnalysisRun.syncScope();await new Promise(r=>setTimeout(r,20));await AnalysisRun.check();renderAgentPrompt();
 const button=$('insp').querySelector('[data-overview-feature]');button.click();
 const storage=$('insp').querySelector('[data-flow-storage] details');check(storage,'Opening the saved feature shows its model step');
 storage.querySelector('summary').click();check(storage.open && storage.innerText.includes('api.py:11'),'Model citation remains discoverable');
 const saved=window.runningAnalysis.saved_overviews[0];
 saved.items[0].evidence=[{file:'form.js',line:7,quote:'const value = form.value;'}];
 await AnalysisRun.check();const evidence=$('insp').querySelector('section.sect > [data-claim-evidence]');
 check(evidence && !evidence.open && evidence.querySelector('summary').innerText.includes('2'),'Multi-line claim keeps citations behind a disclosure');
 evidence.open=true;check(evidence.innerText.includes('form.js:7') && evidence.innerText.includes('const value = form.value;') && evidence.innerText.includes(saved.items[0].file+':'+saved.items[0].line),'Both the primary and supplementary claim sites remain available');
 saved.cli_entries=[{kind:'cobra_subcommand',command:'tool <open>',description:'Read a file',registration:{file:'root.go',line:4,quote:'cmd.AddCommand(open)'},target_file:'open.go',target_evidence:{file:'open.go',line:12,quote:'Use: "open"'},description_evidence:{file:'open.go',line:13,quote:'Short: "Read a file"'}},{kind:'npm_bin',command:'runner',registration:{file:'package.json',line:3,quote:'"bin": "./run.js"'},target_file:'run.js'}];
 await AnalysisRun.check();const commands=$('insp').querySelectorAll('[data-saved-command]');commands.forEach(cmd=>cmd.open=true);
 check(commands[0].innerText.includes('root.go:4') && commands[0].innerText.includes('open.go:13') && !commands[0].querySelector('open'),'CLI declaration and description are cited and escaped');
 check(commands[1].innerText.includes('run.js') && !commands[1].innerText.includes('run.js:'),'Manifest-only command target has no invented line');
 delete saved.cli_entries;
 saved.workspace_packages=[{name:'sample',registration:{file:'core/package.json',line:2,quote:'"name":"sample"'},workspace:{file:'package.json',line:9,quote:'"packages/*"'}}];
 saved.workspace_dependencies=[{source:'sample',target:'util',kind:'dependencies',specifier:'workspace:*',evidence:{file:'core/package.json',line:10,quote:'"util":"workspace:*"'}}];saved.workspace_coverage={verified_packages:39};
 await AnalysisRun.check();const samplePackage=$('insp').querySelector('[data-saved-package]');samplePackage.open=true;
 check(samplePackage.parentElement.querySelector('h4').innerText.includes('1/39') && samplePackage.innerText.includes('package.json:9') && samplePackage.innerText.includes('core/package.json:10') && samplePackage.innerText.includes('"util":"workspace:*"'),'Stored package sample and dependency proof retain verified counts and citations');
 delete saved.workspace_packages;delete saved.workspace_dependencies;delete saved.workspace_coverage;
 const savedEdge=window.runningAnalysis.saved_overviews[0].connections[0];
 savedEdge.details=[{kind:'action',event:'onSubmit',label:'Add',evidence:[{file:'form.js',line:4,quote:'onSubmit={add}'}]},
  {kind:'data',model:'Item',operation:'read',evidence:[{file:'api.py',line:11,quote:'select(Item)'},{file:'api.py',line:11,quote:'select(Item)'}]}];
 savedEdge.details.push({kind:'conditional_filter',model:'Item',when:false,evidence:[{file:'api.py',line:7,quote:'if user.is_admin:'},{file:'api.py',line:13,quote:'Item.owner == user.id'}]});
 savedEdge.basis='declared_defaults';
 const live=S.maps.dev.structure_indexes;S.maps.dev.structure_indexes=[];
 await AnalysisRun.check();
 const filter=$('insp').querySelector('[data-saved-filter]');check(filter && !filter.open && filter.innerText.includes(S.lang==='en'?'When false':'조건이 거짓일 때'),'Saved condition preserves false polarity');filter.open=true;
 check(filter.innerText.includes('if user.is_admin:') && filter.innerText.includes('Item.owner == user.id'),'Condition and query predicate keep separate citations');
 const replay=$('insp').querySelector('[data-flow-storage] details');replay.open=true;
 check(replay.innerText.includes('select(Item)') && replay.innerText.split('api.py:11').length===2 && $('insp').querySelector('[data-flow-actions] summary').textContent==='Add','Verified stages reopen without local index or duplicate citations');
 check($('insp').innerText.includes(S.lang==='en'?'Matches configured client and server defaults':'설정·클라이언트 기본값에서 일치'),'Stored conditional basis survives reopening');
 S.maps.dev.structure_indexes=live;await AnalysisRun.check();
 const scopePicker=$('overviewLocalScope0');
 check(scopePicker && scopePicker.options.length===1 && scopePicker.value==='/profiles' && $('insp').innerText.includes('1/2'),'Only unreviewed local scopes are offered');
 $('overviewOpenScope0').click();
 check(S.view==='sys' && $('map').querySelector('[data-local-resource="/profiles"]').getAttribute('aria-expanded')==='true','Open the exact local group from a sampled overview');
 check(!calls.some(c=>c.command==='analysis_run_start'),'Viewing saved evidence starts no AI');
 check(!$('flowFeature') && !$('flowProof').open && $('map').querySelector('[data-flow-operation]'),'Operations precede closed technical evidence');
 check($('flowSources') && !$('flowSources').open && $('map').querySelector('.flow-trace').innerText.includes('client.js'),'Group shows connected code while documentation and module counts stay closed');
 for(const [ko,en] of [['기능 (베타)','Features (beta)'],['AI 설명 (베타)','AI explanation (beta)'],['문서·모듈','Docs and modules'],['워크스페이스 패키지','Workspace packages'],['코드 위치','Code location'],['모든 경로','All paths'],['저장된 페이지','Saved pages'],['미저장 페이지로','Go to unsaved page'],['호출 흐름','Request flow'],['코드가 맡은 일','What the code does']]){
   const old=S.lang;S.lang='en';check(tr(ko)===en,'English '+ko);S.lang=old;
 }
 $('flowProof').querySelector('summary').click();check($('flowProof').open && $('flowProof').innerText.includes('client.js:5'),'Endpoint evidence opens on demand');
 $('explainLocalScope').click();await new Promise(r=>setTimeout(r,30));
 check($('insp').innerText.includes('/profiles') && $('overviewLimits') && $('startAppAnalysis') && !$('startFullAnalysis'),'Scope has an explicit generation control and bounded disclosure');
 check(!calls.some(c=>c.command==='analysis_run_start'),'Opening scoped AI details is free');
 const record={...window.runningAnalysis.saved_overviews[0],resource:'/profiles',feature_groups:[{name:'Profile evidence',connection_ids:[1]}]};
 window.runningAnalysis.saved_scope_overviews=[{...record,resource:'/items'},record];
 await AnalysisRun.check();
 check($('insp').innerText.includes('Profile evidence') && !$('startAppAnalysis') && !$('insp').innerText.includes('Saved items'),'Stored path reopens independently from the initial overview without another model turn');
 const savedBadge=()=>document.querySelector('[data-saved-scope="/profiles"]');check(!savedBadge().hidden,'Saved map badges become visible after a completed scope');
 savedBadge().click();check($('insp').innerText.includes('Profile evidence') && $('insp').innerText.includes('client.js:5') && !$('startAppAnalysis') && !$('overviewLimits'),'Direct map badge opens saved evidence without AI controls');
 $('explainLocalScope').click();await new Promise(r=>setTimeout(r,15));window.runningAnalysis.saved_scope_overviews=[{...record,commit:'different'}];await AnalysisRun.check();
 check(savedBadge().hidden,'Stale current-scope badges disappear');
 check(!$('insp').innerText.includes('Profile evidence') && $('startAppAnalysis'),'A changed pin hides stale path explanations');
 index.service_flow.registered_route_groups=[{resource:'/internal/8',registered_route_indexes:[9]}];
 S.agentPrompt=null;await doRefresh();const list=$('registeredRoutes');list.open=true;
  const standalone=$('registeredRoutes').querySelector('[data-explain-route]');
 window.runningAnalysis.saved_scope_overviews=[{...record,resource:'/internal/8',feature_groups:[{name:'Internal route',connection_ids:[1]}],connections:[{id:1,kind:'server_registration',method:'GET',path:'/internal/8',server:{file:'api.py',line:28,quote:'def handler8():'}}]}];
 standalone.click();await new Promise(r=>setTimeout(r,20));await AnalysisRun.check();$('insp').querySelector('[data-overview-feature]').click();
 check($('insp').innerText.includes('api.py:28') && !$('insp').innerText.includes(S.lang==='en'?'Request code':'요청 코드') && !$('startAppAnalysis'),'Saved server registration opens without implying a request caller or another model turn');
 S.agentPrompt=null;
 const paths=['src/nested/<example name>.go','src/nested/worker.ts','src/nested/notes.md',...Array.from({length:80},(_,i)=>'src/item'+String(i).padStart(2,'0')+'.go')];
 window.mutateBundle=b=>{b.dev.structure_indexes=[{...index,files:[],imports:[],service_flow:null,coverage:{directories:[{directory:'src',indexed_files:2,candidate_files:80}]}}];b.dev.inventories=[{repository:'web',commit:pin,files:82,paths,paths_truncated:true,directories:[['src',82]]}]};
 await doRefresh();
 const box=()=>$('map').querySelector('[data-inventory]');
 check(purpose().compareDocumentPosition(box()) & Node.DOCUMENT_POSITION_FOLLOWING,'The source description precedes an unsupported-language inventory');
 check(!box().open,'The path inventory starts collapsed');box().querySelector('summary').click();await new Promise(r=>setTimeout(r,50));check(box().open && box().textContent.includes(pin) && box().textContent.includes(tr('파일 경로 표시 한도 도달')),'The path inventory starts collapsed and opens to a pinned, explicitly partial list');
 check(box().querySelector('[data-directory-coverage]').innerText===tr('확인한 파일')+' 2/80','Folder badges use saved coverage for the selected revision');
 box().querySelector('[data-inventory-dir="src"]').click();
 check(box().querySelector('[data-directory-coverage]').parentNode.querySelector('[data-inspect-directory]'),'Folder coverage stays beside its scoped inspection action');
 check(box().querySelectorAll('li').length===40 && !box().innerText.includes('item79.go'),'Directory pages have a bounded DOM');
 box().querySelector('[data-inventory-page="1"]').click();box().querySelector('[data-inventory-page="2"]').click();
 check(box().innerText.includes('item79.go'),'Final partial page is reachable');
 box().querySelector('[data-inventory-page="1"]').click();box().querySelector('[data-inventory-page="0"]').click();
 box().querySelector('[data-inventory-dir="src/nested"]').click();
 const globalMap=M(),folder=box().querySelector('[data-inspect-directory]');folder.click();await new Promise(r=>setTimeout(r,10));
 const folderFile=box().querySelector('[data-directory-file]');check(folderFile.options.length===2 && M()===globalMap,'Folder output does not replace the global map');
 folderFile.value='src/nested/worker.ts';folderFile.dispatchEvent(new Event('change',{bubbles:true}));
 const detail=box().querySelector('[data-directory-detail]');check(detail.innerText.includes('locate') && detail.innerText.includes('outside.ts') && detail.innerText.includes('src/nested/worker.ts:3'),'Choosing a folder result exposes declarations and outgoing imports');
 detail.querySelector('[data-inventory-file$="/outside.ts"]').click();check(calls.at(-1).args.url==='zed://file/fictional/web/outside.ts','Folder import opens its actual destination without borrowing the importing line');
 const folderArgs=calls.filter(c=>c.command==='directory_structure').at(-1).args;check(folderArgs.commit===pin && folderArgs.directory==='src/nested' && folderArgs.repository==='web','Folder analysis is pinned to the selected repository and directory');
 const originalFolder=S.inventoryDirectory.result;
 const sparse={...originalFolder,pagination:{...originalFolder.pagination,total_pages:5},cache_progress:{pages:[1,2,4],total_pages:5,first_missing_page:3}};
 const sample=document.createElement('div');sample.innerHTML=directoryDetail({...S.inventoryDirectory,result:sparse},file=>'zed://file/'+file);
 check(sample.querySelector('[data-missing-page]').dataset.directoryPage==='3' && sample.querySelector('[data-directory-page="2"]').innerText===tr('다음'),'A nonadjacent gap is directly reachable while preserving sequential navigation');
 const jump=box().querySelector('[data-missing-page]');
 check(jump?.dataset.directoryPage==='2' && jump.innerText===tr('미저장 페이지로')+' · 2' && box().querySelector('[data-saved-pages]').innerText===tr('저장된 페이지')+' 1/2','Cached pages and first available gap use one adjacent control');
 const nextPage=()=>box().querySelector('[data-directory-page="2"]').click();
 nextPage();await new Promise(r=>setTimeout(r,20));
 check(!box().querySelector('[data-missing-page]') && box().querySelector('[data-saved-pages]').innerText.endsWith('2/2'),'Fully cached folder has no unsaved-page action');
 check(box().innerText.includes(tr('확인한 파일')+' 0/1') && box().querySelector('[data-directory-page="3"]').disabled,'Unparsed last page retains counts and navigation');
 box().querySelector('[data-directory-page="1"]').click();await new Promise(r=>setTimeout(r,10));
 nextPage();box().querySelector('[data-inspect-directory]').click();await new Promise(r=>setTimeout(r,20));
 check(!box().querySelector('[data-directory-page]') && M()===globalMap,'Late page response cannot replace a closed folder or global map');
 const fileLink=box().querySelector('[data-inventory-file]');check(fileLink.textContent==='<example name>.go','Paths remain text');
 fileLink.click();check(calls.at(-1).command==='open_url' && calls.at(-1).args.url==='zed://file/fictional/web/src/nested/%3Cexample%20name%3E.go','Editor opens the qualified working file without inventing a line');
 const inspect=path=>box().querySelector('[data-inspect-path="'+path+'"]').click();
 check(!box().querySelector('[data-inspect-path="src/nested/notes.md"]'),'Documentation can open as a file without an unsupported parser button');
 inspect('src/nested/<example name>.go');await new Promise(r=>setTimeout(r,10));check(box().innerText.includes('Go') && box().innerText.includes(tr('타입 선언')+' · Runner'),'Go type names and language render at pinned positions');
 const singlePkg=box().querySelector('[data-go-package]');singlePkg.querySelector('summary').click();
 check(singlePkg.open && singlePkg.innerText.includes('src/nested/<example name>.go:4'),'On-demand package points to the import line');
 singlePkg.querySelector('a[data-inventory-file$="/pkg/a.go"]').click();check(calls.at(-1).args.url.endsWith('/pkg/a.go'),'Member opens as a file, not the import source line');
 inspect('src/nested/worker.ts');await new Promise(r=>setTimeout(r,10));
 const args=calls.filter(c=>c.command==='file_structure').at(-1).args;
 check(args.commit===pin && args.repository==='web' && args.file==='src/nested/worker.ts','Detail reads only the selected file and full commit');
 check(box().innerText.includes('doWork0') && box().innerText.includes(tr('대상 미확인 import')) && box().innerText.includes(tr('분석 한도 도달')),'Declarations and coverage limits appear together');
 box().querySelector('[data-structure-page="1"]').click();
 check(box().innerText.includes('import → utility.ts') && box().innerText.includes('src/nested/worker.ts:33'),'Bounded paging retains outgoing import evidence');
 box().querySelector('[data-inventory-dir="src"]').click();check(box().querySelector('[data-inventory-dir="src/nested"]'),'Parent navigation is reversible');
})().then(()=>window.uiSystemResult='[]').catch(e=>window.uiSystemResult=JSON.stringify([String(e)]));
"""
        fake_file = r'''
const originalNative=window.__TAURI__.core.invoke;
window.__TAURI__.core.invoke=async(command,args)=>{
 if(command==='directory_structure'){
   calls.push({command,args});
   const pagination={page:args.page,total_pages:2,selected_files:args.page===2?1:2};
   const cache_progress={pages:args.page===2?[1,2]:[1],total_pages:2,first_missing_page:args.page===2?null:2};
   if(args.page===2){await new Promise(r=>setTimeout(r,5));return JSON.stringify({...args,pagination,cache_progress,status:'indexed',files:[],coverage:{candidate_files:3,indexed_files:0}});}
   return JSON.stringify({...args,pagination,cache_progress,status:'indexed',files:[{file:'src/nested/a.py',language:'python',declarations:[]},{file:'src/nested/worker.ts',language:'typescript',declarations:[{kind:'function',name:'locate',line:8}]}],imports:[{file:'src/nested/worker.ts',target:'outside.ts',line:3}],coverage:{candidate_files:3,indexed_files:2,skipped_files:1,truncated:true}});
 }
 if(command!=='file_structure')return originalNative(command,args);
 calls.push({command,args});
 if(args.file.endsWith('.go'))return JSON.stringify({...args,status:'indexed',language:'go',declarations:[{name:'Runner',kind:'type',line:3}],imports:[],package_imports:[{file:args.file,line:4,package:'example.org/pkg',directory:'pkg',members:['pkg/a.go'],member_count:2}],coverage:{}});
 return JSON.stringify({...args,status:'indexed',language:'typescript',
   declarations:Array.from({length:21},(_,i)=>({name:'doWork'+i,kind:'function',line:i+1})),imports:[{target:'utility.ts',line:33}],
   coverage:{indexed_files:1,unresolved_imports:1,truncated:true}});
};
'''
        source = (ROOT / 'ui/index.html').read_text().replace('<script>', '<script>' + BOOTSTRAP + fake_file, 1)
        for name in ('tokens.css', 'app.css', 'vendor/dagre.min.js', 'connection.js', 'onboarding.js', 'control.js', 'analysis-run.js'):
            source = source.replace(f'"{name}"', f'"{(ROOT / "ui" / name).as_uri()}"')
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            page = folder / 'flow.html'
            page.write_text(source.replace('</body>', '<script>' + checks + '</script></body>'))
            probe = folder / 'probe'
            subprocess.run(['swiftc', str(ROOT / 'tests/webkit_style_probe.swift'), '-o', str(probe)], check=True, capture_output=True)
            result = subprocess.run([str(probe), str(page), '1280'], check=True, capture_output=True, text=True, timeout=30)
            self.assertEqual(json.loads(result.stdout), [])
