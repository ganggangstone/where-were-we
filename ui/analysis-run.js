/* App-owned analysis. Status/provider reads never start a model turn. */
const AnalysisRun = (() => {
  const activeStates = new Set(['preparing', 'running', 'saving']);
  let scopeKey = '', epoch = 0, revision = 0, timer = null, checking = null;
  let run = null, provider = null, providerBusy = false, busy = false, error = null;
  const loaded = new Set();
  let openedPreview = null, openedOverview = null, openedFeature = null;
  const text = (ko, en) => S.lang === 'en' ? en : ko;
  const scope = () => ({project:S.project, repository:['make_steps','make_jobs'].includes(S.analysisChoice?.task) ? '' : (S.analysisChoice?.target || S.repository || '').replace(/^\*$/, ''), branch:S.branch, lang:S.lang});
  function intent() {
    const choice=S.analysisChoice || {}, command=choice.task || 'quick_overview';
    const task=({resource_batch:'resources',scope_overview:'overview',quick_overview:'overview',analysis_plan:'all',analysis_request:'analysis',make_system:'system',suggest_groups:'groups',make_steps:'steps',make_jobs:'jobs',briefing_request:'briefing'})[command] || 'all';
    const args={...scope(),...(task==='steps'?{screen:choice.detailTarget}:task==='jobs'?{node:choice.detailTarget}:{})};
    const targets=['steps','jobs'].includes(task) ? (choice.targets || analysisCalls(command,args).map(a=>({repository:a.repository || '',target:a.screen || a.node}))) : [];
    if(task==='resources')return {task,targets:[],max_calls:choice.maxCalls};
    return {task,targets:command==='scope_overview'?[{repository:scope().repository,target:choice.detailTarget}]:targets};
  }
  const key = () => JSON.stringify([scope(), S.analysisChoice, S.loadToken]);
  const decode = value => typeof value === 'string' ? JSON.parse(value) : value;
  const shown = () => S.agentPurpose === 'analysis' && S.agentPrompt != null;
  const current = token => token === epoch && scopeKey === key();
  const active = () => !!run && activeStates.has(run.state);
  const sameScope = () => !!run && Object.entries(scope()).every(([name,value]) => run[name] === value) && (JSON.stringify(run.intent || {task:'all',targets:[]})===JSON.stringify(intent()) || (!S.analysisChoice?.task && (run.intent?.task || 'all')==='all'));
  const usable = () => provider?.available === true && provider?.authenticated === true && provider?.account && typeof provider.account === 'object';
  function paint() {
    if (shown()) renderAgentPrompt();
    if ($('analyzeMap')) $('analyzeMap').textContent = analysisButtonText();
  }
  function errorCode(value) {
    if (typeof value === 'object' && value) return value.code || value.error_code || value.error?.code;
    try { return JSON.parse(String(value)).error?.code; } catch { return null; }
  }
  function message(value) {
    const code = errorCode(value), messages = {
      CLI_NOT_INSTALLED:['Claude Code를 설치하고 터미널에서 로그인한 뒤 다시 확인하세요.','Install Claude Code, sign in from your terminal, then check again.'],
      CLI_UNSUPPORTED:['Claude Code를 최신 버전으로 업데이트한 뒤 다시 확인하세요.','Update Claude Code to the latest version, then check again.'],
      CLI_NOT_AUTHENTICATED:['터미널의 Claude Code에서 구독 계정에 로그인한 뒤 다시 확인하세요.','Sign in to your subscription account in Claude Code from your terminal, then check again.'],
      CLI_AUTH_UNSUPPORTED:['Claude 구독 계정으로 Claude Code에 로그인하세요. API 계정은 이 실행에서 지원하지 않습니다.','Sign in to Claude Code with a Claude subscription. This runner does not support API accounts.'],
      CLI_AUTH_STATUS:['Claude Code의 로그인 상태를 확인하지 못했습니다. 터미널에서 로그인을 확인하고 다시 시도하세요.','Could not verify Claude Code sign-in. Check its login in your terminal and try again.'],
      CLI_ACCOUNT_CHANGED:['Claude Code 계정이 바뀌었습니다. 계정·상태를 다시 확인한 뒤 표시된 계정으로 다시 시도하세요.','The Claude Code account changed. Check account and status, then retry with the displayed account.'],
      CLI_ACCOUNT_UNIDENTIFIED:['Claude Code 계정을 확인할 수 없습니다. 터미널에서 구독 계정으로 다시 로그인한 뒤 계정·상태를 확인하세요.','Could not identify the Claude Code account. Sign in again with your subscription in the terminal, then check account and status.'],
      CLI_USAGE_LIMIT:['Claude 구독 사용 한도에 도달했습니다. Claude Code에서 한도와 초기화 시간을 확인한 뒤 다시 시도하세요.','The Claude subscription usage limit was reached. Check your limit and reset time in Claude Code, then retry.'],
      CLI_AUTH:['Claude Code 로그인이 만료됐거나 거부됐습니다. 터미널에서 다시 로그인한 뒤 계정·상태를 확인하세요.','Claude Code sign-in expired or was rejected. Sign in again in your terminal, then check account and status.'],
      CANCELLED:['분석이 취소됐습니다. 저장된 결과는 유지됩니다.','Analysis was cancelled. Saved results are retained.'],
      CLI_TIMEOUT:['Claude Code 응답 시간이 초과됐습니다. 연결과 사용 한도를 확인한 뒤 다시 시도하세요.','Claude Code timed out. Check your connection and usage limits, then retry.'],
      CLI_OUTPUT_LIMIT:['Claude 응답이 너무 큽니다. 코드 범위를 줄인 뒤 다시 시도하세요.','The Claude response was too large. Narrow the code scope and retry.'],
      CLI_INVALID_OUTPUT:['Claude 결과를 검증하지 못했습니다. 저장된 결과는 유지됩니다. 다시 시도하세요.','Could not validate the Claude result. Saved results are retained. Retry the analysis.'],
      CLI_INPUT_INVALID:['분석할 코드 범위가 너무 크거나 비어 있습니다. 코드 연결과 범위를 확인하세요.','The analysis input is too large or empty. Check the code connection and scope.'],
      CLI_UNAVAILABLE:['Claude Code를 실행하지 못했습니다. 설치와 실행 권한을 확인하세요.','Could not start Claude Code. Check its installation and permissions.'],
      CLI_FAILED:['Claude Code 실행에 실패했습니다. 로그인·연결·구독 한도를 확인한 뒤 다시 시도하세요.','Claude Code failed. Check sign-in, connection, and subscription limits, then retry.'],
      interrupted:['분석이 중단됐습니다. 저장된 결과는 유지됩니다. 다시 시도하면 필요한 분석을 새 코드 기준으로 이어갑니다.','Analysis was interrupted. Saved results are retained. Retry to run the remaining analysis against the current code.'],
      pins_changed:['코드나 설정이 바뀌었습니다. 필요한 경우 새로고침한 뒤 새 분석을 시작하세요.','Code or settings changed. Refresh if needed, then start a new analysis.'],
      source_unavailable:['분석할 코드를 읽지 못했습니다. 코드 연결을 확인한 뒤 새 분석을 시작하세요.','Could not read the selected source. Check the code connection and start a new analysis.'],
      source_too_large:['추가 분석 자료를 한 번의 입력 한도에 맞추지 못했습니다. 저장된 결과는 유지됩니다.','Additional analysis context could not fit one bounded input. Saved results are retained.'],
      already_running:['이 코드의 분석이 이미 준비되거나 실행 중입니다. 상태를 다시 확인하세요.','Analysis is already prepared or running for this code. Check its status again.'],
      invalid_output:['AI 결과의 형식이나 근거를 검증하지 못했습니다. 저장된 결과는 유지됩니다. 다시 시도하세요.','The AI result format or evidence could not be validated. Saved results are retained. Retry the analysis.'],
      invalid_result:['AI 결과를 검증하지 못했습니다. 저장된 결과는 유지됩니다. 다시 시도하세요.','Could not validate the AI result. Saved results are retained. Retry the analysis.'],
      analysis_failed:['분석을 마치지 못했습니다. 저장된 결과는 유지됩니다. 다시 시도하세요.','Analysis could not finish. Saved results are retained. Retry the analysis.'],
      analysis_blocked:['먼저 확인할 분석이 있습니다. 기존 AI 요청의 안내에서 수집 상태·코드 설정·AI 제안을 확인하세요.','Some analysis needs attention. Check collection, code settings, and AI proposals in the existing request instructions.'],
      timeout:['분석 제한 시간에 도달했습니다. 저장된 결과는 유지됩니다. 다시 시도하면 남은 분석을 실행합니다.','Analysis reached its time limit. Saved results are retained. Retry to finish the remaining analysis.'],
      task_limit:['분석 작업 한도에 도달했습니다. 다시 시도하면 남은 분석을 실행합니다.','Analysis reached its task limit. Retry to finish the remaining analysis.'],
      result_read_failed:['저장된 결과를 읽지 못했습니다. 계정·상태 다시 확인을 누르세요.','Could not read saved results. Click Check account and status.'],
      worker_start_failed:['분석을 시작하지 못했습니다. 다시 시도하세요.','Could not start the analysis worker. Retry the analysis.']
    };
    return messages[code] ? text(...messages[code]) : text('분석을 진행하지 못했습니다. 다시 확인하거나 AI에게 보낼 요청 복사를 이용하세요.','The analysis could not proceed. Check again or copy a request for your AI instead.');
  }
  const stateLabel = () => run?.cancel_requested && active() ? text('취소 중…','Cancelling…') : ({
    preparing:text('준비 중…','Preparing…'), running:text('분석 중…','Running…'), saving:text('저장 중…','Saving…'),
    completed:text('완료','Completed'), failed:text('실패','Failed'), cancelled:text('취소됨','Cancelled')
  })[run?.state] || '';
  function schedule(token) {
    clearTimeout(timer);
    if (current(token) && active() && !document.hidden) timer = setTimeout(() => check(), 1500);
  }
  async function accept(value, token) {
    if (!current(token)) return;
    run = value; error = null; paint();
    // Use the existing analysis-only read: never collect or move change history.
    if (run?.intent?.task!=='overview' && sameScope() && !active() && (run.state === 'completed' || run.completed_tasks?.length) && !loaded.has(run.id)) {
      const id = run.id; loaded.add(id);
      try { await reloadAnalysisOnly(() => current(token) && run?.id === id); }
      catch { if (current(token)) { loaded.delete(id); error = {code:'result_read_failed'}; paint(); } }
    }
    schedule(token);
  }
  async function check() {
    const token = epoch, version = revision;
    if (!S.project || document.hidden || !current(token) || checking === token) return;
    checking = token;
    try {
      const value = decode(await invoke('analysis_run_status', {scope:scope()}));
      if (current(token) && version === revision) await accept(value, token);
    } catch (value) { if (current(token) && version === revision) { error = value; paint(); schedule(token); } }
    finally { if (checking === token) checking = null; schedule(token); }
  }
  function syncScope() {
    const next = key();
    if (next === scopeKey) return;
    scopeKey = next; openedPreview = null; epoch++; revision++; clearTimeout(timer); checking = null;
    run = null; busy = false; error = null;
    if (S.project) void check();
  }
  async function providers() {
    if (providerBusy) return;
    providerBusy = true; paint();
    try { provider = decode(await invoke('analysis_providers', {}))?.providers?.find(p => (p.id || p.provider) === 'claude') || {error_code:'CLI_UNAVAILABLE'}; }
    catch { provider = {error_code:'CLI_UNAVAILABLE'}; }
    finally { providerBusy = false; paint(); }
  }
  async function execute(command) {
    syncScope();
    if (busy || !S.project || (command !== 'analysis_run_cancel' && !usable())) return;
    if (command === 'analysis_run_start' && active()) return;
    if (command === 'analysis_run_retry' && (!sameScope() || !['failed','cancelled'].includes(run?.state))) return;
    if (command === 'analysis_run_cancel' && (!active() || run.cancel_requested)) return;
    const token = epoch, args = command === 'analysis_run_start' ? {scope:{...scope(),intent:intent()}, expectedAccount:provider.account} : {runId:run.id};
    if (command === 'analysis_run_retry') args.expectedAccount = provider.account;
    revision++; busy = true; error = null; clearTimeout(timer); paint();
    try { await accept(decode(await invoke(command, args)), token); }
    catch (value) { if (current(token)) { error = value; paint(); } }
    finally { if (current(token)) { busy = false; paint(); schedule(token); } }
  }
  function savedOverviews() {
    const scoped=S.analysisChoice?.task==='scope_overview';
    const groups=scoped?(run?.saved_scope_overviews || []):(run?.saved_overviews || (run?.branch===S.branch && run?.lang===S.lang ? Object.values(run.overviews || {}) : []));
    return groups.filter(group=>{
      if(scoped && (group.resource!==S.analysisChoice.detailTarget || group.repository!==scope().repository))return false;
      if(group.repository===''){
        const pin=run.current_legacy_pin;
        return !scope().repository && !!pin && group.commit===pin.commit && group.configuration===pin.configuration;
      }
      const repo=S.projectInfo?.repositories?.find(r=>r.id===group.repository);
      const commit=repo?.commits?.[S.branch];
      return (!scope().repository || scope().repository===group.repository) && commit && group.commit.startsWith(commit)
        && repo.fingerprint===group.configuration && !repo.config_changed;
    });
  }
  const overviewKey = group => JSON.stringify([S.project,S.branch,S.lang,group.repository,group.commit,group.configuration,group.resource]);
  function overviewIndex(group) {
    const map=S.maps?.[S.branch];
    return group.repository ? map?.structure_indexes?.find(i=>i.repository===group.repository && i.commit===group.commit)
      : map?.structure_index?.commit===group.commit ? map.structure_index : null;
  }
  function resourcesIn(index) {
    const flow=index?.service_flow || {};
    return [...new Set([...flow.feature_groups || [],...flow.registered_route_groups || []].map(group=>group.resource))];
  }
  function remainingScopes(group) {
    if(group.resource || !Array.isArray(group.scope_coverage?.selected))return [];
    const sampled=new Set(group.scope_coverage.selected);
    return resourcesIn(overviewIndex(group)).filter(resource=>!sampled.has(resource));
  }
  function savedStages(details) {
    const rows=new Map();
    for(const detail of details || []){
      const kind=detail.kind;
      const label=kind==='action' ? detail.label || detail.event
        : kind==='data' && ['read','write'].includes(detail.operation) && detail.model
          ? text(detail.operation==='read'?'모델 읽기':'모델 쓰기',detail.operation==='read'?'Model read':'Model write')+' · '+detail.model : '';
      if(!label || !detail.evidence?.length)continue;
      const key=JSON.stringify([kind,label]);
      if(!rows.has(key))rows.set(key,{kind,label,sites:new Map()});
      for(const site of detail.evidence)rows.get(key).sites.set(JSON.stringify([site.file,site.line]),site);
    }
    return [...rows.values()].map(({kind,label,sites})=>`<div ${kind==='action'?'data-flow-actions':'data-flow-storage'}><details class="sect"><summary>${esc(label)}</summary>${[...sites.values()].map(site=>`<div class="s"><code>${esc(site.file)}:${esc(site.line)}</code></div><pre>${esc(site.quote)}</pre>`).join('')}</details></div>`).join('');
  }
  function overviewTree(group) {
    const files=group.files.map(file=>{
      const items=group.items.filter(item=>item.file===file);
      const nodes=items.map(item=>`<li><b>${esc(item.name)}</b>
        ${item.description ? `<p>${esc(item.description)}</p>` : ''}
        ${esc([item.method,item.path,item.function].filter(Boolean).join(' '))}
        <div class="s"><code>${esc(file)}:${esc(item.line)}</code></div><pre>${esc(item.quote)}</pre></li>`).join('');
      return `<li><code>${esc(file)}</code>${nodes ? `<ul>${nodes}</ul>` : ''}</li>`;
    }).join('');
    const index=overviewIndex(group);
    const edgesInSource=index?.service_flow?.connections || [];
    const sameSite=(a,b)=>!!a && !!b && a.file===b.file && a.line===b.line;
    const edgeHtml=edge=>{
      const matches=row=>row && row.method===edge.method && row.path===edge.path && sameSite(row.client,edge.client) && sameSite(row.server,edge.server);
      const registration=edge.kind==='server_registration';
      const live=registration?index?.service_flow?.registered_routes?.find(row=>row.method===edge.method && row.path===edge.path && sameSite(row.server,edge.server)):edgesInSource.find(matches);
      const match=live || (matches(edge.source_connection)?edge.source_connection:null);
      const evidence=(file,line)=>`<code>${esc(file)}:${esc(line)}</code>`;
      const stored=!live && savedStages(edge.details);
      const stages=stored || (match?flowActions(match.actions,evidence)+flowDataSteps(match.data_steps,evidence):'');
      const basis=edge.basis || match?.basis;
      const condition=basis==='path_template'?` · ${text('경로 패턴이 맞을 때','If the path pattern matches')} <code>${esc(edge.server_path || match?.server_path)}</code>`:basis==='declared_defaults'?` · ${(registration?text('설정 기본값','Configuration defaults'):text('설정·클라이언트 기본값에서 일치','Matches configured client and server defaults'))}`:'';
      return `<li><b>${esc(edge.method)} ${esc(edge.path)}</b>${condition}<ul>${[
        [text('요청 코드','Request code'),edge.client],[text('서버 함수','Server handler'),edge.server]
      ].filter(([,side])=>side).map(([label,side])=>`<li>${label} · ${evidence(side.file,side.line)}<pre>${esc(side.quote)}</pre></li>`).join('')}</ul>${stages}</li>`;
    };
    const edges=group.connections || [];
    const byId=new Map(edges.filter(edge=>Number.isInteger(edge.id)).map(edge=>[edge.id,edge]));
    const grouped=new Set();
    const features=(group.feature_groups || []).map((feature,i)=>{
      const members=(feature.connection_ids || []).map(id=>byId.get(id)).filter(Boolean);
      if(!members.length)return '';
      members.forEach(edge=>grouped.add(edge.id));
      const endpoints=members.flatMap(edge=>[edge.client,edge.server]).filter(Boolean);
      const item=group.items.find(item=>item.description && endpoints.some(side=>side.file===item.file && side.line===item.line));
      const description=item?.description || members.map(edge=>edge.method+' '+edge.path).join(' · ');
      const key=overviewKey(group)+i,open=openedFeature===key;
      return `<section class="sect"><button class="btn plain" data-overview-feature="${esc(key)}" aria-expanded="${open}"><strong>${esc(feature.name)}</strong> · ${esc(description)}</button>${open?`<ul>${members.map(edgeHtml).join('')}</ul>`:''}</section>`;
    }).join('');
    const commands=(group.cli_entries || []).filter(entry=>entry.command && entry.registration?.quote && entry.registration.line>0).map(entry=>{
      const cobra=entry.kind==='cobra_subcommand';
      const rows=[
        [text('상위 명령','Parent command'),entry.parent_evidence],
        [cobra?text('부모·하위 명령','Parent and subcommand'):text('명령 등록','Command declaration'),entry.registration],
        [cobra?text('하위 명령 선언','Subcommand declaration'):text('실행 대상','Entry point'),entry.target_evidence],
        [text('설명','Description'),entry.description_evidence],
        [text('실행 함수','Command handler'),entry.handler_evidence]
      ];
      const citations=rows.filter(([,site])=>site?.quote && site.line>0).map(([label,site])=>`<div class="s">${label} · <code>${esc(site.file)}:${esc(site.line)}</code></div><pre>${esc(site.quote)}</pre>`).join('');
      const target=entry.target_file && !entry.target_evidence?`<p class="s">${text('대상 파일','Target file')} · <code>${esc(entry.target_file)}</code></p>`:'';
      return `<details class="sect" data-saved-command><summary><strong class="mono">${esc(entry.command)}</strong>${entry.description && entry.description_evidence?' · '+esc(entry.description):''}</summary>${citations}${target}</details>`;
    }).join('');
    const remaining=edges.filter(edge=>!grouped.has(edge.id));
    const title=features?text('그 밖의 요청','Other requests'):(remaining.length && remaining.every(edge=>edge.kind==='server_registration')?text('서버 경로','Server routes'):text('코드에서 확인한 요청 연결','Request connections in source'));
    const remainingFlow=remaining.length?`<figure class="overview-tree"><figcaption>${title}</figcaption><ul>${remaining.map(edgeHtml).join('')}</ul></figure>`:'';
    const flow=features && remaining.length?`<details><summary>${title} · ${remaining.length}</summary><ul>${remaining.map(edgeHtml).join('')}</ul></details>`:remainingFlow;
    const sources=`<figure class="overview-tree"><figcaption>${text('파일별 기능 구조도','Feature diagram by source file')}</figcaption><ul>${files}</ul></figure>`;
    return features || commands?`<section class="overview-tree"><h4>${text('기능별 개요 (베타)','Feature overview (beta)')}</h4>${commands}${features}</section>${flow}<details><summary>${text('파일별 근거','Evidence by file')}</summary>${sources}</details>`:`${flow}${sources}`;
  }
  function overviewHtml() {
    return savedOverviews().map((group,index)=>{
      const key=overviewKey(group);
      const open=openedOverview===key || (openedOverview===null && group.format==='overview-v1');
      const coverage=group.scope_coverage;
      const scopeCounts=coverage?.total ? ' · '+text('로컬에서 확인한 요청 경로 묶음 중 ','Verified request scopes sampled: ')+coverage.selected.length+'/'+coverage.total : '';
      const resources=open?remainingScopes(group):[];
      const local=resources.length?`<div class="ctl"><label>${text('개요에 포함되지 않은 경로','Paths outside this overview')} <select id="overviewLocalScope${index}">${resources.map(resource=>`<option>${esc(resource)}</option>`).join('')}</select></label><button class="btn quiet" id="overviewOpenScope${index}">${text('지도에서 열기','Open in map')}</button></div>`:'';
      return `<section class="sect"><button class="btn plain" type="button" id="savedOverview${index}" aria-expanded="${open}">${group.resource?text('저장된 경로 설명','Saved path explanation'):text('저장된 첫 개요','Saved initial overview')} · ${esc(group.repository ? connectionDisplayName(group.repository) : S.project)}</button>
        <p class="s">${text('파일 '+group.files.length+'개의 일부 코드에서 확인한 항목 '+group.items.length+'개','Items verified: '+group.items.length+' · Files sampled: '+group.files.length)}${esc(scopeCounts)}</p>
        ${open ? `<div><code>${esc(group.commit.slice(0,8))}</code>${overviewTree(group)}${local}</div>` : ''}</section>`;
    }).join('');
  }
  function previewItems() {
    if (!sameScope() || run.cancel_requested) return [];
    let groups = [];
    if (active()) {
      const preview = run.preview;
      if (preview && preview.repository === run.current_task?.repository &&
          preview.commit === run.current_task?.commit) groups = [preview];
    } else if (run.state === 'completed') {
      groups = (run.program_observations || []).filter(group => {
        const commit = group.repository
          ? S.projectInfo?.repositories?.find(repo => repo.id === group.repository)?.commits?.[S.branch]
          : S.maps?.[S.branch]?.commit;
        return commit && group.commit === run.pins?.[group.repository]?.commit && group.commit.startsWith(commit);
      });
    }
    return groups.filter(group => !scope().repository || group.repository === scope().repository)
      .flatMap(group => (group.items || []).map(item => ({...item,repository:group.repository,commit:group.commit})));
  }
  function previewKey(item) {
    return JSON.stringify([run.id, item.repository, item.commit, item.kind, item.file, item.line, item.name]);
  }
  function previewHtml() {
    const items = previewItems();
    if (!items.length) return '';
    const kinds = {screen:text('화면','Screen'),request:text('서버 요청','Server request'),program:text('프로그램','Program')};
    const rows = items.map((item,i) => {
      const opened = openedPreview === previewKey(item);
      return `<div><button class="btn plain" type="button" id="analysisPreview${i}" aria-expanded="${opened}">${esc(kinds[item.kind] || item.kind)} · ${esc(item.name)}</button>
        ${opened ? `<div class="s">${esc(item.repository || run.project)} · ${esc(item.commit.slice(0,8))}</div><div><code>${esc(item.file)}:${esc(item.line)}</code></div><pre style="white-space:pre-wrap;overflow-wrap:anywhere">${esc(item.quote)}</pre>` : ''}</div>`;
    });
    return `<section class="sect"><h3>${active() ? text('분석 중 확인한 기능','Features verified so far') : text('확인한 프로그램','Verified programs')}</h3>${rows.join('')}</section>`;
  }
  function localResourceCount() {
    const map=S.maps?.[S.branch],repo=scope().repository;
    const indexes=map?.structure_indexes || (map?.structure_index?[map.structure_index]:[]);
    return indexes.filter(index=>!repo || index.repository===repo).reduce((n,index)=>n+resourcesIn(index).length,0);
  }
  function html(includeOverview=true) {
    if(S.analysisChoice?.task==='scope_overview' && savedOverviews().length && !active())return overviewHtml();
    const account = provider?.account, identity = typeof account === 'string' ? account : account?.email || account?.id;
    const done = Array.isArray(run?.completed_tasks) ? run.completed_tasks.length : Number(run?.completed_tasks || 0);
    const batchRun=run?.intent?.task==='resources';
    const completed=new Set((batchRun?run.completed_tasks || []:[]).map(t=>JSON.stringify([t.repository,t.target])));
    const left=batchRun?(run.tasks || []).filter(t=>!completed.has(JSON.stringify([t.repository,t.target]))).length:run?.tasks?.length || 0;
    const total=done+left;
    const progress=batchRun?text('경로 묶음 '+done+'개 저장 · '+left+'개 남음','Path groups saved: '+done+' · Remaining: '+left):done+'/'+total+' '+text('작업 저장됨','tasks saved');
    const task = run?.current_task;
    const batches=run?.batch_progress,stats=run?.input_stats;
    let inputProgress='';
    if (batches && active()) {
      inputProgress=batches.discovering
        ? text('먼저 살펴본 입력 조각 '+batches.completed+'개 · 전체 개수 집계 전',
               'Initial input units reviewed: '+batches.completed+' · Total not yet known')
        : text('현재 작업 입력 조각','Current task input units')+': '+batches.completed+'/'+batches.total;
    }
    const names={resources:text('경로 묶음 설명','Path group explanations'),overview:text('첫 개요','Initial overview'),all:text('지도·서비스 구성·화면 묶음','Map, service overview, screen groups'),analysis:text('지도','Map'),system:text('서비스 구성','Service overview'),groups:text('화면 묶음','Screen groups'),steps:text('동작 과정','Action steps'),jobs:text('프로그램이 하는 일','Program jobs'),briefing:text('변경 설명','Change explanation')};
    const taskName = typeof task === 'string' ? task : batchRun && task?.target ? [task.repository,task.target].filter(Boolean).join(' · ') : task ? [task.repository, text(task.task==='overview'?'첫 개요':PLAN_NAMES[task.task] || task.task, ({overview:'Initial overview',analysis:'Detailed map',system:'Architecture',groups:'Screen groups',jobs:'Program jobs',steps:'Action steps',briefing:'Change explanation'})[task.task] || task.task)].filter(Boolean).join(' · ') : '';
    const issue = error || run?.error;
    const resources=localResourceCount();
    const batch=intent().task==='resources';
    const canStart = (!batch || intent().max_calls>0) && usable() && !providerBusy && !busy && !active();
    const runScope = run ? [run.repository ? connectionDisplayName(run.repository) : text('연결한 코드 전체','All connected repositories'),run.branch,run.lang].join(' · ') : '';
    const runAccount = run?.account?.email || run?.account?.id;
    const choice=intent();
    const cached=run?.resource_estimate?.cached || 0;
    const savedGroups=batch && batchRun?(run.saved_scope_overviews || []).filter(group=>!scope().repository || scope().repository===group.repository):[];
    const resultPicker=savedGroups.length?`<div class="ctl"><label>${text('저장된 경로 설명','Saved path explanations')} <select id="batchSavedResource">${savedGroups.map((group,i)=>`<option value="${i}">${esc([group.repository,group.resource].filter(Boolean).join(' · '))}</option>`).join('')}</select></label><button class="btn quiet" id="openBatchSaved">${text('설명 열기','Open explanation')}</button></div>`:'';
    const targets=choice.targets.map(t=>[t.repository,t.target].filter(Boolean).map(esc).join(' · '));
    const scoped=S.analysisChoice?.task==='scope_overview';
    const startLabel=batch?text('경로 묶음 설명 생성','Generate path group explanations'):scoped?text('이 경로 설명 생성','Generate path explanation'):choice.task==='overview' ? text('첫 개요 만들기','Create initial overview')
      : choice.task==='all' ? text('전체 코드 분석 (베타)','Analyze full codebase (beta)')
      : choice.task==='analysis' ? text('상세 지도 분석 (베타)','Analyze detailed map (beta)')
      : text(names[choice.task]+' 분석 시작','Analyze '+names[choice.task]);
    return `<section class="sect" aria-label="${text('자동 분석 (베타)','Automatic analysis (beta)')}">
      ${includeOverview?overviewHtml():''}
      <p><strong>Claude Code</strong> · ${esc(identity || text('계정 미확인','Account not verified'))}${account?.subscription_type ? ' · '+esc(account.subscription_type) : ''}</p>
      <p class="s">${esc(scope().repository ? connectionDisplayName(scope().repository) : text('연결한 코드 전체','All connected repositories'))} · ${esc(S.branch)}${targets.length?' · '+targets.join(', '):''}</p>
      <p class="s">${text('선택한 코드가 Claude로 전송되며 구독 한도가 적용됩니다.','Claude receives the selected code. Subscription usage limits apply.')}</p>
      ${providerBusy ? `<p role="status">${text('Claude Code 계정 확인 중…','Checking the Claude Code account…')}</p>` : provider && !usable() ? `<p role="alert">${esc(message(provider))}</p>` : ''}
      ${run ? `${!sameScope() || (runAccount && runAccount!==identity) ? `<p class="s">${text('이 분석의 코드','This run analyzes')}: ${esc(runScope)} · ${esc(names[run.intent?.task || 'all'])}${(run.intent?.targets || []).map(t=>' · '+esc(t.repository)+' · '+esc(t.target)).join('')}${runAccount ? ' · '+esc(runAccount) : ''}</p>` : ''}${!sameScope() ? `<p class="s">${text('다른 분석입니다. 실행 중이면 완료 후 시작하거나 취소하세요.','Different analysis selected. Wait for the active run or cancel it.')}</p>` : ''}<div role="status" aria-live="polite"><strong>${esc(stateLabel())}</strong> · ${esc(progress)}${batchRun && cached?' · '+text('재사용 '+cached+'개',cached+' reused'):''}${taskName ? '<div>'+esc(taskName)+'</div>' : ''}</div><progress max="${Math.max(total, 1)}" value="${done}" aria-label="${text('분석 진행률','Analysis progress')}"></progress>${run.blocked?.length ? `<p class="s">${text('먼저 확인할 분석','Analysis requiring attention')}: ${run.blocked.length}</p>` : ''}` : ''}
      ${stats ? `<details><summary>${text('AI 사용량','AI usage')}</summary><p class="s">${text('입력 호출','Input calls')}: ${stats.calls} · ${text('전송한 입력 바이트','Encoded input bytes')}: ${stats.bytes}${inputProgress ? ' · '+esc(inputProgress) : ''}</p></details>` : ''}
      ${issue ? `<p role="alert">${esc(message(issue))}</p>` : ''}
      ${!active() && choice.task==='overview' ? `<p class="s" id="overviewLimits">${scoped?text('선택한 경로 · 최대 4개 파일, AI 1회 이내','Selected path: up to 4 files, 1 AI call maximum.'):text('첫 개요 · 연결한 코드마다 최대 4개 파일, AI 1회 이내','Per repository: up to 4 files, 1 AI call maximum.')}</p>` : ''}
      ${batch && !active()?`<p class="s" id="resourceLimits">${text('경로 묶음 '+choice.max_calls+'개 · AI 최대 '+choice.max_calls+'회','Path groups: '+choice.max_calls+' · Up to '+choice.max_calls+' AI calls')}</p>`:''}
      <div class="ctl">${active() ? `<button class="btn" id="cancelAppAnalysis" ${busy || run.cancel_requested ? 'disabled' : ''}>${text('분석 취소','Cancel analysis')}</button>` : sameScope() && ['failed','cancelled'].includes(run?.state) ? `<button class="btn primary" id="retryAppAnalysis" ${canStart ? '' : 'disabled'}>${text('현재 코드로 다시 시도','Retry with current code')}</button>` : `<button class="btn primary" id="startAppAnalysis" ${batch?'aria-describedby="resourceLimits"':choice.task==='overview' ? 'aria-describedby="overviewLimits"' : ''} ${canStart ? '' : 'disabled'}>${esc(startLabel)}</button>`}
      ${resources && !scoped && (!batch || resources!==choice.max_calls) && !active()?`<button class="btn quiet" id="chooseResourceBatch">${text('경로 묶음별 AI 설명 (베타)','AI explanations by path group (beta)')}</button>`:''}
      ${!scoped && !active() && intent().task==='overview' ? `<button class="btn quiet" id="startFullAnalysis" ${canStart ? '' : 'disabled'}>${text('전체 코드 분석 (베타)','Analyze full codebase (beta)')}</button>` : ''}
      <button class="btn quiet" id="checkAppAnalysis" ${busy || providerBusy ? 'disabled' : ''}>${text('계정·상태 다시 확인','Check account and status')}</button>
      ${!batchRun && sameScope() && done > 0 && run.intent?.task!=='overview' ? `<button class="btn quiet" id="viewAppAnalysis">${text('저장된 결과 보기','View saved results')}</button>` : ''}</div>
      ${resultPicker}${previewHtml()}</section>`;
  }
  function bind() {
    $('insp')?.querySelectorAll?.('[data-overview-feature]').forEach(button=>button.onclick=()=>{
      const key=button.dataset.overviewFeature;openedFeature=openedFeature===key?null:key;paint();
    });
    savedOverviews().forEach((group,i)=>{
      const openScope=$('overviewOpenScope'+i);
      if(openScope)openScope.onclick=()=>{
        const resource=$('overviewLocalScope'+i)?.value;
        if(!remainingScopes(group).includes(resource))return;
        S.agentPrompt=null;S.controlTarget=null;S.view='sys';S.q='';render();
        const repo=$('moduleRepository');
        if(repo && repo.value!==group.repository){repo.value=group.repository;repo.dispatchEvent(new Event('change'));}
        const target=[...$('moduleGraph').querySelectorAll('[data-local-resource]')].find(el=>el.dataset.localResource===resource);
        if(target?.getAttribute('aria-expanded')==='false')target.click();
        if(!target){
          const flow=overviewIndex(group)?.service_flow;
          const routeGroup=flow?.registered_route_groups?.find(row=>row.resource===resource);
          const route=flow?.registered_routes?.[routeGroup?.registered_route_indexes[0]];
          const position=route?standaloneRoutes(flow).indexOf(route):-1;
          if(position>=0){
            Object.assign(S.moduleGraph,{routePage:Math.floor(position/ROUTES_PER_PAGE),routesOpen:true});render();
            const row=[...$('moduleGraph').querySelectorAll('[data-registered-route]')].find(el=>el.dataset.registeredRoute===resource);
            if(row){row.open=true;row.scrollIntoView({block:'center'});return;}
          }
        }
        $('moduleGraph').scrollIntoView({block:'start'});
      };
      const button=$('savedOverview'+i);
      if(button)button.onclick=()=>{
        const key=overviewKey(group);
        openedOverview=button.getAttribute?.('aria-expanded')==='true' || openedOverview===key ? '' : key;
        paint();
      };
    });
    previewItems().forEach((item,i) => {
      const button = $('analysisPreview'+i);
      if (button) button.onclick = () => {
        const key = previewKey(item);
        openedPreview = openedPreview === key ? null : key;
        paint();
        $('analysisPreview'+i)?.focus?.();
      };
    });
    if ($('startAppAnalysis')) $('startAppAnalysis').onclick = () => execute('analysis_run_start');
    if ($('openBatchSaved')) $('openBatchSaved').onclick=()=>{
      const groups=(run?.saved_scope_overviews || []).filter(group=>!scope().repository || scope().repository===group.repository);
      const selected=groups[Number($('batchSavedResource').value)];
      if(selected)openAnalysisPanel('scope_overview',selected.resource,selected.repository);
    };
    if ($('chooseResourceBatch')) $('chooseResourceBatch').onclick=()=>{
      S.analysisChoice={...S.analysisChoice,task:'resource_batch',detailTarget:'',maxCalls:localResourceCount()};
      syncScope();paint();
    };
    if ($('startFullAnalysis')) $('startFullAnalysis').onclick = () => {
      S.analysisChoice={...S.analysisChoice,task:'analysis_plan'};
      return execute('analysis_run_start');
    };
    if ($('retryAppAnalysis')) $('retryAppAnalysis').onclick = () => execute('analysis_run_retry');
    if ($('cancelAppAnalysis')) $('cancelAppAnalysis').onclick = () => execute('analysis_run_cancel');
    if ($('checkAppAnalysis')) $('checkAppAnalysis').onclick = () => { void providers(); void check(); };
    if ($('viewAppAnalysis')) $('viewAppAnalysis').onclick = async () => {
      const token = epoch;
      try { await reloadAnalysisOnly(() => current(token)); if (current(token)) { S.agentPrompt = null; const task=run.intent?.task || 'all';
        if(task==='steps')Object.assign(S,S.analysisChoice?.resultContext || {});
        else S.view=({groups:'feat',briefing:'changes'})[task] || 'sys';
        render(); } }
      catch { if (current(token)) { error = {code:'result_read_failed'}; paint(); } }
    };
  }
  function open() { syncScope(); if (!provider && !providerBusy) void providers(); else void check(); }
  window.addEventListener('focus', () => { syncScope(); void check(); });
  document.addEventListener('visibilitychange', () => { clearTimeout(timer); if (!document.hidden) { syncScope(); void check(); } });
  return {syncScope, open, html, overviewHtml, bind, stateLabel, check};
})();
AnalysisRun.syncScope();
