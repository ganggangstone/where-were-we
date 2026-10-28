"""Explicit Claude subscription calls with no repository or tool access.

Only execute() starts a model turn. The caller supplies all pinned source in stdin
and validates evidence before saving. Organization-managed CLI policy still applies.
See https://code.claude.com/docs/en/cli-reference and /docs/en/headless.
"""
import json
import os
import re
import selectors
import shutil
import signal
import subprocess
import tempfile
import time
import sys


MAX_OUTPUT = 8_000_000
MAX_PROMPT = 16_000_000
REQUIRED_FLAGS = ('--safe-mode', '--tools', '--disallowedTools', '--strict-mcp-config',
                  '--mcp-config', '--setting-sources', '--settings',
                  '--no-session-persistence', '--output-format', '--disable-slash-commands',
                  '--no-chrome')


class CLIExecutionError(ValueError):
    def __init__(self, code, message):
        self.code = code
        self.message = message
        super().__init__(code + ': ' + message)


def _environment():
    # Keep the system keychain/HOME login, never silently route to an inherited
    # paid API account, proxy provider, debug export, or injected OAuth token.
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(('ANTHROPIC_', 'CLAUDE_', 'OTEL_'))
           and k not in ('API_TIMEOUT_MS', 'DEBUG', 'NODE_OPTIONS', 'NODE_PATH')}
    env.update(CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC='1',
               CLAUDE_CODE_DISABLE_BACKGROUND_TASKS='1', NO_COLOR='1')
    return env


def _stop(process, force=False):
    # start_new_session gives this invocation its own group. Never signal a
    # process found by name, a saved PID, or any pre-existing CLI session.
    if force or process.poll() is None:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            pass
        # Children can outlive the group leader, including one ignoring TERM.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()


def _run(executable, args, *, prompt='', timeout=10, cancelled=None, limit=MAX_OUTPUT):
    if cancelled and cancelled():
        raise CLIExecutionError('CANCELLED', 'Analysis was cancelled.')
    with tempfile.TemporaryDirectory(prefix='where-were-we-ai-') as cwd:
        # Anonymous temporary stdin avoids pipe deadlock with large source packs;
        # prompt and response are never written to app logs or saved run records.
        with tempfile.TemporaryFile() as incoming:
            incoming.write(prompt.encode('utf-8'))
            incoming.seek(0)
            watch_read, watch_write = os.pipe()
            status_read, status_write = os.pipe()
            try:
                # The supervisor watches an unshared pipe: killing this worker
                # closes its only writer, so even SIGKILL cleans up inference.
                process = subprocess.Popen([sys.executable, os.path.abspath(__file__),
                    '--supervise', str(watch_read), str(status_write), str(timeout+1), executable, *args], stdin=incoming,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=cwd,
                    env=_environment(), start_new_session=True, pass_fds=(watch_read, status_write))
            except OSError:
                os.close(watch_write)
                os.close(status_read)
                raise CLIExecutionError('CLI_UNAVAILABLE', 'Claude Code could not start. Install it and restart the app.') from None
            finally:
                os.close(watch_read)
                os.close(status_write)
            selector = selectors.DefaultSelector()
            output = bytearray()
            total = 0
            deadline = time.monotonic() + timeout
            try:
                for pipe in (process.stdout, process.stderr):
                    os.set_blocking(pipe.fileno(), False)
                    selector.register(pipe, selectors.EVENT_READ)
                while selector.get_map() or process.poll() is None:
                    if cancelled and cancelled():
                        raise CLIExecutionError('CANCELLED', 'Analysis was cancelled.')
                    if time.monotonic() >= deadline:
                        raise CLIExecutionError('CLI_TIMEOUT', 'Claude Code took too long. Try the analysis again.')
                    if process.poll() is not None:
                        # A completed leader can leave a child holding pipes.
                        _stop(process, force=True)
                    for key, _ in selector.select(timeout=0.05):
                        chunk = os.read(key.fileobj.fileno(), 65536)
                        if not chunk:
                            selector.unregister(key.fileobj)
                            continue
                        total += len(chunk)
                        if total > limit:
                            raise CLIExecutionError('CLI_OUTPUT_LIMIT', 'Claude Code returned too much output.')
                        if key.fileobj is process.stdout:
                            output.extend(chunk)
                reported = os.read(status_read, 64).decode('ascii', errors='replace')
                code = int(reported) if re.fullmatch(r'-?[0-9]{1,3}', reported) else process.returncode
                return code, output.decode('utf-8', errors='replace')
            finally:
                selector.close()
                _stop(process, force=True)
                os.close(watch_write)
                os.close(status_read)
                process.stdout.close()
                process.stderr.close()


