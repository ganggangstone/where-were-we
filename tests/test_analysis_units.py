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
import analysis_label
import analysis_run
import analysis_units
import test_lang_rules as lang_rules_test
import structure_index
from test_analysis_run import AnalysisRun as _Fixture
_setup,_git,_raw=_Fixture.setUp,_Fixture.git,_Fixture.raw
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
    """분석하기: reading rules, labels and structure from the local map summary, saved as each answer arrives. Fake executors only."""
    git=_git
    raw=_raw
    PATHS=('/orders','/reports','/users')

    def setUp(self):
        _setup(self)
        (self.repo/'ui.ts').write_text('\n'.join(f"export function {p[1:]}(){{return fetch('{p}')}}" for p in self.PATHS))
        (self.repo/'api.py').write_text('from fastapi import FastAPI\napp=FastAPI()\nMAIL=boto3.client("ses")\n'+'\n'.join(f"@app.get('{p}')\ndef {p[1:]}():pass" for p in self.PATHS))
        for folder in ('lib','tools'):
            (self.repo/folder).mkdir()
            for i in range(3):(self.repo/folder/f'm{i}.py').write_text(f'def {folder}_{i}():\n    return {i}\n')
        (self.repo/'.env').write_text('TOKEN=secret\n');(self.repo/'logo.png').write_bytes(b'\x89PNG')
        self.save_code()

    def save_code(self):
        self.git('add','-A');self.git('commit','-qm','Full analysis fixture')
        repo=analysis_run.store.config('demo')['repositories'][0];raw=self.raw()
        raw['dev']['structure_index']=structure_index.build(str(self.repo),self.git('rev-parse','HEAD').strip())
        raw['dev']['commit']=self.git('rev-parse','HEAD').strip()
        analysis_run.store.publish('demo','service',raw,{'fingerprint':analysis_run.store.fingerprint(repo)})

    def board(self):
        analysis_run.unit_signals('demo','service','dev','en')
        return analysis_run.unit_board('demo','service','dev','en')

    def executor(self,calls,fail=lambda prompt:False,rules=None):
        def fake(prompt,*,cancelled,timeout):
            self.assertFalse(cancelled());self.assertNotIn(str(self.repo),prompt)
            calls.append(prompt)
            if fail(prompt):raise RuntimeError('no reply')
            if prompt.startswith('You write line-based reading rules'):return json.dumps(rules)
            if prompt.startswith('You are an analysis-only JSON producer'):
                packet=json.loads(prompt.split('\n',1)[1]);line=packet['sources'][0]['lines'][0]
                return {'items':[{'name':'Feature','role':'Role','description':'Does something','ref':line[0] if isinstance(line,list) else line['ref']}]}
            payload=json.loads(prompt[prompt.index('{"description"'):])
            if prompt.startswith('You build the service structure'):
                refs=[r for g in payload['groups'] for r in g['units']]
                ev=[d[0] for g in payload['groups'] for d in g['declarations']][:1]
                return {'programs':[{'name':'Service','kind':'program','what':'Runs it','units':refs,'ev':ev},{'name':'Ghost','units':[99999]}],'links':[]}
            refs=[u[0] for u in payload['units']]
            return {'units':[{'ref':r,'name':f'Name {r}','what':'Does one thing'} for r in refs]+[{'ref':99999,'name':'Invented'}],
                    'groups':[{'name':'Everything','description':'All of it','units':refs}],
                    'requests':[{'ref':q[0],'name':f'Request {q[3]}'} for q in payload['requests']],
                    'programs':[{'name':'Service','kind':'program','what':'Runs it','units':refs,'ev':[d[0] for u in payload['units'] for d in u[5]][:1]+[99999]}],'links':[],
                    'externals':[{'name':'Mail service','what':'Sends mail','ev':[x[0] for x in payload['externals']][:1],'users':[0]}]}
        return fake

    def analyse(self,calls,**kwargs):
        job=analysis_run.prepare('demo',lang='en',repository='service',intent={'task':'full','targets':[]})
        done=analysis_run.run(job['id'],self.executor(calls,**kwargs))
        return job,done

    def test_full_flow_labels_every_unit_with_the_announced_calls_and_saves_the_map_shapes(self):
        before=self.board();calls=[]
        job,done=self.analyse(calls)
        self.assertEqual(done['state'],'completed')
        self.assertEqual(len(calls),job['announced']['total']);self.assertEqual(before['calls']['total'],job['announced']['total'])
        self.assertEqual(job['announced'],{'rules':0,'labeling':1,'structure':0,'unit':0,'total':1})
        rows=self.board()['repositories'][0]['units']
        named=[r for r in rows if not r[0].startswith('task:') and r[4]!='local']
        self.assertTrue(named and all(r[2].startswith('Name ') and r[6]=='Does one thing' for r in named))
        # A unit 분석하기 named is done for the run; only a detailed explanation, asked per unit, is still possible.
        self.assertEqual({r[4] for r in named},{'named'})
        totals=self.board()['totals'];self.assertEqual((totals['named'],totals['pending']),(len(named),0))
        self.assertEqual({r[0]:r[4] for r in rows if r[0].startswith('task:')},{'task:groups':'saved','task:system':'saved'})
        part=next(iter(analysis_run.read(job['id'])['labels']['service']['parts'].values()))
        self.assertNotIn('Invented',[v['name'] for v in part['units'].values()]);self.assertEqual(part['dropped'],2)  # the invented unit and the unknown evidence ref
        raw=self.raw();system=raw['system.ai'] if (raw.get('system.ai') or {}).get('basis') else raw['system']
        self.assertEqual([n['name'] for n in system['nodes']],['Service']);self.assertEqual(system['basis'],'structure_summary')
        self.assertEqual(([x['name'] for x in system['externals']],system['nodes'][0]['uses']),(['Mail service'],['x1']))  # an outside service the answer cited from the offered lines is kept
        self.assertEqual([(e['file'],e['line'],e['origin']) for e in system['externals'][0]['ev']],[('api.py',3,'local_signal')])
        # The model cited an evidence ref; local code filled the file, line and literal text of the pinned commit.
        ev=system['nodes'][0]['ev'];self.assertEqual((len(ev),ev[0]['origin']),(1,'cited'))
        self.assertEqual((self.repo/ev[0]['file']).read_text().splitlines()[ev[0]['line']-1].strip(),ev[0]['quote'])
        self.assertEqual(raw['groups']['request_names'],{f'api.py::{p[1:]}':f'Request {p}' for p in self.PATHS})
        # Pressing again with nothing changed sends nothing; the reopened board equals what the run saved.
        again=[];job,done=self.analyse(again)
        self.assertEqual((again,job['announced']['total'],done['state']),([],0,'completed'))
        self.assertEqual(self.board()['repositories'][0]['units'],rows)

    def test_progress_writes_that_only_count_a_call_reuse_the_board_and_the_saved_board_equals_a_fresh_one(self):
        self.board();built=[];saves=[];real_board,real_save=analysis_run.unit_board,analysis_run._save_progress
        with patch.object(analysis_run,'unit_board',lambda *a,**k:built.append(1) or real_board(*a,**k)),\
             patch.object(analysis_run,'_save_progress',lambda *a,**k:saves.append(1) or real_save(*a,**k)):job,done=self.analyse([])
        self.assertEqual(done['state'],'completed');self.assertLess(len(built),len(saves))
        saved=analysis_run.status(job['id'],view='progress')['unit_board'];analysis_run._BOARD.clear()
        self.assertEqual(saved,analysis_run._progress(analysis_run.read(job['id']))['unit_board'])
        self.assertEqual(saved['used'],{'labeling':1})

    def test_a_split_summary_labels_each_area_then_builds_the_structure_and_one_failed_part_leaves_the_rest(self):
        with patch.object(analysis_label,'BOUND',300):
            calls=[];first=[]
            def fail(prompt):
                if prompt.startswith('You label') and not first:first.append(prompt)
                return prompt in first
            job,done=self.analyse(calls,fail=fail)
            self.assertEqual(done['state'],'completed')
            announced=job['announced']
            self.assertGreater(announced['labeling'],1);self.assertEqual(announced['structure'],1)
            self.assertEqual(len(calls),announced['total']+1)  # the failed part was retried once
            self.assertEqual([g['part'] for g in done['gaps']],['labeling:0'])
            saved=analysis_run.read(job['id'])['labels']['service']
            self.assertEqual(len(saved['parts']),announced['labeling']-1);self.assertEqual(saved['structure']['dropped'],2)  # the Ghost program's unknown ref and the program left empty
            states={r[0]:r[4] for r in self.board()['repositories'][0]['units']}
            self.assertEqual(states['task:groups'],'saved');self.assertEqual(states['task:system'],'saved')
            # Only the missing part is asked again.
            again=[];job,_=self.analyse(again)
            self.assertEqual(job['announced']['labeling'],1);self.assertEqual(len(again),job['announced']['total'])

    def test_another_language_gets_its_reading_rules_first_then_its_links(self):
        for name,text in {'app/main.rb':"require_relative 'models/user'\nclass App\nend\n",'app/models/user.rb':'class User\n  def name\n  end\nend\n',
                          'app/models/order.rb':"require_relative 'user'\nclass Order\nend\n",'app/models/item.rb':'class Item\nend\n'}.items():
            (self.repo/name).parent.mkdir(parents=True,exist_ok=True);(self.repo/name).write_text(text)
        self.save_code()
        calls=[];job,done=self.analyse(calls,rules=lang_rules_test.RUBY)
        self.assertEqual(job['announced']['rules'],1);self.assertEqual(len(calls),job['announced']['total'])
        self.assertTrue(calls[0].startswith('You write line-based reading rules'))
        self.assertEqual(self.board()['repositories'][0]['missing_rules'],[])
        index=self.raw()['dev']['structure_index']  # the refreshed snapshot carries the rule-read links
        self.assertIn(('app/main.rb','app/models/user.rb'),{(e['file'],e['target']) for e in index['imports']})
        self.assertIn('"User"',calls[-1])  # the labeling summary carries the declarations the rules read
        # The saved snapshot (확인 범위) names the language the new rules read, without pressing refresh.
        self.assertIn('ruby',{k.lower() for k in self.raw()['dev']['structure_index']['coverage']['languages']})
        again=[];job,done=self.analyse(again,fail=lambda prompt:True)
        self.assertEqual((again,job['announced']['total']),([],0))

    def test_rules_saved_earlier_reach_the_snapshot_on_the_next_run(self):
        for name,text in {'app/main.rb':"require_relative 'models/user'\nclass App\nend\n",'app/models/user.rb':'class User\nend\n',
                          'app/models/order.rb':'class Order\nend\n','app/models/item.rb':'class Item\nend\n'}.items():
            (self.repo/name).parent.mkdir(parents=True,exist_ok=True);(self.repo/name).write_text(text)
        self.save_code();analysis_run.lang_rules.save('ruby',lang_rules_test.RUBY)  # e.g. by another project; this snapshot was read without them
        self.assertNotIn('ruby',self.raw()['dev']['structure_index']['coverage']['languages'])
        calls=[];job,done=self.analyse(calls)
        self.assertEqual((job['announced']['rules'],done['state']),(0,'completed'))
        self.assertIn('ruby',self.raw()['dev']['structure_index']['coverage']['languages'])

    def test_a_finished_run_leaves_nothing_for_the_board_or_the_chat_request(self):
        calls=[];job,done=self.analyse(calls);self.assertEqual(done['state'],'completed')
        # The open panel reads the finished run's own board: its saved labels count, so nothing is left to call.
        self.assertEqual(analysis_run.status(project='demo',repository='service',lang='en',view='catalog')['unit_board']['calls']['total'],0)
        self.assertEqual(analysis_run.status(project='demo',repository='service',lang='en',view='latest'),{'id':job['id'],'state':'completed'})
        plan=analysis_run.ai_extract.plan('demo','dev','en','service')
        self.assertFalse({t['task'] for t in plan['tasks']}&{'analysis','system','groups'},plan['tasks'])

    def test_route_rules_add_route_units_inside_the_announced_partition(self):
        for name,text in {'web/app.rb':"require_relative 'store'\nget '/carts' do\nend\npost '/carts' do\nend\n",'web/store.rb':'class Store\nend\n',
                          'web/item.rb':'class Item\nend\n','spec/app_spec.rb':"get '/from-a-test' do\nend\n"}.items():
            (self.repo/name).parent.mkdir(parents=True,exist_ok=True);(self.repo/name).write_text(text)
        self.save_code()
        rules={**lang_rules_test.RUBY,'routes':[{'regex':r'''^\s*(get|post)\s+['"](/[^'"]*)['"]''','method':1,'path':2}]}
        with patch.object(analysis_label,'BOUND',300):
            calls=[];job,done=self.analyse(calls,rules=rules)
        self.assertEqual(done['state'],'completed',done.get('error'))
        self.assertEqual(len(calls),job['announced']['total'])  # the partition announced before the rules still holds
        index=self.raw()['dev']['structure_index']  # the refreshed snapshot carries the rule-read links
        self.assertEqual({(r['method'],r['path']) for r in index['service_flow']['registered_routes'] if r['server']['file'].endswith('.rb')},
                         {('GET','/carts'),('POST','/carts')})  # the route in a test file is left out
        rows={r[0]:r for r in self.board()['repositories'][0]['units']}
        self.assertTrue(rows['route:/carts'][2].startswith('Name '))

    def test_a_second_press_after_route_rules_sends_nothing(self):
        for name,text in {'web/app.rb':"get '/carts' do\nend\n",'web/store.rb':'class Store\nend\n','web/item.rb':'class Item\nend\n'}.items():
            (self.repo/name).parent.mkdir(parents=True,exist_ok=True);(self.repo/name).write_text(text)
        self.save_code()
        rules={**lang_rules_test.RUBY,'routes':[{'regex':r'''^\s*(get|post)\s+['"](/[^'"]*)['"]''','method':1,'path':2}]}
        calls=[];job,done=self.analyse(calls,rules=rules)
        self.assertEqual((job['announced']['rules'],job['announced']['labeling'],len(calls),done['state']),(1,1,2,'completed'))
        rows=self.board()['repositories'][0]['units']
        self.assertTrue(rows and any(r[0]=='route:/carts' for r in rows))
        again=[];job,done=self.analyse(again,fail=lambda prompt:True)  # the route units the rules added keep the part's key
        self.assertEqual((again,job['announced']['total'],done['state']),([],0,'completed'))
        self.assertEqual(self.board()['repositories'][0]['units'],rows)

    def test_failed_reading_rules_keep_the_folder_map_and_say_so(self):
        for i in range(4):(self.repo/f'app/m{i}.rb').parent.mkdir(exist_ok=True);(self.repo/f'app/m{i}.rb').write_text(f'class M{i}\nend\n')
        self.save_code()
        calls=[];job,done=self.analyse(calls,rules={'extensions':[]})
        self.assertEqual(done['state'],'completed');self.assertEqual(done['gaps'][0]['part'],'rules:ruby')
        self.assertIn('folder:app',[r[0] for r in self.board()['repositories'][0]['units']])

    def test_a_file_whose_name_is_not_utf8_is_skipped_and_counted_and_the_run_completes(self):
        import os,subprocess  # the file system refuses such a name; git keeps any bytes, so write the entry into the index
        oid=subprocess.run(['git','-C',str(self.repo),'hash-object','-w','--stdin'],input=b'def bad():\n    return 0\n',capture_output=True,check=True).stdout.strip()
        subprocess.run(['git','-C',str(self.repo),'update-index','--index-info'],input=b'100644 '+oid+b'\tlib/bad\xff.py\n',check=True)
        subprocess.run(['git','-C',str(self.repo),'update-index','--skip-worktree',os.fsdecode(b'lib/bad\xff.py')],check=True)  # so add -A keeps it
        self.save_code()
        calls=[];job,done=self.analyse(calls)
        self.assertEqual(done['state'],'completed');self.assertEqual(len(calls),job['announced']['total'])
        self.assertIn(b'lib/bad\xff.py',subprocess.run(['git','-C',str(self.repo),'ls-tree','-rz','HEAD'],capture_output=True).stdout)
        unsupported=lambda ref:structure_index.build(str(self.repo),self.git('rev-parse',ref).strip())['coverage']['unsupported_files']
        self.assertEqual(unsupported('HEAD'),unsupported('HEAD~1')+1)
        unit=next(r[0] for r in self.board()['repositories'][0]['units'] if r[0]=='folder:lib')
        job=analysis_run.prepare('demo',lang='en',repository='service',intent={'task':'full','targets':[],'only':[{'repository':'service','target':unit}]})
        self.assertEqual(analysis_run.run(job['id'],self.executor([]))['state'],'completed')

    def test_an_opened_unit_is_explained_with_one_call_and_no_confirmation(self):
        unit=next(r[0] for r in self.board()['repositories'][0]['units'] if r[1]=='folder' and r[4]=='pending')
        job=analysis_run.prepare('demo',lang='en',repository='service',intent={'task':'full','targets':[],'only':[{'repository':'service','target':unit}]})
        self.assertEqual(job['announced']['total'],1)
        calls=[];done=analysis_run.run(job['id'],self.executor(calls))
        self.assertEqual((done['state'],len(calls)),('completed',1))
        self.assertEqual({r[0]:r[4] for r in self.board()['repositories'][0]['units']}[unit],'saved')

    def test_an_opened_route_marks_the_other_routes_lines_as_context(self):
        job=analysis_run.prepare('demo',lang='en',repository='service',intent={'task':'full','targets':[],'only':[{'repository':'service','target':'route:/reports'}]})
        calls=[];done=analysis_run.run(job['id'],self.executor(calls))
        self.assertEqual(done['state'],'completed',done.get('error'))
        packet=json.loads(calls[0].split('\n',1)[1]);rows={r['line']:r for s in packet['sources'] if s['file']=='api.py' for r in s['lines']}
        own=[n for n,r in rows.items() if "'/reports'" in r['text'] or 'def reports' in r['text']]
        self.assertTrue(own and not any(rows[n].get('context') for n in own),rows)
        others=[r for r in rows.values() if '/orders' in r['text'] or '/users' in r['text']]
        self.assertTrue(others and all(r.get('context') for r in others),rows)
        self.assertIn('context:true',packet['prompt'])

    def test_an_opened_unit_sends_its_bodies_whole_and_imported_code_as_context(self):
        (self.repo/'lib/m0.py').write_text('from tools.m1 import tools_1\ndef long_job():\n'+''.join(f'    step_{i} = {i}  # step\n' for i in range(60))+'    tools_1()  # the call\n')
        self.save_code()
        unit=next(r[0] for r in self.board()['repositories'][0]['units'] if r[0].startswith('folder:lib'))
        job=analysis_run.prepare('demo',lang='en',repository='service',intent={'task':'full','targets':[],'only':[{'repository':'service','target':unit}]})
        calls=[];done=analysis_run.run(job['id'],self.executor(calls))
        self.assertEqual(done['state'],'completed',done.get('error'))
        packet=json.loads(calls[0].split('\n',1)[1]);files={s['file']:s for s in packet['sources']}
        self.assertIn('tools_1()  # the call',[r[2] for r in files['lib/m0.py']['lines']])  # past the 24 sampled rows
        self.assertTrue(files['tools/m1.py']['context'] and not files['lib/m0.py'].get('context'))


