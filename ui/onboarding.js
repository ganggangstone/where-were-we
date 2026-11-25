/* First-run guide: a full-window modal dialog over the workspace. It only calls the existing project editor,
   setup prompt, connection diagnostics, refresh and analysis panel, and never changes the workspace by itself. */
const GUIDE_KEY='where-were-we.onboarding';
const GUIDE_STEPS=['시작','AI에게 맡기기','연결한 코드','첫 분석'];
const G={step:0,run:0,setup:null,copied:false,connection:null,token:0,opener:null,readError:false,reading:false,plan:null,await:null,session:0};
const GUIDE_POLL_MS=6000;
let guideMemory=null;
// localStorage, then sessionStorage, then this page only: a skip must hold even when storage is blocked.
function guideMarker(){for(const store of ['localStorage','sessionStorage'])try{const v=window[store].getItem(GUIDE_KEY);if(v)return v;}catch{}return guideMemory;}
function rememberGuide(value){guideMemory=value;for(const store of ['localStorage','sessionStorage'])try{window[store].setItem(GUIDE_KEY,value);return;}catch{}}
const guideConnection={prefix:'guide-',compact:true,context:()=>G.run+'|'+S.lang,host:()=>$('guideConnection'),after:()=>{const next=$('guideLater'),rail=$('guide').querySelector('.guide-rail li:nth-child(2)');if(next)next.className='btn '+(guideVerified()?'primary':'plain');if(rail&&guideVerified()&&!rail.querySelector('.dot'))rail.insertAdjacentHTML('afterbegin','<span class="dot ok"></span>');},get report(){return G.connection;},set report(value){G.connection=value;},active:()=>$('guide').open&&G.step===1&&!!$('guideConnection'),get token(){return G.token;},set token(value){G.token=value;}};
function guideVerified(){return G.connection?.connection?.state==='verified';}
function guideHasMap(){
  if(!M())return false;
  // The whole project is judged, whichever code is selected; a code without the shown version is not part of it.
  const all=S.projectInfo?.repositories || [],repos=all.filter(r=>r.refs?.[S.branch]);
  // A map collected before a configuration change is not the map of the current settings.
  return all.length?repos.length>0 && repos.every(r=>r.collected&&r.commits?.[S.branch]&&!r.config_changed):!!M().commit;
}
// The first AI result: for every code on the shown version a saved detailed map of the current language and an actual current commit,
// and the read-only analysis plan (the same one the request follows) has nothing left and nothing blocked.
// A basic map alone, another language or version, one code of several, a failed read or an unread plan never counts.
function guideKey(){return [S.project,S.repository,S.branch,S.lang,...guideRepos().map(r=>r.id+':'+r.commits?.[S.branch]+':'+r.results?.[S.branch]?.analysis?.version)].join('|');}
function guideRepos(){return (S.projectInfo?.repositories || []).filter(r=>r.refs?.[S.branch]);}
function guideAnalysisState(){
  if(!guideHasMap())return {state:'nomap',codes:[]};
  const same=(a,b)=>!!a && !!b && (String(a).startsWith(String(b)) || String(b).startsWith(String(a)));
  const codes=guideRepos().map(r=>{
    const found=r.results?.[S.branch]?.analysis;
    const state=!found?'missing':found.language!==S.lang?'language':found.stale || r.config_changed || !same(found.commit,r.commits?.[S.branch])?'stale':'saved';
    return {id:r.id,name:r.name || r.id,state};
  });
  const some=state=>codes.some(c=>c.state===state);
  if(G.readError)return {state:'error',codes};
  if(codes.length && codes.every(c=>c.state==='saved')){
    const plan=G.plan?.key===guideKey()?G.plan:null;
    return {state:!plan?'unchecked':plan.tasks.length || plan.blocked.length?'remaining':'done',codes,plan};
  }
  return {state:!codes.length?'missing':some('saved')?'partial':some('language')?'language':some('stale')?'stale':'missing',codes};
}
const GUIDE_ANALYSIS_TEXT={
  done:'첫 AI 분석을 저장했다.',missing:'기본 지도를 만들었다. 첫 AI 분석은 아직 없다.',
  partial:'일부 코드의 분석만 저장했다.',unchecked:'「결과 확인」에서 남은 분석을 볼 수 있다.',remaining:'첫 결과를 저장했다. 아직 남은 분석이 있다.',error:'분석이 끝났는지 확인하지 못했다.',language:'분석 결과를 다른 언어로 저장했다.',stale:'이전 코드의 분석이다.'};
