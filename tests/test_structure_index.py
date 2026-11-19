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
