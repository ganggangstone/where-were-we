"""Two configured refs with one immutable commit share extraction but keep independent history."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import os;os.environ.pop('WHERE_WERE_WE_SETTINGS',None)  # fixtures isolate settings through mapcore.ROOT; an inherited settings file would bypass that and be shared


class RefreshReuse(unittest.TestCase):
    def test_no_routes_does_not_read_test_sources_and_retains_stale_records(self):
        import mapcore
        def source(file):
            self.fail('No source should be needed when no route can match')
        rules={'calls':['client.<method>("<path>")'],'files':['test_*.py'],
               'records':[{'file':'test_item.py','route':'app.py::missing','line':1,'quote':'sample'}]}
        hits,stale=mapcore.backend_test_links([],['test_item.py'],source,rules)
        self.assertEqual((hits,stale),({},1))

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

    def test_comparison_reuse_checks_pinned_pair_extractor_settings_and_branch_labels(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            repo=root/'repo';repo.mkdir()
            def git(*args,day=None):
                env=dict(os.environ)
                if day:
                    env.update(GIT_AUTHOR_DATE=day,GIT_COMMITTER_DATE=day)
                subprocess.run(['git','-C',repo,*args],env=env,check=True,capture_output=True)
            git('init','-q','-b','main')
            git('config','user.name','Fixture');git('config','user.email','fixture@example.invalid')
            source=repo/'module.py';source.write_text('def old(): pass\n')
            git('add','.');git('commit','-qm','old',day='2024-01-01T12:00:00Z')
            source.write_text('def current(): pass\n')
            git('commit','-qam','new',day='2024-01-03T12:00:00Z')
            maps=root/'maps';home=maps/'demo';home.mkdir(parents=True)
            (maps/'settings.json').write_text(json.dumps({'since':'time','since_time':'2024-01-02T00:00:00Z'}))
            env={**os.environ,'WHERE_WERE_WE_ROOT':str(maps),'WHERE_WERE_WE_COLLECTION_STAGE':'1',
                 'WHERE_WERE_WE_REMOTE_STATUS':'not_configured','WHERE_WERE_WE_REFS':json.dumps({'dev':'main','main':None})}
            script=Path(__file__).resolve().parents[1]/'refresh.py'
            def refresh():
                subprocess.run([sys.executable,'-I','-B',script,'demo',repo],check=True,capture_output=True,env=env)
                return json.loads((home/'changes.json').read_text())['last_result']
            first=refresh()
            path=home/'dev.json'
            saved=json.loads(path.read_text());saved['analysis']={'source':'ai'};path.write_text(json.dumps(saved))
            again=refresh()
            self.assertEqual(first['evidence']['structure'],again['evidence']['structure'])
            comparison=home/'dev.current-basic.json'
            self.assertFalse(comparison.exists())
            for name,value in [('groups',{'names':{'/':'Home'}}),('tests',{'files':['spec*.py']})]:
                (home/(name+'.json')).write_text(json.dumps(value))
                updated=refresh()
                self.assertNotEqual(updated['comparison_keys'],again['comparison_keys'])
                self.assertTrue(comparison.exists())
                comparison.unlink()
                again=updated
            source.write_text('def latest(): pass\n')
            git('commit','-qam','advance',day='2024-01-04T12:00:00Z')
            self.assertNotEqual(refresh()['comparison_keys'],again['comparison_keys'])
            self.assertTrue(comparison.exists())
