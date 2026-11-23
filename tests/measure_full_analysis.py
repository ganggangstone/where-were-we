#!/usr/bin/env python3
"""Measure the full code analysis of one repository with a fake executor. Never calls real AI.

    python3 tests/measure_full_analysis.py --code . --root /tmp/root --repo /path/to/repo [--project-data DIR] [--ref HEAD]

--code is the source tree to measure (so the same script times an older export and the working tree).
--project-data copies a saved legacy project folder into the root (its dev.json repo path is rewritten to --repo).
Prints one JSON object: local timings, units, the call limit shown at start, calls and bytes per stage,
an interrupted run continued to the end, and whether a reopened board counts what the run saved.
The fake answers every packet with the smallest valid reply, so call counts are the protocol's fixed
part: real models add read requests and retries on top."""
import argparse
import collections
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

parser=argparse.ArgumentParser()
parser.add_argument('--code',required=True);parser.add_argument('--root',required=True);parser.add_argument('--repo',required=True)
parser.add_argument('--project-data');parser.add_argument('--ref',default='HEAD');parser.add_argument('--coverage',default='signal')
parser.add_argument('--fail-at',type=int,default=0,help='interrupt the first run at this call (0: at a third of the limit)')
parser.add_argument('--skip-run',action='store_true');parser.add_argument('--no-change',action='store_true',help='skip the changed_code step')
args=parser.parse_args()
os.environ['WHERE_WERE_WE_ROOT']=args.root
sys.path.insert(0,str(Path(args.code).resolve()))
import mapcore  # noqa: E402
import project  # noqa: E402
import analysis_run  # noqa: E402

real_run=subprocess.run
def guard(command,**kwargs):
    if Path(str(command[0])).name=='claude':raise AssertionError('Real AI calls are forbidden here')
    return real_run(command,**kwargs)
subprocess.run=guard

NAME='measured';out={'code':str(Path(args.code).resolve()),'repo':args.repo}
def timed(key,fn):
    start=time.monotonic();value=fn();out.setdefault('seconds',{})[key]=round(time.monotonic()-start,2);return value

root=Path(args.root)
if not (root/NAME).exists():
    root.mkdir(parents=True,exist_ok=True)
    if args.project_data:
        shutil.copytree(args.project_data,root/NAME)
        for name in ('dev.json','dev.base.json'):
            path=root/NAME/name
            if path.exists():
                data=json.loads(path.read_text());data['repo']=args.repo;path.write_text(json.dumps(data))
        out['seconds']={'first_map':None}
    else:
        project.configure(NAME,{'repositories':[{'id':'service','path':args.repo,'refs':{'dev':args.ref,'main':None}}]})
        timed('first_map',lambda:project.refresh_project(NAME))
RID='' if args.project_data else 'service'

def board():
    value=analysis_run.unit_board(NAME,RID,'dev','ko')
    if value.get('signals')=='pending':
        timed('signal_scan',lambda:analysis_run.unit_signals(NAME,RID,'dev','ko'));value=analysis_run.unit_board(NAME,RID,'dev','ko')
    return value
if hasattr(analysis_run,'unit_quick'):timed('board_quick',lambda:analysis_run.unit_quick(NAME,RID,'dev','ko'))
first=timed('board',board)
def summary(b):
    rows=[r for repo in b['repositories'] for r in repo['units']]
    return {'totals':b['totals'],'kinds':dict(collections.Counter(r[1] for r in rows)),'calls':b['modes'][args.coverage]['calls'],
            'parts':b['modes'][args.coverage]['calls_parts'],'coverage':[r['coverage'] for r in b['repositories']],
            'map_coverage':[r.get('map_coverage') for r in b['repositories']]}
out['board']=summary(first)

stats=collections.defaultdict(lambda:[0,0]);order=[]
def kind(p):
    schema=p.get('schema') or {}
    if 'screens' in schema:return 'map'
    if 'nodes' in schema:return 'structure'
    if 'groups' in schema:return 'groups'
    if 'resources' in p or p.get('resource'):return 'units'
    return 'overview'
def first_ref(packet):
    for source in packet.get('sources',[]):
        for line in source['lines']:return line[0] if isinstance(line,list) else line['ref']
    return None
