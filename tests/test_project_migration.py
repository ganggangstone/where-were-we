"""A folder made before project.json becomes a one-repository project the first time any entry point opens it."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import support  # blocks real AI CLIs; drops an inherited WHERE_WERE_WE_SETTINGS
from unittest.mock import patch

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import mapcore
import project

GITHUB = {'host': 'github.com', 'account': 'someone'}


class Migration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        base = Path(cls.temp.name)
        cls.repo = base / 'code'; cls.repo.mkdir()
        git = lambda *a: subprocess.run(['git', '-C', cls.repo, *a], check=True, capture_output=True)
        git('init', '-q', '-b', 'dev'); git('config', 'user.name', 'Fixture'); git('config', 'user.email', 'fixture@example.invalid')
        (cls.repo / 'app.py').write_text('from fastapi import FastAPI\napp = FastAPI()\n@app.get("/items")\ndef items(): return []\n')
        git('add', '.'); git('commit', '-qm', 'first')
        # The map content comes from the current collector; the old layout places the same files in the project folder.
        cls.seed_root = base / 'seed'
        with cls.roots(cls.seed_root):
            project.configure('seed', {'repositories': [{'id': 'web', 'path': str(cls.repo), 'refs': {'dev': 'dev', 'main': None}}]})
            assert 'refreshed' in project.refresh_project('seed')
            folder = project.repository_folder('seed', {'id': 'web'}, project.states('seed'))
            cls.collected = {p.name: json.loads(p.read_text()) for p in folder.glob('*.json')}

    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    @staticmethod
    def roots(root):
        root.mkdir(parents=True, exist_ok=True)
        env = patch.dict(os.environ, {'WHERE_WERE_WE_ROOT': str(root), 'WHERE_WERE_WE_SETTINGS': str(root / 'settings.json')})
        value = patch.object(mapcore, 'ROOT', str(root))
        class Both:
            def __enter__(self):env.start();value.start()
            def __exit__(self, *a):value.stop();env.stop()
        return Both()

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(dir=self.temp.name))
        self.scope = self.roots(self.root); self.scope.__enter__(); self.addCleanup(self.scope.__exit__)

    def old_folder(self, name, repo=None):
        """Write the files a project kept before project.json; return them as they should read back."""
        home = self.root / name; home.mkdir()
        repo = str(repo or self.repo)
        dev = {**self.collected['dev.json'], 'repo': repo}
        stamp = project.fingerprint({'path': repo, 'refs': {'dev': dev['ref']}, 'layout': {}})
        dev['analysis'] = {**(dev.get('analysis') or {}), 'source': 'ai', 'configuration': stamp, 'commit': dev['commit']}
        files = {'dev.json': dev, 'status.json': self.collected['status.json'], 'changes.json': self.collected['changes.json'],
                 'groups.json': {'names': {'/': 'Home'}, 'request_names': {}, 'groups': [{'name': 'Main', 'screens': ['/']}], 'configuration': stamp},
                 'flows.json': {'routes': {'app.py::items': {'file': 'app.py', 'steps': []}}},
                 'system.json': {'nodes': [{'id': 'api', 'name': 'API', 'kind': 'program', 'code': ['.'], 'uses': []}], 'links': []},
                 'jobs.json': {'nodes': {'api': {'jobs': []}}},
                 'tests.json': {'files': ['test_*.py'], 'calls': ['client.<method>("<path>")'], 'records': [{'route': 'app.py::items', 'file': 'test_app.py', 'line': 1, 'quote': 'client.get'}]}}
        for file, value in files.items():(home / file).write_text(json.dumps(value))
        (home / 'dev.base.json').write_text('{}')
        (home / 'briefing.json').write_text(json.dumps({'results': {json.dumps(['', 'dev', 'en']): {'version': 'v', 'input_hash': 'old'}}}))
        (home / 'repository-state.json').write_text(json.dumps({'@github': {'path': repo, 'github': GITHUB}, '@review': {':dev': {'reason': 'r', 'map': 'm'}}}))
        conf = project.validate({'repositories': [{'id': project.MIGRATED, 'path': repo, 'refs': {'dev': 'dev', 'main': None}, 'layout': {}}]})
        new = project.fingerprint(conf['repositories'][0])
        expected = json.loads(json.dumps(files).replace(stamp, new))
        return home, expected

    def assertMigrated(self, name, expected):
        home = self.root / name
        conf = json.loads((home / 'project.json').read_text())
        repo = conf['repositories'][0]
        self.assertEqual((repo['id'], repo['name'], repo['github'], repo['refs']['dev']), (project.MIGRATED, name, GITHUB, 'dev'))
        state = project.states(name)
        self.assertNotIn('@github', state)
        self.assertEqual(list(state['@review']), [project.MIGRATED + ':dev'])
        folder = project.repository_folder(name, repo, state)
        self.assertEqual({file: json.loads((folder / file).read_text()) for file in expected}, expected)
        self.assertFalse([p.name for p in home.glob('*.json') if p.name not in ('project.json', 'repository-state.json', 'briefing.json')])
        self.assertEqual(sorted(p.name for p in (home / project.OLD_FILES).iterdir()), sorted([*expected, 'dev.base.json']))
        self.assertEqual(json.loads((home / 'briefing.json').read_text())['results'][json.dumps(['', 'dev', 'en'])], {'version': 'v', 'input_hash': 'old'})
        bundle = project.read_bundle(name)
        self.assertEqual([s['source_path'] for s in bundle['dev']['screens']], [s['path'] for s in expected['dev.json']['screens']])
        self.assertEqual([r['source_file'] for r in bundle['dev']['backend_routes']], [r['file'] for r in expected['dev.json']['backend_routes']])
        self.assertEqual(bundle['groups']['groups'][0]['name'], 'Main')
        self.assertIn(project.MIGRATED + '::api', bundle['jobs']['nodes'])
        self.assertIn(project.MIGRATED + '/app.py::items', bundle['flows']['routes'])
        self.assertTrue(bundle['project']['repositories'][0]['results']['dev']['analysis'])
        return folder

    def test_read_bundle_migrates_once(self):
        _, expected = self.old_folder('read')
        project.read_bundle('read')
        folder = self.assertMigrated('read', expected)
        before = {p: p.read_bytes() for p in (self.root / 'read').rglob('*') if p.is_file() and '.project.lock' not in p.name}
        project.read_bundle('read'); project.config('read')
        self.assertEqual({p: p.read_bytes() for p in (self.root / 'read').rglob('*') if p.is_file() and '.project.lock' not in p.name}, before)
        self.assertEqual(project.repository_folder('read', {'id': project.MIGRATED}, project.states('read')), folder)

    def test_refresh_after_migration_keeps_records_and_collects(self):
        _, expected = self.old_folder('fresh')
        self.assertIn(project.MIGRATED + ': refreshed', project.refresh_project('fresh'))
        state = project.states('fresh')[project.MIGRATED]
        self.assertTrue(state['last_success'])
        folder = project.repository_folder('fresh', {'id': project.MIGRATED}, project.states('fresh'))
        self.assertEqual(json.loads((folder / 'system.json').read_text())['nodes'][0]['id'], 'api')  # the collector re-checks its evidence
        for file in ('groups.json', 'flows.json', 'jobs.json', 'tests.json'):
            self.assertEqual(json.loads((folder / file).read_text()), expected[file])

    def test_mcp_tool_and_cli_migrate(self):
        import mcp_server
        _, expected = self.old_folder('tool')
        self.assertIn('tool', mcp_server.overview('tool'))
        self.assertMigrated('tool', expected)
        env = {**os.environ, 'WHERE_WERE_WE_ROOT': str(self.root), 'WHERE_WERE_WE_SETTINGS': str(self.root / 'settings.json')}
        for command in ('read', 'refresh'):
            _, expected = self.old_folder('cli-' + command)
            result = subprocess.run(mapcore.python_command(HERE / 'project.py', command, 'cli-' + command), env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn('FAILED', result.stdout)
            self.assertTrue((self.root / ('cli-' + command) / 'project.json').exists())
            if command == 'read':self.assertMigrated('cli-read', expected)

    def test_crash_before_or_after_switch_recovers(self):
        home, expected = self.old_folder('crash')
        write = project.atomic
        def fail_switch(path, value):
            if path.name == 'project.json':raise OSError('crash')
            write(path, value)
        with patch.object(project, 'atomic', fail_switch), self.assertRaises(OSError):project.config('crash')
        self.assertFalse((home / 'project.json').exists())
        self.assertTrue((home / 'dev.json').exists())
        replace = os.replace
        def fail_move(source, target):
            if project.OLD_FILES in str(target):raise OSError('crash')
            replace(source, target)
        with patch.object(project.os, 'replace', fail_move), self.assertRaises(OSError):project.config('crash')
        self.assertTrue((home / 'project.json').exists() and (home / 'dev.json').exists())
        project.read_bundle('crash')
        self.assertMigrated('crash', expected)
        self.assertEqual(len(list((home / 'repositories' / project.MIGRATED / 'snapshots').iterdir())), 1)

    def test_missing_code_folder_still_migrates(self):
        _, expected = self.old_folder('gone', repo=self.root / 'moved-away')
        self.assertEqual(len(project.read_bundle('gone')['dev']['screens']), len(expected['dev.json']['screens']))
        self.assertTrue((self.root / 'gone' / 'project.json').exists())
        self.assertIn('FAILED', project.refresh_project('gone'))
        self.assertTrue(json.loads(((project.repository_folder('gone', {'id': project.MIGRATED}, project.states('gone'))) / 'dev.json').read_text()))

    def test_collection_stage_folder_is_not_migrated(self):
        home, _ = self.old_folder('stage')
        with patch.dict(os.environ, {'WHERE_WERE_WE_COLLECTION_STAGE': '1'}):self.assertIsNone(project.config('stage'))
        self.assertFalse((home / 'project.json').exists())


if __name__ == '__main__':
    unittest.main()
