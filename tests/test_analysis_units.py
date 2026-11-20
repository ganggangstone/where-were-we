"""Full-code analysis by units: AI-free catalog, saved-as-you-go results, resume and stale handling. Fake executors only."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parent))
import analysis_run
import analysis_units
import structure_index
from test_analysis_run import AnalysisRun as _Fixture
_setup,_git,_raw,_prepare,_map_fake=_Fixture.setUp,_Fixture.git,_Fixture.raw,_Fixture.prepare,_Fixture.source_fake
_plain_fake=_Fixture.fake
_EV,_SYSTEM,_GROUPS=_Fixture.EV,_Fixture.SYSTEM,_Fixture.GROUPS
del _Fixture


def tracked(*names,size=100):return {name:size for name in names}


class Catalog(unittest.TestCase):
    exclusion=staticmethod(lambda file,size:'secret' if file.startswith('.env') else 'binary' if file.endswith('.png') else 'generated' if file.endswith('.lock') else 'large' if size>300_000 else None)

    def test_every_tracked_file_is_in_a_unit_or_counted_under_one_reason(self):
        files=[{'file':f'lib/{i}.py','declarations':[{'name':'f','kind':'function','line':1}]} for i in range(14)]
        files+=[{'file':'cmd/main.go','declarations':[]},{'file':'packages/a/src/a.ts','declarations':[]},{'file':'app/page.tsx','declarations':[]},
                {'file':'server/api.py','declarations':[]},{'file':'tools/run.py','declarations':[]}]
        index={'files':files,'imports':[{'file':'app/page.tsx','target':'server/api.py','line':1}],
               'workspace_packages':[{'name':'pkg-a','file':'packages/a/package.json'}],
               'cli_entries':[{'command':'tool sub','file':'cmd/main.go','target':'cmd/main.go'}],
               'service_flow':{'feature_groups':[],'connections':[],'registered_routes':[{'server':{'file':'server/api.py'}}],
                               'registered_route_groups':[{'resource':'/api/x','registered_route_indexes':[0]}]},
               'coverage':{'candidate_files':len(files)+3,'skipped_files':1,'truncated':True}}
        names=[f['file'] for f in files]+['.env','logo.png','data.json','huge.py','extra.md','uv.lock']
        sizes={n:100 for n in names};sizes['huge.py']=900_000
        built=analysis_units.catalog(index,sizes,self.exclusion,
            screens=[{'file':'app/page.tsx','path':'/','heading':'Home'},{'file':'app/page.tsx','path':'/x','redirect':True}],
            programs=[{'id':'server','name':'Server','code':['server']},{'id':'pkg','name':'Pkg','code':['packages/a']}])
        kinds={}
        for unit in built['units']:kinds.setdefault(unit['kind'],[]).append(unit['name'])
        self.assertEqual(kinds['route'],['/api/x']);self.assertEqual(kinds['package'],['pkg-a']);self.assertEqual(kinds['cli'],['tool'])
        self.assertEqual(kinds['screen'],['Home']);self.assertEqual(kinds['program'],['Server'])  # the package already holds its own program
        self.assertTrue(all(len(u['files'])<=analysis_units.FOLDER_MAX_FILES for u in built['units'] if u['kind']=='folder'))
        coverage=built['coverage']
        # Documents, data and files past the index limit are plain files inside folder units, not silent gaps.
        self.assertEqual(coverage['in_units'],coverage['indexed']+coverage['plain'])
        self.assertEqual(coverage['plain'],2)
        self.assertEqual(coverage['excluded'],{'secret':1,'binary':1,'large':1,'generated':1})
        self.assertEqual(coverage['in_units']+sum(coverage['excluded'].values()),coverage['tracked'])
        plain={f for u in built['units'] for f in u['files']}
        self.assertTrue({'data.json','extra.md'}<=plain and not {'.env','logo.png','huge.py','uv.lock'}&plain)
        self.assertTrue(coverage['truncated'])
        self.assertEqual(coverage['tracked'],len(names))
        self.assertTrue(all(u['digest'] for u in built['units']))

    def test_large_folders_split_into_bounded_units_without_losing_files(self):
        files=[{'file':f'src/mod{i%3}/f{i}.py','declarations':[]} for i in range(60)]
        built=analysis_units.catalog({'files':files,'imports':[]},tracked(*[f['file'] for f in files]),self.exclusion)
        members=[f for u in built['units'] for f in u['files']]
        self.assertEqual(sorted(members),sorted(f['file'] for f in files))
        self.assertTrue(all(u['file_count']<=analysis_units.FOLDER_MAX_FILES or '/' not in u['name'][4:] for u in built['units']))


class FullRun(unittest.TestCase):
    git=_git
    raw=_raw
    prepare=_prepare
    map_fake=_map_fake
    fake=_plain_fake  # the fixture's own fallback for non-batched map tasks
    EV,SYSTEM,GROUPS=_EV,_SYSTEM,_GROUPS
    PATHS=('/orders','/reports','/users')

    def setUp(self):
        _setup(self)
        (self.repo/'ui.ts').write_text('\n'.join(f"export function {p[1:]}(){{return fetch('{p}')}}" for p in self.PATHS))
        (self.repo/'api.py').write_text('from fastapi import FastAPI\napp=FastAPI()\n'+'\n'.join(f"@app.get('{p}')\ndef {p[1:]}():pass" for p in self.PATHS))
        for folder in ('lib','tools'):
            (self.repo/folder).mkdir()
            for i in range(3):(self.repo/folder/f'm{i}.py').write_text(f'def {folder}_{i}():\n    return {i}\n')
        (self.repo/'.env').write_text('TOKEN=secret\n');(self.repo/'logo.png').write_bytes(b'\x89PNG')
        self.git('add','-A');self.git('commit','-qm','Full analysis fixture')
        self.publish_index()

    def publish_index(self):
        repo=analysis_run.store.config('demo')['repositories'][0];raw=self.raw()
        raw['dev']['structure_index']=structure_index.build(str(self.repo),self.git('rev-parse','HEAD').strip())
        raw['dev']['commit']=self.git('rev-parse','HEAD').strip()
        analysis_run.store.publish('demo','service',raw,{'fingerprint':analysis_run.store.fingerprint(repo)})

    def board(self):return analysis_run.unit_board('demo','service','dev','en')
    def states(self,board=None):
        board=board or self.board()
        return {row[0]:row[4] for row in board['repositories'][0]['units']}

    def executor(self,calls,bad=(),after=None):
        def items(packet):
            if packet.get('resource') in bad:return [{'name':'x','description':'y','ref':999999}]
            line=packet['sources'][0]['lines'][0]
            return [{'name':'Feature','role':'Role','description':'Does something','ref':line['ref']}]
        def fake(prompt,**kwargs):
            packet=json.loads(prompt.split('\n',1)[1]);calls.append(packet)
            if after:after(len(calls))
            if {'screens','nodes','groups'}&set(packet.get('schema',{})):return self.map_fake(prompt,**kwargs)  # map, structure, screen groups
            if 'resources' in packet:return {'results':[{'resource':p['resource'],'items':items(p)} for p in packet['resources']]}
            return {'items':items(packet) if packet.get('resource') else []}
        return fake

    def intent(self,board=None):return {'task':'full','targets':[],'max_calls':(board or self.board())['calls']}

    def test_board_is_local_and_the_call_cap_must_be_confirmed(self):
        board=self.board()
        ids=self.states(board)
        self.assertTrue(set(ids.values())=={'pending'})
        self.assertIn('route:/orders',ids);self.assertTrue(any(i.startswith('folder:lib') for i in ids))
        coverage=board['repositories'][0]['coverage']
        self.assertEqual(coverage['excluded']['secret'],1);self.assertEqual(coverage['excluded']['binary'],1)
        with self.assertRaisesRegex(ValueError,'maximum call count'):self.prepare(intent={**self.intent(board),'max_calls':board['calls']-1})
        self.assertEqual(self.prepare(intent=self.intent(board))['state'],'preparing')

    def test_overview_first_then_units_are_saved_with_isolated_failures_and_resume(self):
        board=self.board();job=self.prepare(intent=self.intent(board))
        calls=[];bad='folder:lib'
        done=analysis_run.run(job['id'],self.executor(calls,bad=(bad,)))
        self.assertEqual(done['state'],'completed',done.get('error'))
        self.assertNotIn('resource',calls[0]);self.assertNotIn('resources',calls[0])  # the first overview comes first
        self.assertLessEqual(len(calls),board['calls']*2)
        states=self.states(analysis_run.unit_board('demo','service','dev','en'))
        self.assertEqual(states[bad],'failed')
        self.assertTrue(all(state=='saved' for key,state in states.items() if key!=bad),states)
        self.assertEqual([f['attempts'] for f in done['unit_failures']],[analysis_run.UNIT_ATTEMPTS])
        saved=done['unit_overviews']['service']
        self.assertTrue(all(unit['version']==analysis_run.SCOPED_OVERVIEW_VERSION and unit['unit']['kind']!='route' for unit in saved.values()))
        self.assertEqual(next(iter(saved.values()))['items'][0]['role'],'Role')
        # A new run reuses every saved unit and sends only the one that failed.
        again=[];second=self.prepare(intent=self.intent())
        self.assertEqual([t.get('target') for t in second['tasks']],[bad]);self.assertEqual(second['unit_estimate']['calls'],2)  # one retry plus the allowance for a repeat
        finished=analysis_run.run(second['id'],self.executor(again))
        self.assertEqual(finished['state'],'completed')
        self.assertEqual(len(again),1);self.assertEqual(again[0]['resource'],bad)
        self.assertEqual(set(self.states().values()),{'saved'})
        nothing=self.prepare(intent={**self.intent(),'max_calls':0})
        self.assertEqual(analysis_run.run(nothing['id'],lambda *a,**k:self.fail('unexpected call'))['state'],'completed')

    def legacy(self,mutate=None):
        """A project saved before structure indexes existed: only dev.json (repo and ref), no project.json."""
        bundle=copy.deepcopy(self.raw()['dev']);bundle.pop('structure_index',None)
        if mutate:mutate(bundle)
        home=analysis_run.store.home('legacy');home.mkdir(parents=True,exist_ok=True)
        (home/'dev.json').write_text(json.dumps(bundle))
        return home

    def tree(self,home):
        return {str(p.relative_to(home)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(home.rglob('*')) if p.is_file() and p.name!='.project.lock'}  # an empty lock file is not data

    def test_legacy_project_without_a_saved_index_gets_units_without_refresh_ai_or_data_changes(self):
        home=self.legacy();before=self.tree(home)
        board=analysis_run.unit_board('legacy','','dev','en')
        self.assertGreater(board['calls'],0);self.assertEqual(board['totals']['units'],board['totals']['pending'])
        self.assertIn('route:/orders',{row[0] for row in board['repositories'][0]['units']})
        self.assertEqual(self.tree(home),before)  # the saved project data is byte-identical
        cache=list((Path(analysis_run.mapcore.ROOT)/'.analysis-cache').glob('index-*.json'))
        self.assertEqual(len(cache),1)
        # Another process reads the cache instead of rebuilding.
        analysis_run._INDEXES.clear()
        original=structure_index.build
        structure_index.build=lambda *a,**k:self.fail('rebuilt')
        self.addCleanup(setattr,structure_index,'build',original)
        again=analysis_run.unit_board('legacy','','dev','en')
        self.assertEqual(again['totals'],board['totals'])

    def test_index_from_an_older_version_or_commit_is_replaced_in_memory_only(self):
        for name,change in (('version',lambda ix:ix.update(version=ix['version']-1)),('commit',lambda ix:ix.update(commit='0'*40))):
            raw=self.raw();change(raw['dev']['structure_index'])
            repo=analysis_run.store.config('demo')['repositories'][0]
            analysis_run.store.publish('demo','service',raw,{'fingerprint':analysis_run.store.fingerprint(repo)})
            saved=json.dumps(self.raw()['dev']['structure_index'],sort_keys=True)
            analysis_run._INDEXES.clear()
            board=self.board()
            self.assertGreater(board['calls'],0,name);self.assertIn('route:/orders',self.states(board),name)
            self.assertEqual(json.dumps(self.raw()['dev']['structure_index'],sort_keys=True),saved,name)  # not rewritten

    def test_legacy_project_full_run_starts_with_the_overview_then_saves_every_unit(self):
        self.legacy()
        board=analysis_run.unit_board('legacy','','dev','en')
        job=analysis_run.prepare('legacy',lang='en',intent={'task':'full','targets':[],'max_calls':board['calls']})
        self.assertEqual(job['state'],'preparing')
        calls=[]
        done=analysis_run.run(job['id'],self.executor(calls))
        self.assertEqual(done['state'],'completed',done.get('error'))
        self.assertNotIn('resource',calls[0]);self.assertNotIn('resources',calls[0])  # first overview, then units
        states={row[0]:row[4] for row in analysis_run.unit_board('legacy','','dev','en')['repositories'][0]['units']}
        self.assertTrue(all(state=='saved' for state in states.values()),states)

    def test_board_reads_pins_without_the_whole_tree_and_reuses_cached_reads_across_processes(self):
        import ai_extract
        legacy=self.legacy();del legacy
        ai_extract._BASIC.clear();analysis_run._INDEXES.clear()
        original=ai_extract.basic_catalog
        ai_extract.basic_catalog=lambda *a,**k:self.fail('the board must not read the whole tree for its pins')
        self.addCleanup(setattr,ai_extract,'basic_catalog',original)
        board=analysis_run.unit_board('legacy','','dev','en')
        self.assertGreater(board['calls'],0)
        quick=analysis_run.unit_quick('legacy','','dev','en')
        self.assertTrue(quick['quick']);row=quick['repositories'][0]
        self.assertEqual(row['commit'],self.git('rev-parse','HEAD').strip());self.assertEqual(row['excluded'].get('secret'),1);self.assertGreater(row['tracked'],10)
        # A disk-cached collector result serves another process without running the collector again.
        ai_extract.basic_catalog=original;ai_extract._BASIC.clear()
        repo,_,_,head=ai_extract.context('legacy','','dev')
        first=ai_extract.basic_catalog(repo['path'],head,repo['layout'])
        ai_extract._BASIC.clear()
        real=ai_extract.subprocess.run
        ai_extract.subprocess.run=lambda *a,**k:self.fail('collector ran again')
        self.addCleanup(setattr,ai_extract.subprocess,'run',real)
        self.assertEqual(ai_extract.basic_catalog(repo['path'],head,repo['layout'])['screens'],first['screens'])

    def test_source_profile_matches_what_a_map_batch_really_carries(self):
        repo=str(self.repo);head=self.git('rev-parse','HEAD').strip()
        profile=analysis_run._source_profile(repo,head)
        self.assertNotIn('.env',profile);self.assertNotIn('logo.png',profile)  # credentials and binaries never reach a batch
        snapshots=analysis_run.export_source(repo,head)
        header,units=analysis_run._units({'snapshots':snapshots})
        compact={**header,'source_line_format':'numbered_lines entries are [original one-based line, literal text, optional original character offset].'}
        empty=len(analysis_run._encoded(analysis_run._batch_payload(compact,[],'a'*64)).encode())
        real=len(analysis_run._encoded(analysis_run._batch_payload(compact,units,'a'*64)).encode())-empty
        estimate=sum(profile.values())
        self.assertLessEqual(estimate,real*1.15);self.assertGreaterEqual(estimate,real*0.7)  # tiny files carry more wrapper bytes; on a 14.8k-file repo the estimate was 3% above the real 101.7MB

    def test_map_estimate_follows_the_saved_map_whole_commit_first_then_only_the_changes(self):
        self.large_map()
        whole=self.board()
        done=analysis_run.run(self.prepare(intent={**self.intent(whole),'max_calls':whole['calls']+60})['id'],self.executor([]))
        self.assertEqual(done['state'],'completed',done.get('error'))
        (self.repo/'lib'/'m0.py').write_text('def lib_0():\n    return 100\n');self.git('add','-A');self.git('commit','-qm','Small change')
        analysis_run._INDEXES.clear()
        patched=self.board()
        self.assertEqual(patched['repositories'][0]['commit'],self.git('rev-parse','HEAD').strip())
        self.assertGreater(whole['map_calls'],3)  # the 6500-line padding file alone fills several batches
        self.assertLess(patched['map_calls'],whole['map_calls'])  # only the changes and the files the saved map cites are read again
        repo,raw,_,head=analysis_run.ai_extract.context('demo','service','dev')
        mode=analysis_run.ai_extract.map_mode(repo['path'],raw['dev'],'en',analysis_run.store.fingerprint(repo),head)
        self.assertEqual(mode[0],'patch')

    def test_call_limit_parts_add_up_to_the_confirmed_cap(self):
        board=self.board();parts=board['calls_parts']
        self.assertEqual(sum(parts.values()),board['calls']);self.assertEqual(parts['retry'],-(-parts['units']//2))
        self.assertEqual(parts['map'],board['map_calls'])

    def test_cancel_keeps_saved_units_and_retry_only_asks_for_the_rest(self):
        job=self.prepare(intent=self.intent());calls=[]
        def stop(count):
            if count==3:analysis_run.cancel(job['id'])
        done=analysis_run.run(job['id'],self.executor(calls,after=stop))
        self.assertEqual(done['state'],'cancelled')
        saved=sum(1 for s in self.states().values() if s=='saved')
        self.assertGreater(saved,0);self.assertLess(saved,len(self.states()))
        retry=analysis_run.retry(job['id']);rest=[]
        self.assertEqual(analysis_run.run(retry['id'],self.executor(rest))['state'],'completed')
        self.assertEqual(set(self.states().values()),{'saved'})
        self.assertLess(len(rest),len(calls)+len(rest))

    def test_changed_code_marks_only_affected_units_stale_and_keeps_unchanged_ones(self):
        analysis_run.run(self.prepare(intent=self.intent())['id'],self.executor([]))
        (self.repo/'lib/m0.py').write_text('def lib_0():\n    return 42\n')
        self.git('add','-A');self.git('commit','-qm','Change lib');self.publish_index()
        states=self.states()
        self.assertEqual(states['folder:lib'],'stale')
        self.assertEqual(states['folder:tools'],'saved')
        # A path explanation survives a change in files it never cited: its model input is identical.
        self.assertTrue(all(states[f'route:{p}']=='saved' for p in self.PATHS),states)
        calls=[];self.assertTrue(analysis_run.run(self.prepare(intent=self.intent())['id'],self.executor(calls))['state']=='completed')
        self.assertTrue(all('tools' not in json.dumps(p.get('resource') or p.get('resources')) for p in calls))
        self.assertTrue(all('route' not in json.dumps(p.get('resource') or p.get('resources')) for p in calls))
        self.assertEqual(set(self.states().values()),{'saved'})
        # Changing a cited file invalidates exactly the paths that cite it.
        (self.repo/'api.py').write_text((self.repo/'api.py').read_text()+'\n# changed\n')
        self.git('add','-A');self.git('commit','-qm','Change api');self.publish_index()
        states=self.states()
        self.assertTrue(all(states[f'route:{p}']=='stale' for p in self.PATHS),states)
        self.assertEqual(states['folder:lib'],'saved')

    def large_map(self):
        (self.repo/'zz_padding.txt').write_text('unique row for analysis\n'*6500)
        self.git('add','-A');self.git('commit','-qm','Large map input');self.publish_index()

    def batches(self,calls):return sum(1 for c in calls if 'batch' in c)

    def test_map_progress_is_saved_per_input_piece_but_published_only_when_complete(self):
        self.large_map();baseline=self.raw()
        board=self.board();self.assertEqual(self.states(board)['task:analysis'],'pending')
        job=self.prepare(intent={**self.intent(board),'max_calls':board['calls']+60});calls=[]
        def stop(_):
            saved=(analysis_run.read(job['id']).get('partial_results',{}).get('service') or {}).get('analysis') or {}
            if saved.get('count') and saved['covered']<saved['total']:analysis_run.cancel(job['id'])  # stop once a finding is saved and pieces remain
        stopped=analysis_run.run(job['id'],self.executor(calls,after=stop))
        self.assertEqual(stopped['state'],'cancelled')
        part=stopped['partial_results']['service']['analysis']
        self.assertEqual(part['state'],'partial');self.assertGreater(part['covered'],0);self.assertLess(part['covered'],part['total'])
        self.assertTrue(part['items'] and all(i.get('file') and i.get('line') and i.get('quote') for i in part['items'] if i['kind'] in ('screen','request')))
        self.assertEqual(self.raw(),baseline)  # the saved map is untouched until every input piece is covered
        states=self.states()
        self.assertEqual(states['task:analysis'],'partial');self.assertEqual(states['task:system'],'pending')
        row=next(r for r in self.board()['repositories'][0]['units'] if r[0]=='task:analysis')
        self.assertEqual(row[5],f"{part['covered']}/{part['total']}")
        shown=analysis_run.unit_result('demo','service','dev','en','task:analysis')
        self.assertEqual(shown['state'],'partial');self.assertEqual(shown['items'],part['items'])
        again=[];done=analysis_run.run(analysis_run.retry(job['id'])['id'],self.executor(again))
        self.assertEqual(done['state'],'completed',done.get('error'))
        self.assertEqual(set(self.states().values()),{'saved'})
        self.assertEqual(done['partial_results']['service']['analysis']['state'],'published')
        self.assertEqual([r['path'] for r in self.raw()['dev']['backend_routes']],['/items'])
        self.assertIsNone(analysis_run.unit_result('demo','service','dev','en','task:analysis'))

    def test_call_limit_is_enforced_and_never_reported_as_complete(self):
        self.large_map()
        from unittest.mock import patch
        with patch.object(analysis_run,'MAP_USABLE',10**9):  # an estimate far below what the batches really need
            board=self.board();job=self.prepare(intent=self.intent(board))
        calls=[]
        done=analysis_run.run(job['id'],self.executor(calls))
        self.assertEqual(done['state'],'failed');self.assertEqual(done['error']['code'],'call_limit')
        self.assertEqual(len(calls),board['calls'])  # exactly the confirmed maximum was spent
        self.assertNotEqual(self.states()['task:analysis'],'saved')
        self.assertTrue(done['partial_results']['service']['analysis']['covered']>0)
        # The unit explanations saved before the map started stay saved.
        self.assertTrue(all(v=='saved' for k,v in self.states().items() if k.startswith(('route:','folder:'))))

    def test_units_discovered_by_the_saved_map_and_structure_are_analyzed_too(self):
        self.assertNotIn('program:api',self.states())
        done=analysis_run.run(self.prepare(intent=self.intent())['id'],self.executor([]))
        self.assertEqual(done['state'],'completed',done.get('error'))
        self.assertTrue(done['catalog_refreshed'])
        states=self.states();self.assertEqual(states['program:api'],'saved');self.assertEqual(set(states.values()),{'saved'})

    def test_saved_unit_can_be_read_and_old_code_is_flagged(self):
        analysis_run.run(self.prepare(intent=self.intent())['id'],self.executor([]))
        unit=analysis_run.unit_result('demo','service','dev','en','folder:tools')
        self.assertEqual(unit['unit']['name'],'tools');self.assertNotIn('stale',unit)
        (self.repo/'tools/m0.py').write_text('def tools_0():\n    return 9\n')
        self.git('add','-A');self.git('commit','-qm','Change tools');self.publish_index()
        self.assertTrue(analysis_run.unit_result('demo','service','dev','en','folder:tools')['stale'])

    def test_unit_without_eligible_source_is_skipped_not_failed(self):
        (self.repo/'blank').mkdir();(self.repo/'blank/only.py').write_text('x\n')
        self.git('add','-A');self.git('commit','-qm','Tiny file');self.publish_index()
        calls=[];done=analysis_run.run(self.prepare(intent=self.intent())['id'],self.executor(calls))
        self.assertEqual(done['state'],'completed',done.get('error'))
        states=self.states()
        self.assertEqual(states['folder:blank'],'unavailable')
        self.assertEqual({v for k,v in states.items() if k!='folder:blank'},{'saved'})
        # The skipped unit costs no model call, and a later run does not report it as a failure.
        self.assertEqual(self.prepare(intent=self.intent())['state'],'preparing')


class RepositoryTypes(unittest.TestCase):
    """Units over differently shaped codebases: every tracked file is in a unit or under one exclusion reason."""
    FILES={
        'web app':{'api/main.py':'from fastapi import FastAPI\napp=FastAPI()\n@app.get("/items")\ndef items():pass\n',
                   'web/app.ts':'export function load(){return fetch("/items")}\n','README.md':'# Shop\nOrders and items web shop\n',
                   'docker-compose.yml':'services:\n  api:\n    build: ./api\n','.env':'TOKEN=secret\n','logo.png':'\x89PNG','uv.lock':'version = 1\n'*5},
        'node cli':{'package.json':'{"name":"tool","version":"1.0.0","bin":{"tool":"cli.js"}}\n','cli.js':'#!/usr/bin/env node\nconsole.log("tool");\n',
                    'docs/usage.md':'# Usage\nRun the tool with an argument.\n','LICENSE':'MIT License text for the tool\n'},
        'workspace monorepo':{'package.json':'{"name":"root","private":true,"workspaces":["packages/*"]}\n',
                              'packages/a/package.json':'{"name":"pkg-a","version":"1.0.0"}\n','packages/a/index.js':'module.exports=function a(){return 1}\n',
                              'packages/b/package.json':'{"name":"pkg-b","version":"1.0.0","dependencies":{"pkg-a":"1.0.0"}}\n','packages/b/index.js':'const a=require("pkg-a");module.exports=a;\n'},
        'python library':{'pyproject.toml':'[project]\nname = "lib"\n','src/lib/__init__.py':'from .core import run\n','src/lib/core.py':'def run():\n    return 1\n',
                          'docs/index.md':'# Library docs\nHow to call run().\n','tests/test_core.py':'from lib import run\ndef test_run():\n    assert run()==1\n'},
        'documents only':{'README.md':'# Notes\nPlain notes for the team.\n','docs/a.md':'# A\nFirst document page.\n','docs/b.txt':'Second document page text.\n'}}

    def build(self,name):
        import subprocess,tempfile
        base=Path(tempfile.mkdtemp());self.addCleanup(lambda:__import__('shutil').rmtree(base,ignore_errors=True))
        repo=base/'repo';repo.mkdir()
        for file,text in self.FILES[name].items():
            target=repo/file;target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(text.encode('latin-1') if file.endswith('.png') else text.encode())
        run=lambda *a:subprocess.run(['git','-C',str(repo),*a],check=True,capture_output=True,text=True,env={'GIT_AUTHOR_NAME':'t','GIT_AUTHOR_EMAIL':'t@example.invalid','GIT_COMMITTER_NAME':'t','GIT_COMMITTER_EMAIL':'t@example.invalid','PATH':'/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin','HOME':str(base)}).stdout
        run('init','-q');run('add','-A');run('commit','-qm','fixture')
        return str(repo),run('rev-parse','HEAD').strip()

    def test_every_file_is_in_a_unit_or_counted_under_one_reason_and_each_unit_has_evidence(self):
        kinds_seen={}
        for name in self.FILES:
            repo,head=self.build(name)
            index=structure_index.build(repo,head);tracked=analysis_run._tracked(repo,head)
            built=analysis_units.catalog(index,tracked,analysis_run._exclusion)
            cover=built['coverage'];members=set()
            for unit in built['units']:members.update(unit['files'])
            self.assertEqual(cover['in_units']+sum(cover['excluded'].values()),cover['tracked'],(name,cover))
            eligible={f for f,size in tracked.items() if not analysis_run._exclusion(f,size)}
            self.assertEqual(members,eligible,name)  # small units list all their members
            for unit in built['units']:
                anchors=analysis_run._unit_anchors(index,unit)
                shown=analysis_run.export_source(repo,head,selected={head:set(anchors)})[0]['files']
                self.assertTrue(any(len(row['text'].strip())>=6 for f in shown for row in f['lines']),(name,unit['id']))
                kinds_seen.setdefault(name,set()).add(unit['kind'])
        self.assertIn('route',kinds_seen['web app']);self.assertIn('folder',kinds_seen['web app'])
        self.assertIn('package',kinds_seen['workspace monorepo'])
        self.assertIn('cli',kinds_seen['node cli'])
        self.assertEqual(kinds_seen['documents only'],{'folder'})  # plain files alone still make units
        web=analysis_units.catalog(structure_index.build(*self.build('web app')),analysis_run._tracked(*self.build('web app')),analysis_run._exclusion)
        self.assertEqual(web['coverage']['excluded'],{'binary':1,'generated':1,'secret':1})


if __name__=='__main__':unittest.main()