def items(packet):
    ref=first_ref(packet)
    return [{'name':'Feature','role':'Role','description':'Does something','ref':ref}] if ref else []
def cite(p):
    """One literal line of the supplied source, so an empty map is still an answer that inspected code."""
    for snapshot in p.get('snapshots',[]):
        for file in snapshot['files']:
            for row in file.get('lines') or file.get('numbered_lines') or []:
                line,text=(row[0],row[1]) if isinstance(row,list) else (row['line'],row['text'])
                if len(text.strip())>=6 and 'offset' not in (row if isinstance(row,dict) else {}) and not (isinstance(row,list) and len(row)>2):
                    return [{'file':file['file'],'line':line,'quote':text.strip()[:80]}]
    return []
_EV=[];_DROPPED=set()
def repo_evidence():
    """One literal source line read straight from the pinned commit, for the structure answer (its packet carries no source)."""
    if not _EV:
        commit=real_run(['git','-C',args.repo,'rev-parse',first['repositories'][0]['commit']],capture_output=True,text=True).stdout.strip()
        names=real_run(['git','-C',args.repo,'ls-tree','-r','--name-only',commit],capture_output=True,text=True).stdout.splitlines()
        for name in sorted(names,key=lambda n:(not n.endswith(('.py','.ts','.go','.js','.tsx')),n.count('/')==0,n)):
            text=real_run(['git','-C',args.repo,'show',commit+':'+name],capture_output=True).stdout.decode('utf-8','replace')
            row=next(((i,t) for i,t in enumerate(text.splitlines(),1) if len(t.strip())>=12 and t.isascii()),None)
            if row:_EV.append({'file':name,'line':row[0],'quote':row[1].strip()[:80]});break
    return _EV[0]
def structure():
    ev=repo_evidence()
    return {'nodes':[{'id':'app','name':'App','kind':'program','code':[ev['file'].split('/')[0] if '/' in ev['file'] else '.'],'ev':[ev]}],'links':[],'externals':[],'others':[],'unknown':[]}
class Stop(Exception):pass
limit=[0]
first_call=[None]
def fake(prompt,**kwargs):
    first_call[0]=first_call[0] or time.monotonic()
    p=json.loads(prompt.split('\n',1)[1]);k=kind(p)
    if limit[0] and sum(v[0] for v in stats.values())>=limit[0]:raise Stop()
    stats[k][0]+=1;stats[k][1]+=len(prompt.encode());order.append(k)
    if 'batch' in p:
        result=structure() if k=='structure' else {}
        if k=='map':
            result={'inspected':cite(p),'unknown':['fake executor']}
            if p.get('mode')=='review':
                # A review must dispose every recheck target; the fake drops the ones whose page this packet carries.
                ids=[page['value']['id'] for page in p.get('context_pages',[]) if page['path'][:1]==['recheck'] and isinstance(page.get('value'),dict) and 'id' in page['value']]
                ids+=[r['id'] for page in p.get('context_pages',[]) if page['path']==['recheck'] and isinstance(page.get('value'),list) for r in page['value'] if isinstance(r,dict) and 'id' in r]
                for r in p.get('recheck',[]):  # a short recheck list rides in every packet's header: dispose it once
                    if isinstance(r,dict) and r.get('id') not in _DROPPED:_DROPPED.add(r['id']);ids.append(r['id'])
                result.update(keep='all',**({'drop':ids} if ids else {}))
        return {'batch':p['batch']['id'],'covered':p['batch']['units'],'result':result,'needs':[]}
    if 'resources' in p:return {'results':[{'resource':r['resource'],'items':items(r)} for r in p['resources']]}
    if k in ('units','overview'):return {'items':items(p)}
    if k=='map':
        base={'screens':[],'backend_routes':[],'inspected':cite(p),'unknown':['fake executor']}
        if p.get('mode')=='review':base['keep']='all'
        if p.get('mode')=='patch':base.update(removed=[],accounted=[{'file':f,'kind':'none'} for f in p.get('inspect',[])])
        return base
    if k=='structure':return structure()
    return {'groups':[],'names':{},'request_names':{}}

