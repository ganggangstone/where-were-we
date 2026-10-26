/* Guided repair: app-owned probe and the agent's live MCP are separate checks. */
let connectionRequestToken=0;
const connectionFeatures={onboarding:'서비스 연결',maps:'지도 읽기',detail:'코드 자세히 읽기',briefing:'바뀐 것 설명',app:'앱 화면 제어'};
const connectionMessages={
 ready:'앱의 연결 기능은 정상입니다.',not_verified:'AI 연결을 아직 확인하지 않았습니다.',
 verified:'작업하던 AI가 앱에 연결된 것을 확인했습니다.',
 not_inspected:'AI가 설정을 확인하면 등록된 경로를 표시합니다.',
 matches_app:'등록된 경로가 앱 서버와 같습니다.',different_path:'다른 경로의 서버가 등록돼 있습니다.',
 different_server:'AI가 다른 경로의 서버에 연결돼 있습니다.',
 running_old_server:'AI가 이전 연결을 쓰고 있습니다. 새 AI 대화를 열거나 연결 수정 요청을 보내세요.',
 missing_tools:'AI는 연결돼 있지만 필요한 기능 일부를 쓸 수 없습니다. 새 AI 대화를 열거나 연결 수정 요청을 보내세요.',
 expired:'연결 확인 정보가 만료됐습니다. 다시 확인을 시작하세요.',app_changed:'진단 후 앱 코드가 바뀌었습니다. 다시 진단하세요.',
 missing_runtime:'앱에 필요한 파일이 없습니다. 앱을 다시 설치하세요.',
 missing_runtime_or_server:'등록된 실행 파일이나 서버를 찾지 못했습니다.',
 app_moved_or_missing:'등록된 위치에 앱이 없습니다. 앱 설치 위치를 확인하세요.',
 permission_denied:'파일을 읽거나 실행할 권한이 없습니다.',
 server_unavailable:'앱 서버를 실행하지 못했습니다. 앱 설치 상태를 확인하세요.',
 server_info_unavailable:'서버 정보를 읽지 못했습니다. 앱을 업데이트하고 다시 진단하세요.',
 unsupported_registration:'이 연결 설정은 진단할 수 없습니다. AI에게 설정 확인을 요청하세요.',
 unresolved_registration:'실제 서버 경로를 확인하지 못했습니다. AI에게 설정 확인을 요청하세요.'
};
function connectionMessage(state){return tr(connectionMessages[state]||'연결 상태를 읽지 못했습니다. 다시 진단하세요.');}
/* The inspector and the first-run guide share these actions; each place keeps its own report and request token. */
const inspectorConnection={host:()=>$('insp'),get report(){return S.connectionDiagnostic;},set report(value){S.connectionDiagnostic=value;},active:()=>!!S.agentPrompt&&S.agentPurpose==='connection',get token(){return connectionRequestToken;},set token(value){connectionRequestToken=value;}};
async function startConnectionDiagnostic(feature='detail',place=inspectorConnection){
 const token=++place.token;
 if(place===inspectorConnection){S.agentPurpose='connection';S.agentPrompt='connection';}
 place.report={feature,busy:true};renderConnectionDiagnostic(place);
 try{
  const report=JSON.parse(await invoke('connection_diagnose',{feature,lang:S.lang}));
  if(token!==place.token)return;
  place.report={...report,feature,busy:false}; // kept even when hidden, so coming back is not stuck busy
 }catch{
  if(token!==place.token)return;
  place.report={feature,busy:false,error:true};
 }
 if(place.active())renderConnectionDiagnostic(place);
}
async function checkCurrentConnection(place=inspectorConnection){
 const report=place.report,token=place.token;
 if(!report?.challenge||report.checking)return;
 report.checking=true;report.checkError=false;renderConnectionDiagnostic(place);
 try{
  const result=JSON.parse(await invoke('connection_status',{challenge:report.challenge}));
  if(token!==place.token||place.report!==report)return;
  report.connection=result;if(result.registration)report.registration=result.registration;
 }catch{if(token===place.token&&place.report===report)report.checkError=true;}
 finally{
  // An invalidated check drops its result but still frees the button.
  if(place.report===report){report.checking=false;if(token===place.token&&place.active())renderConnectionDiagnostic(place);}
 }
}
function renderConnectionDiagnostic(place=inspectorConnection){
 const host=place.host(),prefix=place.prefix||'',$=id=>host.querySelector('#'+prefix+id);
 const report=place.report||{feature:'detail'},fresh=report.fresh_server||{},actual=report.connection||{state:'not_verified'},registration=report.registration||{state:'not_inspected'};
 const valid=!!report.challenge&&fresh.state==='ready'&&!['expired','app_changed'].includes(actual.state);
 const verified=actual.state==='verified',missing=[...new Set([...(fresh.missing||[]),...(actual.missing||[])])];
 host.innerHTML=prefix?connectionHtml(report,fresh,actual,registration,valid,verified,missing,place).replaceAll(' id="',' id="'+prefix):connectionHtml(report,fresh,actual,registration,valid,verified,missing,place);
 $('connectionFeature').onchange=e=>startConnectionDiagnostic(e.target.value,place);
 if($('backToMap'))$('backToMap').onclick=()=>{S.agentPrompt=null;S.agentPurpose=null;render();};
 $('runConnectionDiagnostic').onclick=()=>startConnectionDiagnostic(report.feature,place);
 if($('checkCurrentConnection'))$('checkCurrentConnection').onclick=()=>checkCurrentConnection(place);
 place.after?.();
 if($('copyConnectionRequest'))$('copyConnectionRequest').onclick=async()=>{
  if(!valid)return;
  // The guide passes its run and language; a copy finishing after either changed paints nothing.
  const context=place.context?.(),current=()=>place.report===report&&place.active()&&place.context?.()===context&&$('connectionCopyStatus');
  // After copying, checking the connection becomes the main action.
  try{await navigator.clipboard.writeText(report.handoff);if(!current())return;report.copied=true;renderConnectionDiagnostic(place);}
  catch{if(current())$('connectionCopyStatus').textContent=tr('복사하지 못했습니다. 다시 시도하거나 안내를 열어 직접 복사하세요.');}
 };
}
function connectionHtml(report,fresh,actual,registration,valid,verified,missing,place){
 // The actual live state comes first; "not checked" is never shown as disconnected.
 // A valid repair request is the main action until it is copied, then checking the connection is.
 const copyFirst=valid&&!verified&&!report.copied,checkFirst=!verified&&!!report.copied;
 return `${place.compact?'':`<h2>${tr('연결 진단')}</h2>`}
 ${report.busy?`<p role="status">${tr('앱의 연결 기능을 확인하는 중…')}</p>`:report.error?`<p role="alert">${tr('연결 진단을 실행하지 못했습니다. 다시 시도하세요.')}</p>`:`<p id="liveConnectionState" role="status">${connectionMessage(actual.state)}</p>
 ${missing.length?`<p role="alert">${tr('AI 연결에 필요한 기능이 빠져 있습니다')}</p>`:''}`}
 <div class="section-heading"><label>${tr('확인 범위')} <select id="connectionFeature">${Object.entries(connectionFeatures).map(([key,label])=>`<option value="${key}" ${key===report.feature?'selected':''}>${tr(label)}</option>`).join('')}</select></label>
 <button class="btn" id="runConnectionDiagnostic" ${report.busy?'disabled':''}>${tr(report.busy?'확인 중…':'다시 진단')}</button></div>
 ${report.busy||report.error?'':`${verified&&place===inspectorConnection?`<div class="ctl"><button class="btn primary" id="backToMap">${tr('지도로 돌아가기')}</button></div>`:verified?'':''}
 <div class="ctl"><button class="btn ${copyFirst?'primary':'quiet'}" id="copyConnectionRequest" ${valid?'':'disabled'}>${tr('연결 수정 요청 복사')}</button><button class="btn ${checkFirst?'primary':''}" id="checkCurrentConnection" ${report.challenge&&!report.checking?'':'disabled'}>${tr(report.checking?'확인 중…':'연결됐는지 확인')}</button></div>
 <p id="connectionCopyStatus" role="status">${report.copied?tr('복사했습니다. 작업하던 AI 채팅에 붙여 넣으세요.'):''}</p>
 ${report.checkError?`<p role="alert">${tr('연결 확인 결과를 읽지 못했습니다. 다시 진단하세요.')}</p>`:''}`}
 ${metaList([['앱 실행',`<span id="bundledConnectionState" role="${fresh.state==='ready'?'status':'alert'}">${connectionMessage(fresh.state)}</span>`],['등록 경로',`<span id="registeredConnectionState" role="${['not_inspected','matches_app'].includes(registration.state)?'status':'alert'}">${connectionMessage(registration.state)}</span>`]])}
 ${helpDetails(`${missing.length?metaList([['빠진 도구',`<span class="mono">${esc(missing.join(', '))}</span>`]]):''}${report.app?`${metaList([['앱 버전',esc(report.app.app_version||tr('확인할 수 없음'))]])}<pre class="prompt mono">${esc(report.app.python)}\n${esc(report.app.server)}</pre>`:''}${registration.server?`<pre class="prompt mono">${esc(registration.command)}\n${esc(registration.server)}</pre>`:''}`,'진단 상세')}
 ${!report.busy&&!report.error&&valid?`<details><summary>${tr('요청 내용 보기')}</summary><pre class="prompt mono">${esc(report.handoff)}</pre></details>`:''}`;
}