def _safe_label(value):
    if not isinstance(value, str) or not 0 < len(value) <= 200:
        return None
    if any(ord(c) < 32 or ord(c) == 127 for c in value):
        return None
    if not re.fullmatch(r'[\w@.+ :/()\-]+', value):
        return None
    if re.search(r'(?:sk-|Bearer|token|secret)', value, re.I):
        return None
    return value


def availability(*, cancelled=None, timeout=20):
    """Read local CLI help and auth status; never invoke inference or login."""
    result = {'provider': 'claude', 'id': 'claude', 'available': False,
              'authenticated': False, 'account': {},
              'usage_message': 'Uses your existing Claude Code subscription and its usage limits. Organization policy still applies.',
              'error_code': None, 'message': ''}
    executable = shutil.which('claude')
    if not executable:
        result.update(error_code='CLI_NOT_INSTALLED', message='Install Claude Code and restart the app, or use the manual MCP workflow.')
        return result
    deadline = time.monotonic() + timeout
    def probe(args, limit):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise CLIExecutionError('CLI_TIMEOUT', 'Claude Code took too long. Try the analysis again.')
        return _run(executable, args, timeout=min(10, remaining), cancelled=cancelled, limit=limit)
    try:
        code, help_text = probe(['--help'], 1_000_000)
        if code or any(flag not in help_text for flag in REQUIRED_FLAGS):
            result.update(error_code='CLI_UNSUPPORTED', message='Update Claude Code to a version supporting safe mode and isolated print mode, then restart the app.')
            return result
        result['available'] = True
        code, text = probe(['auth', 'status'], 100_000)
        try:
            auth = json.loads(text)
        except (ValueError, TypeError):
            raise CLIExecutionError('CLI_AUTH_STATUS', 'Could not read Claude Code login status. Check it in a terminal.') from None
        if not isinstance(auth, dict):
            raise CLIExecutionError('CLI_AUTH_STATUS', 'Could not read Claude Code login status. Check it in a terminal.')
        method = auth.get('authMethod')
        account = {'auth_method': _safe_label(method)}
        for source, target in (('email', 'email'), ('accountId', 'id'), ('subscriptionType', 'subscription_type')):
            value = _safe_label(auth.get(source))
            if value:
                account[target] = value
        result['account'] = {k: v for k, v in account.items() if v}
        if code == 0 and auth.get('loggedIn') is True and method == 'claude.ai':
            if account.get('id') or account.get('email'):
                result['authenticated'] = True
            else:
                result.update(error_code='CLI_ACCOUNT_UNIDENTIFIED', message='Claude Code did not identify the signed-in account. Update Claude Code and check its login status in a terminal before starting analysis.')
        elif code == 0 and method not in (None, 'none', 'claude.ai'):
            result.update(error_code='CLI_AUTH_UNSUPPORTED', message='This connection needs an existing Claude subscription login. API keys and third-party billing are not supported here; use the manual MCP workflow.')
        else:
            result.update(error_code='CLI_NOT_AUTHENTICATED', message='Sign in to Claude Code in your terminal, then check the connection again.')
    except CLIExecutionError as error:
        result.update(error_code=error.code, message=error.message)
    return result


def _failure(envelope):
    """Classify only fixed machine enums, never provider messages or stderr."""
    enums = [envelope.get('subtype'), envelope.get('error_code')]
    error = envelope.get('error')
    enums.append(error.get('type') if isinstance(error, dict) else error)
    if any(v in ('rate_limit_error', 'usage_limit', 'error_usage_limit',
                 'error_max_budget_usd') for v in enums if isinstance(v, str)):
        return CLIExecutionError('CLI_USAGE_LIMIT', 'Claude Code reached a usage or spend limit. Check your subscription limits in the terminal before retrying.')
    if any(v in ('authentication_error', 'auth_error', 'error_authentication')
           for v in enums if isinstance(v, str)):
        return CLIExecutionError('CLI_AUTH', 'Claude Code authentication failed. Check your subscription login in the terminal before retrying.')
    return CLIExecutionError('CLI_FAILED', 'Claude Code could not complete the analysis. Check your login, usage limits, and organization policy in the terminal, then retry.')