def run_once(job):
    start=time.monotonic()
    try:done=analysis_run.run(job['id'],fake)
    except Stop:done=analysis_run.status(job['id'])
    return done,round(time.monotonic()-start,1)
def snapshot():return {k:{'calls':v[0],'bytes':v[1]} for k,v in stats.items()}

def total():return sum(v[0] for v in stats.values())
def continue_to_end(job,intent,done,runs=1,key='later_errors'):
    """What the board's continue button does: a new confirmation with the number the board shows now. Capped at 12 runs."""
    state=done['state']
    while state!='completed' and runs<12:
        b=analysis_run.unit_board(NAME,RID,'dev','ko')
        try:job=analysis_run.prepare(NAME,'dev','ko',RID,intent={**intent,'max_calls':b['modes'][args.coverage]['calls']})
        except Exception as error:out[key+'_continue']=str(error);break
        done,_=run_once(job);state=done['state'];runs+=1
        if state!='completed':out.setdefault(key,[]).append((done.get('error') or {}).get('message','')[:200])
    return state,runs,job

def totals_equal(job_id):
    """Does the board of the run equal the board opened now (every totals key)?"""
    try:run=analysis_run._run_board(analysis_run.read(job_id))
    except Exception as error:return {'error':str(error)[:100]}
    now=analysis_run.unit_board(NAME,RID,'dev','ko')
    return {'equal':run['totals']==now['totals'],'run':run['totals'],'board':now['totals']}

