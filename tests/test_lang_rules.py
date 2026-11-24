"""Reading rules for languages outside the built-in readers; fake executors only, never a real AI call."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import analysis_units
import lang_rules
import mapcore
import structure_index

JAVA = {'extensions': ['.java'],
        'declarations': [{'regex': r'^\s*(?:public\s+|final\s+|abstract\s+)*(class|interface|enum|record)\s+(\w+)', 'kind': 1, 'name': 2}],
        'imports': [{'regex': r'^import\s+(?:static\s+)?([\w.]+?)(?:\.\*)?\s*;', 'group': 1,
                     'resolve': {'sep': '.', 'from': 'root', 'ext': ['.java'], 'roots': ['src/main/java/'], 'suffix': True, 'trim_tail': True}}]}
RUBY = {'extensions': ['.rb'],
        'declarations': [{'regex': r'^\s*(class|module)\s+([A-Z][\w:]*)', 'kind': 1, 'name': 2},
                         {'regex': r'^\s*def\s+([\w?!]+)', 'kind': 'method', 'name': 1}],
        'imports': [{'regex': r'''^\s*require_relative\s+['"]([^'"]+)['"]''', 'group': 1, 'resolve': {'from': 'dir', 'ext': ['.rb']}},
                    {'regex': r'''^\s*require\s+['"]([^'"]+)['"]''', 'group': 1, 'resolve': {'from': 'root', 'ext': ['.rb'], 'suffix': True}}]}


def repository(folder, files):
    for name, text in files.items():
        path = Path(folder) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    run = lambda *a: subprocess.run(['git', '-C', folder, *a], check=True, capture_output=True, text=True).stdout.strip()
    run('init', '-q')
    run('add', '-A')
    run('-c', 'user.name=t', '-c', 'user.email=t@example.invalid', 'commit', '-qm', 'x')
    return run('rev-parse', 'HEAD')


JAVA_FILES = {
    'src/main/java/shop/owner/Owner.java': 'package shop.owner;\nimport shop.model.Person;\npublic class Owner extends Person {}\n',
    'src/main/java/shop/owner/OwnerController.java': 'package shop.owner;\nimport shop.owner.Owner;\nimport static shop.model.Names.clean;\npublic final class OwnerController {}\n',
    'src/main/java/shop/model/Person.java': 'package shop.model;\npublic abstract class Person {}\n',
    'src/main/java/shop/model/Names.java': 'package shop.model;\npublic class Names { static String clean(String s){return s;} }\n',
    **{f'src/main/java/shop/model/Pet{i}.java': f'package shop.model;\npublic class Pet{i} {{}}\n' for i in range(12)},
}
RUBY_FILES = {
    'lib/app.rb': "require 'app/base'\nrequire_relative 'app/helpers'\nmodule App\nend\n",
    'lib/app/base.rb': "module App\n  class Base\n    def call(env)\n    end\n  end\nend\n",
    'lib/app/helpers.rb': "module App\n  module Helpers\n    def h(text) = text\n  end\nend\n",
    **{f'lib/app/parts/part{i}.rb': f"module App\n  class Part{i}\n  end\nend\n" for i in range(12)},
}


class LangRules(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name) / 'root'
        root.mkdir()
        patcher = patch.object(mapcore, 'ROOT', str(root))
        patcher.start()
        self.addCleanup(patcher.stop)

    def catalog(self, folder, commit, rules):
        index = structure_index.build(folder, commit, excluded=lambda f: False, rules=rules)
        tracked = {f: 1 for f in subprocess.run(['git', '-C', folder, 'ls-files'], capture_output=True, text=True).stdout.split()}
        return index, analysis_units.catalog(index, tracked, lambda f, s: None)

    def rules(self, name, answer):
        rule = lang_rules.validate(answer, name, [])
        self.assertTrue(rule)
        return {ext: rule for ext in rule['extensions']}

    def test_java_and_ruby_units_get_import_links(self):
        for name, files, answer in (('java', JAVA_FILES, JAVA), ('ruby', RUBY_FILES, RUBY)):
            folder = str(Path(self.temp.name) / name)
            commit = repository(folder, files)
            index, catalog = self.catalog(folder, commit, self.rules(name, answer))
            self.assertEqual({row['language'] for row in index['files']}, {name})
            self.assertTrue(all(row['declarations'] for row in index['files']), index['files'])
            edges = {(e['file'], e['target']) for e in index['imports']}
            if name == 'java':
                self.assertIn(('src/main/java/shop/owner/Owner.java', 'src/main/java/shop/model/Person.java'), edges)
                # A static import names a member: the trailing segment is dropped to find the file.
                self.assertIn(('src/main/java/shop/owner/OwnerController.java', 'src/main/java/shop/model/Names.java'), edges)
            else:
                self.assertEqual(edges, {('lib/app.rb', 'lib/app/base.rb'), ('lib/app.rb', 'lib/app/helpers.rb')})
            self.assertTrue(catalog['links'], catalog)
            # Without rules the same repository still has its folder units, only without connections.
            _, plain = self.catalog(folder, commit, {})
            self.assertEqual(sorted(u['id'] for u in plain['units']), sorted(u['id'] for u in catalog['units']))
            self.assertFalse(plain['links'])

    def test_hostile_or_invalid_patterns_are_dropped(self):
        answer = {'extensions': ['.java', '../x', '.py'],
                  'declarations': [{'regex': r'(a+)+$', 'kind': 'x', 'name': 1},       # nested repeat
                                   {'regex': r'(\w)\1', 'kind': 'x', 'name': 1},        # backreference
                                   {'regex': r'([', 'kind': 'x', 'name': 1},            # does not compile
                                   {'regex': 'x' * 400, 'kind': 'x', 'name': 0},        # too long
                                   {'regex': r'(?:(?:a|aa)*)*b(\w+)', 'kind': 'x', 'name': 1},
                                   {'regex': r'^(\w+\s?)+$', 'kind': 'x', 'name': 1},  # slow only on a failing line: timed out
                                   {'regex': r'^\s*class\s+(\w+)', 'kind': 'class', 'name': 1}],
                  'imports': [{'regex': r'^import\s+([\w.]+);', 'group': 1,
                               'resolve': {'sep': '.', 'roots': ['/etc/', '../', 'src/'], 'ext': ['.java', '/../../x']}}]}
        started = time.monotonic()
        rule = lang_rules.validate(answer, 'java', ['a' * 50 + '!'])
        self.assertLess(time.monotonic() - started, 30)
        self.assertEqual([d['regex'] for d in rule['declarations']], [r'^\s*class\s+(\w+)'])
        self.assertEqual(rule['extensions'], ['.java'])
        self.assertEqual(rule['imports'][0]['resolve']['roots'], ['src/'])
        self.assertEqual(rule['imports'][0]['resolve']['ext'], ['.java'])
        self.assertGreaterEqual(rule['dropped'], 7)
        # A resolved import is always a tracked path of the same commit.
        paths = lang_rules.Paths({'src/a/B.java'})
        rows, edges, missing, _ = lang_rules.apply(rule, 'src/a/A.java', 'import a.B;\nimport ..etc.passwd;\n' + 'x' * 100000, paths)
        self.assertEqual(edges, [{'file': 'src/a/A.java', 'line': 1, 'target': 'src/a/B.java'}])
        self.assertIsNone(lang_rules.validate({'declarations': [{'regex': '(', 'name': 1}]}, 'java'))

    def test_rules_are_cached_and_reused_and_a_failure_keeps_the_folder_map(self):
        folder = str(Path(self.temp.name) / 'java')
        commit = repository(folder, JAVA_FILES)
        files = sorted(JAVA_FILES)
        read = lambda f: JAVA_FILES[f]
        sizes = {f: len(t) for f, t in JAVA_FILES.items()}
        self.assertEqual(set(lang_rules.needed(files)), {'java'})

        def failing(prompt, **kwargs):
            raise RuntimeError('no reply')
        rule, calls, sent = lang_rules.obtain('java', files, sizes, read, failing)
        self.assertEqual((rule, calls), (None, 2))  # one retry, then the language stays unread
        self.assertEqual(lang_rules.loaded(['java']), {})
        _, catalog = self.catalog(folder, commit, {})
        self.assertTrue(catalog['units'])

        asked = []

        def fake(prompt, **kwargs):
            asked.append(prompt)
            self.assertIn('src/main/java/shop/owner/Owner.java', prompt)
            return json.dumps(JAVA)
        rule, calls, sent = lang_rules.obtain('java', files, sizes, read, fake)
        self.assertEqual(calls, 1)
        self.assertGreater(sent, 0)
        again, calls, _ = lang_rules.obtain('java', files, sizes, read, fake)
        self.assertEqual((again, calls, len(asked)), (rule, 0, 1))
        self.assertEqual(set(lang_rules.loaded(['java'])), {'.java'})

    def test_an_answer_wrapped_in_one_key_is_accepted_and_cached(self):
        files = sorted(RUBY_FILES)
        sizes = {f: len(t) for f, t in RUBY_FILES.items()}
        asked = []

        def wrapped(prompt, **kwargs):
            asked.append(prompt)
            self.assertNotIn('"format"', prompt)
            return json.dumps({'language': 'ruby', 'format': RUBY})
        rule, calls, _ = lang_rules.obtain('ruby', files, sizes, RUBY_FILES.get, wrapped)
        self.assertEqual((calls, len(rule['imports'])), (1, 2))
        self.assertEqual(lang_rules.obtain('ruby', files, sizes, RUBY_FILES.get, wrapped)[1], 0)


if __name__ == '__main__':
    unittest.main()
