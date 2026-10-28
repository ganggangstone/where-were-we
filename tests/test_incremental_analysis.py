"""Catalog reuse and changed-only AI requests: synthetic Git, fixed fake agent JSON, AI shells blocked."""
import copy
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import mapcore
import project
import ai_extract

FILES=53;PER=9;ROUTES=FILES*PER
ROUTERS=[f'backend/app/routers/h{n:02d}.py' for n in range(FILES)]
ALLOWED=('checked_commit','flow','tests')  # metadata a carry may advance; everything else must stay identical

def router(n,extra=''):
    lines=['from fastapi import APIRouter','from app.db import db',f'router = APIRouter(prefix="/h{n:02d}")']
    for j in range(PER):
        i=n*PER+j
        lines+=[f'@router.post("/r{i}")',f'async def handle_{i}(payload: dict):',f'    db.table("t{i%40}").insert(payload)','    return {"ok": True}']
    return '\n'.join(lines)+'\n'+extra

def main_py(files=range(FILES),extra=''):
    names=[f'h{n:02d}' for n in files]
    return 'from fastapi import FastAPI\nfrom app.routers import '+', '.join(names)+'\napp = FastAPI()\n'+''.join(f'app.include_router({x}.router)\n' for x in names)+extra

FRONT={'frontend/src/App.tsx':'import Items from "./pages/Items";\nexport const routes = <Routes><Route path="/items" element={<Items />} /></Routes>;\n',
       'frontend/src/pages/Items.tsx':'import { saveItem } from "../api/items";\nexport default function Items() { return <button onClick={saveItem}>Save item</button>; }\n',
       'frontend/src/api/items.ts':'export async function saveItem() {\n  return api.post("/h00/r0", {});\n}\n'}

