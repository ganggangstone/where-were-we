/* Commands use the same rendering and native actions as mouse controls.
   No chat history is read or recorded. This file is an app-owned local bridge. */
const CONTROL_SESSION=crypto.randomUUID();
function controlError(code,message) {const error=Error(message || code);error.code=code;throw error;}
function controlCanonical(value) {
  if(Array.isArray(value))return value.map(controlCanonical);
  if(value && typeof value==='object')return Object.fromEntries(Object.keys(value).filter(k=>!k.startsWith('_')).sort().map(k=>[k,controlCanonical(value[k])]));
  return value;
}
function targetID(kind,key) {return kind+':'+(typeof key==='string'?key:JSON.stringify(controlCanonical(key)));}
function controlTargets() {
  const m=M();if(!m)return [];
  const items=new Map(),add=(kind,key,name,description,details,repository='')=>{
    const id=targetID(kind,key);items.set(id,{id,kind,key,name,description:description || '',details,repository});
  };
  for(const s of visibleScreens(m))add('screen',s.path,label(m,s.path),s.source_path || s.path,s,s.repository);
  for(const r of m.backend_routes || [])add('request',r.file+'::'+r.function,r.name || r.function,r.method+' '+r.path,r,r.repository);
  for(const n of S.system?.nodes || [])add('program',n.id,n.name,n.what,n,n.repository);
  for(const t of new Set([...Object.values(m.models || {}),...Object.keys(tableUse(m)),...(S.system?.nodes || []).flatMap(n=>n.tables || [])]))add('data',t,tableName(t),t,{},t.split('::')[0]);
  for(const [node,value] of Object.entries(S.jobs?.nodes || {}))for(const job of value.jobs || [])add('job',{node,job},job.name,job.what,job,(S.system?.nodes || []).find(n=>n.id===node)?.repository);
  for(const link of S.system?.links || [])add('connection',link,linkLabel(link),[(S.system.nodes.find(n=>n.id===link.from)?.name || link.from),(S.system.nodes.find(n=>n.id===link.to)?.name || link.to)].join(' → '),link);
  for(const group of groupsOf(m))add('feature',featureKey(group),group.name,group.description,{screens:group.list.map(s=>s.path)});
  return [...items.values()];
}
// Agent selection and the search box open targets the same way.
function openTarget(target,relations=true) {
  S.q='';$('q').value='';S.agentPrompt=null;S.step=-1;S.ev=-1;
  if(target.kind==='screen'){if(relations)setFocus('screen|'+target.key);else selectScreen(target.key,false);}
  else if(target.kind==='request')setFocus('route|'+target.key);
  else if(target.kind==='data')setFocus('table|'+target.key);
  else if(target.kind==='program')selectProgram(target.key,false);
  else if(target.kind==='job')selectProgram(target.key.node,false);
  else if(target.kind==='connection')selectProgram(target.key.from,false);
  else if(target.kind==='feature'){S.view='feat';S.feat=target.id;render();}
}
async function controlRevision() {
  const bytes=new TextEncoder().encode(JSON.stringify(controlCanonical({project:S.project,repository:S.repository,branch:S.branch,map:M(),system:S.system,jobs:S.jobs,groups:S.groups,flows:S.flows,config:S.projectInfo})));
  return [...new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))].map(v=>v.toString(16).padStart(2,'0')).join('');
}
function controlSelection() {
  if(S.controlTarget && S.controlAnchor===JSON.stringify([S.view,S.sel,S.open,S.node,S.focus,S.feat]))return [S.controlTarget];
  if(S.view==='sys' && S.node)return [targetID('program',S.node)];
  if(S.view==='focus' && S.focus)return [targetID({screen:'screen',route:'request',table:'data'}[S.focus.t],S.focus.id)];
  const feature=selectedFeature(M());
  if(S.view==='feat' && S.feat!=null)return feature?[feature.id]:[];
  // The feature overview on the map has no screen yet; the feature itself is the selection.
  if(S.view==='map' && !S.sel && feature)return [feature.id];
  return [...(S.sel?[targetID('screen',S.sel)]:[]),...(S.open?[targetID('request',S.open)]:[])];
}
async function controlState() {
  const selected=controlSelection(),targets=controlTargets(),feature=selectedFeature(M());
  return {project:S.project,repository:S.repository,branch:S.branch,view:S.view,revision:await controlRevision(),selection:selected,
    selected:targets.filter(t=>selected.includes(t.id)),query:S.q,step:S.step,language:S.lang,settings:S.settings,
    dialogs:[...document.querySelectorAll('dialog[open]')].map(d=>d.id),structure:S.showProposal && S.proposal?'ai_proposal':'written',
    // The chosen feature stays as context; member is true/false only for a screen target, relation also covers requests and data.
    feature_context:feature?(r=>({id:feature.id,name:feature.g.name,member:r==='member'?true:r==='outside'?false:null,relation:r}))(featureRelation(M(),feature)):null,analysis:S.analysisRequest?{state:S.analysisRequest.state,scope:S.analysisRequest.scope,prepared:true}:null};
}
function controlDecoration() {
  // Detailed job/connection selection complements the existing program inspector.
  if(!S.controlTarget || S.controlAnchor!==JSON.stringify([S.view,S.sel,S.open,S.node,S.focus,S.feat]))return;
  const target=controlTargets().find(t=>t.id===S.controlTarget);if(!target)return;
  const el=document.createElement('section');el.className='sect';el.dataset.controlDetail=target.id;
  el.innerHTML=`<h3>${esc(target.name)}</h3><p>${esc(target.description)}</p>`;
  const evidence=target.details?.ev || target.details?.evidence || [];
  for(const ev of evidence){const p=document.createElement('p');p.className='s';p.textContent=typeof ev==='string'?ev:[ev.file,ev.line,ev.quote || ev.why].filter(Boolean).join(' · ');el.append(p);}
  if(['job','connection'].includes(target.kind))$('insp').prepend(el);
  const keys=target.kind==='connection'?[target.key.from,target.key.to]:target.kind==='job'?[target.key.node]:target.kind==='program'?[target.key]:[];
  document.querySelectorAll('[data-node]').forEach(node=>node.classList.toggle('agent-highlight',keys.includes(node.dataset.node)));
}
function controlScroll() {
  const selected=document.querySelector('.agent-highlight, .card.sel, [data-control-detail]') || document.querySelector('#map .sel');
  selected?.scrollIntoView({block:'center',inline:'center',behavior:'instant'});$('insp').scrollTop=0;
}
async function controlContext(args) {
  if(args.project && (args.project!==S.project || args.repository!==undefined && args.repository!==S.repository)) {
    const desiredRepository=args.repository ?? '';
    await loadProject(args.project,false,desiredRepository);
    if(S.project!==args.project || S.repository!==desiredRepository)controlError('context_unavailable');
  }else if(args.repository!==undefined && args.repository!==S.repository){
    await loadProject(S.project,false,args.repository);
    if(S.repository!==args.repository)controlError('context_unavailable');
  }
  if(args.branch){if(!['dev','main'].includes(args.branch) || !S.maps[args.branch])controlError('branch_unavailable');if(S.branch!==args.branch){S.branch=args.branch;S.sel=null;S.open=null;S.focus=null;S.node=null;S.feat=null;S.controlTarget=null;render();}}
  applyBranchDetails();
}
// A shown target must be visible: an explicit navigate/select closes the first-run guide without recording it as skipped or done.
function closeCoveringGuide(){if($('guide')?.open)closeGuide();}
// What a result read tells the agent: the prepared request's own computed state (per code, remaining, blocked, pins); nothing is claimed without one.
function resultReport() {
  const r=activeAnalysis(),scope={project:S.project,repository:S.repository,branch:S.branch,lang:S.lang};
  if(!r)return {scope,state:'no_request'};
  return {scope,command:r.command,state:r.state,codes:r.codes || null,remaining:r.remaining || [],blocked:r.blocked || [],pins:r.pins || null};
}
async function applyAppCommand(command) {
  const a=command.arguments || {};let output=null;
  const contextActions=['targets','navigate','select','refresh','prepare_analysis','github_accounts','github_account'];
  // A dialog opened from the guide holds the user's draft; refuse before changing anything.
  if(['navigate','select'].includes(command.action) && $('guide')?.open && document.querySelectorAll('dialog[open]').length>1)controlError('guide_dialog_open','Close the open dialog in the app first; its draft is kept.');
  if(contextActions.includes(command.action))await controlContext(a);
  switch(command.action){
    case 'state':break;
    case 'focus_app':await invoke('control_focus');break;
    case 'targets':{
      const all=controlTargets().filter(t=>JSON.stringify([t.kind,t.name,t.description,t.repository,t.details]).toLowerCase().includes(String(a.query || '').toLowerCase()));
      output={targets:all.slice(0,200),total:all.length,truncated:all.length>200};break;
    }
    case 'navigate':
      if(!['changes','sys','feat','map','focus'].includes(a.view))controlError('invalid_view');
      closeCoveringGuide();
      S.agentPrompt=null;S.view=a.view;S.controlTarget=null;render();break;
    case 'select':{
      if(!a.project || a.repository===undefined || !a.branch || !a.revision)controlError('explicit_target_context_required');
      if(a.revision!==await controlRevision())controlError('stale_revision');
      const target=controlTargets().find(t=>t.id===a.target);if(!target)controlError('missing_target');
      closeCoveringGuide();
      openTarget(target,a.relations!==false);
      S.controlTarget=target.id;S.controlAnchor=JSON.stringify([S.view,S.sel,S.open,S.node,S.focus,S.feat]);controlDecoration();controlScroll();
      await invoke('control_focus');break;
    }
    case 'clear':S.sel=null;S.open=null;S.node=null;S.focus=null;S.feat=null;S.step=-1;S.ev=-1;S.controlTarget=null;render();break;
    case 'search':S.q=String(a.query || '');$('q').value=S.q;render();break;
    case 'step':{
      const r=(M()?.backend_routes || []).find(r=>r.file+'::'+r.function===S.open),flow=r && flowOf(r);
      if(!Number.isInteger(a.index) || !flow || a.index<0 || a.index>flow.steps.length)controlError('step_unavailable');
      S.step=a.index;S.ev=a.index;render();break;
    }
    case 'dialog':{
      if(a.name==='close')document.querySelectorAll('dialog[open]').forEach(d=>d.close());
      else if(a.name==='code')editProject(false);
      else if(a.name==='create')editProject(true);
      else if(a.name==='settings'){renderSettings();$('settings-dialog').showModal();}
      else if(a.name==='agent')await $('agent').onclick();
      else if(a.name==='updates'){renderUpdates();$('release-dialog').showModal();}
      else controlError('invalid_dialog');break;
    }
    case 'language':if(!['ko','en'].includes(a.lang))controlError('invalid_language');setLanguage(a.lang);break;
    case 'settings':await persistSettings(a.value);break;
    case 'configure':{
      if(!a.project || !a.configuration)controlError('configuration_required');
      const projects=await invoke('list_projects');
      const known=projects.includes(a.project)?JSON.parse(await invoke('read_project',{project:a.project,repository:''})).project?.repositories || []:[];
      output=await saveConnections(a.project,a.configuration,known);
      const ps=await invoke('list_projects');$('project').innerHTML=ps.map(p=>`<option>${esc(p)}</option>`).join('');
      await loadProject(a.project,false,'');break;
    }
    case 'github_logins':output=JSON.parse(await invoke('github_logins',{project:a.project || S.project || 'Account check'}));break;
    case 'update_settings':if(typeof a.automatic!=='boolean')controlError('invalid_update_settings');setUpdateChecks(a.automatic);output={automatic:U.auto};break;
    case 'github_accounts':output=JSON.parse(await invoke('github_accounts',{project:S.project,repository:S.repository}));break;
    case 'github_account':await invoke('use_github_account',{project:S.project,repository:S.repository,account:a.account});await reloadCurrent();break;
    case 'refresh':output=await refreshConnectedCode(S.project,S.repository);break;
    case 'prepare_analysis':{
      const tasks={all:'analysis_plan',analysis:'analysis_request',system:'make_system',groups:'suggest_groups',jobs:'make_jobs',steps:'make_steps',briefing:'briefing_request'};
      if(!tasks[a.task])controlError('invalid_analysis_task');
      output=await requestAgentAction(tasks[a.task],a.task==='jobs'?{node:a.target}:a.task==='steps'?{screen:a.target}:{});
      if(!output)controlError('analysis_request_failed');output={prepared:true,executed:false,request:output};break;
    }
    case 'read_results':{const request=activeAnalysis(),token=S.loadToken;
      if(request){await checkAnalysisResults();if(request!==activeAnalysis() || token!==S.loadToken || request.state==='checking')controlError('context_changed');if(request.state==='error')controlError('result_read_failed',request.error);}
      else await reloadAnalysisOnly();output=resultReport();break;}
    case 'update_state':output=await invoke('app_update_status');break;
    case 'check_update':if(U.busy)controlError('update_check_busy');await checkUpdates(true);if(U.failed)controlError('update_check_failed');output={failed:U.failed,latest:U.latest,current:U.current};break;
    case 'start_update':if(U.installing)controlError('update_already_running');if(!U.latest?.newer)controlError('no_update_available');await startUpdate();if(U.job?.stage==='failed')controlError('update_failed',U.job.error);output={started:true,completed:false,update:await invoke('app_update_status')};break;
    default:controlError('invalid_action');
  }
  // DOM rendering above is synchronous. Animation frames pause in background
  // webviews, so awaiting them would block every later command.
  return {ok:true,output,state:await controlState()};
}
let controlApplying=false;
async function pollAppControl() {
  if(!window.appControlReady)return;
  try{
    const command=await invoke('control_poll',{session:CONTROL_SESSION});
    if(!command || controlApplying)return;
    controlApplying=true;let result;
    try{result=await applyAppCommand(command);}
    catch(error){result={ok:false,error:{code:error.code || 'action_failed',message:String(error)},state:await controlState()};}
    await invoke('control_ack',{session:CONTROL_SESSION,id:command.id,result});
  }catch{/* A reload or missing older bridge must not disrupt ordinary UI controls. */}
  finally{controlApplying=false;}
}
setInterval(pollAppControl,300);
