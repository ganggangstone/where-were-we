"""Shared test harness. Importing it blocks real AI CLIs and drops an inherited settings path for the whole process."""
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
# Fixtures isolate settings through mapcore.ROOT; an inherited settings file would bypass that and be shared.
os.environ.pop('WHERE_WERE_WE_SETTINGS', None)
import mapcore  # noqa: E402

# Every AI CLI the product or a connected agent can start. cli_executor starts only `claude` today;
# codex and gemini are the other agent CLIs the app registers with, so a test reaching them is also a failure.
AI_CLIS = ('claude', 'codex', 'gemini')
_TEMP = os.path.realpath(tempfile.gettempdir()) + os.sep
_execute_child = subprocess.Popen._execute_child


def _real_ai(arg, env):
    arg = os.fsdecode(arg)
    if os.path.basename(arg) not in AI_CLIS:
        return False
    found = arg if os.sep in arg else shutil.which(arg, path=(env if env is not None else os.environ).get('PATH'))
    # A fake CLI script a test wrote into its own temporary folder is allowed; anything else named like an AI CLI is not.
    return not (found and os.path.realpath(found).startswith(_TEMP))


def _guarded(self, args, executable, preexec_fn, close_fds, pass_fds, cwd, env, *rest):
    argv = os.fsdecode(args).split() if isinstance(args, (str, bytes)) else [os.fspath(a) if isinstance(a, os.PathLike) else a for a in args]
    if any(isinstance(a, (str, bytes)) and _real_ai(a, env) for a in [*argv, executable or '']):
        raise AssertionError('Real AI calls are forbidden in tests; inject a fake executor or a fake CLI in a temporary folder: ' + str(argv[:1]))
    return _execute_child(self, args, executable, preexec_fn, close_fds, pass_fds, cwd, env, *rest)


# Popen._execute_child is under subprocess.run/check_output/Popen and any `from subprocess import ...`.
# ponytail: guards this process only; a detached child process (the analysis worker) is not guarded, so tests
# that start one must give it a fake CLI on PATH, as test_analysis_run does.
subprocess.Popen._execute_child = _guarded


class TemporaryProject(unittest.TestCase):
    """A fresh temporary folder as mapcore.ROOT for each test."""
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.patch = patch.object(mapcore, 'ROOT', str(self.root))
        self.patch.start(); self.addCleanup(self.patch.stop)


def git(repo, *args):
    return subprocess.run(['git', '-C', str(repo), *args], check=True, capture_output=True, text=True).stdout


def repository(folder, files):
    """Write files into folder, commit them as one synthetic commit and return its hash."""
    for name, text in files.items():
        path = Path(folder) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    git(folder, 'init', '-q')
    git(folder, 'add', '-A')
    git(folder, '-c', 'user.name=t', '-c', 'user.email=t@example.invalid', 'commit', '-qm', 'x')
    return git(folder, 'rev-parse', 'HEAD').strip()


CHROME = Path('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome')


def dump_dom(uri, user_dir, budget=None, window=None, timeout=30, run=None, flags=()):
    """The DOM headless Chrome leaves after loading uri; pass `run` when subprocess.run is patched."""
    command = [str(CHROME), '--headless', '--disable-gpu', '--no-first-run', '--disable-background-networking',
               '--disable-component-update', '--no-default-browser-check', '--user-data-dir=' + str(user_dir), *flags]
    if window:
        command.append('--window-size=' + window)
    if budget:
        command.append(f'--virtual-time-budget={budget}')
    return (run or subprocess.run)([*command, '--dump-dom', uri], capture_output=True, text=True, timeout=timeout)


UI_ASSETS = ('tokens.css', 'app.css', 'vendor/dagre.min.js', 'connection.js', 'onboarding.js', 'control.js', 'analysis-run.js')


def inline_assets(html, ui=ROOT / 'ui'):
    """Point index.html's relative asset references at the files in ui, so a copied page loads them."""
    for name in UI_ASSETS:
        html = html.replace(f'"{name}"', '"' + (Path(ui) / name).as_uri() + '"')
    return html


def compiled_probe(name):
    """The WebKit probe tests/<name>, compiled once and cached by its source hash in the system temp folder."""
    source = ROOT / 'tests' / name
    key = hashlib.sha256(source.read_bytes()).hexdigest()[:16]
    probe = Path(tempfile.gettempdir()) / 'where-were-we-test-probes' / f'{source.stem}-{key}'
    if not probe.exists():
        probe.parent.mkdir(exist_ok=True)
        partial = probe.with_name(f'{probe.name}.{os.getpid()}')
        subprocess.run(['swiftc', '-O', str(source), '-o', str(partial)], check=True, capture_output=True)
        os.replace(partial, probe)  # atomic, so a concurrent run never sees a half-written binary
    return probe
