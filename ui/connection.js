/* Guided repair: app-owned probe and the agent's live MCP are separate checks. */
let connectionRequestToken=0;
const connectionFeatures={maps:'지도 읽기',detail:'코드 자세히 읽기',briefing:'바뀐 것 설명',app:'앱 화면 제어'};
const connectionMessages={
 ready:'앱 서버가 정상입니다.',not_verified:'아직 현재 에이전트 연결을 확인하지 않았습니다.',
 verified:'현재 에이전트가 앱 서버에 연결된 것을 확인했습니다.',
 not_inspected:'에이전트가 설정을 확인하면 등록된 경로를 표시합니다.',
 matches_app:'등록된 경로가 앱 서버와 같습니다.',different_path:'다른 경로의 서버가 등록돼 있습니다.',
 different_server:'에이전트가 다른 경로의 서버에 연결돼 있습니다.',
 running_old_server:'이전 코드로 실행 중인 연결입니다. MCP를 재연결하거나 새 세션을 여세요.',
 missing_tools:'이 기능에 필요한 도구가 없습니다. MCP를 재연결하거나 앱을 업데이트하세요.',
 expired:'확인 번호가 만료됐습니다. 다시 진단하세요.',app_changed:'진단 후 앱 코드가 바뀌었습니다. 다시 진단하세요.',
 missing_runtime:'앱에 필요한 실행 파일이 없습니다. 앱을 다시 설치하세요.',
 missing_runtime_or_server:'등록된 실행 파일이나 서버를 찾지 못했습니다.',
 app_moved_or_missing:'등록된 위치에 앱이 없습니다. 앱 설치 위치를 확인하세요.',
 permission_denied:'파일을 읽거나 실행할 권한이 없습니다.',
 server_unavailable:'앱 서버를 실행하지 못했습니다. 앱 설치 상태를 확인하세요.',
 server_info_unavailable:'서버 정보를 읽지 못했습니다. 앱을 업데이트하고 다시 진단하세요.',
 unsupported_registration:'이 연결 설정은 진단할 수 없습니다. 에이전트에게 설정 확인을 요청하세요.',
 unresolved_registration:'실제 서버 경로를 확인하지 못했습니다. 에이전트에게 설정 확인을 요청하세요.'
};
function connectionMessage(state){return tr(connectionMessages[state]||'연결 상태를 읽지 못했습니다. 다시 진단하세요.');}
async function startConnectionDiagnostic(feature='detail'){
 const token=++connectionRequestToken;
 S.agentPurpose='connection';S.agentPrompt='connection';S.connectionDiagnostic={feature,busy:true};renderConnectionDiagnostic();
 try{
  const report=JSON.parse(await invoke('connection_diagnose',{feature,lang:S.lang}));
  if(token!==connectionRequestToken||S.agentPurpose!=='connection')return;
  S.connectionDiagnostic={...report,feature,busy:false};
 }catch{
  if(token!==connectionRequestToken||S.agentPurpose!=='connection')return;
  S.connectionDiagnostic={feature,busy:false,error:true};
 }
 if(S.agentPrompt && S.agentPurpose==='connection')renderConnectionDiagnostic();
}
async function checkCurrentConnection(){
 const report=S.connectionDiagnostic,token=connectionRequestToken;
 if(!report?.challenge||report.checking)return;
 report.checking=true;report.checkError=false;renderConnectionDiagnostic();
 try{
  const result=JSON.parse(await invoke('connection_status',{challenge:report.challenge}));
  if(token!==connectionRequestToken||S.connectionDiagnostic!==report)return;
  report.connection=result;if(result.registration)report.registration=result.registration;
 }catch{if(token===connectionRequestToken&&S.connectionDiagnostic===report)report.checkError=true;}
 finally{
  if(token===connectionRequestToken&&S.connectionDiagnostic===report){report.checking=false;if(S.agentPrompt&&S.agentPurpose==='connection')renderConnectionDiagnostic();}
 }
}
function renderConnectionDiagnostic(){
 const report=S.connectionDiagnostic||{feature:'detail'},fresh=report.fresh_server||{},actual=report.connection||{state:'not_verified'},registration=report.registration||{state:'not_inspected'};
 const valid=!!report.challenge&&fresh.state==='ready'&&!['expired','app_changed'].includes(actual.state);
 const verified=actual.state==='verified',missing=[...new Set([...(fresh.missing||[]),...(actual.missing||[])])];
 $('insp').innerHTML=`<h2>${tr('연결 진단')}</h2>
 ${report.busy?`<p role="status">${tr('앱에 포함된 서버를 확인하는 중…')}</p>`:report.error?`<p role="alert">${tr('연결 진단을 실행하지 못했습니다. 다시 시도하세요.')}</p>`:`<p id="liveConnectionState" role="status">${connectionMessage(actual.state)}</p>
 ${fresh.state!=='ready'?`<p role="alert">${connectionMessage(fresh.state)}</p>`:''}
 ${['not_inspected','matches_app'].includes(registration.state)?'':`<p role="alert">${connectionMessage(registration.state)}</p>`}
 ${missing.length?`<p role="alert">${tr('없는 도구')}: ${esc(missing.join(', '))}</p>`:''}`}
 <label>${tr('사용할 기능')} <select id="connectionFeature">${Object.entries(connectionFeatures).map(([key,label])=>`<option value="${key}" ${key===report.feature?'selected':''}>${tr(label)}</option>`).join('')}</select></label>
 <button class="btn" id="runConnectionDiagnostic" ${report.busy?'disabled':''}>${tr(report.busy?'확인 중…':'다시 진단')}</button>
 ${report.busy||report.error?'':`${verified?`<div class="ctl"><button class="btn primary" id="backToMap">${tr('지도로 돌아가기')}</button></div>`:`<p>${tr('요청을 에이전트에 전달한 뒤 현재 연결을 확인하세요.')}</p>`}
 <div class="ctl"><button class="btn ${verified?'quiet':'primary'}" id="copyConnectionRequest" ${valid?'':'disabled'}>${tr('연결 수정 요청 복사')}</button><button class="btn" id="checkCurrentConnection" ${report.challenge&&!report.checking?'':'disabled'}>${tr(report.checking?'확인 중…':'현재 연결 확인')}</button></div>
 <p id="connectionCopyStatus" role="status">${report.copied?tr('복사했습니다. 에이전트 채팅에 붙여 넣으세요.'):''}</p>
 ${report.checkError?`<p role="alert">${tr('연결 확인 결과를 읽지 못했습니다. 다시 진단하세요.')}</p>`:''}
 ${helpDetails(`<p>${tr('앱 서버와 현재 에이전트 연결을 따로 확인합니다. 설정은 자동으로 바꾸지 않습니다.')}</p><h3>${tr('1. 앱 서버')}</h3><p id="bundledConnectionState">${connectionMessage(fresh.state)}</p>
 ${report.app?`<p class="s">${tr('앱 버전')}: ${esc(report.app.app_version||tr('확인할 수 없음'))}</p><pre class="prompt mono">${esc(report.app.python)}\n${esc(report.app.server)}</pre>`:''}
 <h3>${tr('2. 등록된 경로')}</h3><p id="registeredConnectionState">${connectionMessage(registration.state)}</p>${registration.server?`<pre class="prompt mono">${esc(registration.command)}\n${esc(registration.server)}</pre>`:''}
 <p class="s">${tr('앱 서버가 정상이어도 에이전트가 재연결한 것은 아닙니다. 프로젝트와 바뀐 것은 새로고침하지 않습니다.')}</p>`,'진단 상세')}
 ${valid?`<details><summary>${tr('요청 내용 보기')}</summary><pre class="prompt mono">${esc(report.handoff)}</pre></details>`:''}`}`;
 $('connectionFeature').onchange=e=>startConnectionDiagnostic(e.target.value);
 if($('backToMap'))$('backToMap').onclick=()=>{S.agentPrompt=null;S.agentPurpose=null;render();};
 $('runConnectionDiagnostic').onclick=()=>startConnectionDiagnostic(report.feature);
 if($('checkCurrentConnection'))$('checkCurrentConnection').onclick=checkCurrentConnection;
 if($('copyConnectionRequest'))$('copyConnectionRequest').onclick=async()=>{
  if(!valid)return;
  try{await navigator.clipboard.writeText(report.handoff);if(S.connectionDiagnostic!==report||S.agentPurpose!=='connection'||!$('connectionCopyStatus'))return;report.copied=true;$('connectionCopyStatus').textContent=tr('복사했습니다. 에이전트 채팅에 붙여 넣으세요.');}
  catch{if(S.connectionDiagnostic===report&&$('connectionCopyStatus'))$('connectionCopyStatus').textContent=tr('요청을 복사하지 못했습니다. 다시 눌러 주세요.');}
 };
}
