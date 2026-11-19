"""Two configured refs with one immutable commit share extraction but keep independent history."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class RefreshReuse(unittest.TestCase):
    def test_shared_pin_preserves_each_ref_and_previous_map(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            repo=root/'repo'
            repo.mkdir()
            def git(*args):
                return subprocess.check_output(['git','-C',repo,*args],text=True).strip()
            git('init','-q','-b','main')
            git('config','user.name','Fixture')
            git('config','user.email','fixture@example.invalid')
            (repo/'source.py').write_text('def first(): pass\n')
            git('add','source.py')
            git('commit','-qm','first')
            git('branch','dev')
            maps=root/'maps'
            home=maps/'demo'
            home.mkdir(parents=True)
            env={**os.environ,'WHERE_WERE_WE_ROOT':str(maps),'WHERE_WERE_WE_COLLECTION_STAGE':'1',
                 'WHERE_WERE_WE_REMOTE_STATUS':'not_configured','WHERE_WERE_WE_REFS':json.dumps({'dev':'dev','main':'main'})}
            def refresh():
                script=Path(__file__).resolve().parents[1]/'refresh.py'
                return subprocess.check_output([sys.executable,'-I','-B',script,'demo',repo],text=True,env=env)
            def data(name):
                return json.loads((home/(name+'.json')).read_text())
            self.assertIn('main: reused basic map',refresh())
            old={role:data(role) for role in ('dev','main')}
            self.assertEqual(old['dev']['ref'],'dev')
            self.assertEqual(old['main']['ref'],'main')
            self.assertEqual({**old['dev'],'ref':'main'},old['main'])
            (repo/'source.py').write_text('def second(): pass\n')
            git('commit','-qam','second')
            git('branch','-f','dev','main')
            self.assertIn('main: reused basic map',refresh())
            for role in old:
                self.assertEqual(data(role+'.prev'),old[role])
                self.assertNotEqual(data(role)['commit'],old[role]['commit'])
                self.assertEqual(data(role)['ref'],role)
