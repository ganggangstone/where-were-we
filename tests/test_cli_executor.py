"""Transport tests use an executable fixture, never a real AI provider."""
import json
import os
from pathlib import Path
import subprocess
import signal
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cli_executor as cli


class CLIExecutorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        executable = self.root / 'claude'
        executable.write_text('#!' + sys.executable + '\n' + '''
import json, os, pathlib, signal, subprocess, sys, time
args=sys.argv[1:]
mode=os.environ.get('FIXTURE_MODE','ok')
if args==['--help']:
    print(os.environ['FIXTURE_FLAGS'] if mode!='old' else '--print --tools')
elif args==['auth','status']:
    if mode=='bad_auth':print('secret prompt');sys.exit(1)
    print(json.dumps({'loggedIn':mode!='logout','authMethod':'api_key' if mode=='api' else 'claude.ai',
        'email':None if mode=='unidentified' else ('bob@example.invalid' if mode=='bob' else 'alice@example.invalid'),
        'subscriptionType':'max','apiKey':'DO-NOT-EXPOSE'}))
    sys.exit(1 if mode=='logout' else 0)
else:
    prompt=sys.stdin.read()
    pathlib.Path(os.environ['FIXTURE_CAPTURE']).write_text(json.dumps({'args':args,'cwd':os.getcwd(),
        'prompt':prompt,'api_key':os.environ.get('ANTHROPIC_API_KEY'),
        'route':os.environ.get('ANTHROPIC_BASE_URL'),'oauth':os.environ.get('CLAUDE_CODE_OAUTH_TOKEN')}))
    if mode in ('wait','orphan'):
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        child=subprocess.Popen([sys.executable,'-c','import signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);time.sleep(60)'],
            stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        pathlib.Path(os.environ['FIXTURE_CHILD']).write_text(str(child.pid))
        pathlib.Path(os.environ['FIXTURE_LEADER']).write_text(str(os.getpid()))
        if mode=='wait':time.sleep(60)
    if mode=='big':print('x'*1000000);sys.exit()
    if mode=='fail':print('SECRET prompt stderr',file=sys.stderr);sys.exit(1)
    if mode=='invalid':print(json.dumps({'result':'```json\\n{}\\n```'}));sys.exit()
    if mode in ('error','usage','auth_error'):
        print(json.dumps({'is_error':True,'result':'SECRET',
            'subtype':{'usage':'rate_limit_error','auth_error':'authentication_error'}.get(mode,'error_during_execution')}));sys.exit()
    print(json.dumps({'result':json.dumps({'unknown':['source insufficient'],'inspected':[]})}))
''')
        executable.chmod(0o755)
        self.capture = self.root / 'capture.json'
        self.child = self.root / 'child'
        self.leader = self.root / 'leader'
        env = {'PATH':str(self.root), 'FIXTURE_FLAGS':' '.join(cli.REQUIRED_FLAGS),
               'FIXTURE_CAPTURE':str(self.capture),'FIXTURE_CHILD':str(self.child),'FIXTURE_LEADER':str(self.leader),
               'FIXTURE_MODE':'ok', 'ANTHROPIC_API_KEY':'secret-key',
               'ANTHROPIC_BASE_URL':'https://untrusted.invalid',
               'CLAUDE_CODE_OAUTH_TOKEN':'secret-token'}
        self.env = patch.dict(os.environ, env)
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_availability_is_no_inference_and_redacted(self):
        state = cli.availability()
        self.assertTrue(state['available'])
        self.assertTrue(state['authenticated'])
        self.assertEqual(state['account']['email'], 'alice@example.invalid')
        self.assertNotIn('DO-NOT-EXPOSE', json.dumps(state))
        self.assertFalse(self.capture.exists())

    def test_missing_old_and_incompatible_auth_fail_closed(self):
        for mode, error in [('old','CLI_UNSUPPORTED'),('logout','CLI_NOT_AUTHENTICATED'),
                            ('api','CLI_AUTH_UNSUPPORTED'),('bad_auth','CLI_AUTH_STATUS'),
                            ('unidentified','CLI_ACCOUNT_UNIDENTIFIED')]:
            with self.subTest(mode=mode), patch.dict(os.environ, FIXTURE_MODE=mode):
                state = cli.availability()
                self.assertFalse(state['authenticated'])
                self.assertEqual(state['error_code'], error)
                with self.assertRaises(cli.CLIExecutionError):
                    cli.execute('private prompt')
                self.assertFalse(self.capture.exists())
        with patch.dict(os.environ, PATH=''):
            self.assertEqual(cli.availability()['error_code'], 'CLI_NOT_INSTALLED')

    def test_prompt_stdin_isolated_cwd_no_tools_or_api_environment(self):
        prompt = 'Pinned source with hostile `$(commands)` and unicode 한글'
        answer = json.loads(cli.execute(prompt))
        self.assertEqual(answer['unknown'], ['source insufficient'])
        capture = json.loads(self.capture.read_text())
        self.assertEqual(capture['prompt'], prompt)
        self.assertNotIn(prompt, capture['args'])
        args = capture['args']
        self.assertEqual(args[args.index('--tools')+1], '')
        self.assertEqual(args[args.index('--setting-sources')+1], '')
        self.assertEqual(json.loads(args[args.index('--mcp-config')+1]), {'mcpServers':{}})
        self.assertIn('--safe-mode', args)
        self.assertNotIn('--bare', args)
        self.assertTrue(all(capture[k] is None for k in ('api_key','route','oauth')))
        self.assertNotEqual(capture['cwd'], os.getcwd())
        self.assertFalse(Path(capture['cwd']).exists())

    def test_failure_output_is_never_exposed_or_accepted(self):
        for mode, code in [('fail','CLI_FAILED'),('invalid','CLI_INVALID_OUTPUT'),('error','CLI_FAILED'),
                           ('usage','CLI_USAGE_LIMIT'),('auth_error','CLI_AUTH')]:
            with self.subTest(mode=mode), patch.dict(os.environ, FIXTURE_MODE=mode):
                with self.assertRaises(cli.CLIExecutionError) as error:
                    cli.execute('SECRET prompt')
                self.assertEqual(error.exception.code, code)
                self.assertNotIn('SECRET', str(error.exception))
        with patch.dict(os.environ, FIXTURE_MODE='big'), patch.object(cli, 'MAX_OUTPUT', 1000):
            # _run defaults are bound at definition; exercise explicit low bound.
            with self.assertRaises(cli.CLIExecutionError) as error:
                cli._run(str(self.root/'claude'), ['--print'], limit=1000)
            self.assertEqual(error.exception.code, 'CLI_OUTPUT_LIMIT')

    def test_selected_account_change_stops_before_inference(self):
        selected = cli.availability()['account']
        with patch.dict(os.environ, FIXTURE_MODE='bob'):
            with self.assertRaises(cli.CLIExecutionError) as error:
                cli.execute('private prompt', expected_account=selected)
            self.assertEqual(error.exception.code, 'CLI_ACCOUNT_CHANGED')
            self.assertFalse(self.capture.exists())
        self.assertIsInstance(json.loads(cli.execute('private prompt', expected_account=selected)), dict)

    def test_cancellation_timeout_terminate_only_owned_group(self):
        unrelated = subprocess.Popen([sys.executable, '-c', 'import time;time.sleep(60)'])
        self.addCleanup(lambda: unrelated.poll() is None and unrelated.kill())
        with patch.dict(os.environ, FIXTURE_MODE='wait'):
            with self.assertRaises(cli.CLIExecutionError) as error:
                cli.execute('private prompt', cancelled=lambda: self.child.exists())
            self.assertEqual(error.exception.code, 'CANCELLED')
            self.assertIsNone(unrelated.poll())
            self.child.unlink()
            start = time.monotonic()
            with self.assertRaises(cli.CLIExecutionError) as error:
                cli.execute('private prompt', timeout=0.15)
            self.assertEqual(error.exception.code, 'CLI_TIMEOUT')
            self.assertLess(time.monotonic()-start, 3)
        unrelated.kill()
        unrelated.wait()

    def running(self, pid):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        # Linux containers may retain adopted zombies; those cannot infer or
        # consume resources. macOS's reaper removes them directly.
        proc = Path('/proc')/str(pid)/'stat'
        try:
            return proc.read_text().rsplit(')', 1)[1].split()[0] != 'Z'
        except FileNotFoundError:
            return not Path('/proc').exists()

    def wait_stopped(self, *pids):
        deadline = time.monotonic()+3
        while time.monotonic() < deadline and any(self.running(p) for p in pids):
            time.sleep(0.025)
        self.assertFalse(any(self.running(p) for p in pids))

    def test_worker_sigkill_stops_cli_and_term_ignoring_descendants(self):
        with patch.dict(os.environ, FIXTURE_MODE='wait'):
            worker = subprocess.Popen([sys.executable, '-c',
                'import sys;sys.path.insert(0,'+repr(str(Path(cli.__file__).parent))+');'
                'import cli_executor;cli_executor.execute("private pinned source",timeout=30)'],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.addCleanup(lambda: worker.poll() is None and worker.kill())
            deadline = time.monotonic()+5
            while not self.leader.exists() and time.monotonic()<deadline:
                time.sleep(0.025)
            self.assertTrue(self.leader.exists())
            leader = int(self.leader.read_text()); child = int(self.child.read_text())
            self.assertTrue(self.running(leader))
            worker.kill(); worker.wait()
            self.wait_stopped(leader, child)

    def test_successful_cli_exit_does_not_leave_background_child(self):
        with patch.dict(os.environ, FIXTURE_MODE='orphan'):
            self.assertIsInstance(json.loads(cli.execute('private pinned source')), dict)
        self.wait_stopped(int(self.child.read_text()))


if __name__ == '__main__':
    unittest.main()
