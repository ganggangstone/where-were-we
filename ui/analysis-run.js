/* App-owned analysis. Status/provider reads never start a model turn. */
const AnalysisRun = (() => {
  const activeStates = new Set(['preparing', 'running', 'saving']);
  let scopeKey = '', epoch = 0, revision = 0, timer = null, checking = null;
  let run = null, provider = null, providerBusy = false, busy = false, error = null;
  const loaded = new Set();
  const text = (ko, en) => S.lang === 'en' ? en : ko;
  const scope = () => ({project:S.project, repository:S.repository || '', branch:S.branch, lang:S.lang});
  const key = () => JSON.stringify([scope(), S.loadToken]);
  const decode = value => typeof value === 'string' ? JSON.parse(value) : value;
  const shown = () => S.agentPurpose === 'analysis' && S.agentPrompt != null;
  const current = token => token === epoch && scopeKey === key();
  const active = () => !!run && activeStates.has(run.state);
  const sameScope = () => !!run && Object.entries(scope()).every(([name,value]) => run[name] === value);
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
      source_too_large:['분석할 코드가 너무 큽니다. 코드 하나를 선택하거나 범위를 줄인 뒤 다시 시도하세요.','The source is too large. Select one repository or narrow its scope and retry.'],
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
    if (sameScope() && !active() && (run.state === 'completed' || run.completed_tasks?.length) && !loaded.has(run.id)) {
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
    const token = epoch, args = command === 'analysis_run_start' ? {scope:scope(), expectedAccount:provider.account} : {runId:run.id};
    if (command === 'analysis_run_retry') args.expectedAccount = provider.account;
    revision++; busy = true; error = null; clearTimeout(timer); paint();
    try { await accept(decode(await invoke(command, args)), token); }
    catch (value) { if (current(token)) { error = value; paint(); } }
    finally { if (current(token)) { busy = false; paint(); schedule(token); } }
  }
  function html() {
    const account = provider?.account, identity = typeof account === 'string' ? account : account?.email || account?.id;
    const done = Array.isArray(run?.completed_tasks) ? run.completed_tasks.length : Number(run?.completed_tasks || 0);
    const total = done + (run?.tasks?.length || 0);
    const task = run?.current_task;
    const taskName = typeof task === 'string' ? task : task ? [task.repository, text(PLAN_NAMES[task.task] || task.task, ({analysis:'Detailed map',system:'Architecture',groups:'Screen groups',jobs:'Program jobs',steps:'Action steps',briefing:'Change explanation'})[task.task] || task.task)].filter(Boolean).join(' · ') : '';
    const issue = error || run?.error;
    const canStart = usable() && !providerBusy && !busy && !active();
    const runScope = run ? [run.repository ? connectionDisplayName(run.repository) : text('연결한 코드 전체','All connected repositories'),run.branch,run.lang].join(' · ') : '';
    const runAccount = run?.account?.email || run?.account?.id;
    return `<section class="sect" aria-labelledby="appAnalysisHeading"><h3 id="appAnalysisHeading">${text('앱에서 분석','Analyze in the app')}</h3>
      <p class="s">${text('필요한 분석만 Claude Code로 실행하고 검증한 결과를 저장합니다.','Runs the missing analysis with Claude Code and saves validated results.')}</p>
      <p><strong>Claude Code</strong> · ${text('계정','Account')}: ${esc(identity || text('확인되지 않음','Not verified'))}${account?.subscription_type ? ' · '+esc(account.subscription_type) : ''}</p>
      <p class="s">${text('이 컴퓨터에 로그인된 Claude 구독 계정을 사용합니다. 선택한 코드가 Claude에 전송되며 구독 사용량·한도가 적용됩니다. 시작·다시 시도를 누를 때만 AI를 실행합니다.','Uses the Claude subscription signed in on this computer. Selected source is sent to Claude; subscription usage and limits apply. AI runs only when you click Start or Retry.')}</p>
      <p class="s">${text('분석할 코드','Code to analyze')}: ${esc(S.repository ? connectionDisplayName(S.repository) : text('연결한 코드 전체','All connected repositories'))} · ${esc(S.branch)}</p>
      ${providerBusy ? `<p role="status">${text('Claude Code 계정 확인 중…','Checking the Claude Code account…')}</p>` : provider && !usable() ? `<p role="alert">${esc(message(provider))}</p>` : ''}
      ${run ? `<p class="s">${text('이 분석의 코드','This run analyzes')}: ${esc(runScope)}${runAccount ? ' · '+esc(runAccount) : ''}</p>${!sameScope() ? `<p class="s">${text('이 서비스의 다른 코드·버전·언어에서 시작한 분석입니다. 완료하거나 취소한 뒤 선택한 코드를 분석할 수 있습니다.','This project has analysis started for another code selection, version, or language. Finish or cancel it before analyzing the selected code.')}</p>` : ''}<div role="status" aria-live="polite"><strong>${esc(stateLabel())}</strong> · ${done}/${total} ${text('작업 저장됨','tasks saved')}${taskName ? '<div>'+esc(taskName)+'</div>' : ''}</div><progress max="${Math.max(total, 1)}" value="${done}" aria-label="${text('분석 진행률','Analysis progress')}"></progress>${run.blocked?.length ? `<p class="s">${text('먼저 확인할 분석','Analysis requiring attention')}: ${run.blocked.length}</p>` : ''}` : ''}
      ${issue ? `<p role="alert">${esc(message(issue))}</p>` : ''}
      <div class="ctl">${active() ? `<button class="btn" id="cancelAppAnalysis" ${busy || run.cancel_requested ? 'disabled' : ''}>${text('분석 취소','Cancel analysis')}</button>` : sameScope() && ['failed','cancelled'].includes(run?.state) ? `<button class="btn primary" id="retryAppAnalysis" ${canStart ? '' : 'disabled'}>${text('현재 코드로 다시 시도','Retry with current code')}</button>` : `<button class="btn primary" id="startAppAnalysis" ${canStart ? '' : 'disabled'}>${text('Claude Code로 분석 시작','Start analysis with Claude Code')}</button>`}
      <button class="btn quiet" id="checkAppAnalysis" ${busy || providerBusy ? 'disabled' : ''}>${text('계정·상태 다시 확인','Check account and status')}</button>
      ${sameScope() && done > 0 ? `<button class="btn quiet" id="viewAppAnalysis">${text('저장된 결과 보기','View saved results')}</button>` : ''}</div></section>`;
  }
  function bind() {
    if ($('startAppAnalysis')) $('startAppAnalysis').onclick = () => execute('analysis_run_start');
    if ($('retryAppAnalysis')) $('retryAppAnalysis').onclick = () => execute('analysis_run_retry');
    if ($('cancelAppAnalysis')) $('cancelAppAnalysis').onclick = () => execute('analysis_run_cancel');
    if ($('checkAppAnalysis')) $('checkAppAnalysis').onclick = () => { void providers(); void check(); };
    if ($('viewAppAnalysis')) $('viewAppAnalysis').onclick = async () => {
      const token = epoch;
      try { await reloadAnalysisOnly(() => current(token)); if (current(token)) { S.agentPrompt = null; S.view = 'sys'; render(); } }
      catch { if (current(token)) { error = {code:'result_read_failed'}; paint(); } }
    };
  }
  function open() { syncScope(); if (!provider && !providerBusy) void providers(); else void check(); }
  window.addEventListener('focus', () => { syncScope(); void check(); });
  document.addEventListener('visibilitychange', () => { clearTimeout(timer); if (!document.hidden) { syncScope(); void check(); } });
  return {syncScope, open, html, bind, stateLabel, check};
})();
AnalysisRun.syncScope();