class Incremental(unittest.TestCase):
    maxDiff=1000  # 477-route maps must not flood logs
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.repo=Path(self.temp.name)/'code';self.repo.mkdir();self.home=Path(self.temp.name)/'maps'
        p=patch.object(mapcore,'ROOT',str(self.home));p.start();self.addCleanup(p.stop)
        real=subprocess.run
        def guard(command,**kwargs):
            # Same environment as the code under test: any AI shell is a test failure.
            if Path(str(command[0])).name in ('claude','codex','gemini'):raise AssertionError('Real AI calls are forbidden; use the fake agent')
            return real(command,**kwargs)
        g=patch('subprocess.run',side_effect=guard);g.start();self.addCleanup(g.stop)
        self.git('init','-q');self.git('config','user.name','Demo');self.git('config','user.email','demo@example.invalid')
        self.write({**FRONT,'backend/app/main.py':main_py(),'worker/run.py':'while True:\n    process_queue()\n',**{f:router(n) for n,f in enumerate(ROUTERS)}})
        self.c0=self.commit('Synthetic service')
        self.conf=project.configure('demo',{'repositories':[{'id':'service','path':str(self.repo),'refs':{'dev':'HEAD','main':None}}]})['repositories'][0]
        project.publish('demo','service',{'dev':{**project.empty_map(),'repo':str(self.repo),'commit':self.c0,'ref':'HEAD'}},{'fingerprint':project.fingerprint(self.conf)})
    def git(self,*args):return subprocess.run(['git','-C',str(self.repo),*args],check=True,capture_output=True,text=True).stdout
    def write(self,files):
        for name,text in files.items():
            path=self.repo/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text)
    def commit(self,message='Change'):
        self.git('add','-A');self.git('commit','-qm',message,'--allow-empty');return self.git('rev-parse','HEAD').strip()
    def raw(self):return project.raw_bundle(project.repository_folder('demo',self.conf,project.states('demo')))
    def request(self,lang='en'):return ai_extract.request('demo','dev',lang,'service')
    def record(self,request,data,**override):
        return ai_extract.record(**{**request['record_arguments'],**override},result_json=json.dumps(data))
    def tasks(self):return [(t['task'],t['target']) for t in ai_extract.plan('demo','dev','en','service')['tasks']]
    def bytes(self,data):return len(json.dumps(data,ensure_ascii=False).encode())
    def ids(self,request):return {r['id'] for r in request['recheck']}
    def plain(self,items):return sorted((json.dumps({k:v for k,v in x.items() if k not in ALLOWED},sort_keys=True) for x in items))
    def flows(self):return {k:{x:y for x,y in v.items() if x not in ('commit','verified_commit','carried_from')} for k,v in self.raw()['dev']['task_outputs']['flows']['routes'].items()}

    # ---- fake agent: deterministic JSON built from the synthetic source ----
    def full_routes(self,files=range(FILES),steps=True,mount=True,prefix=None,where=None):
        routes=[]
        for n in files:
            f=where or f'backend/app/routers/h{n:02d}.py'
            for j in range(PER):
                i=n*PER+j;deco=4+4*j;dbl=deco+2
                r={'file':f,'line':deco,'quote':f'@router.post("/r{i}")','method':'POST','path':(prefix or '')+f'/h{n:02d}/r{i}','function':f'handle_{i}',
                   'tables':[{'name':f't{i%40}','file':f,'line':dbl,'quote':f'db.table("t{i%40}")'}]}
                if prefix:r['dependencies']=[{'file':'backend/app/main.py','line':4+n,'quote':f'app.include_router(h{n:02d}.router, prefix=API_PREFIX)'},
                                             {'file':'backend/app/prefix.py','line':1,'quote':f'API_PREFIX = "{prefix}"'}]
                elif mount:r['dependencies']=[{'file':'backend/app/main.py','line':4+n,'quote':f'app.include_router(h{n:02d}.router)'}]
                if steps:r['steps']=[{'file':f,'line':dbl,'quote':f'db.table("t{i%40}")','lane':'저장소','text':'Store the payload','uncertain':False}]
                routes.append(r)
        return routes
    def screen(self):
        return {'path':'/items','heading':'Items','file':'frontend/src/App.tsx','line':2,'quote':'<Route path="/items"',
                'dependencies':[{'file':'frontend/src/pages/Items.tsx','line':2,'quote':'<button onClick={saveItem}>'}],
                'calls':[{'file':'frontend/src/api/items.ts','line':2,'quote':'api.post("/h00/r0"','method':'POST','path':'/h00/r0'}]}
    def full(self,**kw):return {'screens':[self.screen()],'backend_routes':self.full_routes(**kw),'unknown':['Authentication was not established.']}
    def answer(self,request,data):
        """The fake agent answers in the contract of the server's mode: a review keeps the catalog explicitly."""
        return {'keep':'all',**data} if request['mode']=='review' else data
    def baseline(self,data=None):
        """A v2 AI baseline: the first review answers with full items; record_arguments carry the base."""
        request=self.request();self.record(request,self.answer(request,data or self.full()));return request
    def save_task(self,task,data,target=''):
        r=ai_extract.task_request('demo',task,'dev','en','service',target)
        ai_extract.task_record(**r['record_arguments'],result_json=json.dumps(data));return r
    def save_outputs(self,worker=False):
        ev={'file':'backend/app/main.py','line':3,'quote':'app = FastAPI()'};job={'name':'Serve','what':'API','starts_when':'Request','trigger':ev,'steps':[]}
        web={'file':'frontend/src/App.tsx','line':1,'quote':'import Items'};run={'file':'worker/run.py','line':2,'quote':'process_queue()'}
        nodes=[{'id':'api','name':'API','kind':'program','code':['backend'],'ev':[ev],'jobs':[job]},
               {'id':'web','name':'Web','kind':'program','code':['frontend'],'ev':[web],'jobs':[{**job,'trigger':web}]}]
        if worker:nodes.append({'id':'worker','name':'Worker','kind':'program','code':['worker'],'ev':[run],'jobs':[{**job,'trigger':run}]})
        self.save_task('system',{'nodes':nodes})
        self.save_task('groups',{'groups':[{'name':'Items','screens':['/items']}],'names':{},'request_names':{}})
        self.assertEqual(self.tasks(),[])

    # 1. First baseline reuses the basic catalog: sparse output, provenance stays basic.
    def test_first_baseline_reuses_basic_catalog_without_reoutput(self):
        request=self.request()
        self.assertEqual((request['mode'],request['reason']),('review','basic_catalog'))
        self.assertEqual(sum(1 for k in request['known'] if k[0].startswith('r:')),ROUTES)
        result={'keep':'all','unknown':['Steps are not established yet.']}
        self.assertLess(self.bytes(result)*100,self.bytes(self.full(steps=False)))
        self.record(request,result)
        m=self.raw()['dev']
        self.assertEqual(len(m['backend_routes']),ROUTES)
        self.assertEqual({r['source'] for r in m['backend_routes']},{'basic'})
        self.assertEqual(m['analysis']['sources'],{'ai':0,'basic':ROUTES+1})
        scope=project.read_bundle('demo')['project']['repositories'][0]['analysis_scope']['dev']
        self.assertEqual((scope['frontend'],scope['backend']),('mixed','mixed'))
        self.assertEqual(m['api_functions'][0]['calls'][0]['backend'][0]['function'],'handle_0')
        self.assertEqual(self.tasks()[0][0],'system')

    # 2. An existing v1 AI baseline is reviewed with the catalog; nothing is re-emitted for the upgrade.
    def test_v1_snapshot_migrates_with_sparse_review(self):
        request=self.request();ai_extract.record(**{k:v for k,v in request['record_arguments'].items() if k!='base'},result_json=json.dumps(self.full(mount=False)))
        raw=self.raw();m=raw['dev']
        for r in m['backend_routes']:
            for key in ('id','service_evidence','external_evidence','dependencies','verified_commit','checked_commit'):r.pop(key,None)
        for s in m['screens']:
            for key in ('id','dependencies','verified_commit','checked_commit'):s.pop(key,None)
        m['analysis']['version']=1;project.publish('demo','service',raw,{})
        before=self.flows()
        self.write({ROUTERS[3]:router(3,'# note\n')});self.commit()
        request=self.request()
        self.assertEqual((request['mode'],request['reason']),('review','v1_snapshot'))
        self.assertEqual(self.ids(request),set())  # appended line: every cited literal still matches at head
        result={'keep':'all'};self.assertLess(self.bytes(result),100)
        self.record(request,result)
        m=self.raw()['dev']
        self.assertEqual(m['analysis']['version'],ai_extract.VERSION)
        self.assertEqual(len([r for r in m['backend_routes'] if r['source']=='ai']),ROUTES)
        self.assertTrue(all(r['verified_commit']==self.c0 and r['checked_commit']==m['commit'] for r in m['backend_routes']))
        after=self.flows();changed={k for k in before if k.startswith(ROUTERS[3])}
        self.assertEqual({k:v for k,v in before.items() if k not in changed},after)
        steps=[t for t in self.tasks() if t[0]=='steps']
        self.assertEqual(sorted(json.loads(steps[0][1][8:])),sorted(changed))

    def test_review_rechecks_items_whose_literals_moved(self):
        self.baseline()
        ai_extract.set_review_flag('demo','service','dev',self.raw()['dev'],'unaccounted:x')
        self.write({ROUTERS[3]:'# header\n'+router(3)});self.commit()
        request=self.request()
        self.assertEqual(request['mode'],'review')
        self.assertEqual({r['reason'] for r in request['recheck']},{'evidence_changed'})
        self.assertEqual(len(request['recheck']),PER)  # lines moved: kept items must pass the literal check at head
        with self.assertRaisesRegex(ValueError,'No valid'):self.record(request,{'keep':'all'})
        moved=[{**r,'line':r['line']+1,'tables':[{**x,'line':x['line']+1} for x in r['tables']],'steps':[{**x,'line':x['line']+1} for x in r['steps']]} for r in self.full_routes([3])]
        self.record(request,{'keep':'all','backend_routes':moved})
        self.assertEqual({r['line'] for r in self.raw()['dev']['backend_routes'] if r['file']==ROUTERS[3]},{5+4*j for j in range(PER)})

    def test_actual_v1_output_keeps_navigation_through_the_review(self):
        """The v1 map comes from the released d6cf44a apply_result, not from a v2 map with fields removed."""
        import types
        root=Path(__file__).resolve().parents[1]
        shown=subprocess.run(['git','-C',str(root),'show','d6cf44a:ai_extract.py'],capture_output=True,text=True)
        if shown.returncode:self.skipTest('released v1 source is not available in this checkout')
        v1=types.ModuleType('ai_extract_v1');v1.__file__=str(root/'ai_extract_v1.py');exec(compile(shown.stdout,'ai_extract_v1.py','exec'),v1.__dict__)
        items={'path':'/items','heading':'Items','file':'frontend/src/App.tsx','line':2,'quote':'<Route path="/items"',
               'actions':[{'file':'frontend/src/pages/Items.tsx','line':2,'quote':'Save item</button>','kind':'nav','label':'Other','to':'/other'}],
               'calls':[{'file':'frontend/src/api/items.ts','line':2,'quote':'api.post("/h00/r0"','method':'POST','path':'/h00/r0'}]}
        other={'path':'/other','heading':'Other','file':'frontend/src/pages/Items.tsx','line':1,'quote':'import { saveItem }'}
        data={'screens':[items,other],'backend_routes':self.full_routes(mount=False),'unknown':[]}
        raw=self.raw();head=self.c0
        updated,_=v1.apply_result(raw,str(self.repo),{'dev':'HEAD'},'dev','en',json.dumps(data),head,{},project.fingerprint(self.conf))
        updated['dev']['analysis']['provider']='mcp-agent';project.publish('demo','service',updated,{})
        before=self.raw()['dev']
        self.assertEqual(before['analysis']['version'],1);self.assertNotIn('to_raw',json.dumps(before['screens']))
        self.write({ROUTERS[3]:router(3,'# note\n')});self.commit()
        request=self.request();self.assertEqual((request['mode'],request['reason'],request['recheck']),('review','v1_snapshot',[]))
        self.record(request,{'keep':'all'})
        after=self.raw()['dev']
        relation=lambda m:[(s['path'],[(a['kind'],a['label'],a['to'],a['targets']) for a in s['actions']],s['api_functions']) for s in m['screens']]
        self.assertEqual(relation(after),relation(before))
        self.assertEqual(after['screens'][0]['actions'][0]['targets'],[{'to':'/other','label':'Other'}])
        self.assertEqual(self.plain(r for r in after['backend_routes'] if r['file']!=ROUTERS[3]),
                         self.plain({**r,'id':ai_extract.route_id(r),'verified_commit':self.c0} for r in before['backend_routes'] if r['file']!=ROUTERS[3]))

    # 3. One independent file changes: exactly that file's routes are targets; the rest is untouched.
    def test_one_independent_file_change_requests_only_its_routes(self):
        self.baseline();before=self.raw()['dev'];old_flows=self.flows()
        self.write({ROUTERS[5]:router(5,'# changed\n')});self.commit()
        request=self.request()
        self.assertEqual((request['mode'],len(request['recheck']),request['inspect']),('patch',PER,[ROUTERS[5]]))
        self.assertNotIn('known',request);self.assertLess(self.bytes(request),20000)
        result={'backend_routes':self.full_routes([5]),'accounted':[{'file':ROUTERS[5],'kind':'items'}]}
        self.assertLess(self.bytes(result)*20,self.bytes(self.full()))
        self.record(request,result)
        m=self.raw()['dev']
        self.assertEqual(self.plain(r for r in m['backend_routes'] if r['file']!=ROUTERS[5]),self.plain(r for r in before['backend_routes'] if r['file']!=ROUTERS[5]))
        self.assertEqual(self.plain(m['screens']),self.plain(before['screens']))
        self.assertEqual({k:v for k,v in self.flows().items() if not k.startswith(ROUTERS[5])},{k:v for k,v in old_flows.items() if not k.startswith(ROUTERS[5])})
        self.assertEqual(sum(r['verified_commit']==m['commit'] for r in m['backend_routes']),PER)
        tasks=[t for t,_ in self.tasks()]
        self.assertNotIn('steps',tasks)  # replacements carried their own steps
        self.assertIn('system',tasks)  # tree changed: architecture review, never retagged

    # 4. A shared mount file changes: every route citing it is rechecked and flows lose their proof.
    def test_shared_mount_change_invalidates_dependents_with_a_compact_steps_request(self):
        self.baseline()
        self.write({'backend/app/main.py':main_py(extra='# mounted\n')});self.commit()
        request=self.request()
        self.assertEqual(len(request['recheck']),ROUTES)
        self.record(request,{'backend_routes':self.full_routes(steps=False),'accounted':[{'file':'backend/app/main.py','kind':'items'}]})
        steps=[t for t in self.tasks() if t[0]=='steps']
        self.assertEqual(len(json.loads(steps[0][1][8:])),ROUTES)
        task=ai_extract.task_request('demo','steps','dev','en','service',steps[0][1])
        full_routes={k:r for r in self.raw()['dev']['backend_routes'] if (k:=r['file']+'::'+r['function']) in task['input']['routes']}
        self.assertLess(self.bytes(task['input'])*2,self.bytes(full_routes))

    # 5. Identical tree: nothing to request; provenance kept and the checked commit advanced.
    def test_identical_tree_is_carried_without_ai(self):
        self.baseline();self.save_outputs()
        old=self.raw()['dev']['commit'];head=self.commit('Empty')
        raw=self.raw();self.assertTrue(ai_extract.carry_unchanged(raw['dev'],str(self.repo),head))
        project.publish('demo','service',raw,{})
        self.assertEqual(self.tasks(),[])
        m=self.raw()['dev']
        self.assertTrue(all(r['verified_commit']==old and r['checked_commit']==head for r in m['backend_routes']))
        flow=next(iter(m['task_outputs']['flows']['routes'].values()))
        self.assertEqual((flow['commit'],flow['verified_commit']),(head,old))
        self.write({'README.md':'x\n'});later=self.commit()
        self.assertFalse(ai_extract.carry_unchanged(self.raw()['dev'],str(self.repo),later))

    def test_refresh_uses_the_identical_tree_carry(self):
        self.baseline();m=self.raw()['dev']
        stage=self.home/'stage';stage.mkdir();(stage/'dev.json').write_text(json.dumps(m))
        self.git('remote','add','origin',str(self.repo));head=self.commit('Empty')
        real=subprocess.run
        def run(command,**kwargs):
            if any(str(x).endswith('/collect.py') for x in command):return subprocess.CompletedProcess(command,0,'','')
            if Path(str(command[0])).name in ('claude','codex','gemini'):raise AssertionError('Real AI calls are forbidden')
            return real(command,**kwargs)
        with patch.object(sys,'argv',['refresh.py','stage',str(self.repo)]),patch.dict(os.environ,{'WHERE_WERE_WE_REFS':json.dumps({'dev':'HEAD','main':None})}),patch('subprocess.run',side_effect=run):
            runpy.run_path(str(Path(__file__).resolve().parents[1]/'refresh.py'),run_name='__main__')
        saved=json.loads((stage/'dev.json').read_text())
        self.assertEqual((saved['commit'],saved['analysis']['stale'],saved['analysis']['carried_from']),(head,False,m['commit']))

    # 6. Files with no map items are accounted explicitly; gaps never pass and fall back to one review.
    def test_unmapped_file_accounting_and_bounded_review_fallback(self):
        self.baseline()
        self.write({'README.md':'Docs\n','tools/outside.txt':'Outside the roots\n'});self.commit()
        request=self.request()
        self.assertEqual((request['inspect'],request['recheck']),(['README.md','tools/outside.txt'],[]))
        before=json.dumps(self.raw(),sort_keys=True)
        with self.assertRaisesRegex(ValueError,'review'):self.record(request,{'accounted':[{'file':'README.md','kind':'none'}]})
        self.assertEqual(json.dumps(self.raw(),sort_keys=True),before)  # the fallback flag lives outside the map bundle
        review=self.request()
        self.assertEqual((review['mode'],review['reason']),('review','unaccounted:tools/outside.txt'))
        with self.assertRaisesRegex(ValueError,'full-context review'):self.record(review,{'full_required':'x'})
        self.assertEqual(self.request()['mode'],'review')  # bounded: review stays review, no loop
        self.record(review,{'keep':'all'})
        self.assertIsNone(ai_extract.review_flag('demo','service','dev',self.raw()['dev']))
        self.write({'README.md':'Docs 2\n'});self.commit()
        request=self.request()
        self.record(request,{'accounted':[{'file':'README.md','kind':'none'}]})
        self.assertEqual(self.raw()['dev']['analysis']['accounted'],{'items':0,'affects':0,'none':1,'source':'ai'})

    def test_affects_accounting_requires_saved_ids_and_a_disposition(self):
        self.baseline()
        self.write({'README.md':'Route h01/r9 is documented here\n'});self.commit()
        request=self.request();route=next(r for r in self.raw()['dev']['backend_routes'] if r['function']=='handle_9')
        with self.assertRaisesRegex(ValueError,'affects'):self.record(request,{'accounted':[{'file':'README.md','kind':'affects','ids':['r:missing']}]})
        with self.assertRaisesRegex(ValueError,'No valid'):self.record(request,{'accounted':[{'file':'README.md','kind':'affects','ids':[route['id']]}]})
        with self.assertRaisesRegex(ValueError,'review'):self.record(request,{'accounted':[{'file':'README.md','kind':'unknown'}]})
        request=self.request()  # the unknown kind made it a full-context review
        self.assertEqual(request['reason'],'unaccounted:README.md')
        self.record(request,{'keep':'all'})
        self.write({'README.md':'Route h01/r9 moved\n'});self.commit();request=self.request()
        self.record(request,{'backend_routes':self.full_routes([1])[:1],'accounted':[{'file':'README.md','kind':'affects','ids':[route['id']]}]})

    # 7. Endpoint identity keeps each mount; the handler flow is shared; exact duplicate AI input is rejected.
    def test_multiple_mounts_keep_endpoints_and_share_handler_flow(self):
        self.write({'backend/app/main.py':main_py(extra='app.include_router(h00.router, prefix="/v2")\n'),'backend/admin.py':'admin.include_router(h00.router)\n'});self.commit()
        request=self.request()
        twin={**self.full_routes([0])[0],'path':'/v2/h00/r0','dependencies':[{'file':'backend/app/main.py','line':4+FILES,'quote':'prefix="/v2"'}]}
        # Same method, path and handler served by a second app: only the mount tells them apart.
        admin={**self.full_routes([0])[0],'dependencies':[{'file':'backend/admin.py','line':1,'quote':'admin.include_router(h00.router)'}]}
        data=self.full();data['backend_routes']+=[twin,admin]
        self.record(request,self.answer(request,data))
        m=self.raw()['dev'];same=[r for r in m['backend_routes'] if r['function']=='handle_0']
        self.assertEqual((len({r['id'] for r in same}),len(same)),(3,3))
        self.assertEqual(len([k for k in m['task_outputs']['flows']['routes'] if k.endswith('::handle_0')]),1)
        request=self.request();data=self.full();data['backend_routes'].append(copy.deepcopy(data['backend_routes'][0]))
        with self.assertRaisesRegex(ValueError,'Duplicate'):self.record(request,self.answer(request,data))

    def test_basic_variant_of_another_mount_survives_partial_ai_enrichment(self):
        self.write({'backend/app/main.py':main_py(extra='app.include_router(h00.router, prefix="/v2")\n')});self.commit()
        request=self.request()
        basic={k[2] for k in request['known'] if k[3]=='handle_0'}
        self.assertIn('/v2/h00/r0',basic)
        self.record(request,{'keep':'all','backend_routes':self.full_routes([0])[:1]})  # the AI enriches only /h00/r0
        paths={r['path']:r['source'] for r in self.raw()['dev']['backend_routes'] if r['function']=='handle_0'}
        self.assertEqual(paths.get('/h00/r0'),'ai')
        self.assertEqual(paths.get('/v2/h00/r0'),'basic')  # a different mount is not superseded by handler identity

    def test_prefix_only_change_replaces_endpoints_explicitly(self):
        # Real source: main mounts h00 with a prefix constant the deterministic collector cannot resolve.
        main=main_py().replace('from fastapi import FastAPI\n','from fastapi import FastAPI; from app.prefix import API_PREFIX\n').replace(
            'app.include_router(h00.router)\n','app.include_router(h00.router, prefix=API_PREFIX)\n')
        self.write({'backend/app/prefix.py':'API_PREFIX = "/v1"\n','backend/app/main.py':main});self.commit()
        request=self.request();self.assertEqual(request['mode'],'review')
        wrong=sorted(k[0] for k in request['known'] if k[5]=='basic' and k[4]==ROUTERS[0])
        self.assertEqual(({k[2] for k in request['known'] if k[0] in wrong},len(wrong)),({f'/h00/r{i}' for i in range(PER)},PER))
        data=self.full();data['backend_routes']=self.full_routes([0],prefix='/v1')+self.full_routes(range(1,FILES))
        self.record(request,{'keep':'all',**data,'drop':wrong})  # the review drops the unresolved basic seeds explicitly
        m=self.raw()['dev']
        self.assertEqual(m['basic_drop'],wrong)
        self.assertEqual({r['path'] for r in m['backend_routes'] if r['file']==ROUTERS[0]},{f'/v1/h00/r{i}' for i in range(PER)})
        old={r['id'] for r in m['backend_routes'] if r['file']==ROUTERS[0]}
        self.write({'backend/app/prefix.py':'API_PREFIX = "/v2"\n'});self.commit()
        request=self.request()
        self.assertEqual((request['mode'],self.ids(request),request['inspect']),('patch',old,['backend/app/prefix.py']))
        moved=self.full_routes([0],prefix='/v2',steps=False);acc=[{'file':'backend/app/prefix.py','kind':'affects','ids':sorted(old)}]
        with self.assertRaisesRegex(ValueError,'No valid replacement'):self.record(request,{'backend_routes':moved,'accounted':acc})
        by_function={r['function']:r['id'] for r in request['recheck']}
        self.record(request,{'backend_routes':[{**r,'replaces':by_function[r['function']]} for r in moved],'accounted':acc})
        m=self.raw()['dev'];paths={r['path'] for r in m['backend_routes'] if r['file']==ROUTERS[0]}
        self.assertEqual(paths,{f'/v2/h00/r{i}' for i in range(PER)})  # dropped basic seeds stay dropped
        self.assertEqual(m['basic_drop'],wrong)
        self.assertFalse(old&{r['id'] for r in m['backend_routes']})
        self.assertNotIn('replaces',json.dumps(m))
        steps=[t for t in self.tasks() if t[0]=='steps']  # same handler key, new path: the flow is asked again
        self.assertEqual(sorted(json.loads(steps[0][1][8:])),sorted(f'{ROUTERS[0]}::handle_{i}' for i in range(PER)))

    # 8. Atomic rejection; the previous generation is untouched.
    def test_invalid_patches_are_rejected_atomically(self):
        self.baseline()
        self.write({ROUTERS[5]:router(5,'# changed\n')});self.commit()
        request=self.request();first=sorted(self.ids(request))[0];before=json.dumps(self.raw(),sort_keys=True)
        good=self.full_routes([5]);acc=[{'file':ROUTERS[5],'kind':'items'}];other=self.full_routes([6])[0]
        bad_evidence=copy.deepcopy(good);bad_evidence[0]['quote']='not in this file'
        bad_table=copy.deepcopy(good);bad_table[0]['tables'][0]['quote']='not in this file'
        bad_step=copy.deepcopy(good);bad_step[3]['steps'][0]['line']=1
        unpinned={k:v for k,v in request['record_arguments'].items() if k!='base'}
        cases=[('no base',{'backend_routes':good,'accounted':acc},unpinned),
               ('legacy full over v2',self.full(),unpinned),
               ('wrong base',{'base':'0'*64,'backend_routes':good,'accounted':acc},unpinned),
               ('two bases',{'base':'0'*64,'backend_routes':good,'accounted':acc},request['record_arguments']),
               ('out of scope',{'backend_routes':good+[other],'accounted':acc},request['record_arguments']),
               ('replace and remove',{'backend_routes':good,'removed':[first],'accounted':acc},request['record_arguments']),
               ('replaces outside recheck',{'backend_routes':good[1:]+[{**good[0],'path':'/x','replaces':'r:other'}],'accounted':acc},request['record_arguments']),
               ('rejected evidence',{'backend_routes':bad_evidence,'accounted':acc},request['record_arguments']),
               ('rejected nested table evidence',{'backend_routes':bad_table,'accounted':acc},request['record_arguments']),
               ('rejected nested step evidence',{'backend_routes':bad_step,'accounted':acc},request['record_arguments']),
               ('drop outside catalog',{'backend_routes':good,'drop':['r:unknown'],'accounted':acc},request['record_arguments']),
               ('duplicate removed',{'backend_routes':good[1:],'removed':[first,first],'accounted':acc},request['record_arguments']),
               ('unaccounted target',{'backend_routes':good[1:],'accounted':acc},request['record_arguments']),
               ('stale configuration',{'backend_routes':good,'accounted':acc},{**request['record_arguments'],'configuration':'0'*64})]
        for label,data,args in cases:
            with self.subTest(label),self.assertRaises(ValueError):ai_extract.record(**args,result_json=json.dumps(data))
            self.assertEqual(json.dumps(self.raw(),sort_keys=True),before,label)
        # The commit moves between request and record.
        self.write({ROUTERS[6]:router(6,'# later\n')});self.commit()
        with self.assertRaisesRegex(ValueError,'commit changed'):self.record(request,{'backend_routes':good,'accounted':acc})
        self.git('reset','-q','--hard','HEAD~1')
        # A concurrent save changes the pinned base.
        self.record(request,{'backend_routes':good,'accounted':acc})
        with self.assertRaisesRegex(ValueError,'request'):self.record(request,{'backend_routes':good,'accounted':acc})
        # Replacements alone never become a full replacement: the unaccounted change is rejected byte-identically.
        self.write({ROUTERS[6]:router(6,'# later\n')});self.commit()
        request=self.request();before=json.dumps(self.raw(),sort_keys=True)
        with self.assertRaisesRegex(ValueError,'review'):self.record(request,{'backend_routes':self.full_routes([6])})
        self.assertEqual(json.dumps(self.raw(),sort_keys=True),before)
        self.assertEqual(self.request()['mode'],'review')

    def test_patch_cannot_drop_basic_items_outside_its_targets(self):
        seed=self.request();self.record(seed,{'keep':'all'})
        self.write({'README.md':'Docs\n'});self.commit()
        request=self.request();self.assertEqual((request['mode'],request['recheck'],request['inspect']),('patch',[],['README.md']))
        basic=next(r['id'] for r in self.raw()['dev']['backend_routes'] if r['function']=='handle_0')
        before=json.dumps(self.raw(),sort_keys=True)
        with self.assertRaisesRegex(ValueError,'drop'):self.record(request,{'drop':[basic],'accounted':[{'file':'README.md','kind':'none'}]})
        self.assertEqual(json.dumps(self.raw(),sort_keys=True),before)
        self.record(request,{'accounted':[{'file':'README.md','kind':'none'}]})
        self.assertEqual(len(self.raw()['dev']['backend_routes']),ROUTES)

    def test_mcp_record_analysis_accepts_the_returned_record_arguments(self):
        import inspect,mcp_server
        self.assertIn('base',inspect.signature(mcp_server.record_analysis).parameters)
        request=json.loads(mcp_server.analyze('demo','service','dev','en'))
        message=mcp_server.record_analysis(**request['record_arguments'],result_json=json.dumps({'keep':'all'}))
        self.assertIn('review',message)
        self.assertEqual(ai_extract.analysis_cli(['demo','dev','en','--repository','service'])['mode'],'review')

    def test_every_mode_pins_the_base(self):
        seed=self.request();self.assertEqual(seed['mode'],'review')
        with self.assertRaisesRegex(ValueError,'request'):self.record(seed,{'keep':'all'},base='0'*64)
        with self.assertRaisesRegex(ValueError,'keep'):self.record(seed,self.full())  # a review never becomes a full replacement
        self.record(seed,self.answer(seed,self.full()))
        full=self.request('ko');self.assertEqual((full['mode'],full['reason']),('full','language_changed'))
        with self.assertRaisesRegex(ValueError,'sparse'):self.record(full,{'keep':'all'})
        with self.assertRaisesRegex(ValueError,'request'):self.record(full,self.full(),base='0'*64)
        self.record(full,self.full())
        self.write({ROUTERS[5]:router(5,'# changed\n')});self.commit()
        patch_request=self.request('ko');self.assertEqual(patch_request['mode'],'patch')
        with self.assertRaisesRegex(ValueError,'request'):self.record(patch_request,{'backend_routes':self.full_routes([5]),'accounted':[{'file':ROUTERS[5],'kind':'items'}]},base='0'*64)

    # 9. Rename, delete, all-delete, missing base and rewritten history.
    def test_rename_delete_and_history_policies(self):
        self.baseline();source=self.full_routes([7],where='backend/app/routers/h07b.py')
        self.git('mv',ROUTERS[7],'backend/app/routers/h07b.py');self.git('rm','-q',ROUTERS[8]);self.commit('Move and delete')
        request=self.request()
        self.assertEqual(request['deleted'],[ROUTERS[7],ROUTERS[8]])
        self.assertEqual(request['inspect'],['backend/app/routers/h07b.py'])
        self.assertEqual(len(self.ids(request)),2*PER)
        # Deleted paths need no quote: git's D/R record disposes them; the moved routes are new items.
        self.record(request,{'backend_routes':source,'removed':sorted(self.ids(request)),'accounted':[{'file':'backend/app/routers/h07b.py','kind':'items'}]})
        self.assertEqual(len(self.raw()['dev']['backend_routes']),ROUTES-PER)
        self.git('commit','-q','--amend','-m','Rewritten');self.assertEqual(self.request()['mode'],'patch')  # saved commit is not an ancestor; tree diff is exact
        raw=self.raw();raw['dev']['commit']='f'*40;raw['dev']['analysis']['commit']='f'*40;project.publish('demo','service',raw,{})
        self.assertEqual(self.request()['reason'],'base_commit_missing')

    def test_all_deleted_code_saves_an_explicit_empty_map(self):
        self.baseline()
        self.git('rm','-rq','backend','frontend','worker');self.write({'README.md':'Retired\n'});self.commit('Retire')
        request=self.request();removed=sorted(self.ids(request))
        self.assertEqual(len(removed),ROUTES+1)
        with self.assertRaisesRegex(ValueError,'No valid'):self.record(request,{'removed':removed[1:],'accounted':[{'file':'README.md','kind':'none'}]})
        self.record(request,{'removed':removed,'accounted':[{'file':'README.md','kind':'none'}]})  # unknown=[] is truthful here
        m=self.raw()['dev'];self.assertEqual((m['screens'],m['backend_routes']),([],[]))

    # 10. Dependents: input proofs, deltas, and architecture review for code inside a program.
    def test_dependent_results_use_input_proofs(self):
        self.baseline();self.save_outputs()
        self.write({ROUTERS[5]:router(5,'# changed\n'),'backend/worker2/run.py':'while True:\n    drain()\n'});self.commit()
        request=self.request()
        self.record(request,{'backend_routes':self.full_routes([5]),'accounted':[{'file':ROUTERS[5],'kind':'items'},{'file':'backend/worker2/run.py','kind':'none'}]})
        self.assertEqual(self.tasks(),[('system','')])  # groups proof unchanged; a new worker inside a program needs architecture review
        review=ai_extract.task_request('demo','system','dev','en','service')
        self.assertEqual(review['input']['changed_files'],[ROUTERS[5],'backend/worker2/run.py'])
        with self.assertRaisesRegex(ValueError,'Account every changed file'):
            ai_extract.task_record(**review['record_arguments'],result_json=json.dumps({'keep':'all','accounted':[{'file':ROUTERS[5],'kind':'none'}]}))
        ai_extract.task_record(**review['record_arguments'],result_json=json.dumps({'keep':'all','accounted':[{'file':f,'kind':'none'} for f in review['input']['changed_files']]}))
        self.assertEqual(self.tasks(),[('jobs','api')])  # web's code and the served routes are unchanged

    def test_jobs_follow_route_changes_even_when_program_files_are_unchanged(self):
        self.baseline();self.save_outputs(worker=True)
        self.write({'backend/app/routers/h53.py':router(53),'backend/app/main.py':main_py(range(FILES+1))});self.commit()
        request=self.request()
        self.record(request,{'backend_routes':self.full_routes(range(FILES+1)),'accounted':[{'file':f,'kind':'items'} for f in request['inspect']]})
        review=ai_extract.task_request('demo','system','dev','en','service')
        ai_extract.task_record(**review['record_arguments'],result_json=json.dumps({'keep':'all','accounted':[{'file':f,'kind':'none'} for f in review['input']['changed_files']]}))
        tasks=self.tasks()
        self.assertIn(('jobs','worker'),tasks)  # a new route may now start the worker: its made_by input changed
        self.assertIn(('groups',''),tasks)
        delta=ai_extract.task_request('demo','groups','dev','en','service')
        self.assertEqual((len(delta['input']['new_routes']),delta['input']['changed_screens']),(PER,[]))
        ai_extract.task_record(**delta['record_arguments'],result_json=json.dumps({'keep':'previous','groups':[],'request_names':{k:'New' for k in delta['input']['new_routes']}}))
        g=project.branch_bundle(self.raw(),'dev')['groups']
        self.assertEqual((g['groups'][0]['screens'],len(g['request_names'])),(['/items'],PER))

    def test_valid_empty_jobs_settle_after_a_change(self):
        self.baseline()
        ev={'file':'backend/app/main.py','line':3,'quote':'app = FastAPI()'}
        self.save_task('system',{'nodes':[{'id':'api','name':'API','kind':'program','code':['backend'],'ev':[ev],'jobs':[],'unknown':['No background jobs were established.']}]})
        self.save_task('groups',{'groups':[{'name':'Items','screens':['/items']}],'names':{},'request_names':{}})
        self.assertEqual(self.tasks(),[])
        self.write({ROUTERS[5]:router(5,'# comment\n')});self.commit()
        request=self.request();self.record(request,{'backend_routes':self.full_routes([5]),'accounted':[{'file':ROUTERS[5],'kind':'items'}]})
        for _ in range(4):  # follow the actual handoff until it settles
            tasks=self.tasks()
            if not tasks:break
            task,target=tasks[0]
            r=ai_extract.task_request('demo',task,'dev','en','service',target)
            answer={'keep':'all','accounted':[{'file':f,'kind':'none'} for f in r['input']['changed_files']]} if task=='system' else {'jobs':[],'unknown':['No background jobs were established.']}
            ai_extract.task_record(**r['record_arguments'],result_json=json.dumps(answer))
        self.assertEqual(self.tasks(),[])
        self.assertEqual(project.branch_bundle(self.raw(),'dev')['jobs']['nodes']['api']['jobs'],[])
        r=ai_extract.task_request('demo','jobs','dev','en','service','api')
        with self.assertRaisesRegex(ValueError,'job'):ai_extract.task_record(**r['record_arguments'],result_json=json.dumps({'jobs':[]}))  # empty needs unknown

    def test_provenance_label_and_handoff_mention_the_pinned_base(self):
        html=(Path(__file__).resolve().parents[1]/'ui/index.html').read_text()
        self.assertIn("mixed:'AI 분석과 기본 수집으로 확인'",html)
        self.assertLess(html.index('"AI 분석과 기본 수집으로 확인"'),html.index('const UI_PATTERN'))
        request=self.request()
        self.assertIn('base',request['handoff']);self.assertIn('review',request['prompt'])
        self.assertEqual(request['record_arguments']['base'],request['base'])

if __name__=='__main__':unittest.main()
