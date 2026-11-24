/* App-owned analysis. Status/provider reads never start a model turn. */
const AnalysisRun = (() => {
  const activeStates = new Set(['preparing', 'running', 'saving']);
  let scopeKey = '', epoch = 0, revision = 0, timer = null, checking = null;
  let run = null, provider = null, providerBusy = false, busy = false, error = null;
  const loaded = new Set();
  let mapResults=null;
  let openedOverview = null, openedFeature = null;
  const text = (ko, en) => S.lang === 'en' ? en : ko;
  const scope = () => ({project:S.project, repository:['make_steps','make_jobs'].includes(S.analysisChoice?.task) ? '' : (S.analysisChoice?.target || S.repository || '').replace(/^\*$/, ''), branch:S.branch, lang:S.lang});
  function intent() {
    const choice=S.analysisChoice || {}, command=choice.task || 'quick_overview';
    // The map, names, groups and service structure come from the one 「분석하기」 (full); the rest are details the user asked for.
    const task=({resource_batch:'resources',scope_overview:'overview',quick_overview:'overview',make_steps:'steps',make_jobs:'jobs',briefing_request:'briefing'})[command] || 'full';
    const args={...scope(),...(task==='steps'?{screen:choice.detailTarget}:task==='jobs'?{node:choice.detailTarget}:{})};
    const targets=['steps','jobs'].includes(task) ? (choice.targets || analysisCalls(command,args).map(a=>({repository:a.repository || '',target:a.screen || a.node}))) : [];
    if(task==='resources')return {task,targets:[],max_calls:choice.maxCalls,...(choice.area?{area:choice.area}:{})};
    if(task==='full')return {task,targets:[],...(Array.isArray(choice.only)?{only:choice.only}:{})};
    return {task,targets:command==='scope_overview'?[{repository:scope().repository,target:choice.detailTarget}]:targets};
  }
  const key = () => JSON.stringify([scope(), S.analysisChoice, S.loadToken]);
  const decode = value => typeof value === 'string' ? JSON.parse(value) : value;
  const shown = () => S.agentPurpose === 'analysis' && S.agentPrompt != null;
  const current = token => token === epoch && scopeKey === key();
  const active = () => !!run && activeStates.has(run.state);
  const sameScope = () => !!run && Object.entries(scope()).every(([name,value]) => run[name] === value) && (JSON.stringify(run.intent)===JSON.stringify(intent()) || (run.intent?.task==='full' && intent().task==='full'));
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
    completed:run?.map_gaps?text('완료 · 일부 확인 불가','Completed · some parts unconfirmed'):text('완료','Completed'), failed:text('실패','Failed'), cancelled:text('취소됨','Cancelled')
  })[run?.state] || '';
  function schedule(token) {
    clearTimeout(timer);
    if (current(token) && active() && !document.hidden) timer = setTimeout(() => check(), 1500);
  }
  async function accept(value, token) {
    if (!current(token)) return;
    run = value; error = null;
    if(value && Array.isArray(value.saved_scope_overviews) && mapResults && mapResults.pin.project===scope().project && mapResults.pin.branch===scope().branch && mapResults.pin.lang===scope().lang && (!scope().repository || scope().repository===mapResults.pin.repository)){
      rememberScopes(mapResults,value);showMapBadges();
    }
    paint();
    // Use the existing analysis-only read: never collect or move change history.
    if (!['overview','full'].includes(run?.intent?.task) && sameScope() && !active() && (run.state === 'completed' || (run.completed_tasks?.length || Number(run.completed_tasks)>0)) && !loaded.has(run.id)) {
      const id = run.id; loaded.add(id);
      try { await reloadAnalysisOnly(() => current(token) && run?.id === id); }
      catch { if (current(token)) { loaded.delete(id); error = {code:'result_read_failed'}; paint(); } }
    }
    schedule(token);
  }
  const catalog=requested=>invoke('analysis_run_status',{scope:requested,view:'catalog'}).then(decode);
  async function readResource(ref) {
    if(ref.files && ref.items)return ref;
    const value=decode(await invoke('analysis_run_status',{view:'resource',scope:{...scope(),repository:ref.repository},resource:ref.resource}));
    return value && value.commit===ref.commit && value.configuration===ref.configuration && value.repository===ref.repository && value.resource===ref.resource?value:null;
  }
  async function check(refreshCatalog=false) {
    const token = epoch, version = revision;
    if (!S.project || document.hidden || !current(token) || checking === token) return;
    checking = token;
    try {
      let value;
      if(active() && !refreshCatalog){
        const progress=decode(await invoke('analysis_run_status',{view:'progress',runId:run.id}));
        if(progress && activeStates.has(progress.state))value={...run,...progress};
      }
      if(!value)value=await catalog(scope());
      if(value && S.analysisChoice?.task==='scope_overview'){
        const refs=value.saved_scope_overviews || [];
        const ref=refs.find(group=>group.resource===S.analysisChoice.detailTarget && group.repository===scope().repository);
        if(ref && !ref.files){
          const detail=await readResource(ref);
          value={...value,saved_scope_overviews:refs.filter(g=>g!==ref).concat(detail || [])};
        }
      }
      if (current(token) && version === revision) await accept(value, token);
      if (current(token) && !active() && S.agentPurpose==='analysis') void loadBoard(token);
    } catch (value) { if (current(token) && version === revision) { error = value; paint(); schedule(token); } }
    finally { if (checking === token) checking = null; schedule(token); }
  }
  function syncScope() {
    const next = key();
    if (next === scopeKey) return;
    scopeKey = next; epoch++; revision++; clearTimeout(timer); checking = null;
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
  function mapPin() {
    const m=M(),repository=S.moduleGraph?.repository || '';
    const index=(m?.structure_indexes || [m?.structure_index]).find(i=>i && (i.repository || '')===repository);
    if(!index)return null;
    const repo=S.projectInfo?.repositories?.find(r=>r.id===repository);
    if(repo?.config_changed)return null;
    return {project:S.project,repository,branch:S.branch,lang:S.lang,commit:index.commit,configuration:repo?.fingerprint,loadToken:S.loadToken};
  }
  function rememberScopes(cache,value) {
    if(!value || cache!==mapResults)return;
    const pin=cache.pin,configuration=pin.configuration || value.current_legacy_pin?.configuration;
    const resource=S.analysisChoice?.task==='saved_scope'?S.analysisChoice.detailTarget:null;
    const opened=cache.groups.get(resource);
    cache.groups.clear();
    if(!configuration)return;
    for(const group of value.saved_scope_overviews || []){
      if(group.repository===pin.repository && group.commit===pin.commit && group.configuration===configuration){
        cache.groups.set(group.resource,group.resource===resource && opened?.files && !group.files?opened:group);
      }
    }
  }
  function showMapBadges() {
    const cache=mapResults;
    for(const button of document.querySelectorAll('#moduleGraph [data-saved-scope]')){
      button.hidden=!cache?.groups.has(button.dataset.savedScope);
      button.onclick=async e=>{
        e.preventDefault();e.stopPropagation();
        if(cache!==mapResults || cache.key!==JSON.stringify(mapPin()) || !cache.groups.has(button.dataset.savedScope))return;
        const group=cache.groups.get(button.dataset.savedScope);
        openAnalysisPanel('saved_scope',group.resource,cache.pin.repository);
        if(!group.files){
          const choice=S.analysisChoice;
          let detail;try{detail=await readResource(group);}catch{}
          if(cache!==mapResults || cache.key!==JSON.stringify(mapPin()) || S.analysisChoice!==choice)return;
          if(!detail){cache.groups.delete(group.resource);showMapBadges();paint();return;}
          cache.groups.set(group.resource,detail);
          if(detail.feature_groups?.length)openedFeature=overviewKey(detail)+0;
          paint();
        }else if(group.feature_groups?.length){openedFeature=overviewKey(group)+0;paint();}
      };
    }
  }
  function bindMapResults() {
    if(!document.querySelector('#moduleGraph [data-saved-scope]'))return;
    const pin=mapPin();if(!pin){mapResults=null;showMapBadges();return;}
    const key=JSON.stringify(pin);
    if(mapResults?.key===key){showMapBadges();return;}
    const cache={pin,key,groups:new Map()};mapResults=cache;
    const requested={project:pin.project,repository:pin.repository,branch:pin.branch,lang:pin.lang};
    (async()=>{
      const value=await catalog(requested);
      rememberScopes(cache,value);
      if(cache===mapResults && JSON.stringify(mapPin())===key)showMapBadges();
    })().catch(()=>{if(cache===mapResults)mapResults=null;});
  }
  function savedScopeHtml() {
    const group=savedOverviews()[0];
    if(!group)return text('저장된 설명을 읽지 못했습니다.','Saved explanation unavailable.');
    if(!group.files)return text('불러오는 중…','Loading…');
    return `<code>${esc(group.commit.slice(0,8))}</code>${overviewTree(group)}`;
  }
  function savedOverviews() {
    if(S.analysisChoice?.task==='saved_scope'){
      const group=mapResults?.key===JSON.stringify(mapPin()) && mapResults.groups.get(S.analysisChoice.detailTarget);
      return group?[group]:[];
    }
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
  function savedWorkspace(group) {
    const valid=site=>site?.file && site.line>0 && site.quote;
    const packages=(group.workspace_packages || []).filter(pkg=>pkg.name && valid(pkg.registration) && valid(pkg.workspace));
    if(!packages.length)return '';
    const cite=site=>`<div class="s"><code>${esc(site.file)}:${esc(site.line)}</code></div><pre>${esc(site.quote)}</pre>`;
    const rows=packages.map(pkg=>{
      const description=pkg.description && valid(pkg.description_evidence);
      const edges=(group.workspace_dependencies || []).filter(edge=>edge.source===pkg.name && valid(edge.evidence));
      const deps=edges.map(edge=>`<div><b>${esc(edge.target)}</b> · <code>${esc(edge.kind)} · ${esc(edge.specifier)}</code>${cite(edge.evidence)}</div>`).join('');
      return `<details class="sect" data-saved-package><summary><strong>${esc(pkg.name)}</strong>${description?' · '+esc(pkg.description):''}</summary>${cite(pkg.registration)}${cite(pkg.workspace)}${description?cite(pkg.description_evidence):''}${deps}</details>`;
    }).join('');
    const total=group.workspace_coverage?.verified_packages;
    const count=Number.isInteger(total) && total>=packages.length?`${packages.length}/${total}`:String(packages.length);
    const matched=group.workspace_coverage?.matched_manifests;
    const coverage=Number.isInteger(total) && matched>total?`<span class="s">${text('지도에서 확인','Indexed in map')} · ${total}/${matched}</span>`:'';
    return `<section><h4>${text('개요에 포함된 패키지','Packages sampled')} · ${count}</h4>${coverage}${rows}</section>`;
  }
  function claimEvidence(item) {
    const sites=[item,...item.evidence || []].filter(site=>site?.file && site.line>0 && site.quote);
    if(!sites.length)return '';
    const unique=new Map(sites.map(site=>[JSON.stringify([site.file,site.line]),site]));
    const citations=[...unique.values()].map(site=>`<div class="s"><code>${esc(site.file)}:${esc(site.line)}</code></div><pre>${esc(site.quote)}</pre>`).join('');
    return `<details data-claim-evidence><summary>${text('코드 근거','Code evidence')} · ${unique.size}</summary>${citations}</details>`;
  }
  function overviewTree(group) {
    const files=group.files.map(file=>{
      const items=group.items.filter(item=>item.file===file);
      const nodes=items.map(item=>`<li><b>${esc(item.name)}</b>
        ${item.description ? `<p>${esc(item.description)}</p>` : ''}
        ${esc([item.method,item.path,item.function].filter(Boolean).join(' '))}
        ${claimEvidence(item)}</li>`).join('');
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
      const filters=(edge.details || []).filter(d=>d.kind==='conditional_filter' && typeof d.when==='boolean' && d.evidence?.length>=2);
      const filterHtml=filters.map(d=>{
        const claim=group.items.find(item=>d.evidence.every(site=>[item,...item.evidence || []].some(proof=>sameSite(proof,site))));
        return `<details class="sect" data-saved-filter><summary>${text('조회 필터','Query filter')} · ${esc(d.model)} · ${d.when?text('조건이 참일 때','When true'):text('조건이 거짓일 때','When false')}</summary>${claim?`<p>${esc(claim.description)}</p>${claimEvidence(claim)}`:d.evidence.map(site=>`<div class="s"><code>${esc(site.file)}:${esc(site.line)}</code></div><pre>${esc(site.quote)}</pre>`).join('')}</details>`;
      }).join('');
      return `<li><b>${esc(edge.method)} ${esc(edge.path)}</b>${condition}<ul>${[
        [text('요청 코드','Request code'),edge.client],[text('서버 함수','Server handler'),edge.server]
      ].filter(([,side])=>side).map(([label,side])=>`<li>${label} · ${evidence(side.file,side.line)}<pre>${esc(side.quote)}</pre></li>`).join('')}</ul>${stages}${filterHtml}</li>`;
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
      const conditional=members.some(edge=>['path_template','declared_defaults'].includes(edge.basis) || (edge.details || []).some(d=>d.kind==='conditional_filter'));
      const chips=`${members.slice(0,2).map(edge=>`<code class="route-chip">${esc(edge.method)} ${esc(edge.path)}</code>`).join('')}${members.length>2?`<span class="chip">+${members.length-2}</span>`:''}${conditional?`<span class="chip warn">${text('조건','Conditional')}</span>`:''}`;
      return `<section class="sect"><button class="feature-row" type="button" data-overview-feature="${esc(key)}" aria-expanded="${open}"><strong>${esc(feature.name)}</strong>${item?.role?`<span class="role">${esc(item.role)}</span>`:''}<span class="chips">${chips}</span></button>${open?`<p>${esc(description)}</p>${item?.evidence?.length?claimEvidence(item):''}<ul>${members.map(edgeHtml).join('')}</ul>`:''}</section>`;
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
    const workspace=savedWorkspace(group);
    return features || commands || workspace?`<section class="overview-tree"><h4>${text('기능별 개요','Features')} ${beta()}</h4>${workspace}${commands}${features}</section>${flow}<details><summary>${text('파일별 근거','Evidence by file')}</summary>${sources}</details>`:`${flow}${sources}`;
  }
  function overviewHtml() {
    return savedOverviews().map((group,index)=>{
      const key=overviewKey(group);
      const open=openedOverview===key || (openedOverview===null && group.format==='overview-v1');
      const coverage=group.scope_coverage;
      const scopeChip=coverage?.total ? `<span class="chip warn">${text('경로','Paths')} ${coverage.selected.length}/${coverage.total} · ${text('표본','sample')}</span>` : '';
      const resources=open?remainingScopes(group):[];
      const local=resources.length?`<div class="ctl"><label>${text('개요에 포함되지 않은 경로','Paths outside this overview')} <select id="overviewLocalScope${index}">${resources.map(resource=>`<option>${esc(resource)}</option>`).join('')}</select></label><button class="btn quiet" id="overviewOpenScope${index}">${text('지도에서 열기','Open in map')}</button></div>`:'';
      return `<section class="sect overview-head"><button class="btn plain" type="button" id="savedOverview${index}" aria-expanded="${open}">${group.resource?text('경로 설명','Path explanation'):text('첫 개요','Initial overview')} · ${esc(group.repository ? connectionDisplayName(group.repository) : S.project)}</button>
        <span class="chips"><code>${esc(group.commit.slice(0,8))}</code><span class="chip">${text('표본 파일','Sampled files')} ${group.files.length}</span><span class="chip">${text('항목','Items')} ${group.items.length}</span>${scopeChip}</span>
        ${open ? `<div>${overviewTree(group)}${local}</div>` : ''}</section>`;
    }).join('');
  }
  function savedBatchGroups() {
    const {area}=intent(),repository=scope().repository;
    return (run?.saved_scope_overviews || []).filter(group=>(!repository || group.repository===repository)
      && (!area || group.repository===area.repository && area.resources.includes(group.resource)));
  }
  function localResourceCount() {
    const map=S.maps?.[S.branch],repo=scope().repository;
    const indexes=map?.structure_indexes || (map?.structure_index?[map.structure_index]:[]);
    return indexes.filter(index=>!repo || index.repository===repo).reduce((n,index)=>n+resourcesIn(index).length,0);
  }

  // ---- Full code analysis: units are saved as they finish and read as a map and cards, not as a wall of text ----
  const KINDS={route:['경로','Paths'],screen:['화면','Screens'],program:['프로그램','Programs'],package:['패키지','Packages'],cli:['CLI','CLI'],folder:['폴더','Folders'],map:['지도','Map'],system:['서비스 구성','Service structure'],groups:['화면 묶음','Screen groups']};
  const MAP_KINDS=['map','system','groups'];
  const UNIT_STATES={saved:['저장됨','Saved'],named:['이름·설명 있음','Named and described'],working:['분석 중','Analyzing'],local:['로컬 확인','Checked locally'],pending:['설명 없음','No explanation'],failed:['검증 실패','Failed'],stale:['오래됨','Outdated']};
  // A unit's saved state is its detailed explanation; the map rows (groups, service structure) are simply saved.
  const stateText=row=>row.state==='saved' && !MAP_KINDS.includes(row.kind)?text('자세한 설명 있음','Detailed explanation'):text(...UNIT_STATES[row.state]);
  const STATE_ORDER=['working','saved','named','local','failed','stale','pending'];
  const LOCAL_KINDS={doc:['문서','Documents'],data:['데이터','Data'],support:['테스트·외부 코드','Tests and vendored code']};
  let unitEdges=new Map(),linkStore={scope:'',repos:{}};
  const REASONS={secret:['비밀 파일','Credential files'],binary:['이미지·바이너리','Binary files'],large:['300KB 초과','Over 300KB'],generated:['생성·잠금 파일','Generated or lock files']};
  const SAMPLE_FILES=4;
  let board=null,boardQuick=null,boardScope='',boardError=null,unitFilter='all',unitLimit=24,openedUnit=null,loadingBoard=false,unitRows=[];
  const unitDetails=new Map();
  const beta=()=>`<span class="beta">${text('베타','Beta')}</span>`;
  const boardScopeKey=()=>JSON.stringify([scope(),S.loadToken]);
  const fullRun=()=>!!run && run.intent?.task==='full' && Object.entries(scope()).every(([name,value])=>run[name]===value);
  const liveBoard=()=>fullRun() && run.unit_board && (active() || !run.unit_board.only) ? run.unit_board : boardScope===boardScopeKey() ? board : null;
  const unitKey=row=>JSON.stringify([row.repo,row.id]);
  async function loadBoard(token) {
    const requested=boardScopeKey();
    if(!S.project || loadingBoard)return;
    loadingBoard=true;boardQuick=null;
    // The pinned commit and file counts arrive at once; the units follow as soon as they are calculated.
    if(!liveBoard())paint();
    void invoke('analysis_run_status',{scope:scope(),view:'units_quick'}).then(decode).then(value=>{
      if(current(token) && loadingBoard && Array.isArray(value?.repositories)){boardQuick=value;if(!liveBoard())paint();}
    }).catch(()=>{});
    // The local signal scan (which sets the map's exact call count) runs beside the unit list and never blocks it.
    const scanned=invoke('analysis_run_status',{scope:scope(),view:'signals'}).then(decode).then(value=>value?.ready===true).catch(()=>false);
    try {
      let value=decode(await invoke('analysis_run_status',{scope:scope(),view:'units'}));
      if(!current(token))return;
      boardScope=requested;board=Array.isArray(value?.repositories)?value:null;boardError=null;unitDetails.clear();
      if(board?.signals==='pending'){
        paint();
        const ready=await scanned;
        if(!current(token))return;
        if(ready){value=decode(await invoke('analysis_run_status',{scope:scope(),view:'units'}));if(!current(token))return;if(Array.isArray(value?.repositories))board=value;}
      }
    } catch(value) { if(current(token)){boardScope=requested;board=null;boardError=value;} }
    finally { loadingBoard=false;boardQuick=null; }
    if(current(token))paint();
  }
  function unitSummary(b) {
    const cover=b.repositories.reduce((sum,repo)=>{
      const c=repo.coverage || {};sum.tracked+=c.tracked || 0;sum.inside+=c.in_units || 0;sum.plain+=c.plain || 0;sum.local+=c.local || 0;sum.truncated=sum.truncated || !!c.truncated;
      for(const [reason,count] of Object.entries(c.excluded || {}))sum.excluded[reason]=(sum.excluded[reason] || 0)+count;
      return sum;
    },{tracked:0,inside:0,plain:0,local:0,truncated:false,excluded:{}});
    const out=Object.values(cover.excluded).reduce((a,n)=>a+n,0);
    const reports=b.repositories.map(r=>r.map_coverage).filter(Boolean);
    const readLocal=reports.length?reports.reduce((n,r)=>n+(r.files || 0),0):cover.tracked-out;
    const ai=Math.max(0,cover.inside-cover.local);
    const reasons=Object.entries(cover.excluded).map(([reason,count])=>`<li><span>${text(...(REASONS[reason] || [reason,reason]))}</span><b>${count}</b></li>`).join('');
    return `<div class="unit-scope" data-unit-scope><p class="chips"><span class="chip">${text('파일','Files')} ${cover.inside}/${cover.tracked}</span> <span class="chip">${text('추적 파일','Tracked')} ${cover.tracked}</span> <span class="chip">${text('로컬에서 확인','Read locally')} ${readLocal}</span> <span class="chip">${text('AI 범위','AI range')} ${ai}</span> <span class="chip">${text('로컬만','Local only')} ${cover.local}</span>${out?` <span class="chip warn">${text('제외','Excluded')} ${out}</span>`:''}${cover.plain?` <span class="chip">${text('색인 밖 일반 파일 '+cover.plain+'개 포함',cover.plain+' plain files outside the index included')}</span>`:''}${cover.truncated?` <span class="chip warn">${text('색인 한도 도달','Index limit reached')}</span>`:''} <span class="chip">${text('단위당 표본 ≤'+SAMPLE_FILES+'파일','≤'+SAMPLE_FILES+' sampled files per unit')}</span></p>${reasons?`<ul class="unit-excluded">${reasons}</ul>`:''}</div>`;
  }
  function localDetail(group) {
    const kinds=Object.entries(group.kinds || {}).map(([k,n])=>`<span class="chip">${text(...(LOCAL_KINDS[k] || [k,k]))} ${n}</span>`).join('');
    const files=(group.files || []).map(f=>`<li><code>${esc(f)}</code></li>`).join('');
    const more=group.file_count>(group.files || []).length?`<p class="s">+${group.file_count-group.files.length}</p>`:'';
    return `<p class="chips">${kinds}<span class="chip">${text('파일','Files')} ${group.file_count}</span></p><p class="s">${text('로컬에서 읽고 세었습니다. AI는 읽지 않았습니다. 포함하려면 위에서 「모든 텍스트 파일」을 고르세요.','Read and counted locally. The AI did not read it. To include it, choose "every text file" above.')}</p><details><summary>${text('파일 목록','Files')}</summary><ul class="unit-files">${files}</ul>${more}</details>`;
  }
  function linkChips(index) {
    const e=unitEdges.get(index);if(!e || !(e.out.length+e.in.length))return '';
    const chips=list=>list.map(i=>`<button class="chip" type="button" data-unit-link="${i}">${esc(unitRows[i].name)}</button>`).join('');
    return `<div class="unit-links">${e.out.length?`<p class="chips"><span class="s">${text('사용 →','Uses →')}</span>${chips(e.out)}</p>`:''}${e.in.length?`<p class="chips"><span class="s">${text('← 사용됨','← Used by')}</span>${chips(e.in)}</p>`:''}</div>`;
  }
  function unitDetail(row) {
    if(row.state==='working')return '';
    if(['pending','named'].includes(row.state))return `<p class="chips"><span class="chip">${text('파일','Files')} ${row.count}</span></p>`;
    if(row.state==='failed')return `<p class="s">${text('AI 설명이 근거와 맞지 않아 저장하지 않았습니다.','The AI answer did not match its evidence and was not saved.')}</p>`;
    const group=unitDetails.get(unitKey(row));
    if(group===undefined)return `<p class="s">${text('불러오는 중…','Loading…')}</p>`;
    if(group?.local)return localDetail(group);
    if(!group || !group.files)return `<p class="s">${text('저장된 설명을 읽지 못했습니다.','Saved explanation unavailable.')}</p>`;
    return `${group.stale?`<p class="s">${text('이전 코드 기준','Based on older code')}</p>`:''}<code>${esc(group.commit.slice(0,8))}</code>${overviewTree(group)}`;
  }
  const canExplain=()=>usable() && !providerBusy && !busy && !active();
  function explainButton(row,index) {
    if(MAP_KINDS.includes(row.kind) || !['pending','named','failed','local','stale'].includes(row.state))return '';
    const label=['stale','failed'].includes(row.state)?text('다시 설명 · 호출 1회','Explain again · 1 call'):text('AI 설명 · 호출 1회','AI explanation · 1 call');
    return `<p class="unit-ask"><button class="btn" type="button" data-unit-explain="${index}" ${canExplain()?'':'disabled'}>${label}</button><span class="chip">${text('코드가 Claude로 전송','Code sent to Claude')}</span>${beta()}</p>`;
  }
  function unitCard(row,index,multi) {
    const mapRow=MAP_KINDS.includes(row.kind),navigates=mapRow && row.state==='saved';
    const open=openedUnit===unitKey(row),expandable=row.state!=='working' && !mapRow;
    const state=stateText(row);
    const title=mapRow?text(...KINDS[row.kind]):esc(row.name);
    const body=open && expandable?(row.what?`<p class="s">${esc(row.what)} <span class="chip">${text('AI 해석','AI interpretation')}</span></p>`:'')+linkChips(index)+unitDetail(row)+explainButton(row,index):'';
    return `<li class="unit-card" data-state="${row.state}" data-unit-card="${index}"><button class="unit-head" type="button" data-unit-open="${index}" aria-expanded="${expandable?open:false}" ${expandable||navigates?'':'aria-disabled="true"'}><i class="unit-dot" aria-hidden="true"></i><strong>${title}</strong><span class="chips">${mapRow?'':`<span class="chip">${text(...(KINDS[row.kind] || [row.kind,row.kind]))}</span>`}${multi?`<span class="chip">${esc(connectionDisplayName(row.repo))}</span>`:''}${row.detail==='reused'?`<span class="chip">${text('코드 변경 없음','Code unchanged')}</span>`:''}</span><span class="unit-state">${state}</span></button>${body}</li>`;
  }
  function boardHtml() {
    const b=liveBoard(),live=fullRun() && active();
    if(!b) {
      if(!boardError && loadingBoard){
        const quick=boardQuick?.repositories || [],files=quick.reduce((n,r)=>n+r.tracked,0),skipped=quick.reduce((n,r)=>n+Object.values(r.excluded || {}).reduce((a,c)=>a+c,0),0);
        const known=quick.length?` ${text('추적 파일 '+files+'개 · 제외 '+skipped+'개 · 코드 '+quick[0].commit.slice(0,8),'Tracked files '+files+' · excluded '+skipped+' · code '+quick[0].commit.slice(0,8))}`:'';
        return `<section class="sect unit-board" data-unit-board="loading" aria-busy="true"><h3>${text('전체 코드 분석','Full code analysis')} ${beta()}</h3><p class="s" role="status">${text('단위를 계산하는 중입니다. AI는 부르지 않습니다.','Calculating units. No AI is called.')}${esc(known)}</p></section>`;
      }
      if(!boardError)return '';
      const refresh=/\bRefresh\b/.test(String(boardError?.message || boardError));
      return `<section class="sect unit-board" data-unit-board="error"><h3>${text('전체 코드 분석','Full code analysis')} ${beta()}</h3><p class="s">${refresh?text('이 코드를 한 번 새로고침하면 단위가 계산됩니다. 새로고침은 AI를 부르지 않습니다.','Units are calculated after one refresh of this code. Refreshing does not call AI.'):text('단위를 읽지 못했습니다.','Could not read the units.')}</p>${refresh?`<button class="btn primary" type="button" id="refreshForUnits">${text('새로고침하고 단위 계산','Refresh and calculate units')}</button>`:''}</section>`;
    }
    const t={...b.totals},total=t.units || 0;
    if(!total)return '';
    const multi=b.repositories.length>1,starts={};
    if(!live){linkStore={scope:boardScopeKey(),repos:{}};for(const repo of b.repositories)if(repo.links)linkStore.repos[repo.repository]=repo.links;}
    else if(linkStore.scope!==boardScopeKey())linkStore={scope:'',repos:{}};
    let at=0;
    unitRows=b.repositories.flatMap(repo=>{starts[repo.repository]=at;at+=repo.units.length;return repo.units.map((row,ri)=>({repo:repo.repository,ri,id:row[0],kind:row[1],name:row[2],count:row[3],state:row[4],detail:row[5],what:row[6] || ''}));});
    unitEdges=new Map();
    for(const [repo,links] of Object.entries(linkStore.repos))for(const [from,to] of links){
      const a=starts[repo]+from,c=starts[repo]+to;if(!unitRows[a] || !unitRows[c])continue;
      for(const [x,y,k] of [[a,c,'out'],[c,a,'in']]){if(!unitEdges.has(x))unitEdges.set(x,{out:[],in:[]});unitEdges.get(x)[k].push(y);}
    }
    const openIndex=unitRows.findIndex(row=>unitKey(row)===openedUnit),linkedSet=new Set(openIndex>=0?[...(unitEdges.get(openIndex)?.out || []),...(unitEdges.get(openIndex)?.in || [])]:[]);
    const aiTotal=total-(t.local || 0);
    const explained=unitRows.filter(r=>!MAP_KINDS.includes(r.kind) && r.state==='saved').length;
    const present=STATE_ORDER.filter(k=>t[k]);
    const bar=`<div class="unit-bar" role="img" aria-label="${t.saved || 0}/${aiTotal}">${present.map(k=>`<i data-state="${k}" style="width:${(t[k]*100/total).toFixed(2)}%"></i>`).join('')}</div>`;
    const filters=`<div class="unit-legend" role="group" aria-label="${text('상태 필터','State filter')}"><button type="button" data-unit-filter="all" aria-pressed="${unitFilter==='all'}">${text('전체','All')} ${total}</button>${present.map(k=>`<button type="button" data-unit-filter="${k}" data-state="${k}" aria-pressed="${unitFilter===k}"><i aria-hidden="true"></i>${text(...UNIT_STATES[k])} ${t[k]}</button>`).join('')}</div>${t.retired?`<p class="s unit-retired">${text('현재 구조에 없는 이전 단위 '+t.retired+'개의 설명은 기록에만 남아 있고 위 개수에 넣지 않습니다.',t.retired+' explanations of earlier units that the current structure no longer has stay in history only and are not counted above.')}</p>`:''}`;
    const lanes=Object.keys(KINDS).filter(k=>unitRows.some(r=>r.kind===k)).map(kind=>{
      const set=unitRows.map((row,i)=>[row,i]).filter(([row])=>row.kind===kind);
      return `<div class="unit-lane"><span class="unit-kind">${text(...KINDS[kind])}<b>${set.filter(([row])=>row.state==='saved').length}/${set.filter(([row])=>row.state!=='local').length}</b></span><span class="unit-cells">${set.map(([row,i])=>`<button class="unit-cell" type="button" data-unit-cell="${i}" data-state="${row.state}" ${linkedSet.has(i)?'data-linked="1"':''} title="${esc(row.name)} · ${stateText(row)}" aria-label="${esc(row.name)} · ${stateText(row)}"></button>`).join('')}</span></div>`;
    }).join('');
    const rank=row=>STATE_ORDER.indexOf(row.state);
    const listed=unitRows.map((row,i)=>[row,i]).filter(([row])=>unitFilter==='all' || row.state===unitFilter).sort((a,b)=>rank(a[0])-rank(b[0]) || a[1]-b[1]);
    const shown=listed.slice(0,unitLimit),opened=unitRows.findIndex(row=>unitKey(row)===openedUnit);
    if(opened>=0 && !shown.some(([,i])=>i===opened))shown.unshift([unitRows[opened],opened]);
    const hidden=listed.length-shown.length;
    const scanning=!live && b.signals==='pending';
    const usableNow=usable(),canStart=usableNow && !providerBusy && !busy && !active() && !scanning;
    const finished=fullRun() && ['failed','cancelled'].includes(run.state);
    const calls=b.calls?.total ?? 0,used=Object.values(b.used || {}).reduce((n,c)=>n+c,0);
    const rulesNote=b.repositories.some(r=>r.missing_rules?.length)?`<p class="s">${text('내장 읽기 규칙이 없는 언어는 먼저 읽기 규칙을 받아 연결을 읽는다.','Languages without built-in readers first get reading rules, then their connections are read.')}</p>`:'';
    const gaps=b.repositories.flatMap(r=>r.gaps || []);
    const gapNote=gaps.length?`<p class="s" role="status">${text('AI 해석이 없는 부분 '+gaps.length+'곳. 지도는 그대로 남는다.',gaps.length+' parts have no AI interpretation. The map stays.')}</p>`:'';
    const scopeHtml=`<details class="unit-calls" data-read-scope><summary>${text('읽기 범위','Reading range')}</summary><p class="s">${text('지도는 로컬에서 계산한다. 이름·묶음·서비스 구성은 AI가 지도 요약만 보고 해석한 것이다. 단위 설명은 그 단위의 코드 줄을 읽고 만든다.','The map is calculated locally. Names, groups and the service structure are AI interpretations of a map summary only. A unit explanation is made from that unit\'s code lines.')}</p>${rulesNote}${unitSummary(b)}</details>`;
    const progress=`<span class="unit-count"><span class="chip">${text('이름·설명','Named')} ${t.named || 0}</span><span class="chip">${text('자세한 설명','Detailed')} ${explained}</span>${t.local?`<span class="chip" data-state="local">${text('로컬 확인','Checked locally')} ${t.local}</span>`:''}</span>`;
    const start=live?`<div class="unit-run" role="status" aria-live="polite"><span class="chip">${text('AI 호출','AI calls')} ${used}/${b.announced?.total ?? calls}</span><button class="btn" id="cancelFullAnalysis" ${busy || run.cancel_requested?'disabled':''}>${text('취소','Cancel')}</button></div>`
      : scanning ? `<div class="unit-start"><span class="chips"><span class="chip" role="status">${text('파일 확인 중','Checking files')}</span></span><button class="btn primary" id="startFullAnalysis" disabled>${text('분석하기','Analyze')}</button></div>`
      : calls>0 ? `<div class="unit-start"><span class="chips"><span class="chip">${text('지도 요약이 Claude로 전송','Map summary sent to Claude')}</span></span><button class="btn primary" id="startFullAnalysis" ${canStart?'':'disabled'}>${text('분석하기 · 호출 '+calls+'회','Analyze · '+calls+' calls')}</button>${usableNow?'':`<button class="btn quiet" id="checkFullAccount">${text('계정 확인','Check account')}</button>`}</div>`
      : `<p class="chips"><span class="chip ok">${text('분석할 것 없음','Nothing left to analyze')}</span></p>`;
    const alert=finished?`<p role="alert">${esc(message(run.error || {code:'CANCELLED'}))}</p>`:fullRun() && run.state==='completed' && run.map_gaps?`<p class="s" role="status">${esc(stateLabel())}</p>`:'';
    return `<section class="sect unit-board" data-unit-board><h3>${text('전체 코드 분석','Full code analysis')} ${beta()}${progress}</h3>${start}${scopeHtml}${alert}${gapNote}${bar}${filters}<div class="unit-map" role="group" aria-label="${text('단위 구조도','Unit map')}">${lanes}</div><ul class="unit-cards">${shown.map(([row,i])=>unitCard(row,i,multi)).join('')}</ul>${hidden>0?`<button class="btn quiet" type="button" id="unitMore">${text('더 보기','Show more')} (${hidden})</button>`:''}</section>`;
  }
  async function readUnit(row) {
    const base={...scope(),repository:row.repo};
    return decode(await invoke('analysis_run_status',{view:'unit',scope:base,resource:row.id}));
  }
  async function openUnit(row) {
    const key=unitKey(row);
    if(MAP_KINDS.includes(row.kind) && row.state==='saved'){S.agentPrompt=null;S.view=row.kind==='groups'?'feat':'sys';render();return;}
    if(row.state==='working' || MAP_KINDS.includes(row.kind)){openedUnit=key;paint();return;}
    openedUnit=openedUnit===key?null:key;paint();
    if(openedUnit!==key || unitDetails.has(key) || ['pending','named','failed'].includes(row.state))return;
    const token=epoch;
    let group=null;try{group=await readUnit(row);}catch{}
    if(token!==epoch)return;
    unitDetails.set(key,group);paint();
  }
  function bindBoard() {
    const root=$('insp');
    root?.querySelectorAll?.('[data-unit-cell]').forEach(button=>button.onclick=()=>{
      const row=unitRows[Number(button.dataset.unitCell)];if(!row)return;
      unitFilter='all';openedUnit=null;void openUnit(row);
      $('insp')?.querySelector?.(`[data-unit-card="${button.dataset.unitCell}"]`)?.scrollIntoView?.({block:'nearest'});
    });
    root?.querySelectorAll?.('[data-unit-open]').forEach(button=>button.onclick=()=>{const row=unitRows[Number(button.dataset.unitOpen)];if(row)void openUnit(row);});
    root?.querySelectorAll?.('[data-unit-filter]').forEach(button=>button.onclick=()=>{unitFilter=button.dataset.unitFilter;unitLimit=24;paint();});
    if($('unitMore'))$('unitMore').onclick=()=>{unitLimit+=48;paint();};
    if($('startFullAnalysis'))$('startFullAnalysis').onclick=()=>{
      const b=liveBoard();if(!b || active())return;
      S.analysisChoice={...S.analysisChoice,task:'full_analysis',only:undefined};
      return execute('analysis_run_start');
    };
    root?.querySelectorAll?.('[data-unit-explain]').forEach(button=>button.onclick=()=>{
      const b=liveBoard(),row=unitRows[Number(button.dataset.unitExplain)];if(!b || !row || !canExplain())return;
      S.analysisChoice={...S.analysisChoice,task:'full_analysis',only:[{repository:row.repo,target:row.id}]};
      unitDetails.delete(unitKey(row));
      return execute('analysis_run_start');
    });
    root?.querySelectorAll?.('[data-unit-link]').forEach(button=>button.onclick=()=>{const row=unitRows[Number(button.dataset.unitLink)];if(row){unitFilter='all';void openUnit(row);}});
    if($('refreshForUnits'))$('refreshForUnits').onclick=()=>$('refresh')?.click();
    if($('cancelFullAnalysis'))$('cancelFullAnalysis').onclick=()=>execute('analysis_run_cancel');
    if($('checkFullAccount'))$('checkFullAccount').onclick=()=>{void providers();};
  }
  function html(includeOverview=true) {
    if(S.analysisChoice?.task==='scope_overview' && savedOverviews().length && !active())return overviewHtml();
    const account = provider?.account, identity = typeof account === 'string' ? account : account?.email || account?.id;
    const done = Array.isArray(run?.completed_tasks) ? run.completed_tasks.length : Number(run?.completed_tasks || 0);
    const batchRun=run?.intent?.task==='resources';
    const completed=new Set((batchRun && Array.isArray(run.completed_tasks)?run.completed_tasks:[]).map(t=>JSON.stringify([t.repository,t.target])));
    const left=Number.isInteger(run?.tasks)?run.tasks:batchRun?(run.tasks || []).filter(t=>!completed.has(JSON.stringify([t.repository,t.target]))).length:run?.tasks?.length || 0;
    const total=done+left;
    const progress=batchRun?text('경로 묶음 '+done+'개 저장 · '+left+'개 남음','Path groups saved: '+done+' · Remaining: '+left):done+'/'+total+' '+text('작업 저장됨','tasks saved');
    const task = run?.current_task;
    const batches=run?.batch_progress,stats=run?.input_stats;
    let inputProgress='';
    if (batches && active()) {
      inputProgress=text('현재 작업 입력 조각','Current task input units')+': '+batches.completed+'/'+batches.total;
    }
    const names={resources:text('경로 묶음 설명','Path group explanations'),overview:text('첫 개요','Initial overview'),full:text('분석하기','Analyze'),steps:text('동작 과정','Action steps'),jobs:text('프로그램이 하는 일','Program jobs'),briefing:text('변경 설명','Change explanation')};
    const taskName = typeof task === 'string' ? task : batchRun && task?.target ? [task.repository,task.target].filter(Boolean).join(' · ') : task ? [task.repository, text(task.task==='overview'?'첫 개요':PLAN_NAMES[task.task] || task.task, ({overview:'Initial overview',analysis:'Detailed map',system:'Architecture',groups:'Screen groups',jobs:'Program jobs',steps:'Action steps',briefing:'Change explanation'})[task.task] || task.task)].filter(Boolean).join(' · ') : '';
    const retryWarning=sameScope() && run.state==='failed' && errorCode(run.error)==='interrupted' && run.input_stats?.calls>0;
    const issue=error || (!retryWarning && run?.error);
    const resources=localResourceCount();
    const batch=intent().task==='resources';
    const canStart = (!batch || intent().max_calls>0) && usable() && !providerBusy && !busy && !active();
    const runScope = run ? [run.repository ? connectionDisplayName(run.repository) : text('연결한 코드 전체','All connected repositories'),run.branch,run.lang].join(' · ') : '';
    const runAccount = run?.account?.email || run?.account?.id;
    const choice=intent();
    const cached=run?.resource_estimate?.cached || 0;
    const targets=choice.targets.map(t=>[t.repository,t.target].filter(Boolean).map(esc).join(' · '));
    const scoped=S.analysisChoice?.task==='scope_overview';
    const fullReady=choice.task==='full' || choice.task==='overview' && !scoped && !!liveBoard()?.repositories;  // the board owns the one main action; this panel keeps only account problems, errors and redelivery warnings
    const startLabel=batch?text('경로 묶음 설명 생성','Generate path group explanations'):scoped?text('이 경로 설명 생성','Generate path explanation'):choice.task==='overview' ? text('첫 개요 만들기','Create initial overview')
      : text(names[choice.task]+' 분석 시작','Analyze '+names[choice.task]);
    if(fullReady){
      const parts=[providerBusy?`<p role="status">${text('계정 확인 중…','Checking the account…')}</p>`:provider && !usable()?`<p role="alert">${esc(message(provider))}</p><button class="btn quiet" id="checkAppAnalysis">${text('계정 확인','Check account')}</button>`:'',
        retryWarning?`<p role="alert" id="retryDeliveryWarning">${text('분석이 중단됐습니다. 마지막 요청이 Claude에 전달됐을 수 있어, 다시 시도하면 재전송될 수 있습니다.','Analysis was interrupted. Claude may already have received the last request; retrying may send it again.')}</p>`:'',
        issue?`<p role="alert">${esc(message(issue))}</p>`:'',
        retryWarning && sameScope() && ['failed','cancelled'].includes(run?.state)?`<button class="btn" id="retryAppAnalysis" aria-describedby="retryDeliveryWarning" ${canStart?'':'disabled'}>${text('현재 코드로 다시 시도','Retry with current code')}</button>`:''].join('');
      return parts?`<section class="sect" aria-label="${text('자동 분석 (베타)','Automatic analysis (beta)')}">${parts}</section>`:'';
    }
    return `<section class="sect" aria-label="${text('자동 분석 (베타)','Automatic analysis (beta)')}">
      ${includeOverview?overviewHtml():''}
      <p class="auto-line"><strong title="${esc(identity || '')}">Claude Code</strong>${account?.subscription_type ? ' · '+esc(account.subscription_type) : identity ? '' : ' · '+text('계정 미확인','Account not verified')}</p>
      <p class="chips"><span class="chip">${esc(scope().repository ? connectionDisplayName(scope().repository) : text('연결한 코드 전체','All connected repositories'))}</span><span class="chip">${esc(S.branch)}</span>${targets.map(target=>`<span class="chip">${target}</span>`).join('')}<span class="chip">${text('코드가 Claude로 전송 · 구독 한도 적용','Code sent to Claude · subscription limit')}</span></p>
      ${providerBusy ? `<p role="status">${text('Claude Code 계정 확인 중…','Checking the Claude Code account…')}</p>` : provider && !usable() ? `<p role="alert">${esc(message(provider))}</p>` : ''}
      ${run ? `${!sameScope() || (runAccount && runAccount!==identity) ? `<p class="chips"><span class="chip">${text('마지막 실행','Last run')}: ${esc(names[run.intent?.task || 'all'])}</span><span class="chip">${esc(runScope)}</span>${(run.intent?.targets || []).map(t=>`<span class="chip">${esc(t.repository)} · ${esc(t.target)}</span>`).join('')}${runAccount && runAccount!==identity ? `<span class="chip warn">${esc(runAccount)}</span>` : ''}${!sameScope() ? `<span class="chip warn">${text('현재 선택과 다름','Differs from selection')}</span>` : ''}</p>` : ''}<div role="status" aria-live="polite"><strong>${esc(stateLabel())}</strong> · ${esc(progress)}${batchRun && cached?' · '+text('재사용 '+cached+'개',cached+' reused'):''}${taskName ? '<div>'+esc(taskName)+'</div>' : ''}</div><progress max="${Math.max(total, 1)}" value="${done}" aria-label="${text('분석 진행률','Analysis progress')}"></progress>${run.blocked?.length ? `<p class="s">${text('먼저 확인할 분석','Analysis requiring attention')}: ${run.blocked.length}</p>` : ''}` : ''}
      ${stats ? `<details><summary>${text('AI 사용량','AI usage')}</summary><p class="s">${text('입력 호출','Input calls')}: ${stats.calls} · ${text('전송한 입력 바이트','Encoded input bytes')}: ${stats.bytes}${inputProgress ? ' · '+esc(inputProgress) : ''}</p></details>` : ''}
      ${retryWarning?`<p role="alert" id="retryDeliveryWarning">${text('분석이 중단됐습니다. 마지막 요청이 Claude에 전달됐을 수 있습니다. 다시 시도하면 같은 요청이 재전송될 수 있습니다.','Analysis was interrupted. Claude may already have received the last request. Retrying may send it again.')}</p>`:''}
      ${issue ? `<p role="alert">${esc(message(issue))}</p>` : ''}
      ${!active() && !fullReady && choice.task==='overview' ? `<p class="s" id="overviewLimits">${scoped?text('선택한 경로 · 최대 4파일 · AI 1회','Selected path: up to 4 files · 1 AI call'):text('연결한 코드마다 최대 4파일 · AI 1회','Per repository: up to 4 files · 1 AI call')}</p>` : ''}
      ${batch && !active()?`<p class="s" id="resourceLimits">${text('경로 묶음 '+choice.max_calls+'개 · AI 최대 '+choice.max_calls+'회','Path groups: '+choice.max_calls+' · Up to '+choice.max_calls+' AI calls')}</p>`:''}
      <div class="ctl">${active() ? `<button class="btn" id="cancelAppAnalysis" ${busy || run.cancel_requested ? 'disabled' : ''}>${text('분석 취소','Cancel analysis')}</button>` : sameScope() && ['failed','cancelled'].includes(run?.state) ? `<button class="btn primary" id="retryAppAnalysis" ${retryWarning?'aria-describedby="retryDeliveryWarning"':''} ${canStart ? '' : 'disabled'}>${text('현재 코드로 다시 시도','Retry with current code')}</button>` : `${fullReady?'':`<button class="btn primary" id="startAppAnalysis" ${batch?'aria-describedby="resourceLimits"':choice.task==='overview' ? 'aria-describedby="overviewLimits"' : ''} ${canStart ? '' : 'disabled'}>${esc(startLabel)}</button>`}`}
      ${!batchRun && sameScope() && done > 0 && !['overview','full'].includes(run.intent?.task) ? `<button class="btn quiet" id="viewAppAnalysis">${text('저장된 결과 보기','View saved results')}</button>` : ''}
      ${usable()?'':`<button class="btn quiet" id="checkAppAnalysis" ${busy || providerBusy ? 'disabled' : ''}>${text('계정 확인','Check account')}</button>`}</div>
      </section>`;
  }
  function bind() {
    bindBoard();
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
    if ($('startAppAnalysis')) $('startAppAnalysis').onclick = () => execute('analysis_run_start');
    if ($('retryAppAnalysis')) $('retryAppAnalysis').onclick = () => execute('analysis_run_retry');
    if ($('cancelAppAnalysis')) $('cancelAppAnalysis').onclick = () => execute('analysis_run_cancel');
    if ($('checkAppAnalysis')) $('checkAppAnalysis').onclick = () => { void providers(); void check(); };
    if ($('viewAppAnalysis')) $('viewAppAnalysis').onclick = async () => {
      const token = epoch;
      try { await reloadAnalysisOnly(() => current(token)); if (current(token)) { S.agentPrompt = null; const task=run.intent?.task;
        if(task==='steps')Object.assign(S,S.analysisChoice?.resultContext || {});
        else S.view=task==='briefing'?'changes':'sys';
        render(); } }
      catch { if (current(token)) { error = {code:'result_read_failed'}; paint(); } }
    };
  }
  function open() { syncScope(); if (!provider && !providerBusy) void providers(); else void check(); }
  window.addEventListener('focus', () => { syncScope(); void check(); });
  document.addEventListener('visibilitychange', () => { clearTimeout(timer); if (!document.hidden) { syncScope(); void check(); } });
  return {syncScope, open, html, overviewHtml, boardHtml, savedScopeHtml, bind, bindMapResults, stateLabel, check, checkAccount:()=>{void providers();void check();}};
})();
AnalysisRun.syncScope();