class LinkEvidence(unittest.TestCase):
    def test_outside_services_named_in_code_and_connected_codes_are_offered_locally(self):
        texts={'api/mail.py':"import boto3\nstore=boto3.client('s3')\nKEY=os.environ['STRIPE_API_KEY']\n# redis://only-a-comment\nsubprocess.run(['ffmpeg','-i',x])\nDOC='https://www.w3.org/x'\n"}
        hints=analysis_label.hints(texts)
        # An SDK name counts only as an import, a call on it or a whole string, not as a word inside text.
        self.assertEqual([h[0] for h in analysis_label.hints({'a.py':'import stripe\nWORDS = r"stripe[sd]?|plaid"\nopenai.chat(x)\nNAME = "anthropic words"\n'})],['openai','stripe'])
        self.assertEqual([analysis_label.program_file(f) for f in ('api/mail.py','run.sh','site/x.css','page.html','.env.dev.example','tests/a.py','docs/a.md')],
                         [True,True,False,False,False,False,False])
        self.assertEqual(hints,[('STRIPE','api/mail.py',3),('ffmpeg','api/mail.py',5),('s3','api/mail.py',2)])  # comments and well-known hosts are not services
        catalog={'units':[{'id':'folder:api','kind':'folder','name':'api','files':['api/mail.py'],'file_count':1},
                          {'id':'folder:skills','kind':'folder','name':'skills','files':['skills/a.md'],'file_count':1,'reading':'local'}]}
        spots={}
        whole=analysis_label.summary(catalog,{'files':[]},'',(),spots,hints,[['Shop','sends requests to']])
        self.assertEqual(whole['externals'],[[e,0,n] for e,n in zip(sorted(spots['evidence'])[-3:],('STRIPE','ffmpeg','s3'))])
        self.assertEqual([spots['evidence'][x[0]] for x in whole['externals']],[['api/mail.py',3],['api/mail.py',5],['api/mail.py',2]])
        self.assertEqual((whole['codes'],[u[1] for u in whole['units']]),([['Shop','sends requests to']],['folder','local']))  # a skills folder is named, not hidden
        prompt=analysis_label.prompt('labeling',whole,'ko',True)
        self.assertIn('non-developer',prompt);self.assertIn('externals rows',prompt)
        structure=analysis_label.structure_input(whole,[{'groups':[{'name':'Mail','description':'','units':[0]}]}],{0:0})
        self.assertEqual([(g['name'],g['units']) for g in structure['groups']],[('Mail',[0]),('(not grouped)',[1])])  # the skills folder reaches the structure call

    """A link's evidence is the local line that makes it; without one, the cited declarations are kept as related code."""
    def test_only_links_backed_by_local_lines_are_drawn_and_each_folder_has_one_program(self):
        catalog={'units':[{'id':'folder:web','kind':'folder','files':['web/a.ts','web/b.ts']},{'id':'folder:api','kind':'folder','files':['api/s.py']},
                          {'id':'folder:jobs','kind':'folder','files':['jobs/j.py']},{'id':'file:run.py','kind':'file','files':['run.py']}]}
        labels={'units':{},'groups':[],'programs':[{'name':n,'kind':'program','what':'','units':u,'ev':[['api/s.py',2],['api/s.py',2]]} for n,u in
                                                   (('Web',['folder:web']),('API',['folder:api','file:run.py']),('Jobs',['folder:jobs']),('Again',['folder:web']))],
                'links':[{'from':0,'to':1,'label':'calls'},{'from':2,'to':1,'label':'uses'},{'from':1,'to':0,'label':'backwards'}],
                'externals':[{'name':'Mail','what':'sends mail','ev':[['api/s.py',5]],'users':[1]}]}
        flows=[('web/b.ts',4,'api/s.py'),('web/a.ts',7,'api/s.py'),('web/a.ts',3,'api/s.py'),('web/a.ts',1,'web/b.ts')]  # the most-connected file first
        line=lambda file,number:f'{file} line {number}'
        _,system=analysis_label.shapes(catalog,labels,line,flows)
        rows=lambda ev:[(e['file'],e['line'],e['quote'],e['origin']) for e in ev]
        # Only web -> api has import lines; a link the model named without local lines is not drawn.
        self.assertEqual([(l['from'],l['to'],rows(l['ev'])) for l in system['links']],
                         [('p1','p2',[('web/a.ts',3,'web/a.ts line 3','local_link'),('web/b.ts',4,'web/b.ts line 4','local_link')])])
        self.assertEqual([(n['name'],n['code']) for n in system['nodes']],[('Web',['web']),('API',['.','api']),('Jobs',['jobs'])])  # 'Again' repeats web: dropped
        self.assertEqual(rows(system['nodes'][1]['ev']),[('api/s.py',2,'api/s.py line 2','cited')])  # duplicate evidence once
        self.assertEqual((system['externals'][0]['name'],system['nodes'][1]['uses']),('Mail',['x1']))
        # A connected code is a cross-code line, not an outside service; style sheets, samples and docs are no service evidence.
        labels['externals']+=[{'name':'Shop App','what':'x','ev':[['api/s.py',6]],'users':[1]},{'name':'Pay','what':'x','ev':[['mock/x.css',2],['.env.example',3]],'users':[1]}]
        _,system=analysis_label.shapes(catalog,labels,line,flows,['shop-app-server'])
        self.assertEqual(([x['name'] for x in system['externals']],system['nodes'][1]['uses']),(['Mail'],['x1']))
        index={'imports':[{'file':'tests/test_web.py','line':1,'target':'api/s.py'},{'file':'web/a.ts','line':3,'target':'api/s.py'}],
               'service_flow':{'connections':[{'client':{'file':'web/b.ts','line':4},'server':{'file':'api/s.py','line':2}}]}}
        self.assertEqual(analysis_label.edges(index),[('web/a.ts',3,'api/s.py'),('web/b.ts',4,'api/s.py')])  # a test file shows no connection


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
