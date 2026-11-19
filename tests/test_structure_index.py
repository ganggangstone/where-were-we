import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import structure_index


class Structure(unittest.TestCase):
    def test_pinned_declarations_and_exact_imports_without_reading_private_or_untracked_files(self):
        with tempfile.TemporaryDirectory() as root:
            repo = Path(root)
            git = lambda *args: subprocess.check_output(['git','-C',root,*args]).decode().strip()
            git('init','-q')
            sources = {'src/pkg/__init__.py':'', 'src/pkg/db.py':'class Store:\n    async def read(self): pass\n',
                       'src/pkg/cli.py':'from .db import Store\nimport pkg.db\nimport missing\nfrom . import dynamic\n',
                       'docs.txt':'text', '.aws/private.py':'def secret(): pass', 'broken.py':'def ??',
                       'ambiguous.py':'import dup', 'dup.py':'', 'src/dup.py':''}
            for name,text in sources.items():
                path=repo/name
                path.parent.mkdir(parents=True,exist_ok=True)
                path.write_text(text)
            os.symlink('src/pkg/db.py',repo/'link.py')
            git('add','.')
            git('-c','user.name=Test','-c','user.email=test@example.invalid','commit','-qm','original')
            pin=git('rev-parse','HEAD')
            (repo/'src/pkg/db.py').write_text('def altered(): pass')
            index=structure_index.build(root,pin)
            rows={f['file']:f['declarations'] for f in index['files']}
            self.assertEqual(rows['src/pkg/db.py'],[{'kind':'class','name':'Store','line':1},
                                                   {'kind':'async_function','name':'Store.read','line':2}])
            self.assertEqual([(e['line'],e['target']) for e in index['imports'] if e['file']=='src/pkg/cli.py'],
                             [(1,'src/pkg/db.py'),(2,'src/pkg/db.py')])
            self.assertFalse({'link.py','broken.py','.aws/private.py'} & set(rows))
            self.assertEqual(index['coverage']['unresolved_imports'],3)
            self.assertEqual(index['coverage']['skipped_files'],1)
            self.assertEqual(index['coverage']['unsupported_files'],1)
            with patch.object(structure_index,'MAX_FILES',1):
                limited=structure_index.build(root,pin)
            self.assertTrue(limited['coverage']['truncated'])
            self.assertLessEqual(limited['coverage']['indexed_files'],1)

    def test_selected_file_uses_only_its_blob_and_resolves_unsampled_imports(self):
        import json
        import sys
        with tempfile.TemporaryDirectory() as root:
            repo=Path(root)
            git=lambda *args:subprocess.check_output(['git','-C',root,*args]).decode().strip()
            git('init','-q')
            (repo/'target.py').write_text('import peer\ndef run(): pass')
            (repo/'peer.py').write_text('class Peer: pass')
            (repo/'.aws').mkdir()
            (repo/'.aws/key.py').write_text('class Private: pass')
            (repo/'alias.py').write_bytes((repo/'.aws/key.py').read_bytes())
            (repo/'odd_alias.py').write_text('def private_alias(): pass')
            (repo/'note.md').write_text('note')
            (repo/'bad.py').write_text('def ?')
            os.symlink('target.py',repo/'link.py')
            git('add','.')
            odd_oid=git('rev-parse',':odd_alias.py')
            subprocess.run(['git','-C',root,'update-index','-z','--index-info'],check=True,
                           input=b'100644 '+odd_oid.encode()+b'\t.aws/invalid-\xff.py\0')
            git('-c','user.name=Test','-c','user.email=test@example.invalid','commit','-qm','original')
            pin=git('rev-parse','HEAD')
            with patch.object(structure_index,'_blobs',wraps=structure_index._blobs) as blobs:
                result=structure_index.build(root,pin,only_file='target.py')
                self.assertEqual([file for file,_ in blobs.call_args.args[2]],['target.py'])
            self.assertEqual(result['imports'],[{'file':'target.py','target':'peer.py','line':1}])
            self.assertEqual(result['declarations'],[{'name':'run','kind':'function','line':2}])
            for file,expected in [('note.md','unsupported'),('bad.py','unparsed'),('link.py','unavailable'),
                                  ('.aws/key.py','unavailable'),('alias.py','unavailable'),('odd_alias.py','unavailable'),('unknown.py','unavailable')]:
                self.assertEqual(structure_index.build(root,pin,only_file=file)['status'],expected)
            with patch.object(structure_index,'MAX_FILE_BYTES',2):
                self.assertEqual(structure_index.build(root,pin,only_file='target.py')['status'],'too_large')
            with self.assertRaises(ValueError):
                structure_index.build(root,pin,only_file='../target.py')
            folder=repo/'maps'/'demo'
            folder.mkdir(parents=True)
            (folder/'dev.json').write_text(json.dumps({'repo':root,'ref':'HEAD','commit':pin,'structure_index':{'commit':pin}}))
            cmd=[sys.executable,str(Path(structure_index.__file__).with_name('project.py')),'file-structure','demo','--','','dev']
            env={**os.environ,'WHERE_WERE_WE_ROOT':str(folder.parent)}
            self.assertEqual(json.loads(subprocess.check_output(cmd+[pin,'target.py'],env=env)),result)
            (folder/'main.json').write_text(json.dumps({'repo':root,'ref':pin,'commit':pin,'inventory':{'commit':pin}}))
            main_cmd=cmd[:-1]+['main']
            self.assertEqual(json.loads(subprocess.check_output(main_cmd+[pin,'target.py'],env=env)),result)
            git('-c','user.name=Test','-c','user.email=test@example.invalid','commit','--allow-empty','-qm','Advance dev')
            different_branch=subprocess.run(cmd+[pin,'target.py'],env=env,capture_output=True)
            self.assertNotEqual(different_branch.returncode,0)
            self.assertEqual(json.loads(subprocess.check_output(main_cmd+[pin,'target.py'],env=env)),result)
            stale=subprocess.run(cmd+['0'*40,'target.py'],env=env,capture_output=True)
            self.assertNotEqual(stale.returncode,0)
            self.assertIn(b'Code changed',stale.stderr)

    def test_cli_manifests_resolve_only_tracked_local_targets_at_pin(self):
        with tempfile.TemporaryDirectory() as root:
            repo=Path(root)
            git=lambda *args:subprocess.check_output(['git','-C',root,*args]).decode().strip()
            git('init','-q')
            sources={'package.json':'{"bin":{"launch":"./tool","linked":"link","missing":"dist/tool"}}',
                     'tool':'#!/usr/bin/env node', 'nested/package.json':'{"name":"@org/other","bin":"../tool"}',
                     'pyproject.toml':'[project.scripts]\nstart = "app:run"\nbad = "dup:run"\n',
                     'src/app.py':'def run(): pass','dup.py':'','src/dup.py':''}
            for file,content in sources.items():
                path=repo/file
                path.parent.mkdir(parents=True,exist_ok=True)
                path.write_text(content)
            os.symlink('tool',repo/'link')
            git('add','.')
            git('-c','user.name=Test','-c','user.email=test@example.invalid','commit','-qm','commands')
            pin=git('rev-parse','HEAD')
            (repo/'package.json').write_text('{}')
            result=structure_index.build(root,pin)
            by_command={r['command']:r for r in result['cli_entries']}
            self.assertEqual(set(by_command),{'launch','start'})
            self.assertEqual(by_command['launch'],dict(command='launch',kind='npm_bin',file='package.json',target='tool',line=1))
            self.assertEqual(by_command['start'],dict(command='start',kind='python_script',file='pyproject.toml',
                                                       target='src/app.py',symbol='run',line=2,target_line=1))
            self.assertEqual(result['coverage']['cli_manifests_read'],3)
            private=structure_index.build(root,pin,excluded=lambda file:file=='tool')
            self.assertEqual([r['command'] for r in private['cli_entries']],['start'])

    def test_bounded_selection_visits_sibling_code_and_keeps_auxiliary_evidence(self):
        paths=['aaa/examples/case'+str(i)+'.py' for i in range(30)]
        paths+=['services/a/worker'+str(i)+'.py' for i in range(30)]
        paths+=['services/z/entry.py','web/ui/index.py']
        entries=[(path,(b'blob',10)) for path in paths]
        sample=[p for p,_ in structure_index._bounded_order(entries)]
        self.assertEqual(sample,[p for p,_ in structure_index._bounded_order(entries[::-1])])
        self.assertEqual(set(sample),set(paths))
        self.assertEqual(len(sample),len(paths))
        self.assertIn('services/z/entry.py',sample[:7])
        self.assertIn('web/ui/index.py',sample[:7])
        self.assertTrue(any('/examples/' in path for path in sample[:8]))

    def test_standalone_commonjs_cli_connects_explicit_local_modules(self):
        with tempfile.TemporaryDirectory() as root:
            repo=Path(root)
            git=lambda *args:subprocess.check_output(['git','-C',root,*args]).decode().strip()
            git('init','-q')
            (repo/'cli.cjs').write_text("#!/usr/bin/env node\nconst worker=require('./worker.cjs');\nworker.run();")
            (repo/'worker.cjs').write_text('function run(){};module.exports={run};')
            (repo/'shadow.cjs').write_text("function other({require}){return require('./worker.cjs')} ")
            (repo/'missing.cjs').write_text("require('./absent.cjs');require('third-party');")
            git('add','.');git('-c','user.name=Test','-c','user.email=test@example.invalid','commit','-qm','Add CLI')
            index=structure_index.build(root,git('rev-parse','HEAD'))
            self.assertEqual(index['service_flow']['connections'],[])
            self.assertEqual(index['imports'],[{'file':'cli.cjs','line':2,'target':'worker.cjs'}])
            self.assertEqual(index['coverage']['unresolved_imports'],2)
            worker=next(row for row in index['files'] if row['file']=='worker.cjs')
            self.assertEqual(worker['declarations'],[{'name':'run','kind':'function','line':1}])

    def test_typescript_tsx_and_javascript_static_structure(self):
        with tempfile.TemporaryDirectory() as root:
            repo=Path(root)
            git=lambda *args:subprocess.check_output(['git','-C',root,*args]).decode().strip()
            git('init','-q')
            sources={
                'src/main.tsx':"""import {run} from './task';
export {shared} from './shared.js';
import {ambiguous} from './choice';
import external from 'external';
// import unused from './fake';
const text = "export function fake() {}";
export function View() { return <div/> }
export const persist = async () => run();
""",
                'src/task.ts':"export interface Item { name: string }\nexport async function run() {}\n",
                'src/choice.ts':'export type X = string;',
                'src/choice.js':'export function noop() {}',
                'src/shared.js':'export class Shared { save() {} }',
                'src/bad.ts':'const = ;',
            }
            for name,txt in sources.items():
                path=repo/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(txt)
            git('add','.');git('-c','user.name=Test','-c','user.email=test@example.invalid','commit','-qm','Pinned modules')
            pin=git('rev-parse','HEAD')
            index=structure_index.build(root,pin)
            if index['coverage']['unavailable_languages']:
                self.skipTest('Install the packaged JavaScript and TypeScript grammars to check parsing')
            files={f['file']:f for f in index['files']}
            self.assertEqual(files['src/main.tsx']['language'],'typescript')
            self.assertEqual([(x['kind'],x['name'],x['line']) for x in files['src/main.tsx']['declarations']],
                             [('function','View',7),('async_function','persist',8)])
            self.assertEqual(files['src/shared.js']['declarations'][-1]['name'],'Shared.save')
            self.assertEqual(files['src/task.ts']['declarations'][0]['kind'],'interface')
            self.assertEqual(index['imports'],[{'file':'src/main.tsx','line':1,'target':'src/task.ts'},
                                               {'file':'src/main.tsx','line':2,'target':'src/shared.js'}])
            self.assertEqual(index['coverage']['unresolved_imports'],2)
            self.assertEqual(index['coverage']['languages']['typescript'],{'candidate_files':4,'indexed_files':3})
