"""App worker lifecycle with synthetic Git and injected executors; no real AI calls."""
import copy
import json
import os
from pathlib import Path
import sys
import time
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parent))
import analysis_run
import ai_extract
import briefing
import project
import test_ai_extract

class AnalysisRun(unittest.TestCase):
    setUp=test_ai_extract.Analysis.setUp
    git=test_ai_extract.Analysis.git
    EV={'file':'server/items.go','line':2,'quote':'db.Table("items").Create(item)'}
    SYSTEM={'nodes':[{'id':'api','name':'API','kind':'program','code':['server'],'ev':[EV],'jobs':[]}],
            'links':[],'externals':[],'others':[],'unknown':[]}
    GROUPS={'groups':[{'name':'Items','screens':['/items']}],'names':{},'request_names':{}}

    ROUTE='server/items.go::SaveItem'
    STEPS={'task':'steps','targets':[{'repository':'service','target':'@routes:["server/items.go::SaveItem"]'}]}

    def prepare(self,**kwargs):return analysis_run.prepare('demo',lang='en',**kwargs)
    def steps(self):return self.prepare(intent=self.STEPS)
    def seed_map(self):
        """Save the map, structure and groups directly; 분석하기 (full) owns how they are made."""
        data=copy.deepcopy(self.data)
        for route in data['backend_routes']:route.pop('steps',None)  # the steps are the detail these tests ask for
        req=ai_extract.request('demo','dev','en','service')
        ai_extract.record(**req['record_arguments'],result_json=json.dumps(test_ai_extract.agent_answer(req,data)))
        system={**self.SYSTEM,'nodes':[{k:v for k,v in n.items() if k!='jobs'} for n in self.SYSTEM['nodes']]}  # and so are the jobs
        for task,result in (('system',system),('groups',self.GROUPS)):
            req=ai_extract.task_request('demo',task,'dev','en','service');ai_extract.task_record(**req['record_arguments'],result_json=json.dumps(result))
    def pad(self,lines=13000):
        """Grow the route's own file past one input so its steps are sent in batches, then save the map of that commit."""
        f=self.repo/'server/items.go';f.write_text(f.read_text()+'// padding line\n'*lines)
        self.git('add','.');self.git('commit','-qm','Route file larger than one input')
        self.seed_map()
    def two_routes(self):
        """A second endpoint, so one steps intent with two targets makes two tasks."""
        (self.repo/'server/other.go').write_text('func Other() {}\nrouter.GET("/other", Other)\n')
        self.git('add','.');self.git('commit','-qm','Independent second endpoint')
        self.data['backend_routes'].append({'file':'server/other.go','line':2,'quote':'router.GET("/other", Other)',
            'method':'GET','path':'/other','function':'Other'})
        self.seed_map()
        return {'task':'steps','targets':[self.STEPS['targets'][0],{'repository':'service','target':'@routes:["server/other.go::Other"]'}]}
    def routes(self):return {'routes':{self.ROUTE:{'steps':[],'unknown':'No further steps established'}}}
    def raw(self):return project.raw_bundle(project.repository_folder('demo',project.config('demo')['repositories'][0],project.states('demo')))
    def fake(self,prompt,*,cancelled,timeout):
        self.assertFalse(cancelled());self.assertLessEqual(timeout,analysis_run.TASK_SECONDS)
        self.assertNotIn('record_arguments',prompt);self.assertNotIn(str(self.repo),prompt)
        payload=json.loads(prompt.split('\n',1)[1]);schema=payload['schema']
        if 'screens' in schema:
            request={'mode':payload['mode'],'inspect':payload.get('inspect',[]),'recheck':payload.get('recheck',[])}
            return json.dumps(test_ai_extract.agent_answer(request,self.data))
        if 'nodes' in schema:return json.dumps(self.SYSTEM)
        if 'groups' in schema:return json.dumps(self.GROUPS)
        if 'routes' in schema:return json.dumps({'routes':{k:{'steps':[],'unknown':'No further steps established'} for k in payload['input']['routes']}})
        self.fail('Unexpected task schema')

    def test_explicit_steps_target_only_and_retry_keeps_intent(self):
        (self.repo/'server/other.go').write_text('func Other() {}\nrouter.GET("/other", Other)\n')
        self.git('add','.');self.git('commit','-qm','Independent second endpoint')
        self.data['backend_routes'].append({'file':'server/other.go','line':2,'quote':'router.GET("/other", Other)',
            'method':'GET','path':'/other','function':'Other'})
        self.seed_map()
        intent={'task':'steps','targets':[{'repository':'service','target':'@routes:["server/items.go::SaveItem"]'}]}
        value=self.prepare(intent=intent)
        self.assertEqual([t['task'] for t in value['tasks']],['steps'])
        def bad(prompt,**kwargs):return {'routes':{'not/requested':{'steps':[],'unknown':'unknown'}}}
        before=self.raw();failed=analysis_run.run(value['id'],bad)
        self.assertEqual(failed['state'],'failed');self.assertEqual(self.raw(),before)
        again=analysis_run.retry(value['id']);self.assertEqual(again['intent'],intent)
        calls=[]
        def fake(prompt,**kwargs):
            p=json.loads(prompt.split('\n',1)[1]);calls.append(p)
            self.assertEqual(set(p['input']['routes']),{'server/items.go::SaveItem'})
            self.assertEqual({f['file'] for ss in p['snapshots'] for f in ss['files']},{'server/items.go'})
            return self.fake(prompt,**kwargs)
        done=analysis_run.run(again['id'],fake)
        self.assertEqual(done['state'],'completed',done.get('error'));self.assertEqual(len(calls),1)

    def test_cli_prepare_preserves_selected_intent_and_overview_keeps_proven_details(self):
        import subprocess
        self.seed_map()
        intent={'task':'steps','targets':[{'repository':'service','target':'/items'}]}
        argv=[sys.executable,'-B',str(Path(analysis_run.__file__)),'prepare','demo','--lang','en','--intent',json.dumps(intent)]
        result=subprocess.run(argv,env={**os.environ,'WHERE_WERE_WE_ROOT':str(self.home)},text=True,capture_output=True,check=True)
        value=json.loads(result.stdout);self.assertEqual(value['intent'],intent)
        done=analysis_run.run(value['id'],self.fake);self.assertEqual(done['state'],'completed',done.get('error'))
        flow=copy.deepcopy(self.raw()['dev']['task_outputs']['flows']['routes']['server/items.go::SaveItem'])
        (self.repo/'independent.txt').write_text('An independent file without route dependencies.\n')
        self.git('add','.');self.git('commit','-qm','Independent text change')
        self.seed_map()
        carried=self.raw()['dev']['task_outputs']['flows']['routes']['server/items.go::SaveItem']
        self.assertEqual(carried['steps'],flow['steps'])
        self.assertEqual(carried['verified_commit'],flow['commit'])
        self.assertEqual(carried['carried_from'],flow['commit'])

    def source_fake(self,prompt,**kwargs):
        """A steps reply for one packet, wrapped in the batch envelope when the input was split."""
        p=json.loads(prompt.split('\n',1)[1])
        return {'batch':p['batch']['id'],'covered':p['batch']['units'],'result':self.routes()} if 'batch' in p else self.routes()

    def test_large_batch_encoding_preserves_every_source_coordinate_and_omission(self):
        lines=[{'line':1,'text':'original "\t" line'},{'line':3,'text':'긴 줄의 일부','offset':2176}]
        omitted=[{'file':f'assets/image{i}.png','reason':'binary_asset'} for i in range(500)]
        _,units=analysis_run._units({'snapshots':[{'commit':'pinned','files':[{'file':'app','lines':lines}],'omitted':omitted}]})
        header={'source_line_format':'[line,text,offset?]'}
        packet=analysis_run._batch_payload(header,units,'batch')
        self.assertEqual(packet['snapshots'][0]['files'][0]['numbered_lines'],[[1,lines[0]['text']],[3,lines[1]['text'],2176]])
        self.assertEqual([entry for page in packet['context_pages'] for entry in page['value']],omitted)
        self.assertTrue(all(len(x)==16 for x in packet['batch']['units']))
        self.assertLess(len(packet['context_pages']),10)
        units[0]['id']=units[1]['id'][:16]+'x'*48
        self.assertEqual(analysis_run._batch_payload(header,units,'batch')['batch']['units'],[u['id'] for u in units])

    def test_bad_batch_coverage_claim_cancel_and_changed_pin_preserve_last_good_map(self):
        self.pad()
        for fault in ('missing','duplicate','quote','route','cancel','commit'):
            with self.subTest(fault=fault):
                before=self.raw();value=self.steps();calls=[]
                def executor(prompt,**kwargs):
                    answer=self.source_fake(prompt,**kwargs);calls.append(prompt)
                    if len(calls)==2 or (len(calls)==3 and fault in ('quote','route')):
                        if fault=='missing':answer['covered']=[]
                        if fault=='duplicate':answer['covered']*=2
                        if fault=='quote':answer['result']['routes'][self.ROUTE]['steps']=[{'file':'server/items.go','line':1,'quote':'invented content','text':'Save','lane':'서버'}]
                        if fault=='route':answer['result']['routes']={'not/requested':{'steps':[],'unknown':'unknown'}}
                        if fault=='cancel':analysis_run.cancel(value['id'])
                        if fault=='commit':
                            f=self.repo/'server/items.go';f.write_text(f.read_text()+'more\n');self.git('add','.');self.git('commit','-qm','Change during batch')
                    return answer
                done=analysis_run.run(value['id'],executor)
                self.assertEqual(done['state'],'cancelled' if fault=='cancel' else 'failed',done.get('error'))
                self.assertEqual(self.raw(),before);self.assertGreaterEqual(len(calls),2)

    def test_small_invalid_nested_claims_are_not_silently_filtered(self):
        self.seed_map()
        jobs={'task':'jobs','targets':[{'repository':'service','target':'api'}]}
        for fault,intent in (('language',self.STEPS),('step_target',self.STEPS),('jobs_language',jobs)):
            with self.subTest(fault=fault):
                before=self.raw();value=self.prepare(intent=intent)
                def executor(prompt,**kwargs):
                    if fault=='language':return {**self.routes(),'lang':'ko'}
                    if fault=='step_target':return {'routes':{'unknown::handler':{'steps':[],'unknown':'Not established'}}}
                    return {'jobs':[],'unknown':[{'text':'No jobs established','needs':'read'}],'language':'ko'}
                done=analysis_run.run(value['id'],executor)
                self.assertEqual(done['state'],'failed',done.get('error'))
                self.assertEqual(self.raw(),before)

    def test_source_reads_and_literal_search_stay_inside_eligible_pinned_files(self):
        (self.repo/'big.source').write_text('p'*150000)
        (self.repo/'.env').write_text('PRIVATE_DO_NOT_SEND=credential\n')
        (self.repo/'link.source').symlink_to('/etc/passwd')
        self.git('add','.');self.git('commit','-qm','Pinned read eligibility fixture');self.pad()
        (self.repo/'untracked.source').write_text('UNTRACKED_DO_NOT_SEND\n')
        for file in ('../outside','.env','link.source','untracked.source'):
            with self.subTest(file=file):
                before=self.raw();value=self.steps()
                def denied(prompt,**kwargs):
                    p=json.loads(prompt.split('\n',1)[1]);self.assertNotIn('PRIVATE_DO_NOT_SEND',prompt);self.assertNotIn('UNTRACKED_DO_NOT_SEND',prompt)
                    return {'batch':p['batch']['id'],'covered':p['batch']['units'],'result':{},'needs':[{'file':file}]}
                done=analysis_run.run(value['id'],denied)
                self.assertEqual(done['state'],'failed');self.assertEqual(self.raw(),before)
        calls=[];searched=False
        def searching(prompt,**kwargs):
            nonlocal searched
            p=json.loads(prompt.split('\n',1)[1]);calls.append(p)
            self.assertNotIn('PRIVATE_DO_NOT_SEND',prompt);self.assertNotIn('UNTRACKED_DO_NOT_SEND',prompt)
            if not searched:
                searched=True
                return {'batch':p['batch']['id'],'covered':p['batch']['units'],'result':{},'needs':[{'query':'db.Table','start':1,'limit':1}]}
            return self.source_fake(prompt,**kwargs)
        done=analysis_run.run(self.steps()['id'],searching)
        self.assertEqual(done['state'],'completed',done.get('error'))
        self.assertTrue(any(page['value'].get('query')=='db.Table' and page['value']['total']==1 for p in calls for page in p.get('context_pages',[]) if isinstance(page['value'],dict)))

    def test_a_batch_that_keeps_requesting_reads_ends_with_what_it_found_and_says_so(self):
        self.pad();rounds=[]
        def endless(prompt,**kwargs):
            p=json.loads(prompt.split('\n',1)[1]);self.assertIn('batch',p);rounds.append(1)
            return {'batch':p['batch']['id'],'covered':p['batch']['units'],'needs':[{'query':'zz'+str(len(rounds)),'start':1,'limit':1}],
                    'result':{'jobs':[],'unknown':[{'text':'No jobs established by supplied source','needs':'read'}]}}
        value=self.prepare(intent={'task':'jobs','targets':[{'repository':'service','target':'api'}]})
        with patch.object(analysis_run,'MAX_READ_ROUNDS',2):done=analysis_run.run(value['id'],endless)
        self.assertEqual(done['state'],'completed',done.get('error'))
        self.assertIn('read rounds allowed',json.dumps(self.raw()['dev']['task_outputs']['jobs']['nodes']['api']['unknown']))

    def test_literal_searches_in_one_analysis_do_not_reread_pinned_blobs(self):
        import subprocess
        # The padding, a cited dependency of the route, fills the first batch, so its rounds carry only search hits from the other files.
        padding='a-padding.source';(self.repo/padding).write_text('ordinary unrelated source line\n'*9000)
        self.git('add','.');self.git('commit','-qm','Padding that splits the input')
        self.data['backend_routes'][0]['dependencies']=[{'file':padding,'line':1,'quote':'ordinary unrelated source line'}];self.seed_map()
        files=[padding,'pages/items.vue','server/items.go']
        names={self.git('rev-parse','HEAD:'+f).strip():f for f in files}
        needs=[{'query':'"/items"','start':1,'limit':1},{'query':'"/items"','start':2,'limit':1},{'query':'db.Table','start':1,'limit':1}]
        expected=[({'query':'"/items"','start':1,'total':2,'next':2},[('pages/items.vue',2,'fetch("/items", {method:"POST"})')]),
                  ({'query':'"/items"','start':2,'total':2,'next':None},[('server/items.go',4,'router.POST("/items", SaveItem)')]),
                  ({'query':'db.Table','start':1,'total':1,'next':None},[('server/items.go',2,' db.Table("items").Create(item)')])]
        answers=[];seen=set();first=None
        def executor(prompt,**kwargs):
            nonlocal first
            p=json.loads(prompt.split('\n',1)[1])
            first=first or p['batch']['id']
            pages=[page for page in p.get('context_pages',[]) if page.get('path')==['read_page']]
            if p['batch']['id']==first and len(pages)==1:
                hits=[(f['file'],line['line'],line['text']) for s in p.get('snapshots',[]) for f in s['files'] if f['file']!=padding for line in f['lines']]
                answers.append((pages[0]['value'],[hit for hit in hits if hit not in seen]));seen.update(hits)
            answer={'batch':p['batch']['id'],'covered':p['batch']['units'],'result':{}}
            if p['batch']['id']==first:
                if needs:answer['needs']=[needs.pop(0)]
                else:answer['result']=self.routes()
            return answer
        value=self.steps();blob_reads=[];real_popen=subprocess.Popen
        def observed(command,*args,**kwargs):
            # cat-file -s reads only the size; a future reader that hides object IDs from argv fails the exact count.
            if '-s' not in command:blob_reads.extend(names[arg] for arg in command if arg in names)
            return real_popen(command,*args,**kwargs)
        with patch('subprocess.Popen',observed):done=analysis_run.run(value['id'],executor)
        self.assertEqual(done['state'],'completed',done.get('error'))
        self.assertEqual(answers,expected)
        self.assertEqual({f:blob_reads.count(f) for f in files},{f:1 for f in files})

    def test_stateless_continuation_can_revisit_an_evicted_page_but_stops_cycles(self):
        self.pad()
        for sequence,should_finish,call_limit in (
                (['absent-A']*10, False, 3),
                (['absent-A', 'absent-B']*20, False, 5),
                (['absent-A', 'absent-B', 'absent-A'], True, 4)):
            with self.subTest(sequence=sequence[:4]):
                baseline=self.raw()
                run=self.steps()
                first_batch=None
                queried=[]
                def executor(prompt,**kwargs):
                    nonlocal first_batch
                    packet=json.loads(prompt.split('\n',1)[1])
                    batch=packet['batch']
                    answer={'batch':batch['id'],'covered':batch['units'],'result':{}}
                    first_batch=first_batch or batch['id']
                    if first_batch!=batch['id']:return answer
                    current_queries=[p['value']['query'] for p in packet.get('context_pages',[])
                                     if p['path']==['read_page']]
                    if queried:
                        self.assertIn(queried[-1],current_queries)
                    if len(queried)==2 and queried==['absent-A']*2:
                        self.assertEqual(batch['satisfied_needs'],[{'query':'absent-A'}])
                    if len(queried)<len(sequence):
                        query=sequence[len(queried)]
                        queried.append(query)
                        answer['needs']=[{'query':query}]
                    else:
                        answer['result']=self.routes()
                    return answer
                done=analysis_run.run(run['id'],executor)
                self.assertLessEqual(len(queried),call_limit)
                if should_finish:
                    self.assertEqual(done['state'],'completed',done.get('error'))
                    self.assertEqual(queried,sequence)
                else:
                    self.assertEqual(done['state'],'failed')
                    self.assertEqual(done['error']['code'],'invalid_result')
                    self.assertEqual(self.raw(),baseline)

    def test_evidence_accepts_literal_unicode_and_tab_in_tracked_path(self):
        path='작업\t명령.py'
        (self.repo/path).write_text('run_command()\n')
        self.git('add','.');self.git('commit','-qm','Add named command')
        commit=self.git('rev-parse','HEAD').strip()
        evidence={'file':path,'line':1,'quote':'run_command()'}
        analysis_run._strict_result('analysis',{'inspected':[evidence]},str(self.repo),commit)

    def test_same_read_notice_allows_current_packet_to_settle(self):
        self.pad()
        need={'query':'not-found','start':1,'limit':2}
        other={'query':'another-absent-term','start':1,'limit':1}
        notices=[]
        first_batch=None
        def executor(prompt,**kwargs):
            nonlocal first_batch
            p=json.loads(prompt.split('\n',1)[1]);batch=p['batch']
            first_batch=first_batch or batch['id']
            reply={'batch':batch['id'],'covered':batch['units'],'result':{}}
            if batch['id']==first_batch:
                if batch.get('satisfied_needs'):
                    notices.append(batch['satisfied_needs'])
                    self.assertTrue(any(page['value'].get('total')==0 for page in p.get('context_pages',[])
                                        if page['path']==['read_page']))
                    reply['result']=self.routes()
                else:
                    pages=[page['value']['query'] for page in p.get('context_pages',[])
                           if page['path']==['read_page']]
                    if not pages:reply['needs']=[need]
                    elif pages==[need['query']]:reply['needs']=[need,other]
                    else:
                        self.assertCountEqual(pages,[need['query'],other['query']])
                        reply['needs']=[need]
            return reply
        done=analysis_run.run(self.steps()['id'],executor)
        self.assertEqual(done['state'],'completed',done.get('error'))
        self.assertEqual(notices,[[need]])

    def read_source(self,commit,need,blobs,cancelled=None):
        units=analysis_run._needed(str(self.repo),commit,[need],cancelled,None,{},blobs)
        return [(u['value']['file'],line['line'],line['text']) for u in units if u['kind']=='source' for line in u['value']['lines']]

    def test_reused_source_keeps_full_lines_after_partial_reads_and_pages(self):
        (self.repo/'pages.txt').write_text('needle one\nplain\nneedle two\n')
        self.git('add','.');self.git('commit','-qm','Lines to page')
        commit=self.git('rev-parse','HEAD').strip();blobs={}
        self.assertEqual(self.read_source(commit,{'file':'pages.txt','start':2,'limit':1},blobs),[('pages.txt',2,'plain')])
        self.assertEqual(self.read_source(commit,{'query':'needle','start':2,'limit':1},blobs),[('pages.txt',3,'needle two')])
        self.assertEqual(self.read_source(commit,{'file':'pages.txt'},blobs),[('pages.txt',1,'needle one'),('pages.txt',2,'plain'),('pages.txt',3,'needle two')])
        self.assertEqual(self.read_source(commit,{'query':'needle'},blobs),[('pages.txt',1,'needle one'),('pages.txt',3,'needle two')])
        # A sloppy range from the model is clamped to a bounded read instead of failing the run.
        for bad in ({'start':0,'limit':999},{'start':-3,'limit':0},{'start':'2','limit':None},{'start':True,'limit':1.5}):
            self.assertEqual(self.read_source(commit,{'file':'pages.txt',**bad},blobs)[0][:2],('pages.txt',1))

    def test_selected_initial_source_does_not_limit_a_later_full_search(self):
        (self.repo/'chosen.txt').write_text('needle chosen\n');(self.repo/'other.txt').write_text('needle other\n')
        self.git('add','.');self.git('commit','-qm','Chosen and unchosen files')
        commit=self.git('rev-parse','HEAD').strip();blobs={}
        exported=analysis_run.export_source(str(self.repo),commit,selected={commit:{'chosen.txt'}},blobs=blobs)
        self.assertEqual([f['file'] for f in exported[0]['files']],['chosen.txt'])
        self.assertEqual(self.read_source(commit,{'query':'needle'},blobs),[('chosen.txt',1,'needle chosen'),('other.txt',1,'needle other')])

    def test_reused_source_stays_separate_between_commits(self):
        (self.repo/'state.txt').write_text('needle old\n');(self.repo/'removed.txt').write_text('needle removed\n')
        self.git('add','.');self.git('commit','-qm','Old state');old=self.git('rev-parse','HEAD').strip()
        (self.repo/'state.txt').write_text('needle new\n');(self.repo/'removed.txt').unlink()
        self.git('add','.');self.git('commit','-qm','New state');new=self.git('rev-parse','HEAD').strip()
        blobs={}
        exported=analysis_run.export_source(str(self.repo),new,[old],blobs=blobs)
        lines={s['commit']:{f['file']:[l['text'] for l in f['lines']] for f in s['files'] if f['file'] in ('state.txt','removed.txt')} for s in exported}
        self.assertEqual(lines,{new:{'state.txt':['needle new']},old:{'state.txt':['needle old'],'removed.txt':['needle removed']}})
        self.assertEqual(self.read_source(new,{'query':'needle'},blobs),[('state.txt',1,'needle new')])
        self.assertEqual(self.read_source(old,{'query':'needle'},blobs),[('removed.txt',1,'needle removed'),('state.txt',1,'needle old')])

    def test_reused_content_does_not_make_an_excluded_path_eligible(self):
        # One object ID at four paths: only the path and mode decide eligibility.
        text='needle shared'
        for name in ('plain.txt','.env','photo.png'):(self.repo/name).write_text(text)
        os.symlink(text,self.repo/'link.txt')
        self.git('add','-f','.');self.git('commit','-qm','One blob at excluded paths')
        commit=self.git('rev-parse','HEAD').strip();blobs={}
        self.assertEqual(self.read_source(commit,{'file':'plain.txt'},blobs),[('plain.txt',1,text)])
        self.assertEqual(self.read_source(commit,{'query':'needle'},blobs),[('plain.txt',1,text)])
        omitted={x['file']:x['reason'] for x in analysis_run.export_source(str(self.repo),commit,blobs=blobs)[0]['omitted']}
        self.assertEqual({k:omitted[k] for k in ('.env','photo.png','link.txt')},{'.env':'credential_file','photo.png':'binary_asset','link.txt':'not_regular_source'})
        with self.assertRaisesRegex(analysis_run.RunError,'not eligible'):self.read_source(commit,{'file':'.env'},blobs)  # a credential path is refused outright
        for name in ('photo.png','link.txt'):self.assertEqual(self.read_source(commit,{'file':name},blobs),[])  # other excluded paths are answered as unavailable, nothing is read

    def test_reused_binary_blob_stays_omitted_without_rereading(self):
        (self.repo/'data.bin').write_bytes(b'needle\x00')
        self.git('add','.');self.git('commit','-qm','Binary without a known suffix')
        commit=self.git('rev-parse','HEAD').strip();blobs={}
        for _ in range(2):
            omitted=analysis_run.export_source(str(self.repo),commit,blobs=blobs)[0]['omitted']
            self.assertIn({'file':'data.bin','reason':'binary'},omitted)
            with patch.object(analysis_run,'_git',wraps=analysis_run._git) as git:self.assertEqual(self.read_source(commit,{'query':'needle'},blobs),[])
            self.assertFalse([c for c in git.call_args_list if c.args[1]=='cat-file'])

    def test_cancellation_and_deadline_stop_a_search_over_reused_source(self):
        commit=self.git('rev-parse','HEAD').strip();blobs={}
        self.read_source(commit,{'query':'needle'},blobs)
        checks=[]
        self.read_source(commit,{'query':'needle'},blobs,lambda:checks.append(1) or False)
        # Every checkpoint of a fully reused search must still stop it, including the last one.
        for stop in range(1,len(checks)+1):
            seen=[]
            with self.assertRaises(analysis_run.Cancelled):
                self.read_source(commit,{'query':'needle'},blobs,lambda:seen.append(1) or len(seen)>=stop)
        tree=len(self.git('ls-tree','-r','--name-only',commit).splitlines())
        # The commit, each ls-tree entry and its trailing empty entry are checked before any search begins.
        self.assertGreater(len(checks),2+tree,'the search over reused lines needs its own checkpoints')
        with self.assertRaises(analysis_run.RunError) as caught:
            analysis_run._needed(str(self.repo),commit,[{'query':'needle'}],None,time.monotonic()-1,{},blobs)
        self.assertEqual(caught.exception.code,'timeout')

    def test_source_reuse_spans_tasks_in_a_run_but_not_separate_runs(self):
        seen=[];real=analysis_run.generate;intent=self.two_routes()
        def observed(*args,**kwargs):
            seen.append(args[7]);return real(*args,**kwargs)
        with patch.object(analysis_run,'generate',observed):
            done=analysis_run.run(self.prepare(intent=intent)['id'],self.fake);self.assertEqual(done['state'],'completed',done.get('error'))
            first=list(seen);seen.clear()
            self.assertGreater(len(first),1)
            self.assertTrue(all(x is first[0] for x in first))
            (self.repo/'server/items.go').write_text((self.repo/'server/items.go').read_text()+'// Second run source.\n')
            self.git('add','.');self.git('commit','-qm','Change for a second run');self.seed_map()
            done=analysis_run.run(self.prepare(intent=intent)['id'],self.fake);self.assertEqual(done['state'],'completed',done.get('error'))
        self.assertTrue(seen)
        self.assertFalse([x for x in seen if x is first[0]])

    def test_same_url_in_unrelated_handlers_does_not_widen_changed_input(self):
        files={'backend/app/main.py':'from fastapi import FastAPI\nfrom app.routers import a, b\napp = FastAPI()\napp.include_router(a.router)\napp.include_router(b.router)\n'}
        routes=[]
        for name in ('a','b'):
            router=f'backend/app/routers/{name}.py';service=f'backend/app/services/health_{name}.py'
            files[router]=f'from fastapi import APIRouter\nfrom ..services.health_{name} import check_health\nrouter = APIRouter()\n@router.get("/health")\ndef health_{name}():\n    return check_health()\n'
            files[service]=f'def check_health():\n    return "PRIVATE_UNRELATED_{name.upper()}"\n'
            routes.append({'file':router,'line':4,'quote':'@router.get("/health")','method':'GET','path':'/health','function':f'health_{name}',
                'services':[{'file':service,'line':1,'quote':'def check_health():'}],
                'steps':[{'file':service,'line':1,'quote':'def check_health():','text':'Check health','lane':'서버'}]})
        for file,text in files.items():
            p=self.repo/file;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text)
        self.git('add','.');self.git('commit','-qm','Same URL in independent handler files')
        self.data['backend_routes']+=routes
        req=ai_extract.request('demo','dev','en','service')
        ai_extract.record(**req['record_arguments'],result_json=json.dumps(test_ai_extract.agent_answer(req,self.data)))
        for task,result in (('system',self.SYSTEM),('groups',self.GROUPS)):
            req=ai_extract.task_request('demo',task,'dev','en','service');ai_extract.task_record(**req['record_arguments'],result_json=json.dumps(result))
        changed=self.repo/'backend/app/services/health_a.py';changed.write_text(changed.read_text()+'# changed\n')
        self.git('add','.');self.git('commit','-qm','Change only service A')
        req=ai_extract.request('demo','dev','en','service')
        self.assertEqual([r['function'] for r in req['recheck']],['health_a'])
        def executor(prompt,**kwargs):
            self.assertNotIn('PRIVATE_UNRELATED_B',prompt)
            return self.fake(prompt,**kwargs)
        done=analysis_run.run(self.prepare()['id'],executor)
        self.assertEqual(done['state'],'completed',done.get('error'))

    def test_direct_reply_needs_are_fulfilled_before_any_result_is_saved(self):
        helper='server/helper.go';(self.repo/helper).write_text('func HiddenHelper() { return }\n')
        path=self.repo/'server/items.go'
        path.write_text(path.read_text()+'HiddenHelper()\n//'+('x'*120000)+'\n')
        self.git('add','.');self.git('commit','-qm','Reference an uncited helper');self.seed_map()
        before=self.raw();calls=[];saw_helper=False
        def executor(prompt,**kwargs):
            nonlocal saw_helper
            p=json.loads(prompt.split('\n',1)[1]);calls.append(len(prompt.encode()))
            files={f['file'] for s in p.get('snapshots',[]) for f in s['files']}
            if len(calls)==1:
                self.assertNotIn('batch',p);self.assertNotIn(helper,files)
                return {**self.routes(),'needs':[{'file':helper,'limit':10}]}
            self.assertEqual(self.raw(),before,'The provisional direct reply must not be saved')
            answer=self.source_fake(prompt,**kwargs)
            if helper in files:
                saw_helper=True
                answer['result']['routes'][self.ROUTE]['steps']=[{'file':helper,'line':1,'quote':'func HiddenHelper() { return }','text':'Call the helper','lane':'서버'}]
            return answer
        done=analysis_run.run(self.steps()['id'],executor)
        self.assertEqual(done['state'],'completed',done.get('error'));self.assertTrue(saw_helper)
        flow=self.raw()['dev']['task_outputs']['flows']['routes'][self.ROUTE]
        self.assertEqual([s['file'] for s in flow['steps']],[helper]);self.assertGreater(len(calls),1)
        self.assertLessEqual(max(calls),128*1024)

    def test_provider_failure_keeps_saved_results_and_retry_only_finishes_missing_tasks(self):
        intent=self.two_routes();calls=[]
        def executor(prompt,**kwargs):
            calls.append(prompt)
            if len(calls)==2:raise ValueError('Synthetic provider unavailable')
            return self.fake(prompt,**kwargs)
        value=self.prepare(intent=intent);failed=analysis_run.run(value['id'],executor)
        self.assertEqual(failed['state'],'failed')
        self.assertEqual([t['task'] for t in failed['completed_tasks']],['steps'])
        saved=copy.deepcopy(self.raw()['dev']['task_outputs']['flows']['routes'][self.ROUTE])
        retried=analysis_run.retry(value['id']);self.assertNotEqual(retried['id'],value['id'])
        self.assertEqual([t['target'] for t in retried['tasks']],['@routes:["server/other.go::Other"]'])
        done=analysis_run.run(retried['id'],self.fake)
        self.assertEqual(done['state'],'completed',done.get('error'))
        self.assertEqual(self.raw()['dev']['task_outputs']['flows']['routes'][self.ROUTE],saved)

    def test_invalid_output_is_failed_without_publishing(self):
        self.seed_map();before=self.raw();value=self.steps()
        done=analysis_run.run(value['id'],lambda *a,**k:'not JSON')
        self.assertEqual(done['state'],'failed');self.assertEqual(self.raw(),before)

    def test_cancel_before_start_and_while_model_runs_retains_previous_results(self):
        value=self.prepare();cancelled=analysis_run.cancel(value['id'])
        self.assertEqual(cancelled['state'],'cancelled')
        before=self.raw();value=self.prepare()
        def executor(prompt,*,cancelled,timeout):
            analysis_run.cancel(value['id']);self.assertTrue(cancelled())
            return self.fake(prompt,cancelled=lambda:False,timeout=timeout)
        done=analysis_run.run(value['id'],executor)
        self.assertEqual(done['state'],'cancelled');self.assertEqual(self.raw(),before)

    def test_pin_change_during_execution_rejects_save(self):
        self.seed_map();before=self.raw();value=self.steps()
        def executor(prompt,**kwargs):
            result=self.fake(prompt,**kwargs)
            (self.repo/'server/items.go').write_text((self.repo/'server/items.go').read_text()+'// changed\n')
            self.git('add','.');self.git('commit','-qm','Changed while model runs')
            return result
        done=analysis_run.run(value['id'],executor)
        self.assertEqual(done['state'],'failed');self.assertEqual(done['error']['code'],'pins_changed')
        self.assertEqual(self.raw(),before)

    def test_configuration_changes_and_repository_membership_are_pinned(self):
        value=self.prepare();conf=project.config('demo');conf['repositories'][0]['layout']={'frontend':'pages'}
        project.atomic(project.home('demo')/'project.json',conf)
        done=analysis_run.run(value['id'],lambda *a,**k:self.fail('Pins changed before invocation'))
        self.assertEqual(done['error']['code'],'pins_changed')

    def test_duplicate_preparations_are_rejected_and_status_is_scoped(self):
        value=self.prepare()
        with self.assertRaisesRegex(ValueError,'already'):self.prepare()
        with self.assertRaisesRegex(ValueError,'already'):analysis_run.prepare('demo',branch='main',lang='ko')
        self.assertEqual(analysis_run.status(project='demo',lang='en')['id'],value['id'])
        self.assertEqual(analysis_run.status(project='demo',branch='main',lang='en')['id'],value['id'])
        self.assertEqual(analysis_run.status(project='demo',lang='ko')['id'],value['id'])
        analysis_run.cancel(value['id']);self.assertEqual(analysis_run.status(value['id'])['state'],'cancelled')
        self.assertIsNone(analysis_run.status(project='demo',lang='ko'))

    def test_recovery_distinguishes_prepared_live_and_interrupted_workers(self):
        self.seed_map();value=self.steps()
        self.assertEqual(analysis_run.status(value['id'])['state'],'preparing')
        self.assertFalse(analysis_run.active()['active'])
        value.update(state='running',launch_epoch=time.time()-60);analysis_run.write(value)
        with (analysis_run.root()/(value['id']+'.worker.lock')).open('a') as lock:
            import fcntl
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            self.assertEqual(analysis_run.status(value['id'])['state'],'running')
            self.assertTrue(analysis_run.active()['active'])
        done=analysis_run.status(value['id'])
        self.assertEqual(done['state'],'failed');self.assertEqual(done['error']['code'],'interrupted')
        self.assertFalse(analysis_run.active()['active'])
        startup=analysis_run.retry(value['id'],launch_intended=True)
        startup['prepare_epoch']=time.time()-120;analysis_run.write(startup)
        self.assertEqual(analysis_run.status(startup['id'])['error']['code'],'interrupted')

    def test_export_uses_commit_blobs_omits_credentials_and_symlinks(self):
        (self.repo/'.env').write_text('SECRET=do-not-send\n')
        (self.repo/'.git-credentials').write_text('https://user:never-send@github.com\n')
        (self.repo/'.netrc').write_text('machine service password never-send\n')
        (self.repo/'auth.json').write_text('{"token":"never-send"}')
        (self.repo/'server'/'link').symlink_to('/etc/passwd')
        self.git('add','.');self.git('commit','-qm','Synthetic credentials and link')
        commit=self.git('rev-parse','HEAD').strip()
        (self.repo/'server/items.go').write_text('working-tree-secret')
        exported=analysis_run.export_source(str(self.repo),commit)
        text=json.dumps(exported)
        self.assertNotIn('never-send',text);self.assertNotIn('do-not-send',text);self.assertNotIn('working-tree-secret',text)
        self.assertIn('router.POST',text);self.assertIn('not_regular_source',text)
        self.assertIn('credential_file',text)

    def test_input_that_cannot_fit_one_encoded_unit_fails_without_executor(self):
        self.seed_map();value=self.steps();before=self.raw()
        with patch.object(analysis_run,'MAX_PROMPT_BYTES',32):
            done=analysis_run.run(value['id'],lambda *a,**k:self.fail('Input exceeds limit'))
        self.assertEqual(done['error']['code'],'source_too_large');self.assertEqual(self.raw(),before)

    def test_large_binary_assets_are_omitted_and_large_text_is_available_for_batches(self):
        (self.repo/'picture.png').write_bytes(b'X'*400_000)
        (self.repo/'binary-unknown').write_bytes(b'\x00'*400_000)
        self.git('add','.');self.git('commit','-qm','Synthetic binary assets')
        commit=self.git('rev-parse','HEAD').strip()
        exported=analysis_run.export_source(str(self.repo),commit)
        self.assertEqual({x['reason'] for x in exported[0]['omitted']},{'binary_asset','binary'})
        (self.repo/'huge.txt').write_text('text source '*40000)
        self.git('add','.');self.git('commit','-qm','Synthetic oversized text')
        exported=analysis_run.export_source(str(self.repo),self.git('rev-parse','HEAD').strip())
        huge=next(f for f in exported[0]['files'] if f['file']=='huge.txt')
        self.assertEqual(huge['lines'][0]['text'],'text source '*40000)
        with self.assertRaises(analysis_run.Cancelled):
            analysis_run.export_source(str(self.repo),commit,cancelled=lambda:True)

    def test_start_rejects_changed_displayed_account_before_worker_launch(self):
        import cli_executor
        shown={'email':'shown@example.invalid','auth_method':'claude.ai'}
        current={'email':'other@example.invalid','auth_method':'claude.ai'}
        self.seed_map();value=self.steps()
        with patch.object(cli_executor,'availability',return_value={'available':True,'authenticated':True,'account':current}),patch.object(analysis_run.subprocess,'Popen') as spawn:
            with self.assertRaisesRegex(ValueError,'account changed'):analysis_run.start(value['id'],shown)
            spawn.assert_not_called()
        self.assertEqual(analysis_run.status(value['id'])['error']['code'],'CLI_ACCOUNT_CHANGED')

    def fake_cli(self):
        import cli_executor
        folder=Path(self.temp.name)/'bin';folder.mkdir()
        fixtures=Path(self.temp.name)/'fixtures.json'
        fixtures.write_text(json.dumps({'flags':' '.join(cli_executor.REQUIRED_FLAGS)}))
        script=folder/'claude'
        script.write_text('#!'+sys.executable+'\n'+"""
import json, os, sys, time
fixtures=json.load(open(os.environ['TEST_ANALYSIS_FIXTURES']))
if '--help' in sys.argv:print(fixtures['flags'])
elif sys.argv[1:]==['auth','status']:
    print(json.dumps({'loggedIn':True,'authMethod':'claude.ai','email':'fake@example.invalid'}))
else:
    payload=json.loads(sys.stdin.read().split('\\n',1)[1]);schema=payload['schema']
    if os.environ.get('TEST_ANALYSIS_PAUSE'):
        open(os.environ['TEST_ANALYSIS_PAUSE'],'w').write('started')
        time.sleep(30)
    result={'routes':{k:{'steps':[],'unknown':'No further steps established'} for k in payload['input']['routes']}}
    print(json.dumps({'result':json.dumps(result)}))
""")
        script.chmod(0o700)
        return {'PATH':str(folder)+os.pathsep+os.environ.get('PATH',''),'TEST_ANALYSIS_FIXTURES':str(fixtures)}

    def wait_terminal(self,run_id,seconds=15):
        until=time.monotonic()+seconds
        while time.monotonic()<until:
            value=analysis_run.status(run_id)
            if value['state'] in analysis_run.TERMINAL:return value
            time.sleep(.05)
        self.fail('Detached synthetic worker did not finish')

    def test_real_detached_worker_uses_fake_cli_and_pinned_account(self):
        import cli_executor
        self.seed_map()
        with patch.dict(os.environ,self.fake_cli()):
            account=cli_executor.availability()['account'];value=self.steps()
            started=analysis_run.start(value['id'],account)
            self.assertEqual(started['account'],account)
            done=self.wait_terminal(value['id'])
        self.assertEqual(done['state'],'completed',done.get('error'))
        self.assertEqual([t['task'] for t in done['completed_tasks']],['steps'])

    def test_detached_cancellation_stops_only_its_owned_fake_cli_without_saving(self):
        import cli_executor
        env=self.fake_cli();marker=Path(self.temp.name)/'model-started';env['TEST_ANALYSIS_PAUSE']=str(marker)
        self.seed_map();before=self.raw()
        with patch.dict(os.environ,env):
            account=cli_executor.availability()['account'];value=self.steps()
            analysis_run.start(value['id'],account)
            until=time.monotonic()+10
            while not marker.exists() and time.monotonic()<until:time.sleep(.05)
            self.assertTrue(marker.exists(),'Synthetic model did not start')
            analysis_run.cancel(value['id']);done=self.wait_terminal(value['id'])
        self.assertEqual(done['state'],'cancelled');self.assertEqual(self.raw(),before)

    def test_program_jobs_and_briefing_require_explicit_intent(self):
        self.SYSTEM={**self.SYSTEM,'nodes':self.SYSTEM['nodes']+[{'id':'web','name':'Web','kind':'program','code':['pages'],
            'ev':[{'file':'pages/items.vue','line':1,'quote':'<button @click="saveItem">'}]}]}
        self.data={**self.data,'screens':[]};self.GROUPS={'groups':[],'names':{},'request_names':{}}
        self.seed_map()
        raw=self.raw();self.assertFalse(raw['dev']['task_outputs'].get('jobs',{}).get('nodes'))
        value=self.prepare(intent={'task':'jobs','targets':[{'repository':'service','target':'api'}]})
        calls=[]
        def jobs(prompt,**kwargs):
            p=json.loads(prompt.split('\n',1)[1]);calls.append(p)
            self.assertEqual(p['input']['node']['id'],'api')
            self.assertEqual({f['file'] for snapshot in p['snapshots'] for f in snapshot['files']},{'server/items.go'})
            return {'jobs':[],'unknown':[{'text':'No jobs established by supplied source','needs':'read'}]}
        done=analysis_run.run(value['id'],jobs)
        self.assertEqual(done['state'],'completed',done.get('error'));self.assertEqual(len(calls),1)
        raw=self.raw();self.assertEqual(raw['dev']['task_outputs']['jobs']['nodes']['api']['source'],'ai')
        # Frozen briefing evidence changes schedule a real briefing task, whose claims still pass its validator.
        # Supply a minimal frozen evidence window directly, without any external collection.
        raw['changes']={'last_result':{'since':'2026-10-01T00:00:00+00:00','at':'2026-10-02T00:00:00+00:00','changed':True,'evidence':{
            'commits':{'dev':{'from':self.commit,'to':self.commit}},'comparison':{'since':'last_refresh','since_time':''},
            'structure':{},'prs':[],'issues':[],'collection':{}}}}
        project._publish('demo','service',raw,{},collection=False)
        # Changed briefing evidence never adds a briefing task to another intent.
        value=self.steps();self.assertEqual([t['task'] for t in value['tasks']],['steps']);analysis_run.cancel(value['id'])
        value=self.prepare(intent={'task':'briefing'});self.assertEqual([t['task'] for t in value['tasks']],['briefing'])
        def executor(prompt,**kwargs):
            payload=json.loads(prompt.split('\n',1)[1]);self.assertIn('sources',payload)
            return json.dumps({'cards':[],'unknown':['The collected evidence does not establish a specific problem']})
        done=analysis_run.run(value['id'],executor)
        self.assertEqual(done['state'],'completed',done.get('error'))
        self.assertEqual(briefing.view('demo','','dev','en')['state'],'saved')

if __name__=='__main__':unittest.main()
