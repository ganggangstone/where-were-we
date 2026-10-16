"""Packaging checks use temporary paths and never read real project maps."""
import importlib.util
import ast
import hashlib
import os
from pathlib import Path
import shlex
import io
import json
import plistlib
import shutil
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import zipfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import mapcore

spec = importlib.util.spec_from_file_location('prepare_runtime', ROOT / 'scripts/prepare-runtime.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class PromptPaths(unittest.TestCase):
    def test_prompt_languages_keep_commands_and_project_text(self):
        with patch.object(mapcore, 'projects', return_value=[]):
            default = mapcore.setup_prompt()
            english = mapcore.setup_prompt(lang='en')
        self.assertIn('MCP 서버', default)
        self.assertIn('Before changing configuration', english)
        self.assertIn('claude mcp add --scope user where-were-we --', english)
        self.assertIn('[mcp_servers.where-were-we]', english)
        with patch.object(mapcore, 'tests_conf', return_value={'files':['test_*.py'], 'calls':['client.<method>("<path>")']}):
            prompt = mapcore.tests_prompt('원문-project', ['backend/render.py::cancel'], lang='en')
        self.assertIn('원문-project', prompt)
        self.assertIn('backend/render.py::cancel', prompt)
        self.assertIn('Do not conclude that tests do not exist', prompt)
        self.assertIn('record_test', prompt)
        with patch.object(mapcore, 'projects', return_value=['source-name']), patch.object(mapcore, '_read', return_value={'repo':'/demo/path with spaces'}), patch('subprocess.run', return_value=SimpleNamespace(returncode=0,stdout='https://example.invalid/demo.git\n')):
            english = mapcore.setup_prompt(lang='en')
        self.assertIn('any working folder cloned from https://example.invalid/demo.git', english)
        self.assertIn('/demo/path with spaces', english)

    def test_nested_refresh_uses_isolated_nonwriting_python(self):
        calls = []
        process = SimpleNamespace(run=lambda args, **kwargs: (calls.append(args) or
                                 SimpleNamespace(returncode=0, stdout='', stderr='')))
        for filename in ('refresh.py', 'mcp_server.py'):
            tree = ast.parse((ROOT / filename).read_text())
            name = 'run' if filename == 'refresh.py' else 'refresh'
            function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
            function.decorator_list = []
            scope = dict(subprocess=process, sys=sys, mapcore=mapcore, os=os, HERE='/bundled backend',
                         need=lambda project: project, changes=lambda project: '',
                         project_store=SimpleNamespace(config=lambda project: None))
            exec(compile(ast.Module(body=[function], type_ignores=[]), filename, 'exec'), scope)
            if name == 'run': scope[name]('/bundled backend/extract.py', 'fake')
            else: scope[name]('fake')
            self.assertEqual(calls[-1][:3], [sys.executable, '-I', '-B'])

    def test_installed_interpreter_and_paths_with_spaces(self):
        base = Path('/Applications/where were we.app/Contents/Resources/runtime')
        python = str(base / 'python/bin/python3')
        server = str(base / 'backend/mcp_server.py')
        with patch.object(mapcore, '__file__', str(base / 'backend/mapcore.py')), \
             patch.object(sys, 'executable', python), patch.object(mapcore, 'projects', return_value=[]):
            prompt = mapcore.setup_prompt()
        claude = next(line.strip()[2:] for line in prompt.splitlines() if line.strip().startswith('- Claude Code:'))
        self.assertEqual(shlex.split(claude.split(': ', 1)[1]),
                         ['claude', 'mcp', 'add', '--scope', 'user', 'where-were-we', '--', python, '-I', '-B', server])
        config = prompt.split('[mcp_servers.where-were-we]', 1)[1].split('   - 다른 에이전트:', 1)[0]
        parsed = tomllib.loads('[mcp_servers.where-were-we]' + config)['mcp_servers']['where-were-we']
        self.assertEqual(parsed, {'command': python, 'args': ['-I', '-B', server]})


class ArchiveChecks(unittest.TestCase):
    def test_bad_cached_archive_is_rejected_before_use(self):
        with tempfile.TemporaryDirectory() as temporary:
            cache = Path(temporary)
            name = f'cpython-{builder.PYTHON_VERSION}+{builder.PYTHON_RELEASE}-aarch64-apple-darwin-install_only_stripped.tar.gz'
            (cache / name).write_bytes(b'corrupted download')
            with patch.object(builder.urllib.request, 'urlopen') as network:
                with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
                    builder.fetch_archive('aarch64-apple-darwin', cache)
                network.assert_not_called()

    def test_archive_cannot_write_outside_runtime(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            archive = base / 'bad.tar.gz'
            with tarfile.open(archive, 'w:gz') as tar:
                member = tarfile.TarInfo('../escaped')
                member.size = 1
                tar.addfile(member, io.BytesIO(b'x'))
            with self.assertRaises(tarfile.FilterError):
                builder.unpack(archive, base / 'output')
            self.assertFalse((base / 'escaped').exists())


class ReleaseArtifacts(unittest.TestCase):
    def test_cask_uses_only_available_architectures_and_fixed_hashes(self):
        arm = 'a' * 64
        intel = 'b' * 64
        cask = builder.cask_definition('0.1.0', {'aarch64-apple-darwin': arm})
        self.assertIn('depends_on arch: :arm64', cask)
        self.assertIn(f'sha256 "{arm}"', cask)
        self.assertIn('where-were-we_#{version}_aarch64-apple-darwin.zip', cask)
        self.assertIn('app "where-were-we.app"', cask)
        self.assertNotIn('auto_updates', cask)
        self.assertNotIn('zap', cask, 'Uninstall must preserve project maps')
        both = builder.cask_definition('0.1.0', {'aarch64-apple-darwin': arm, 'x86_64-apple-darwin': intel})
        self.assertIn('arch arm: "aarch64-apple-darwin", intel: "x86_64-apple-darwin"', both)
        self.assertIn(f'intel: "{intel}"', both)

    def test_cask_rejects_unusable_inputs(self):
        for version in ('../private', '0.1.0-beta.1', '0.1'):
            with self.assertRaises(ValueError): builder.cask_definition(version, {'aarch64-apple-darwin': 'a' * 64})
        with self.assertRaises(ValueError): builder.cask_definition('0.1.0', {})
        with self.assertRaises(ValueError): builder.cask_definition('0.1.0', {'aarch64-apple-darwin': 'not a digest'})

    @unittest.skipUnless(sys.platform == 'darwin', 'Uses the macOS ZIP packaging tool')
    def test_release_zip_matches_cask_and_rejects_version_mismatch(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            app = root / 'src-tauri/target/aarch64-apple-darwin/release/bundle/macos/where-were-we.app'
            contents = app / 'Contents'
            (contents / 'MacOS').mkdir(parents=True)
            (contents / 'MacOS/where-were-we').write_bytes(b'fictional test executable; never run')
            runtime = contents / 'Resources/runtime'
            runtime.mkdir(parents=True)
            (runtime / 'runtime.json').write_text(json.dumps({'target':'aarch64-apple-darwin'}))
            info = {'CFBundleShortVersionString':'0.1.0'}
            (contents / 'Info.plist').write_bytes(plistlib.dumps(info))
            (root / 'src-tauri/tauri.conf.json').write_text('{"version":"0.1.0"}')
            (root / 'README.md').write_text('<!-- release-notes:start -->\n### 한국어\n- 가상\n### English\n- Fictional\n<!-- release-notes:end -->')
            # ZIP creation is real; only architecture inspection of the fake binary is mocked.
            with patch.object(builder, 'ROOT', root), patch.object(builder.subprocess, 'check_output', return_value='arm64\n'):
                preview = builder.release_preview('aarch64-apple-darwin')
                archive = Path(preview['archive'])
                self.assertEqual(preview['sha256'], hashlib.sha256(archive.read_bytes()).hexdigest())
                self.assertIn(preview['sha256'], preview['cask'])
                with zipfile.ZipFile(archive) as zipped:
                    self.assertIn('where-were-we.app/Contents/Info.plist', zipped.namelist())
                info['CFBundleShortVersionString'] = '0.0.9'
                (contents / 'Info.plist').write_bytes(plistlib.dumps(info))
                with self.assertRaisesRegex(ValueError, 'current app version'):
                    builder.release_preview('aarch64-apple-darwin')


@unittest.skipUnless(os.environ.get('WHERE_WERE_WE_RUNTIME'), 'Set WHERE_WERE_WE_RUNTIME for the real relocatable-runtime check')
class RelocatedRuntime(unittest.TestCase):
    def test_app_binary_omits_build_machine_home(self):
        runtime = Path(os.environ['WHERE_WERE_WE_RUNTIME']).resolve()
        binary = runtime.parent.parent / 'MacOS/where-were-we'
        if not binary.is_file():
            self.skipTest('Point WHERE_WERE_WE_RUNTIME at the built .app resources for binary checks')
        self.assertFalse(str(Path.home()).encode() in binary.read_bytes(), 'Build home leaked into executable')

    def test_prompt_and_mcp_without_checkout_or_system_python(self):
        with tempfile.TemporaryDirectory(prefix='where were we ') as temporary:
            base = Path(temporary)
            runtime = base / 'Installed App.app/Contents/Resources/runtime'
            shutil.copytree(Path(os.environ['WHERE_WERE_WE_RUNTIME']).resolve(), runtime, symlinks=True)
            self.assertEqual({p.name for p in (runtime / 'backend').iterdir()}, set(builder.BACKEND_FILES))
            self.assertEqual({p.name for p in (runtime / 'python/bin').iterdir()}, {'python3'})
            metadata = json.loads((runtime / 'python/PYTHON.json').read_text())
            def notice_paths(value):
                if isinstance(value, dict):
                    for key, child in value.items():
                        if key == 'license_path': yield child
                        elif key == 'license_paths': yield from child
                        else: yield from notice_paths(child)
                elif isinstance(value, list):
                    for child in value: yield from notice_paths(child)
            notices = set(notice_paths(metadata))
            self.assertTrue(any('openssl' in path.lower() for path in notices))
            for path in notices:
                self.assertTrue((runtime / 'python' / path).is_file(), path)
            home = base / 'empty home'
            home.mkdir()
            python = runtime / 'python/bin/python3'
            env = dict(builder.clean_environment(), HOME=str(home), PATH='/usr/bin:/bin')
            result = subprocess.run([str(python), '-I', '-B', str(runtime / 'backend/mapcore.py'), 'setup'],
                                    cwd=home, env=env, text=True, capture_output=True, check=True)
            self.assertIn(str(python), result.stdout)
            self.assertNotIn(str(ROOT), result.stdout)
            config = result.stdout.split('[mcp_servers.where-were-we]', 1)[1].split('   - 다른 에이전트:', 1)[0]
            registration = tomllib.loads('[mcp_servers.where-were-we]' + config)['mcp_servers']['where-were-we']
            # Real MCP protocol handshake and tool request, not a mocked SDK import.
            client = '''
import anyio, json, sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
async def main():
    registration = json.loads(sys.argv[1])
    async with stdio_client(StdioServerParameters(**registration)) as streams:
        async with ClientSession(*streams) as session:
            await session.initialize()
            tools = await session.list_tools()
            assert 'projects' in [tool.name for tool in tools.tools]
            result = await session.call_tool('projects', {})
            assert not result.is_error, result
            print('MCP handshake and projects passed')
anyio.run(main)
'''
            result = subprocess.run([str(python), '-I', '-B', '-c', client, json.dumps(registration)],
                                    cwd=home, env=env, text=True, capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('MCP handshake and projects passed', result.stdout)
            self.assertFalse(list(runtime.rglob('__pycache__')), 'Installed bundle must not be modified')


if __name__ == '__main__':
    unittest.main()
