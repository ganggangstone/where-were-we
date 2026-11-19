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