const GUIDE_CODE_ANALYSIS={saved:'분석 저장됨',partial:'분석 일부만 저장됨',language:'다른 언어로 저장됨',stale:'최신이 아님',missing:'아직 분석 없음'};
function openGuide(opener=document.activeElement){
  if($('guide').open)return;
  if(G.connection?.busy)G.connection=null; // a diagnostic dropped at close is offered again
  else if(G.connection)G.connection.checking=false; // a live check dropped at close can be run again; its challenge stays
  G.opener=opener;G.step=0;G.run++;G.session++;G.await=null;G.plan=null;G.readError=false;renderGuide();$('guide').showModal();$('guideTitle').focus();
}
function closeGuide(marker){
  if(marker)rememberGuide(marker);
  G.token++;G.run++;G.session++;G.await=null;G.plan=null;G.readError=false; // Work still running must not repaint or write into a closed guide; the awaited request ends with it.
  if($('guide').open){$('guide').close();guideReturnFocus();}
}
function guideReturnFocus(){const back=G.opener?.isConnected&&!G.opener.closest('dialog')?G.opener:$('menuButton');back?.focus();}
function guideStep(step){G.run++;G.step=Math.max(0,Math.min(GUIDE_STEPS.length-1,step));renderGuide();$('guideTitle').focus();}
function guideBody(){
  const m=guideHasMap();
  if(G.step===0)return `<h2 id="guideTitle" tabindex="-1">${tr('내 코드 지도')}</h2>
    <div class="guide-visual">${['화면','서버','데이터'].map((name,i)=>`${i?'<span class="arrow">→</span>':''}<div class="card" title="${esc(['/items','POST /items','items'][i])}"><div class="nm">${tr(name)}</div><div class="meta"><span class="dot ${['','strong','ok'][i]}"></span>${tr(['목록 화면','항목 저장','저장된 항목'][i])}</div></div>`).join('')}</div>
    <div class="ctl"><button class="btn primary" id="guideNext">${tr('시작하기')}</button></div>`;
  if(G.step===2)return `<h2 id="guideTitle" tabindex="-1">${tr('연결한 코드')}</h2>
    <p role="status" id="guideProjectState">${S.project?`<span class="dot ok"></span>${tr('연결한 서비스: ')}${esc(S.project)}`:tr('아직 연결한 서비스가 없다. AI 채팅에서 연결을 마치면 여기에 지도가 나온다.')}</p>
    ${S.project?`<ul>${guideCodes().map(guideCodeLine).join('')}</ul>`:''}
    <div class="ctl">${S.project?`<button class="btn primary" id="guideNext">${tr('다음')}</button>`:`<button class="btn primary" id="guideToAgent">${tr('AI에게 맡기기')}</button>`}${guideManual()}</div>`;
  if(G.step===1)return `<h2 id="guideTitle" tabindex="-1">${tr('작업하던 AI에 연결 맡기기')}</h2>
    <p class="s">${tr('첫 분석은 연결한 AI의 요금과 사용 한도를 따른다.')} ${tr('확인한 뒤에 분석 시작')}</p>
    <div class="ctl"><button class="btn ${G.connection?'quiet':'primary'}" id="guideCopySetup">${tr('AI에 보낼 글 복사')}</button><span id="guideCopyState" role="status">${G.copied?tr('복사했다. 작업하던 AI 채팅에 붙여 넣으면 보낼 수 있다.'):''}</span></div>
    ${G.setup?helpDetails(`<pre class="prompt mono">${esc(G.setup.text)}</pre>`,'연결 안내 보기'):''}
    <div class="ctl">${guideManual()}</div>
    ${G.connection?'':`<div class="ctl"><button class="btn" id="guideDiagnose">${tr('연결 진단')}</button></div>`}<div id="guideConnection"></div>
`;
  return guideAnalysisBody(m);
}
function guideAnalysisBody(m){
  const a=guideAnalysisState(),done=a.state==='done';
  const status=!S.project?tr('서비스 연결 필요'):!m?tr('아직 지도가 없다.'):`<span class="dot ${done?'ok':''}"></span>${tr(GUIDE_ANALYSIS_TEXT[a.state])}`;
  const codes=m && a.codes.length?`<ul>${a.codes.map(c=>`<li data-guide-code><b>${esc(c.name)}</b> · ${tr(GUIDE_CODE_ANALYSIS[c.state])}</li>`).join('')}</ul>`:'';
  const plan=a.state==='remaining'?planSummary({remaining:a.plan.tasks,tasks:[],blocked:a.plan.blocked}):'';
  const error=G.readError?`<p role="alert" class="s error">${tr('저장한 결과를 읽지 못했다.')}</p>`:!m && S.project && $('status').classList.contains('error')?`<p role="alert" class="s error">${esc($('status').textContent)}</p>`:'';
  const buttons=!S.project?`<button class="btn primary" id="guideToProject">${tr('AI에게 맡기기')}</button>`
    :!m?`<button class="btn primary" id="guideRefresh" ${$('refresh').disabled?'disabled':''}>${tr('↻ 지도 만들기')}</button>`
    :done?`<button class="btn primary" id="guideFinish">${tr('분석 결과 보기')}</button>`
    :`<button class="btn primary" id="guideReadNow" ${G.reading?'disabled':''}>${tr('결과 확인')}</button><button class="btn quiet" id="guideAnalysis">${tr(['missing','language','stale'].includes(a.state)?'AI에 분석 맡기기':'남은 분석을 AI에 맡기기')}</button>`;
  return `<h2 id="guideTitle" tabindex="-1">${tr('첫 분석')}</h2>
    <p role="status" id="guideMapState">${status}</p>${codes}${plan}${error}
    <div class="ctl">${buttons}</div>`;
}
// A service that is already shown is edited in place; only an empty workspace starts a new one.
function guideManual(){return `<button class="btn quiet" id="guideCreate">${tr(S.project?'연결한 코드 수정':'직접 연결하기')}</button>`;}
// Each connected code names where it comes from and whether its own map is ready, so a wrong folder is visible here.
// A legacy single-folder service has no repository list; its shown map stands for its one code.
function guideCodes(){const repos=S.projectInfo?.repositories || [],m=S.maps.dev||S.maps.main;return repos.length?repos:m?.repo?[{name:S.project,path:m.repo,collected:!!m.commit,commits:{[S.branch]:M()?.commit}}]:[];}
function guideCodeLine(r){
  const where=r.url||r.configured_path||r.path||'',state=r.error?'새 지도를 가져오지 못했다':r.config_changed?'설정을 바꿨다. 새로고침하면 지도에 반영된다.':r.collected&&r.commits?.[S.branch]?'지도 준비됨':'아직 지도 없음';
  return `<li data-guide-code><b>${esc(r.name || r.id)}</b>${where?` · <span class="mono">${esc(where)}</span>`:''} · <span class="${r.error?'error':''}">${tr(state)}</span></li>`;
}
function renderGuide(){
  const box=$('guide'),focused=box.contains(document.activeElement)?document.activeElement.id:'',body=guideBody();
  const done=[false,guideVerified(),!!S.project,guideAnalysisState().state==='done'];
  box.innerHTML=`<div class="guide-frame"><nav class="guide-rail" aria-label="${tr('시작 안내')}"><ol>${GUIDE_STEPS.map((name,i)=>`<li ${i===G.step?'aria-current="step"':''} class="${i===G.step?'on':''}">${done[i]?'<span class="dot ok"></span>':''}${i+1}. ${tr(name)}</li>`).join('')}</ol>
    <div class="seg light" role="group" aria-label="언어 / Language">${['ko','en'].map(lang=>`<button data-guide-lang="${lang}" lang="${lang}" aria-pressed="${S.lang===lang}" class="${S.lang===lang?'on':''}">${lang==='ko'?'한국어':'English'}</button>`).join('')}</div></nav>
    <section class="guide-step" aria-labelledby="guideTitle">${body}
    <div class="ctl guide-nav">${G.step?`<button class="btn quiet" id="guideBack">${tr('이전')}</button>`:''}<span class="spacer"></span>${G.step&&G.step<GUIDE_STEPS.length-1&&!body.includes('id="guideNext"')?`<button class="btn plain" id="guideLater">${tr('다음')}</button>`:''}<button class="btn plain" id="guideSkip">${tr('안내 닫기')}</button></div></section></div>`;
  const on=(id,handler)=>{const el=box.querySelector('#'+id);if(el)el.onclick=handler;};
  box.querySelectorAll('[data-guide-lang]').forEach(b=>b.onclick=()=>setLanguage(b.dataset.guideLang));
  on('guideNext',()=>guideStep(G.step+1));on('guideLater',()=>guideStep(G.step+1));on('guideBack',()=>guideStep(G.step-1));
  on('guideSkip',()=>closeGuide('skipped'));
  on('guideCreate',()=>editProject(!S.project));on('guideToProject',()=>guideStep(1));on('guideToAgent',()=>guideStep(1));
  on('guideCopySetup',guideCopySetup);
  // The guide checks the tools its own request uses: connection and collection (projects, refresh, app_control) and the first analysis.
  on('guideDiagnose',()=>{G.connection={feature:'onboarding',busy:true};renderGuide();startConnectionDiagnostic('onboarding',guideConnection);});
  on('guideRefresh',async()=>{const work=doRefresh();renderGuide();await work;guideSync();});
  on('guideReadNow',()=>guideReadSaved(true));
  // The analyzed structure is the result; the basic map stays one click away in the view switcher.
  on('guideFinish',()=>{
    // The new AI structure when there is one, else the written structure; never the basic map for an analyzed service.
    const details=S.branchDetails?.[S.branch],proposal=!!details?.['system.ai'];
    S.agentPrompt=null;S.showProposal=proposal;S.view=proposal || details?.system?.nodes?.length?'sys':'map';closeGuide('done');render();});
  on('guideAnalysis',()=>{closeGuide();openAnalysisPanel();});
  if(G.step===1&&G.connection)renderConnectionDiagnostic(guideConnection);
  if(focused&&box.querySelector('#'+CSS.escape(focused)))box.querySelector('#'+CSS.escape(focused)).focus();
}
async function guideCopySetup(){
  // The prompt follows the current language; an earlier copy stays marked as copied.
  // A late answer or failure after closing, moving to another step or switching language is dropped.
  const run=G.run,lang=S.lang,current=()=>run===G.run&&lang===S.lang&&$('guide').open;
  try{
    if(G.setup?.lang!==lang){const text=await invoke('setup_prompt',{lang,onboarding:true});if(!current())return;G.setup={lang,text};}
    await navigator.clipboard.writeText(G.setup.text);if(!current())return;G.copied=true;G.await={lang,base:S.project,project:S.project,branch:S.branch,bound:false};
  }catch{
    // Manual copy is only offered when the instructions were actually created and can be opened below.
    if(!current())return;const made=G.setup?.lang===lang;if(!made)G.setup=null;renderGuide();
    $('guideCopyState').textContent=tr(made?'복사하지 못했다. 안내를 열면 직접 복사할 수 있다.':'안내를 만들지 못했다. 다시 연결해야 한다.');return;}
  renderGuide();
}
// Saved results are read, never produced: only while the request this run copied is awaited, on returning to the app or on a slow poll,
// one read at a time, bound to the language, project and version it was copied for. Nothing here collects or calls a model.
let guideReading=false;
function guideAwaiting(){
  const w=G.await;
  // The first project that appears (or changes) after copying is the one the AI connected, on the version it opened with.
  if(w && S.project && S.project!==w.base && !w.bound){w.project=S.project;w.branch=S.branch;w.bound=true;}
  return !!w && $('guide').open && w.lang===S.lang && S.project===w.project && S.branch===w.branch && guideAnalysisState().state!=='done';
}
async function guideReadSaved(manual=false){
  if(guideReading || !$('guide').open || !S.project || (!manual && !guideAwaiting()))return;
  guideReading=true;G.reading=true;const run=G.session,key=[S.project,S.repository,S.branch,S.lang].join('|'),scope={project:S.project,repository:'',branch:S.branch,lang:S.lang};
  const here=()=>run===G.session && $('guide').open && key===[S.project,S.repository,S.branch,S.lang].join('|');
  if(manual)renderGuide();
  try{
    await reloadAnalysisOnly(here);
    if(!here())throw Error('context');
    G.plan=null;G.readError=false;
    // Only when every code has its first result is the plan asked: what it still lists is the rest of the request, whatever the task rules are.
    if(guideAnalysisState().codes.length && guideAnalysisState().codes.every(c=>c.state==='saved')){
      const now=JSON.parse(await invoke('analysis_plan',scope));
      if(!here())throw Error('context');
      G.plan={key:guideKey(),tasks:now.tasks || [],blocked:now.blocked || []};
    }
  }catch{if(here())G.readError=true;}
  finally{guideReading=false;G.reading=false;}
  if(run===G.session)guideSync(!G.readError);
  else if($('guide').open)renderGuide(); // a guide reopened meanwhile was painted while this read held the guard; its button must not stay disabled
}
window.addEventListener('focus',()=>guideReadSaved());
document.addEventListener('visibilitychange',()=>{if(!document.hidden)guideReadSaved();});
setInterval(guideReadSaved,GUIDE_POLL_MS);
// Main renders (project saved, map collected, language) repaint the open guide so its states stay current.
// A service the AI connected after the request was copied moves the guide to the first analysis once; the user can still go back.
function guideSync(returned=false){
  if(!$('guide').open)return;
  if(G.await)guideAwaiting(); // binds the project the AI connected
  if(G.await && !G.await.advanced && S.project && G.step>0 && G.step<3 && (G.await.bound || returned)){G.await.advanced=true;guideStep(3);return;}
  renderGuide();
}
// One Escape acts once: the native cascade would cancel the project editor and then the guide on the same key press.
document.addEventListener('keydown',e=>{
  if(e.key!=='Escape'||!$('guide').open||e.defaultPrevented)return;
  const top=[...document.querySelectorAll('dialog[open]')].filter(d=>d!==$('guide')).pop();
  e.preventDefault();
  if(top){top.close();return;}
  if(!document.activeElement?.matches?.('input,textarea,select'))closeGuide('skipped');
},true);
$('guide').addEventListener('cancel',e=>{
  // Escape while typing or choosing stays with that control; otherwise it skips the guide.
  if(e.target!==$('guide')||document.activeElement?.matches?.('input,textarea,select')){e.preventDefault();return;}
  e.preventDefault();closeGuide('skipped');
});
// The close event arrives later; after a quick reopen it must not cancel the new run's work.
$('guide').addEventListener('close',()=>{if($('guide').open)return;G.token++;G.run++;G.session++;G.await=null;if(document.activeElement===document.body||$('guide').contains(document.activeElement))guideReturnFocus();});
$('project-dialog').addEventListener('close',guideSync);
// Startup may finish before or after this file loads; either side opens the guide once.
function guideFirstRun(){if(S.firstRun&&!guideMarker()&&!$('guide').open)openGuide();}
$('guideOpen').onclick=()=>openGuide($('menuButton'));
guideFirstRun();