def execute(prompt, *, cancelled=None, timeout=600, expected_account=None):
    """Return JSON object text; the caller validates the task's schema/evidence."""
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt.encode('utf-8')) > MAX_PROMPT:
        raise CLIExecutionError('CLI_INPUT_INVALID', 'The analysis source pack is empty or too large.')
    if not isinstance(timeout, (int, float)) or not 0 < timeout <= 3600:
        raise CLIExecutionError('CLI_INPUT_INVALID', 'Invalid analysis time limit.')
    deadline = time.monotonic() + timeout
    args = ['--print', '--safe-mode', '--tools', '', '--disallowedTools', 'mcp__*',
            '--strict-mcp-config', '--mcp-config', '{"mcpServers":{}}',
            '--setting-sources', '', '--settings', '{"disableAllHooks":true}',
            '--disable-slash-commands', '--no-chrome', '--no-session-persistence',
            '--output-format', 'json']
    # The caller freezes the account shown when starting the run. Recheck before
    # every model invocation, including each task in a multi-task run. A CLI
    # cannot atomically pin the external keychain, so a concurrent login change
    # after this check remains outside this adapter's control.
    status = availability(cancelled=cancelled, timeout=timeout)
    if not status['available'] or not status['authenticated']:
        raise CLIExecutionError(status['error_code'] or 'CLI_UNAVAILABLE', status['message'])
    if expected_account is not None and (not isinstance(expected_account, dict)
                                         or expected_account != status['account']):
        raise CLIExecutionError('CLI_ACCOUNT_CHANGED', 'The Claude Code account changed. Check the displayed connection and start a new analysis run.')
    executable = shutil.which('claude')
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise CLIExecutionError('CLI_TIMEOUT', 'Claude Code took too long. Try the analysis again.')
    code, text = _run(executable, args, prompt=prompt, timeout=remaining, cancelled=cancelled)
    if cancelled and cancelled():
        raise CLIExecutionError('CANCELLED', 'Analysis was cancelled.')
    try:
        envelope = json.loads(text)
    except (ValueError, TypeError):
        envelope = None
    if code or isinstance(envelope, dict) and envelope.get('is_error'):
        raise _failure(envelope if isinstance(envelope, dict) else {})
    try:
        if not isinstance(envelope, dict):
            raise ValueError()
        data = envelope.get('structured_output')
        if data is None:
            answer = envelope.get('result')
            if not isinstance(answer, str):
                raise ValueError()
            data = json.loads(answer)
        if not isinstance(data, dict):
            raise ValueError()
        return json.dumps(data, ensure_ascii=False)
    except (ValueError, TypeError):
        raise CLIExecutionError('CLI_INVALID_OUTPUT', 'Claude Code did not return the requested JSON object. No analysis was saved.') from None


class ClaudeCLIExecutor:
    availability = staticmethod(availability)
    execute = staticmethod(execute)


def _supervise(watch_fd, status_fd, timeout, command):
    """Private process guardian; owns only the group created by _run()."""
    stopping = False
    def stop_requested(signum, frame):
        nonlocal stopping
        stopping = True
    signal.signal(signal.SIGTERM, stop_requested)
    signal.signal(signal.SIGINT, stop_requested)
    child = subprocess.Popen(command)  # Inherit guardian's private process group.
    deadline = time.monotonic() + timeout
    watcher = selectors.DefaultSelector()
    watcher.register(watch_fd, selectors.EVENT_READ)
    try:
        while child.poll() is None and not stopping and time.monotonic() < deadline:
            if watcher.select(timeout=0.05) and not os.read(watch_fd, 1):
                stopping = True
        if child.poll() is not None and not stopping:
            # Send only the actual CLI exit code on a private channel. The
            # guardian can then KILL its entire group, including itself, even
            # on success, without disguising the CLI's exit status.
            os.write(status_fd, str(child.returncode).encode('ascii'))
        os.killpg(os.getpgrp(), signal.SIGTERM)
        # Escalate without relying on the app process surviving. This also kills
        # the guardian itself; every member belongs to this one invocation.
        time.sleep(0.25)
        os.killpg(os.getpgrp(), signal.SIGKILL)
    finally:
        watcher.close()
        os.close(watch_fd)
        os.close(status_fd)


if __name__ == '__main__' and len(sys.argv) >= 6 and sys.argv[1] == '--supervise':
    try:
        sys.exit(_supervise(int(sys.argv[2]), int(sys.argv[3]), float(sys.argv[4]), sys.argv[5:]))
    except (OSError, ValueError):
        sys.exit(1)