if not args.skip_run:
    cap=out['board']['calls'];intent={'task':'full','targets':[],'max_calls':cap,'coverage':args.coverage}
    limit[0]=args.fail_at or max(2,cap//3)
    t0=time.monotonic();job=analysis_run.prepare(NAME,'dev','ko',RID,intent=intent);prepared=time.monotonic()
    done,seconds=run_once(job)
    out['time_to_first_call']={'prepare_seconds':round(prepared-t0,2),'local_seconds_before_first_ai_call':round((first_call[0] or time.monotonic())-t0,2),
                               'note':'fake executor: real AI latency is not measured'}
    out['interrupted']={'state':done['state'],'error':(done.get('error') or {}).get('code'),'calls':total(),'local_seconds':seconds,'first_calls':order[:3]}
    reopened=analysis_run.unit_board(NAME,RID,'dev','ko')
    live=analysis_run._run_board(analysis_run.read(job['id'])) if 'units' in analysis_run.read(job['id']) else None
    out['reopen_after_interrupt']={'board':reopened['totals'],'run':live and live['totals'],'match':bool(live) and reopened['totals']==live['totals'],
                                   'calls_shown':reopened['modes'][args.coverage]['calls'],'budget':reopened.get('budget')}
    limit[0]=0
    state,runs,job=continue_to_end(job,intent,done)
    final=analysis_run.unit_board(NAME,RID,'dev','ko')
    out['finished']={'state':state,'runs':runs,'calls':total(),'bytes':sum(v[1] for v in stats.values()),'by_stage':snapshot(),'cap_shown_at_start':cap,
                     'within_limit':total()<=cap,'board':final['totals'],'calls_left_shown':final['modes'][args.coverage]['calls'],'run_equals_reopened':totals_equal(job['id'])}
    # What opening three cards does (a tree that has `only`): a route or program, a code folder and a local (documents/tests) folder.
    rows=[r for r in final['repositories'][0]['units'] if not r[0].startswith('task:') and r[4] in ('pending','local')]
    pick=[next((r for r in rows if r[1] in ('route','program') and r[4]=='pending'),None),next((r for r in rows if r[1]=='folder' and r[4]=='pending' and not r[0].startswith('folder:local:')),None),
          next((r for r in rows if r[0].startswith('folder:local:')),None)]
    pick=[r for r in pick if r]
    if pick and hasattr(analysis_run,'_only_board'):
        before=snapshot();rid=final['repositories'][0]['repository'];n=len(pick)
        try:job=analysis_run.prepare(NAME,'dev','ko',RID,intent={'task':'full','targets':[],'max_calls':n+-(-n//2),'coverage':args.coverage,'only':[{'repository':rid,'target':r[0]} for r in pick]})
        except Exception as error:out['on_demand']={'error':str(error)}
        else:
            done,seconds=run_once(job);after=snapshot();units=after.get('units',{'calls':0,'bytes':0});was=before.get('units',{'calls':0,'bytes':0})
            states={r[0]:r[4] for r in analysis_run.unit_board(NAME,RID,'dev','ko')['repositories'][0]['units']}
            out['on_demand']={'state':done['state'],'units':[r[0] for r in pick],'calls':units['calls']-was['calls'],'bytes':units['bytes']-was['bytes'],'seconds':seconds,
                              'states':{r[0]:states.get(r[0]) for r in pick},'run_equals_reopened':totals_equal(job['id'])}
    if not args.no_change and state=='completed':
        # One line changes in one tracked source file of the (throwaway) repository; then the same full run is started again.
        env={**os.environ,'GIT_INDEX_FILE':str(root/'change.index'),'GIT_AUTHOR_NAME':'m','GIT_AUTHOR_EMAIL':'m@example.invalid','GIT_COMMITTER_NAME':'m','GIT_COMMITTER_EMAIL':'m@example.invalid'}
        def git(*a,**k):return real_run(['git','-C',args.repo,*a],capture_output=True,env=env,**k)
        ref=git('rev-parse','--symbolic-full-name',final['repositories'][0].get('ref') or ('origin/dev' if args.project_data else 'HEAD'),text=True).stdout.strip() or 'HEAD'
        head=git('rev-parse',ref,text=True).stdout.strip()
        names=git('ls-tree','-r','--name-only',head,text=True).stdout.splitlines()
        pick_file=next((n for n in sorted(names,key=lambda n:(n.count('/'),n)) if n.endswith(('.py','.ts','.go')) and not any(w in n for w in ('test','vendor','node_modules','docs','example','fixtures','migrations'))),None)
        if pick_file:
            body=git('show',head+':'+pick_file).stdout
            note=b'\n// measured change\n' if pick_file.endswith(('.ts','.go')) else b'\n# measured change\n'
            blob=real_run(['git','-C',args.repo,'hash-object','-w','--stdin'],input=body+note,capture_output=True,env=env).stdout.strip().decode()
            mode=next(l.split()[0] for l in git('ls-tree',head,'--',pick_file,text=True).stdout.splitlines())
            git('read-tree',head);git('update-index','--cacheinfo',f'{mode},{blob},{pick_file}')
            tree=git('write-tree',text=True).stdout.strip();new=git('commit-tree',tree,'-p',head,'-m','measured change',text=True).stdout.strip()
            git('update-ref',ref,new)
            if not args.project_data:timed('refresh_after_change',lambda:project.refresh_project(NAME))
            analysis_run._INDEXES.clear()
            changed=timed('board_after_change',board);rows=[r for r in changed['repositories'][0]['units'] if not r[0].startswith('task:')]
            c_cap=changed['modes'][args.coverage]['calls'];c_intent={'task':'full','targets':[],'max_calls':c_cap,'coverage':args.coverage}
            c0,b0=total(),sum(v[1] for v in stats.values());snap=snapshot();limit[0]=0
            job=analysis_run.prepare(NAME,'dev','ko',RID,intent=c_intent);done,seconds=run_once(job)
            state2,runs2,job=continue_to_end(job,c_intent,done,key='changed_later_errors')
            after=snapshot()
            out['changed_code']={'file':pick_file,'state':state2,'runs':runs2,'board_calls_shown':c_cap,'calls':total()-c0,'bytes':sum(v[1] for v in stats.values())-b0,
                                 'by_stage':{k:{'calls':v['calls']-snap.get(k,{'calls':0})['calls'],'bytes':v['bytes']-snap.get(k,{'bytes':0})['bytes']} for k,v in after.items()},
                                 'units_saved_after_change':sum(1 for r in rows if r[4]=='saved'),'units_stale_after_change':sum(1 for r in rows if r[4]=='stale'),
                                 'units_total':len(rows),'totals_after_change':changed['totals']}
print(json.dumps(out,ensure_ascii=False))
