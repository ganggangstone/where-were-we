"""Full-code analysis by units: AI-free catalog, saved-as-you-go results, resume and stale handling. Fake executors only."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
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

    def test_import_edges_between_units_become_links_and_documents_and_tests_become_local_units(self):
        files=[{'file':'app/a.py','declarations':[]},{'file':'core/b.py','declarations':[]},{'file':'core/c.py','declarations':[]}]
        index={'files':files,'imports':[{'file':'app/a.py','target':'core/b.py','line':1},{'file':'app/a.py','target':'core/c.py','line':2}],'coverage':{}}
        names=[f['file'] for f in files]+['docs/a.md','docs/b.md','tests/test_a.py']
        built=analysis_units.catalog(index,tracked(*names),self.exclusion,local=lambda f:f.startswith(('docs/','tests/')))
        self.assertEqual(built['links'],{'folder:app':[['folder:core',2]]})
        local={u['name']:u for u in built['units'] if u.get('reading')=='local'}
        self.assertEqual(set(local),{'docs','tests'});self.assertEqual(local['docs']['id'],'folder:local:docs');self.assertEqual(built['coverage']['local'],3)
        self.assertEqual(built['coverage']['in_units'],len(names))

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

    def board(self):
        """What the UI does: open the board at once, then let the local signal scan finish and read it again."""
        board=analysis_run.unit_board('demo','service','dev','en')
        if board['signals']=='pending':
            analysis_run.unit_signals('demo','service','dev','en');board=analysis_run.unit_board('demo','service','dev','en')
        return board
    def states(self,board=None):
        board=board or self.board()
        return {row[0]:row[4] for row in board['repositories'][0]['units']}

    def executor(self,calls,bad=(),after=None):
        def items(packet):
            if packet.get('resource') in bad:return [{'name':'x','description':'y','ref':999999}]
            line=packet['sources'][0]['lines'][0]
            return [{'name':'Feature','role':'Role','description':'Does something','ref':line[0] if isinstance(line,list) else line['ref']}]
        def fake(prompt,**kwargs):
            packet=json.loads(prompt.split('\n',1)[1]);calls.append(packet)
            if after:after(len(calls))
            if {'screens','nodes','groups'}&set(packet.get('schema',{})):return self.map_fake(prompt,**kwargs)  # map, structure, screen groups
            if 'resources' in packet:return {'results':[{'resource':p['resource'],'items':items(p)} for p in packet['resources']]}
            return {'items':items(packet) if packet.get('resource') else []}
        return fake

    def intent(self,board=None,coverage='signal'):
        board=board or self.board()
        return {'task':'full','targets':[],'max_calls':board['modes'][coverage]['calls'],'coverage':coverage}

    def only(self,*targets,rid='service',**extra):
        """The intent of opening cards: explain exactly these units. The cap is one call per pack plus half again for the retry."""
        n=len(targets);return {'task':'full','targets':[],'coverage':'signal','max_calls':n+-(-n//2),'only':[{'repository':rid,'target':t} for t in targets],**extra}

    def cards(self,*targets,calls=None,bad=(),after=None,project='demo',rid='service'):
        job=analysis_run.prepare(project,lang='en',intent=self.only(*targets,rid=rid))
        return analysis_run.run(job['id'],self.executor([] if calls is None else calls,bad=bad,after=after))

    def unit_ids(self,board=None):return [r[0] for r in (board or self.board())['repositories'][0]['units'] if not r[0].startswith('task:')]

    def explain_everything(self,calls=None):
        """A full analysis, then a card opened for every unit."""
        analysis_run.run(self.prepare(intent=self.intent())['id'],self.executor([]))
        return self.cards(*self.unit_ids(),calls=calls)

    def map_calls(self,board,coverage='signal'):return board['modes'][coverage]['calls_parts']['map']

    def test_board_is_local_and_the_call_cap_must_be_confirmed(self):
        board=self.board()
        ids=self.states(board)
        self.assertTrue(set(ids.values())=={'pending'})
        self.assertIn('route:/orders',ids);self.assertTrue(any(i.startswith('folder:lib') for i in ids))
        coverage=board['repositories'][0]['coverage']
        self.assertEqual(coverage['excluded']['secret'],1);self.assertEqual(coverage['excluded']['binary'],1)
        with self.assertRaisesRegex(ValueError,'maximum call count'):self.prepare(intent={**self.intent(board),'max_calls':board['calls']-1})
        self.assertEqual(self.prepare(intent=self.intent(board))['state'],'preparing')

    def test_structure_batches_that_repeat_unservable_reads_end_early_and_stay_within_the_shown_limit(self):
        """A model that asks every round for pages that do not exist must not use up every read round of every structure batch."""
        board=self.board();calls=[];system=[];inner=self.executor(calls)
        cap=board['modes']['signal']['calls']
        self.assertGreaterEqual(board['modes']['signal']['map_by']['system'],1+analysis_run.EXTRA_PER_BATCH['system'])  # the limit counts the read rounds
        def hollow(prompt,**kwargs):
            answer=inner(prompt,**kwargs);packet=calls[-1]
            if 'nodes' in packet.get('schema',{}):
                if 'batch' in packet:system.append(packet)
                answer['needs']=[{'metadata':['changed_files']},{'file':'does/not/exist.py'},{'metadata':['input','files'],'start':1+200*len(calls)}]  # a page range further out every round
            return answer
        done=analysis_run.run(self.prepare(intent=self.intent(board))['id'],hollow)
        self.assertEqual(done['state'],'completed',done.get('error'))
        batches={p['batch']['id'] for p in system}
        self.assertLess(len(system),(1+analysis_run._batch_extra_cap('system'))*len(batches))  # not every round of every batch
        self.assertTrue(all(len([p for p in system if p['batch']['id']==b])<=3 for b in batches))
        self.assertTrue(any('unavailable_requests' in p['batch'] for p in system))
        self.assertTrue(all(len(p['batch']['unavailable_requests'])<=12 for p in system if 'unavailable_requests' in p['batch']))
        self.assertLessEqual(len(calls),cap)

    def test_a_full_run_asks_no_unit_and_cards_explain_exactly_the_chosen_units_with_isolated_failures(self):
        board=self.board();calls=[]
        done=analysis_run.run(self.prepare(intent=self.intent(board))['id'],self.executor(calls))
        self.assertEqual(done['state'],'completed',done.get('error'))
        self.assertNotIn('resource',calls[0]);self.assertNotIn('resources',calls[0])  # the first overview comes first
        self.assertFalse(any('resource' in c or 'resources' in c for c in calls));self.assertLessEqual(len(calls),board['calls'])
        self.assertEqual({v for k,v in self.states().items() if not k.startswith('task:')},{'pending'})
        bad='folder:lib';asked=[]
        done=self.cards('route:/orders','folder:tools',bad,calls=asked,bad=(bad,))
        self.assertEqual(done['state'],'completed',done.get('error'))
        states=self.states()
        self.assertEqual(states[bad],'failed');self.assertEqual((states['route:/orders'],states['folder:tools']),('saved','saved'))
        self.assertEqual(states['route:/users'],'pending')  # only the chosen units were asked
        self.assertEqual([f['attempts'] for f in done['unit_failures']],[analysis_run.UNIT_ATTEMPTS])
        saved=done['unit_overviews']['service'];self.assertEqual(set(saved),{'folder:tools'})
        self.assertTrue(all(unit['version']==analysis_run.SCOPED_OVERVIEW_VERSION and unit['unit']['kind']!='route' for unit in saved.values()))
        self.assertEqual(next(iter(saved.values()))['items'][0]['role'],'Role')
        # The run's own board and the opened board agree, and a new request sends only the failed one.
        self.assertEqual(analysis_run._run_board(done)['totals'],self.board()['totals'])
        again=[];second=analysis_run.prepare('demo',lang='en',intent=self.only(bad))
        self.assertEqual([t.get('target') for t in second['tasks']],[bad]);self.assertEqual(second['unit_estimate']['calls'],2)  # one ask plus the allowance for a repeat
        finished=analysis_run.run(second['id'],self.executor(again))
        self.assertEqual(finished['state'],'completed');self.assertEqual(len(again),1);self.assertEqual(again[0]['resource'],bad)
        self.assertEqual(self.states()[bad],'saved')
        nothing=analysis_run.prepare('demo',lang='en',intent={**self.only(bad),'max_calls':0})
        self.assertEqual(analysis_run.run(nothing['id'],lambda *a,**k:self.fail('unexpected call'))['state'],'completed')

    def test_the_units_to_explain_are_validated_against_the_catalog_and_the_cap(self):
        for bad in ([],[{'repository':'service','target':''}],[{'repository':'service'}],'x',[{'repository':'service','target':f'folder:{i}'} for i in range(25)]):
            with self.assertRaisesRegex(ValueError,'1 to 24 units'):self.prepare(intent={**self.only('folder:lib'),'only':bad})
        with self.assertRaisesRegex(ValueError,'current catalog'):self.prepare(intent=self.only('folder:nowhere'))
        with self.assertRaisesRegex(ValueError,'maximum call count'):self.prepare(intent={**self.only('folder:lib'),'max_calls':1})
        job=self.prepare(intent=self.only('folder:lib'))  # a run of this kind counts its calls plainly, without stage reservations
        self.assertNotIn('floor',job['budget']);self.assertEqual([t.get('target') for t in job['tasks']],['folder:lib'])
        self.assertEqual(analysis_run.run(job['id'],self.executor([]))['state'],'completed')
        self.assertIsNone(self.board()['budget'])

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

    def test_legacy_project_full_run_starts_with_the_overview_then_the_map_and_a_card_saves_a_unit(self):
        self.legacy()
        board=analysis_run.unit_board('legacy','','dev','en')
        job=analysis_run.prepare('legacy',lang='en',intent={'task':'full','targets':[],'max_calls':board['calls']})
        self.assertEqual(job['state'],'preparing')
        calls=[]
        done=analysis_run.run(job['id'],self.executor(calls))
        self.assertEqual(done['state'],'completed',done.get('error'))
        self.assertNotIn('resource',calls[0]);self.assertNotIn('resources',calls[0])  # first overview, then units
        self.assertFalse(any('resource' in c for c in calls))
        ids=[row[0] for row in analysis_run.unit_board('legacy','','dev','en')['repositories'][0]['units'] if not row[0].startswith('task:')]
        self.assertEqual(self.cards(ids[0],project='legacy',rid='')['state'],'completed')
        states={row[0]:row[4] for row in analysis_run.unit_board('legacy','','dev','en')['repositories'][0]['units']}
        self.assertEqual(states[ids[0]],'saved');self.assertTrue(all(states[i]=='pending' for i in ids[1:]),states)

    def test_a_saved_unit_overview_for_other_files_is_outdated_even_on_the_same_commit_and_a_retired_unit_is_not_counted(self):
        self.legacy()
        board=analysis_run.unit_board('legacy','','dev','en')
        job=analysis_run.prepare('legacy',lang='en',intent=self.only(*self.unit_ids(board),rid=''))
        self.assertEqual(analysis_run.run(job['id'],self.executor([]))['state'],'completed')
        record=analysis_run.read(job['id']);units=record['unit_overviews']['']
        victim=next(t for t in units if t.startswith('folder:lib'))
        units[victim]['unit']={**units[victim]['unit'],'digest':'0'*64,'file_count':99}  # the unit holds other files now
        units['folder:gone']={**units[victim],'unit':{**units[victim]['unit'],'id':'folder:gone'}}  # a unit of an older structure
        analysis_run.write(record)
        board=analysis_run.unit_board('legacy','','dev','en');states=self.states(board)
        self.assertEqual(states[victim],'stale');self.assertEqual(board['totals']['stale'],1)
        self.assertEqual(board['totals']['saved']+1+board['totals']['pending'],board['totals']['units'])  # every other unit is saved (the three map rows are not asked yet)
        retired=board['repositories'][0]['retired'];self.assertIn('folder:gone',retired);self.assertEqual(board['totals']['retired'],len(retired))
        self.assertFalse(set(retired)&set(states))  # kept in history, never counted as units
        # A new run does not take that explanation as cached.
        again=analysis_run.prepare('legacy',lang='en',intent=self.only(victim,rid=''))
        self.assertIn(victim,[t.get('target') for t in again['tasks']])

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
        done=analysis_run.run(self.prepare(intent={**self.intent(whole,'all'),'max_calls':whole['modes']['all']['calls']+60})['id'],self.executor([]))
        self.assertEqual(done['state'],'completed',done.get('error'))
        (self.repo/'lib'/'m0.py').write_text('def lib_0():\n    return 100\n');self.git('add','-A');self.git('commit','-qm','Small change')
        analysis_run._INDEXES.clear()
        patched=self.board()
        self.assertEqual(patched['repositories'][0]['commit'],self.git('rev-parse','HEAD').strip())
        self.assertGreater(self.map_calls(whole,'all'),3)  # the 6500-line padding file alone fills several batches
        self.assertLess(self.map_calls(whole),self.map_calls(whole,'all'))  # signal windows leave the padding document to the local index
        self.assertLess(self.map_calls(patched),self.map_calls(whole,'all'))  # only the changes and the files the saved map cites are read again
        repo,raw,_,head=analysis_run.ai_extract.context('demo','service','dev')
        mode=analysis_run.ai_extract.map_mode(repo['path'],raw['dev'],'en',analysis_run.store.fingerprint(repo),head)
        self.assertEqual(mode[0],'patch')

    def test_call_limit_parts_add_up_to_the_confirmed_cap(self):
        board=self.board();parts=board['calls_parts']
        floor=parts['overview']+sum(r['map_floor_by']['signal'] for r in board['repositories'])
        self.assertEqual(sum(parts.values()),board['calls']);self.assertEqual(parts['retry'],1+floor//8)  # the allowance is over first calls only
        self.assertEqual(parts['map'],board['map_calls'])
        plan=analysis_run.ai_extract.plan('demo','dev','en','service',overview=True,light=True)
        for mode in ('signal','all'):  # the board read every stage plan of both choices from the cache the scan filled, none fell back to a rough count
            value={'project':'demo','branch':'dev','lang':'en','intent':{'task':'full','coverage':mode}}
            self.assertTrue(all(analysis_run._planned(value,t,False) for t in plan['tasks'] if t['task'] in ('analysis','groups')))
        for mode in ('signal','all'):
            # prepare() reserves exactly what the board shows: one first call per batch, the extra share per batch and the allowance.
            job=self.prepare(intent=self.intent(board,mode));budget=job['budget']
            self.assertEqual(sum(budget['floor'].values())+sum(budget['extra'].values())+budget['retry'],board['modes'][mode]['calls'])
            analysis_run.cancel(job['id'])

    def test_cancel_keeps_saved_map_tasks_and_retry_only_asks_for_the_rest(self):
        job=self.prepare(intent=self.intent());calls=[]
        def stop(count):
            if count==3:analysis_run.cancel(job['id'])
        done=analysis_run.run(job['id'],self.executor(calls,after=stop))
        self.assertEqual(done['state'],'cancelled')
        saved=sum(1 for s in self.states().values() if s=='saved')
        self.assertGreater(saved,0);self.assertLess(saved,len(self.states()))
        retry=analysis_run.retry(job['id']);rest=[]
        self.assertEqual(analysis_run.run(retry['id'],self.executor(rest))['state'],'completed')
        self.assertEqual({v for k,v in self.states().items() if k.startswith('task:')},{'saved'})
        self.assertLess(len(rest),len(calls)+len(rest))

    def test_changed_code_marks_only_affected_units_stale_and_keeps_unchanged_ones(self):
        self.explain_everything()
        (self.repo/'lib/m0.py').write_text('def lib_0():\n    return 42\n')
        self.git('add','-A');self.git('commit','-qm','Change lib');self.publish_index()
        states=self.states()
        self.assertEqual(states['folder:lib'],'stale')
        self.assertEqual(states['folder:tools'],'saved')
        # A path explanation survives a change in files it never cited: its model input is identical.
        self.assertTrue(all(states[f'route:{p}']=='saved' for p in self.PATHS),states)
        calls=[];self.assertEqual(self.cards('folder:lib',calls=calls)['state'],'completed')
        self.assertTrue(all('tools' not in json.dumps(p.get('resource') or p.get('resources')) for p in calls))
        self.assertEqual({v for k,v in self.states().items() if not k.startswith('task:')},{'saved'})
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
        job=self.prepare(intent={**self.intent(board,'all'),'max_calls':board['modes']['all']['calls']+60});calls=[]
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
        left=self.board()['modes']['all']['map_by'];full=board['modes']['all']['map_by']  # the processed share is not asked for again, and each stage is named
        self.assertLess(left['analysis'],full['analysis']);self.assertEqual({k:left[k] for k in ('system','groups')},{k:full[k] for k in ('system','groups')})
        self.assertEqual(sum(left.values()),self.map_calls(self.board(),'all'))
        shown=analysis_run.unit_result('demo','service','dev','en','task:analysis')
        self.assertEqual(shown['state'],'partial');self.assertEqual(shown['items'],part['items'])
        again=[];done=analysis_run.run(analysis_run.retry(job['id'])['id'],self.executor(again))
        self.assertEqual(done['state'],'completed',done.get('error'))
        self.assertEqual({v for k,v in self.states().items() if k.startswith('task:')},{'saved'})
        self.assertEqual(done['partial_results']['service']['analysis']['state'],'published')
        self.assertEqual([r['path'] for r in self.raw()['dev']['backend_routes']],['/items'])
        self.assertIsNone(analysis_run.unit_result('demo','service','dev','en','task:analysis'))

    def test_a_model_that_never_stops_reading_spends_only_the_reserved_calls_and_later_stages_still_run(self):
        """(b) Extra calls of one stage come from its own share: the map's endless reads cannot use up the structure's and groups' first calls."""
        self.large_map();board=self.board();job=self.prepare(intent=self.intent(board,'all'));calls=[];inner=self.executor(calls)
        def endless(prompt,**kwargs):
            answer=inner(prompt,**kwargs);packet=calls[-1]
            if 'screens' in packet.get('schema',{}) and 'batch' in packet:answer['needs']=[{'query':'zz'+str(len(calls)),'start':1,'limit':1}]
            return answer
        done=analysis_run.run(job['id'],endless)
        self.assertEqual(done['state'],'completed',done.get('error'))
        self.assertLessEqual(len(calls),board['modes']['all']['calls'])
        self.assertEqual({v for k,v in self.states().items() if k.startswith('task:')},{'saved'})  # the structure and the groups ran
        by=done['input_stats']['by_stage']
        self.assertLessEqual(by['analysis@service']['extra'],job['budget']['extra']['analysis@service']+job['budget']['retry'])
        self.assertTrue(analysis_run._map_gaps(done))  # the map batches that were cut short are named
        self.assertTrue(any('could not be read to the end' in u for u in self.raw()['dev']['analysis']['unknown']))

    def signal_fixture(self):
        """A route file buried in padding, a long document, a test and a plain module without any signal."""
        (self.repo/'bulk').mkdir()
        (self.repo/'bulk/big.py').write_text('\n'.join(['value = 1']*1500+["@app.get('/deep')","def deep():","    return 1"]+['value = 2']*1500)+'\n')
        (self.repo/'NOTES.md').write_text('unique note row\n'*4000)
        (self.repo/'tests').mkdir();(self.repo/'tests/test_api.py').write_text("client.get('/orders')\n"*5)
        (self.repo/'lib/plain.py').write_text('def plain():\n    return 3\n'*40)
        self.git('add','-A');self.git('commit','-qm','Signal fixture');self.publish_index()

    def supplied(self,calls):
        """{file: lines the map prompts carried}, and every map prompt's text."""
        seen={};text=[]
        for packet in calls:
            if 'screens' not in packet.get('schema',{}):continue
            text.append(json.dumps(packet))
            for snapshot in packet.get('snapshots',[]):
                for file in snapshot['files']:
                    rows=file.get('numbered_lines') or file.get('lines') or []
                    seen.setdefault(file['file'],set()).update(r[0] if isinstance(r,list) else r['line'] for r in rows)
        return seen,text

    def test_signal_reading_sends_windows_names_every_tier_and_stays_inside_the_cap(self):
        self.signal_fixture()
        board=self.board();coverage=board['repositories'][0]['map_coverage']
        self.assertEqual(coverage['files'],coverage['windows']+coverage['whole']+coverage['local']+coverage['docs']+coverage['support'])
        self.assertGreaterEqual(coverage['docs'],1);self.assertGreaterEqual(coverage['support'],1);self.assertGreaterEqual(coverage['local'],1)
        self.assertLess(coverage['sent_bytes'],coverage['text_bytes']/4)
        self.assertLess(board['modes']['signal']['calls'],board['modes']['all']['calls'])
        calls=[];intent=self.intent(board)
        done=analysis_run.run(self.prepare(intent=intent)['id'],self.executor(calls))
        self.assertEqual(done['state'],'completed',done.get('error'))
        self.assertLessEqual(len(calls),intent['max_calls'])
        seen,text=self.supplied(calls)
        self.assertEqual(sorted(seen['bulk/big.py'])[0],1499);self.assertIn(1501,seen['bulk/big.py']);self.assertLess(len(seen['bulk/big.py']),12)  # the route and its neighbours, original numbers
        self.assertNotIn('NOTES.md',seen);self.assertNotIn('tests/test_api.py',seen);self.assertNotIn('lib/plain.py',seen)
        notes=[c['coverage'] for c in calls if 'screens' in c.get('schema',{}) and 'coverage' in c]
        self.assertTrue(notes and all(n['text_files_read_locally']==coverage['files'] and n['sent_as_signal_windows']==coverage['windows'] for n in notes),'the AI is told what it does not see as text')
        self.assertTrue(all('unique note row' not in t for t in text))
        self.assertEqual([r['path'] for r in self.raw()['dev']['backend_routes']],['/items'])  # the map is saved as before
        structure=[json.dumps(c) for c in calls if 'nodes' in c.get('schema',{})]
        self.assertTrue(structure and all('lib/plain.py' in t and 'bulk/big.py' in t for t in structure[:1]))  # code paths are listed
        joined=' '.join(structure)
        self.assertNotIn('NOTES.md',joined);self.assertNotIn('tests/test_api.py',joined)  # documents and tests are counted per directory instead
        self.assertIn('docs/data=',joined);self.assertIn('tests/vendored=',joined);self.assertIn('other_files',joined)

    def test_every_text_file_reading_still_sends_all_of_it(self):
        self.signal_fixture()
        board=self.board();calls=[]
        done=analysis_run.run(self.prepare(intent={**self.intent(board,'all'),'max_calls':board['modes']['all']['calls']+30})['id'],self.executor(calls))
        self.assertEqual(done['state'],'completed',done.get('error'))
        seen,text=self.supplied(calls)
        self.assertIn('NOTES.md',seen);self.assertIn('lib/plain.py',seen);self.assertEqual(len(seen['bulk/big.py']),3003)
        self.assertTrue(all('coverage' not in c for c in calls if 'screens' in c.get('schema',{})))
        self.assertIn('NOTES.md',' '.join(json.dumps(c) for c in calls if 'nodes' in c.get('schema',{})))  # every path is listed when everything is sent

    def test_the_ai_can_still_ask_for_a_file_the_signal_scan_did_not_send(self):
        self.signal_fixture()
        board=self.board();job=self.prepare(intent={**self.intent(board),'max_calls':board['calls']+4});calls=[]  # +4: the read request costs one more call, the map one more unit
        inner=self.executor(calls)
        def fake(prompt,**kwargs):
            answer=inner(prompt,**kwargs);packet=calls[-1]
            if 'screens' in packet.get('schema',{}) and 'batch' not in packet and not packet.get('provisional_result'):
                answer={**(answer if isinstance(answer,dict) else json.loads(answer)),'needs':[{'file':'lib/plain.py','start':1,'limit':4}]}
            return answer
        done=analysis_run.run(job['id'],fake)
        self.assertEqual(done['state'],'completed',done.get('error'))
        seen,_=self.supplied(calls)
        self.assertEqual(seen.get('lib/plain.py'),{1,2,3,4})  # only the requested range travelled

    def test_signal_scan_is_cached_so_another_process_does_not_scan_again(self):
        self.signal_fixture()
        first=self.board()
        self.assertEqual(len(list((Path(analysis_run.mapcore.ROOT)/'.analysis-cache').glob('signals-*.json'))),1)
        analysis_run._SIGNALS.clear()
        original=analysis_run.source_signals.scan_commit
        analysis_run.source_signals.scan_commit=lambda *a,**k:self.fail('scanned again')
        self.addCleanup(setattr,analysis_run.source_signals,'scan_commit',original)
        again=self.board()
        self.assertEqual(again['repositories'][0]['map_coverage'],first['repositories'][0]['map_coverage']);self.assertEqual(again['modes'],first['modes'])

    def test_board_opens_before_the_scan_and_its_numbers_become_exact_after_it(self):
        self.signal_fixture()
        original=analysis_run.source_signals.scan_commit
        analysis_run.source_signals.scan_commit=lambda *a,**k:self.fail('the board must not scan')
        try:opened=analysis_run.unit_board('demo','service','dev','en')
        finally:analysis_run.source_signals.scan_commit=original
        self.assertEqual(opened['signals'],'pending');self.assertIsNone(opened['repositories'][0]['map_coverage'])
        self.assertGreater(opened['totals']['units'],0)  # the unit list is already there
        analysis_run.unit_signals('demo','service','dev','en')
        ready=analysis_run.unit_board('demo','service','dev','en')
        self.assertEqual(ready['signals'],'ready');self.assertTrue(ready['repositories'][0]['map_coverage']['files'])
        self.assertLessEqual(ready['modes']['signal']['calls'],opened['modes']['signal']['calls'])  # the pending number is an upper bound
        self.assertEqual(ready['totals'],opened['totals'])

    def test_batches_that_describe_the_same_identity_differently_keep_the_first_and_say_so_while_identity_conflicts_still_fail(self):
        first={'screens':[{'path':'/p/{}','heading':'A','file':'f1.tsx','line':3,'actions':[{'kind':'nav','to':'/a'}]}],'unknown':['kept']}
        second={'screens':[{'path':'/p/{}','heading':'B','file':'f2.tsx','line':9,'component':'C','actions':[{'kind':'nav','to':'/b'}]}]}
        merged=analysis_run._combine(first,second)
        screen=merged['screens'][0]
        self.assertEqual((screen['heading'],screen['file'],screen['component']),('A','f1.tsx','C'))  # first wins, new fields join
        self.assertEqual([a['to'] for a in screen['actions']],['/a','/b'])  # lists are unioned
        self.assertEqual(merged['unknown'][0],'kept');self.assertIn('f2.tsx:9',merged['unknown'][1])  # the divergence is stated, never silent
        route=lambda name,mount='m.py':{'backend_routes':[{'method':'GET','path':'/x','file':'a.py','function':'f','name':name,'dependencies':[{'file':mount}]}]}
        kept=analysis_run._combine(route('one'),route('two'))  # the same registration seen by two batches: the label differs, the registration is one
        self.assertEqual(kept['backend_routes'][0]['name'],'one');self.assertIn('name differ',kept['unknown'][0])
        bare={'backend_routes':[{'method':'GET','path':'/x','file':'a.py','function':'f'}]}  # the same registration where no mount was found
        joined=analysis_run._combine(bare,route('one'))['backend_routes'];self.assertEqual(len(joined),1);self.assertEqual(joined[0]['dependencies'],[{'file':'m.py'}])
        self.assertEqual(len(analysis_run._combine(route('one'),bare)['backend_routes']),1)
        again=route('one');again['backend_routes'][0]['dependencies']=[{'file':'m.py','line':7,'quote':'mounted here too'}]  # same mount file, other evidence line
        both=analysis_run._combine(route('one'),again)['backend_routes'][0]
        self.assertEqual([d.get('line') for d in both['dependencies']],[None,7]);self.assertEqual(analysis_run.ai_extract.route_id(both),analysis_run.ai_extract.route_id(route('one')['backend_routes'][0]))  # the identity keeps its first anchor
        # The path is the full mounted path: another mount listed first is the same endpoint, and the first batch's mount stays first.
        merged=analysis_run._combine(route('one'),route('one','other.py'))['backend_routes']
        self.assertEqual(len(merged),1);self.assertEqual(analysis_run._mount_file(merged[0]),analysis_run._mount_file(route('one')['backend_routes'][0]))
        with self.assertRaisesRegex(analysis_run.RunError,r'at /count'):analysis_run._combine({'count':1},{'count':2})  # a conflicting scalar outside an identity item still fails
        nodes=analysis_run._combine({'nodes':[{'id':'api','name':'A'}]},{'nodes':[{'id':'api','name':'B'}]})
        self.assertEqual(nodes['nodes'][0]['name'],'A');self.assertEqual(nodes['unknown'][0]['needs'],'read')  # the structure task's unknown shape

    def test_recheck_targets_no_batch_judged_are_found_from_the_merged_result(self):
        kept={'method':'GET','path':'/a','file':'a.py','function':'f'};moved={'method':'GET','path':'/b','file':'b.py','function':'g'}
        request={'recheck':[{'id':analysis_run.ai_extract.route_id(kept)},{'id':'r:gone'},{'id':'r:old'},{'id':'s:'+'x'*4},{'id':analysis_run.ai_extract.screen_id({'path':'/p'})}]}
        result={'backend_routes':[kept,{**moved,'replaces':'r:old'}],'screens':[{'path':'/p'}],'removed':['r:gone']}
        self.assertEqual(analysis_run._undisposed(result,request),['s:xxxx'])

    def test_a_reemitted_registration_with_a_new_mount_names_the_saved_item_it_succeeds(self):
        from unittest.mock import patch
        old={'method':'GET','path':'/a','file':'a.py','function':'f','dependencies':[{'file':'main.py'}]}
        new={'method':'GET','path':'/a','file':'a.py','function':'f','dependencies':[{'file':'a.py'}]}
        target=analysis_run.ai_extract.route_id(old);raw={'commit':'c','backend_routes':[{**old,'source':'ai'}],'analysis':{'commit':'c'}}
        result={'backend_routes':[new]}
        with patch.object(analysis_run.ai_extract,'basic_catalog',return_value={'backend_routes':[],'screens':[]}):
            analysis_run._supersede(result,{'recheck':[{'id':target}]},raw,'repo','c',{})
        self.assertEqual(new.get('replaces'),target);self.assertEqual(analysis_run._undisposed(result,{'recheck':[{'id':target}]}),[])

    def test_a_metadata_request_for_a_missing_path_is_answered_not_fatal(self):
        payload={'input':{'routes':['a']}}
        for path in (['input','changes'],['nowhere'],['input','routes',9],['input']):
            units=analysis_run._needed('repo','c',[{'metadata':path}],None,None,payload)
            self.assertEqual(len(units),1 if path!=['input'] else len(units));self.assertTrue(units)
        self.assertEqual(analysis_run._needed('repo','c',[{'metadata':['nowhere']}],None,None,payload)[0]['value']['value']['error'],'Not an existing analysis metadata path')

    def test_keep_all_from_an_early_round_does_not_survive_nodes_found_by_a_later_round(self):
        union=analysis_run._combine({'keep':'all','nodes':[]},{'nodes':[{'id':'api'}]})
        self.assertEqual(analysis_run._unkeep('system',union),{'nodes':[{'id':'api'}]})
        self.assertEqual(analysis_run._unkeep('system',{'keep':'all','nodes':[]}),{'keep':'all','nodes':[]})
        self.assertEqual(analysis_run._unkeep('analysis',{'keep':'all','nodes':[1]}),{'keep':'all','nodes':[1]})

    def test_references_no_round_defined_are_dropped_and_named_in_unknown(self):
        result={'nodes':[{'id':'api','uses':['db','ghost']},{'id':'web'}],'externals':[{'id':'db'}],'links':[{'from':'web','to':'api'},{'from':'api','to':'folder'}],'unknown':[]}
        out=analysis_run._prune_dangling('system',result)
        self.assertEqual(out['links'],[{'from':'web','to':'api'}]);self.assertEqual(out['nodes'][0]['uses'],['db'])
        self.assertEqual(len(out['unknown']),2);self.assertIn('api -> folder',out['unknown'][0]['text']);self.assertIn('ghost',out['unknown'][1]['text'])
        clean={'nodes':[{'id':'a'}],'externals':[],'links':[],'unknown':[]};self.assertEqual(analysis_run._prune_dangling('system',dict(clean)),clean)
        self.assertEqual(analysis_run._prune_dangling('analysis',{'links':[{'from':'x','to':'y'}]}),{'links':[{'from':'x','to':'y'}]})

    def test_structure_labels_the_saved_structure_would_coerce_do_not_fail_validation(self):
        node={'id':'db','name':'DB','kind':'database','origin':'external','code':[],'ev':[]}
        with patch.object(analysis_run,'_regular_files',return_value={'a.go'}),patch.object(analysis_run.ai_extract,'evidence_reader',return_value=(lambda ev:True,{},lambda:0)):
            data={'nodes':[node],'links':[],'externals':[],'others':[]};node['ev']=[{'file':'a.go','line':1,'quote':'package main'}]
            analysis_run._strict_result('system',data,'repo','c',None,{},False)
        self.assertEqual((node['kind'],node['origin']),('program','repo'))

    def test_a_dict_valued_metadata_entry_larger_than_one_page_is_paged_not_refused(self):
        payload={'input':{'map':{'api_functions':['x'*40000],'small':[1]}}}
        units=analysis_run._needed('repo','c',[{'metadata':['input','map']}],None,None,payload)
        self.assertGreater(len(units),2);self.assertTrue(all(u['kind']=='metadata' for u in units))

    def test_a_file_read_for_a_path_that_is_not_tracked_source_is_answered_but_secrets_and_traversal_still_fail(self):
        units=analysis_run._needed(str(Path(__file__).resolve().parent.parent),'HEAD',[{'file':'no/such/file.txt'}],None,None,{})
        self.assertEqual(units[0]['value']['value']['error'],'Not an eligible tracked source file at the pinned commit')
        for bad in ('../outside','/etc/passwd','.env'):
            with self.assertRaises(analysis_run.RunError):analysis_run._needed(str(Path(__file__).resolve().parent.parent),'HEAD',[{'file':bad}],None,None,{})

    def test_malformed_read_request_lists_are_trimmed_or_answered_not_fatal(self):
        payload={'input':{'a':['x']}}
        units=analysis_run._needed('repo','c',[{'metadata':['input','a']}]*20,None,None,payload)
        self.assertTrue(units);self.assertEqual(analysis_run._needed('repo','c','not a list',None,None,payload),[])
        for bad in ({},{'file':'a','query':'b'},{'query':'two\nlines'},{'query':'x'*300},'text'):
            out=analysis_run._needed('repo','c',[bad],None,None,payload);self.assertEqual(len(out),1);self.assertIn('error',out[0]['value']['value'])

    def test_batches_naming_one_program_differently_merge_by_spelling_and_references_follow(self):
        first={'nodes':[{'id':'image_worker','name':'Engine','code':['x']}],'externals':[{'id':'media_store','name':'Work'}],'links':[]}
        second={'nodes':[{'id':'image-worker','name':'Image worker','code':['y']},{'id':'api','uses':['media-store']}],
                'externals':[{'id':'media-store','name':'Work folder'}],'links':[{'from':'api','to':'image-worker'}]}
        merged=analysis_run._combine(first,second)
        self.assertEqual([n['id'] for n in merged['nodes']],['image_worker','api']);self.assertEqual(merged['nodes'][0]['code'],['x','y'])
        self.assertEqual(len(merged['externals']),1)
        self.assertFalse([u for u in merged.get('unknown',[]) if 'id differ' in str(u)])  # the spelling is not reported as a conflict
        out=analysis_run._prune_dangling('system',merged)
        self.assertEqual(out['links'],[{'from':'api','to':'image_worker'}]);self.assertEqual(out['nodes'][1]['uses'],['media_store'])

    def test_a_saved_map_that_can_be_patched_still_waits_for_the_scan_only_to_tell_text_from_binary(self):
        self.large_map()
        whole=self.board()
        done=analysis_run.run(self.prepare(intent={**self.intent(whole,'all'),'max_calls':whole['modes']['all']['calls']+60})['id'],self.executor([]))
        self.assertEqual(done['state'],'completed',done.get('error'))
        (self.repo/'lib'/'m0.py').write_text('def lib_0():\n    return 100\n');self.git('add','-A');self.git('commit','-qm','Small change');analysis_run._INDEXES.clear()
        # The unit catalog needs the scan to tell text from binary, so the board waits for it even when the map only needs a patch.
        self.assertEqual(analysis_run.unit_board('demo','service','dev','en')['signals'],'pending')
        self.assertTrue(analysis_run.unit_signals('demo','service','dev','en')['ready'])
        self.assertEqual(analysis_run.unit_board('demo','service','dev','en')['signals'],'ready')

    def test_signal_windows_over_several_batches_save_progress_cancel_and_resume_without_resending(self):
        (self.repo/'mods').mkdir()
        for i in range(420):
            (self.repo/'mods'/f'm{i}.py').write_text('\n'.join([f'a{i} = {n}' for n in range(30)]+[f"@app.get('/m{i}')",f'def m{i}():']+[f"    step_{n} = 'padding text of window {i} line {n} to widen the rows'" for n in range(12)])+'\n')
        self.git('add','-A');self.git('commit','-qm','Many route files');self.publish_index()
        board=self.board();job=self.prepare(intent={**self.intent(board),'max_calls':board['calls']+30});calls=[]
        def stop(_):
            if self.batches(calls)==2:analysis_run.cancel(job['id'])
        stopped=analysis_run.run(job['id'],self.executor(calls,after=stop))
        self.assertEqual(stopped['state'],'cancelled',stopped.get('error'))
        part=stopped['partial_results']['service']['analysis']
        self.assertEqual(part['state'],'partial');self.assertGreater(part['covered'],0);self.assertLess(part['covered'],part['total'])
        sent=[c['batch']['id'] for c in calls if 'batch' in c and 'screens' in c['schema']]
        self.assertGreaterEqual(len(sent),2)
        again=[];done=analysis_run.run(analysis_run.retry(job['id'])['id'],self.executor(again))
        self.assertEqual(done['state'],'completed',done.get('error'))
        resent=[c['batch']['id'] for c in again if 'batch' in c and 'screens' in c['schema']]
        self.assertFalse(set(resent)&set(sent[:1]),'a settled batch is not sent again')
        self.assertEqual(done['partial_results']['service']['analysis']['state'],'published')
        self.assertTrue(all(len(c.get('coverage',{}))==6 for c in calls if 'batch' in c and 'screens' in c['schema']))

    def test_a_saved_maps_cited_files_are_sent_whole_beside_the_windows(self):
        self.signal_fixture()
        raw=self.raw();raw['dev']['analysis']={**(raw['dev'].get('analysis') or {}),'source':'ai'}
        routes=analysis_run.ai_extract.ai_catalog({'analysis':{'source':'ai'},'backend_routes':[{'file':'lib/plain.py','path':'/plain','method':'GET','function':'plain'}],'screens':[]})[0]
        rows,report=analysis_run._window_plan(analysis_run._signals(str(self.repo),self.git('rev-parse','HEAD').strip()),{'lib/plain.py'})
        self.assertIsNone(rows['lib/plain.py']);self.assertEqual(report['whole'],1);del routes

    def test_unit_calls_are_packed_by_sample_bytes_and_the_cap_counts_the_same_packs(self):
        rows=[(f'/r{i}','route',500) for i in range(9)]+[(f'folder:f{i}','folder',9000) for i in range(30)]+[('package:p','package',200)]
        packs=analysis_run._packs(rows)
        self.assertEqual([len(p) for p in packs[:3]],[4,4,1])  # path groups four at a time, never mixed with other units
        plain=packs[3:]
        self.assertTrue(all(sum(9000 if t.startswith('folder') else 200 for t in p)<=analysis_run.UNIT_PACK_BYTES and len(p)<=analysis_run.UNIT_PACK_MAX for p in plain))
        self.assertEqual(sorted(t for p in packs for t in p),sorted(t for t,_,_ in rows))  # nothing is dropped or repeated
        self.assertLess(len(plain),30//4)  # fewer calls than four units each
        board=self.board();calls=[]
        done=analysis_run.run(self.prepare(intent=self.intent(board))['id'],self.executor(calls))
        self.assertEqual(done['state'],'completed',done.get('error'))
        self.assertLessEqual(sum(1 for c in calls if 'resources' in c),board['calls_parts']['units'])

    def test_a_failing_unit_is_asked_exactly_as_often_as_the_attempt_limit_allows(self):
        calls=[];done=self.cards('folder:lib','folder:tools',calls=calls,bad=('folder:lib',))
        self.assertEqual(done['state'],'completed',done.get('error'))
        asked=sum(1 for c in calls for r in (c.get('resources') or [c]) if r.get('resource')=='folder:lib')
        self.assertEqual(asked,analysis_run.UNIT_ATTEMPTS)
        self.assertEqual([f['attempts'] for f in done['unit_failures']],[analysis_run.UNIT_ATTEMPTS])

    def test_a_long_list_of_paths_travels_in_pages_of_whole_entries(self):
        paths=[f'src/module{i:05d}/file_name_{i:05d}.py' for i in range(3000)]
        header,units=analysis_run._units({'input':{'files':paths,'k':1}})
        pages=[u['value'] for u in units if u['value']['path']==['input','files']]
        self.assertLess(len(pages),len(paths)/100)  # one unit per page, not per path
        joined=[p for page in pages for p in page['value']];self.assertEqual(joined,paths)
        self.assertEqual([page['offset'] for page in pages],[sum(len(q['value']) for q in pages[:i]) for i in range(len(pages))])

    def test_units_discovered_by_the_saved_map_and_structure_are_listed_not_asked_and_a_card_can_explain_them(self):
        self.assertNotIn('program:api',self.states())
        calls=[];done=analysis_run.run(self.prepare(intent=self.intent())['id'],self.executor(calls))
        self.assertEqual(done['state'],'completed',done.get('error'))
        self.assertTrue(done['catalog_refreshed']);self.assertFalse(any('resource' in c or 'resources' in c for c in calls))
        self.assertEqual(self.states()['program:api'],'pending')
        self.assertEqual(self.cards('program:api')['state'],'completed');self.assertEqual(self.states()['program:api'],'saved')

    def test_saved_unit_can_be_read_and_old_code_is_flagged(self):
        self.assertEqual(self.cards('folder:tools')['state'],'completed')
        unit=analysis_run.unit_result('demo','service','dev','en','folder:tools')
        self.assertEqual(unit['unit']['name'],'tools');self.assertNotIn('stale',unit)
        (self.repo/'tools/m0.py').write_text('def tools_0():\n    return 9\n')
        self.git('add','-A');self.git('commit','-qm','Change tools');self.publish_index()
        self.assertTrue(analysis_run.unit_result('demo','service','dev','en','folder:tools')['stale'])

    def test_unit_without_eligible_source_is_skipped_not_failed(self):
        (self.repo/'blank').mkdir();(self.repo/'blank/only.py').write_text('x\n')
        self.git('add','-A');self.git('commit','-qm','Tiny file');self.publish_index()
        calls=[];done=self.cards('folder:blank',calls=calls)
        self.assertEqual(done['state'],'completed',done.get('error'));self.assertEqual(self.states()['folder:blank'],'unavailable')
        # The skipped unit costs no model call, and asking again is free.
        self.assertEqual(calls,[]);again=analysis_run.prepare('demo',lang='en',intent=self.only('folder:blank'))
        self.assertEqual((again['tasks'],again['unit_estimate']['calls']),([],0))

    def local_fixture(self):
        (self.repo/'docs').mkdir()
        for i in range(3):(self.repo/'docs'/f'g{i}.md').write_text(f'# Guide {i}\nsome words about the product\n')
        (self.repo/'lib/blob.dat').write_bytes(b'\xff\xfe\x00\x01binary payload\xff')
        self.git('add','-A');self.git('commit','-qm','Docs and a binary blob');self.publish_index()

    def test_local_units_are_counted_and_listed_and_a_card_explains_one_when_the_user_asks(self):
        self.local_fixture()
        board=self.board();self.assertEqual(self.states(board)['folder:local:docs'],'local')
        self.assertEqual(board['totals']['local'],1)
        calls=[];done=analysis_run.run(self.prepare(intent=self.intent(board))['id'],self.executor(calls))
        self.assertEqual(done['state'],'completed',done.get('error'))
        self.assertFalse(any('resource' in c or 'resources' in c for c in calls))
        self.assertEqual(self.states()['folder:local:docs'],'local')
        shown=analysis_run.unit_result('demo','service','dev','en','folder:local:docs')
        self.assertEqual((shown['local'],shown['file_count']),(True,3))
        # The user asked for this unit, so it is explained whatever the coverage choice is.
        asked=[];card=self.cards('folder:local:docs','folder:lib',calls=asked)
        self.assertEqual(card['state'],'completed',card.get('error'));self.assertTrue(any('folder:local:docs' in json.dumps(c.get('resource') or c.get('resources')) for c in asked))
        self.assertEqual(self.states()['folder:local:docs'],'saved');self.assertEqual(self.board()['totals']['local'],0)
        self.assertEqual(analysis_run._run_board(card)['totals'],self.board()['totals'])  # the run's board and the opened board agree
        self.assertEqual(analysis_run.unit_result('demo','service','dev','en','folder:local:docs')['unit']['id'],'folder:local:docs')

    def test_a_file_the_scan_cannot_read_as_text_is_excluded_as_binary_once_the_scan_is_cached(self):
        self.local_fixture()
        board=self.board();self.assertGreaterEqual(board['repositories'][0]['coverage']['excluded'].get('binary',0),2)  # logo.png and lib/blob.dat
        units=analysis_run._unit_catalogs({'project':'demo','branch':'dev','lang':'en'},analysis_run.ai_extract.plan('demo','dev','en','service',overview=True,light=True))
        self.assertNotIn('lib/blob.dat',{f for u in units['service']['units'] for f in u['files']})
        self.assertNotIn('pending_signals',units['service'])

    def test_a_continued_analysis_counts_only_what_is_left_and_stays_within_the_first_limit(self):
        """(d) Settled batches are kept by the content they answer: a retry or a new request after a cancel asks only the rest,
        and the board's number for it is the one prepare() checks."""
        self.large_map();board=self.board();intent=self.intent(board,'all');job=self.prepare(intent=intent);calls=[]
        def stop(_):
            if self.batches(calls)==2:analysis_run.cancel(job['id'])
        self.assertEqual(analysis_run.run(job['id'],self.executor(calls,after=stop))['state'],'cancelled')
        left=self.board()['modes']['all']['calls'];self.assertLess(left,intent['max_calls'])
        with self.assertRaisesRegex(ValueError,'maximum call count'):self.prepare(intent={**intent,'max_calls':left-1})
        more=self.prepare(intent={**intent,'max_calls':left});rest=[];done=analysis_run.run(more['id'],self.executor(rest))
        self.assertEqual(done['state'],'completed',done.get('error'));self.assertLessEqual(len(calls)+len(rest),intent['max_calls'])
        self.assertLessEqual(len(rest),left);self.assertEqual(analysis_run._run_board(done)['budget']['used'],len(rest))

    def test_a_new_request_continues_the_settled_map_batches_of_an_interrupted_analysis(self):
        (self.repo/'mods').mkdir()
        for i in range(420):
            (self.repo/'mods'/f'm{i}.py').write_text('\n'.join([f'a{i} = {n}' for n in range(30)]+[f"@app.get('/m{i}')",f'def m{i}():']+[f"    step_{n} = 'padding text of window {i} line {n} to widen the rows'" for n in range(12)])+'\n')
        self.git('add','-A');self.git('commit','-qm','Many route files');self.publish_index()
        board=self.board();intent={**self.intent(board),'max_calls':board['calls']+30};job=self.prepare(intent=intent);calls=[]
        def stop(_):
            if self.batches(calls)==3:analysis_run.cancel(job['id'])
        self.assertEqual(analysis_run.run(job['id'],self.executor(calls,after=stop))['state'],'cancelled')
        sent=[c['batch']['id'] for c in calls if 'batch' in c and 'screens' in c['schema']]
        again=[];follow=self.prepare(intent=intent)
        done=analysis_run.run(follow['id'],self.executor(again));self.assertEqual(done['state'],'completed',done.get('error'))
        resent=[c['batch']['id'] for c in again if 'batch' in c and 'screens' in c['schema']]
        self.assertFalse(set(resent)&set(sent[:2]),'a settled batch is not asked again')
        self.assertLessEqual(len(calls)+len(again),intent['max_calls'])

    def test_a_stage_whose_merged_result_cannot_be_saved_closes_alone_and_keeps_its_batches(self):
        """(c) A save that fails closes that stage; the run goes on with the next stage and ends completed with gaps."""
        self.large_map();board=self.board();job=self.prepare(intent=self.intent(board,'all'));calls=[]
        real=analysis_run._save
        def save(task,request,result):
            if task['task']=='analysis':raise ValueError('merge')
            return real(task,request,result)
        with patch.object(analysis_run,'_save',side_effect=save):done=analysis_run.run(job['id'],self.executor(calls))
        self.assertEqual(done['state'],'completed',done.get('error'));self.assertTrue(analysis_run._map_gaps(done))
        closed=done['stage_unavailable'];self.assertEqual((closed[0]['task'],closed[0]['reason']),('analysis','merge'))
        self.assertTrue(all(c['reason'] for c in closed))  # the stages after it ran and each closed on its own reason (here the fake's answers need the saved map)
        self.assertLessEqual(len(calls),board['modes']['all']['calls'])
        again=[];follow=self.prepare(intent=self.intent(self.board(),'all'));analysis_run.run(follow['id'],self.executor(again))
        self.assertEqual(sum(1 for c in again if 'batch' in c and 'screens' in c['schema']),0)  # the settled map batches were kept

    def asking(self,calls,answer_for):
        """An executor whose map batch replies are changed by answer_for(packet, answer, batch call count)."""
        inner=self.executor(calls);seen={}
        def fake(prompt,**kwargs):
            answer=inner(prompt,**kwargs);packet=calls[-1]
            if 'screens' in packet.get('schema',{}) and 'batch' in packet:
                n=seen[packet['batch']['id']]=seen.get(packet['batch']['id'],0)+1
                answer_for(packet,answer,n)
            return answer
        return fake

    def test_a_read_round_sends_an_index_of_what_the_batch_settled_not_the_settled_result(self):
        """(e) Earlier rounds are named by identity in batch.settled; the model never rewrites them and the server keeps them."""
        self.large_map();board=self.board();calls=[]
        def ask(packet,answer,n):
            if n==1:answer['needs']=[{'query':'unique row','start':1,'limit':1}]
        done=analysis_run.run(self.prepare(intent=self.intent(board,'all'))['id'],self.asking(calls,ask))
        self.assertEqual(done['state'],'completed',done.get('error'))
        later=[c for c in calls if 'batch' in c and 'screens' in c['schema'] and 'settled' in c['batch']]
        self.assertTrue(later);self.assertTrue(all('prior' not in c['batch'] for c in calls if 'batch' in c))
        self.assertIn('Do not return those entries again',later[0]['batch']['rules'])
        self.assertLessEqual(len(json.dumps(later[0]['batch']['settled'])),analysis_run.SETTLED_INDEX_BYTES)

    def test_a_piece_asked_for_again_is_answered_from_the_packet_and_the_batch_closes_without_failing(self):
        """(g) The header lists what metadata can be asked for; asking again for a piece it already has never fails the run."""
        self.large_map();board=self.board();calls=[]
        first=[None]
        def ask(packet,answer,n):
            first[0]=first[0] or packet['batch']['id']
            if packet['batch']['id']==first[0]:answer['needs']=[{'query':'unique row','start':1,'limit':1}]
        with patch.dict(analysis_run.EXTRA_PER_BATCH,{'analysis':4}):  # a share that lets one batch use every round it may
            board=self.board();done=analysis_run.run(self.prepare(intent=self.intent(board,'all'))['id'],self.asking(calls,ask))
        self.assertEqual(done['state'],'completed',done.get('error'))
        asked=[c for c in calls if 'batch' in c and c['batch']['id']==first[0]]
        self.assertEqual(sum(1 for c in asked if 'satisfied_needs' in c['batch']),1)  # told once that the piece is already in its packet
        self.assertEqual(done['map_scope']['service']['analysis']['reasons'],{'repeated':1})  # the batch closed with what it found, not as a failure
        self.assertTrue(all('requestable_metadata' in c for c in calls if 'batch' in c and 'screens' in c['schema']))
        self.assertLessEqual(len(asked),1+analysis_run._batch_extra_cap('analysis'))

    def test_remarks_about_a_whole_batch_are_counted_not_saved_as_unknown_findings(self):
        """(h) An unknown entry is kept when it names a file, screen or route; a batch-wide remark goes to the stage's counts."""
        self.large_map();board=self.board();calls=[]
        def remark(packet,answer,n):
            answer['result']['unknown']=['This batch holds no screens',{'about':'ui.ts','text':'the fetch target is built at run time'}]
        done=analysis_run.run(self.prepare(intent=self.intent(board,'all'))['id'],self.asking(calls,remark))
        self.assertEqual(done['state'],'completed',done.get('error'))
        unknown=self.raw()['dev']['analysis']['unknown']
        self.assertFalse(any('holds no screens' in str(u) for u in unknown))
        self.assertTrue(any('ui.ts: the fetch target' in str(u) for u in unknown))
        self.assertGreater(done['map_scope']['service']['analysis']['notes'],0)

    def test_an_ended_run_whose_board_cannot_open_records_why(self):
        """(f) The ended run is shown by the live board; a board that fails is recorded on the run, not swallowed."""
        job=self.prepare(intent=self.intent())
        with patch.object(analysis_run,'unit_board',side_effect=RuntimeError('board broke')):done=analysis_run.run(job['id'],self.executor([]))
        self.assertEqual(done['state'],'completed');self.assertEqual(done['seal_error'],{'type':'RuntimeError','message':'board broke'})
        self.assertNotIn('final_board',analysis_run.read(job['id']))

    def test_the_structure_packets_carry_the_verified_unit_evidence_and_an_answer_citing_it_needs_no_read(self):
        self.assertEqual(self.cards('folder:lib','folder:tools')['state'],'completed')  # explanations the user asked for earlier
        calls=[];seen=[]
        base=self.executor(calls)
        def fake(prompt,**kwargs):
            packet=json.loads(prompt.split('\n',1)[1])
            if 'nodes' in packet.get('schema',{}):
                text=prompt
                seen.append(text) if 'verified_units' in text else None
                rows=packet.get('input',{}).get('verified_units')
                if rows:
                    file,line,quote=rows[0][1][0][2][0]
                    return {'nodes':[{'id':'lib','name':'Lib','kind':'program','code':['lib'],'ev':[{'file':file,'line':line,'quote':quote}],'jobs':[]}],'links':[],'externals':[],'others':[],'unknown':[]}
            return base(prompt,**kwargs)
        done=analysis_run.run(self.prepare(intent=self.intent())['id'],fake)
        self.assertEqual(done['state'],'completed',done.get('error'));self.assertTrue(seen,'the structure packet carries verified_units')
        self.assertIn('without reading them again',seen[0])
        self.assertEqual(len(seen),1,'one structure round: the cited lines needed no read')
        self.assertIn('lib',[n['id'] for n in analysis_run.store.branch_bundle(self.raw(),'dev').get('system',{}).get('nodes',[])])

    def same_board(self,done):
        live=analysis_run._run_board(done);opened=self.board()
        self.assertEqual(live['totals'],opened['totals']);self.assertEqual(live['repositories'][0]['units'],opened['repositories'][0]['units'])
        self.assertEqual(live['repositories'][0]['links'],opened['repositories'][0]['links'])

    def test_the_run_board_equals_the_reopened_board_after_a_failure_a_cancel_and_a_completion_that_adds_a_program_unit(self):
        self.large_map();board=self.board();job=self.prepare(intent={**self.intent(board,'all'),'max_calls':board['modes']['all']['calls']+20})
        def stop(_):
            if self.batches(calls)==1:analysis_run.cancel(job['id'])
        calls=[];cancelled=analysis_run.run(job['id'],self.executor(calls,after=stop))
        self.assertEqual(cancelled['state'],'cancelled');self.same_board(cancelled)
        with patch.object(analysis_run,'_save',side_effect=ValueError('merge')):
            failed=analysis_run.run(analysis_run.retry(job['id'])['id'],self.executor([]))
        self.assertEqual(failed['state'],'completed');self.assertTrue(analysis_run._map_gaps(failed));self.same_board(failed)
        done=analysis_run.run(self.prepare(intent=self.intent(self.board(),'all'))['id'],self.executor([]))
        self.assertEqual(done['state'],'completed',done.get('error'));self.same_board(done)
        self.assertIn('program:api',self.states())  # the structure introduced a unit, and both boards list it in the same place

    def test_records_saved_before_budgets_and_local_units_still_open_continue_and_retry(self):
        job=self.prepare(intent=self.intent());calls=[]
        def stop(count):
            if count==3:analysis_run.cancel(job['id'])
        analysis_run.run(job['id'],self.executor(calls,after=stop))
        with analysis_run.locked():
            old=analysis_run.read(job['id']);old.pop('family',None);old.pop('budget')
            for catalog in old['units'].values():
                catalog.pop('links',None);catalog['coverage'].pop('local',None)
                for unit in catalog['units']:unit.pop('reading',None)
            analysis_run.write(old)
        self.assertIsNone(self.board()['budget']);self.assertEqual(analysis_run._run_board(analysis_run.read(job['id']))['budget'],None)
        again=analysis_run.retry(job['id']);self.assertEqual((again['budget']['limit'],again['budget']['used_before']),(again['intent']['max_calls'],0))
        self.assertEqual(analysis_run.run(again['id'],self.executor([]))['state'],'completed')

    def test_after_a_change_a_card_asks_only_for_the_affected_unit(self):
        first=[];self.explain_everything(first)
        (self.repo/'lib/m0.py').write_text('def lib_0():\n    return 42\n')
        self.git('add','-A');self.git('commit','-qm','Change lib');self.publish_index()
        second=[];done=self.cards(*[i for i,s in self.states().items() if not i.startswith('task:') and s!='saved'],calls=second)
        self.assertEqual(done['state'],'completed',done.get('error'))
        asked={r['resource'] for c in second for r in (c.get('resources') or [c])}
        self.assertEqual(asked,{'folder:lib'},asked)

class StructureRepair(unittest.TestCase):
    """Duplicate nodes saved before spelling-based merging existed: merged only when the content says they are one thing."""
    def node(self,id,name,code=(),kind='program',ev=(),uses=()):
        return {'id':id,'name':name,'kind':kind,'code':list(code),'uses':list(uses),'ev':[{'file':f,'line':l,'quote':q,'ok':True} for f,l,q in ev],'unknown':[]}
    def link(self,a,b,label,ev=()):return {'from':a,'to':b,'label':label,'style':'','sure':'code','ev':[{'file':f,'line':l,'quote':q,'ok':True} for f,l,q in ev]}
    def system(self):
        return {'language':'en','commit':'c','nodes':[
            self.node('web_api','API server',['api'],ev=[('api/app.py',1,'app=App()')],uses=['pg']),
            self.node('web-api','API server (v2)',['api','api/db'],ev=[('api/app.py',1,'app=App()'),('api/db.py',3,'conn')],uses=['p_g']),
            self.node('queue_worker','Queue worker',['api'],ev=[('compose.yml',9,'worker:')]),
            self.node('queue-worker','Queue worker',['api'],ev=[('compose.yml',9,'worker:')]),
            self.node('old_job','Old job',['legacy'],ev=[('a.py',1,'x')]),
            self.node('old-job','New job',['api'],ev=[('b.py',1,'y')]),   # same spelling, different thing: kept apart
            self.node('database','Database',kind='store',ev=[('compose.yml',3,'db:')])],
            'externals':[{'id':'pg','name':'Postgres','ev':[{'file':'c.py','line':1,'quote':'pg'}]},{'id':'p_g','name':'Postgres','ev':[{'file':'c.py','line':2,'quote':'pg2'}]}],
            'links':[self.link('web_api','database','reads',[('api/db.py',3,'conn')]),self.link('web-api','database','reads',[('api/db.py',7,'read')]),
                     self.link('queue-worker','web_api','calls',[('compose.yml',9,'worker:')]),self.link('web_api','web-api','same',[('z',1,'z')]),
                     self.link('old-job','database','writes',[('b.py',2,'w')])],
            'others':[{'text':'x'}],'unknown':[{'text':'old note','needs':'read'}]}

    def test_only_identity_checked_duplicates_merge_and_nothing_is_lost(self):
        before=self.system();fresh=copy.deepcopy(before)
        merged,report=analysis_run.merge_duplicate_structure(before)
        self.assertEqual(before,fresh)  # the input is never changed in place
        self.assertEqual(report['before'],{'nodes':7,'externals':2,'links':5});self.assertEqual(report['after'],{'nodes':5,'externals':1,'links':3})
        ids=[n['id'] for n in merged['nodes']]
        self.assertIn('web_api',ids);self.assertNotIn('web-api',ids);self.assertEqual(len({'queue_worker','queue-worker'}&set(ids)),1)  # the linked copy keeps its id
        self.assertTrue({'old_job','old-job'}<=set(ids))  # contradicting code folders: ambiguous, kept apart
        self.assertEqual([a['ids'] for a in report['ambiguous']],[['old_job','old-job']])
        api=next(n for n in merged['nodes'] if n['id']=='web_api')
        self.assertEqual(api['code'],['api','api/db']);self.assertEqual(len(api['ev']),2);self.assertEqual(sorted(api['uses']),['pg'])
        self.assertTrue(any('API server (v2)' in u['text'] for u in api['unknown']))  # the other name is kept in unknown
        reads=[l for l in merged['links'] if l['label']=='reads'];self.assertEqual(len(reads),1);self.assertEqual(len(reads[0]['ev']),2)
        self.assertEqual(next(l for l in merged['links'] if l['label']=='calls')['from'],'queue-worker');self.assertEqual(next(l for l in merged['links'] if l['label']=='calls')['to'],'web_api')
        self.assertEqual(report['dropped_self_links'],1);self.assertTrue(any('same' in u['text'] for u in merged['unknown']))  # a link between the two copies is noted, not silently lost
        self.assertEqual(merged['others'],before['others'])
        ids=set(ids)|{x['id'] for x in merged['externals']}
        self.assertTrue(all(l['from'] in ids and l['to'] in ids for l in merged['links']))
        again,second=analysis_run.merge_duplicate_structure(merged);self.assertEqual(second['merged'],[]);self.assertEqual(again,merged)  # a second repair changes nothing

    def test_repair_keeps_a_copy_writes_a_record_and_leaves_the_hand_written_structure_and_other_data_alone(self):
        import tempfile
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as root:
            home=Path(root)/'demo';home.mkdir()
            dev={'commit':'c','task_outputs':{'system':self.system(),'groups':{'groups':[]},'jobs':{'nodes':{}}}}
            (home/'dev.json').write_text(json.dumps(dev));(home/'system.hand.json').write_text('{"nodes":[]}')
            digest=lambda:{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in home.iterdir() if p.is_file() and p.name!='.project.lock'}
            with patch.object(analysis_run.mapcore,'ROOT',root),patch.object(analysis_run,'active',lambda:{'active':False}):
                before=digest();report=analysis_run.repair_structure('demo')
                self.assertFalse(report['applied']);self.assertEqual(digest(),before)  # a dry run writes nothing
                with patch.object(analysis_run,'active',lambda:{'active':True}),self.assertRaisesRegex(analysis_run.RunError,'running'):analysis_run.repair_structure('demo',apply=True)
                self.assertEqual(digest(),before)
                report=analysis_run.repair_structure('demo',apply=True)
                self.assertTrue(report['applied']);self.assertEqual(json.loads((home/report['backup']).read_text()),dev)  # the original is kept as it was
                saved=json.loads((home/'dev.json').read_text())
                self.assertEqual(len(saved['task_outputs']['system']['nodes']),5)
                self.assertEqual({k:v for k,v in saved['task_outputs'].items() if k!='system'},{k:v for k,v in dev['task_outputs'].items() if k!='system'})
                self.assertEqual(digest()['system.hand.json'],before['system.hand.json'])
                self.assertEqual(len(list(home.glob('structure-repair-*.json'))),1)
                self.assertEqual(analysis_run.repair_structure('demo',apply=True)['merged'],[])  # nothing left to repair


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
