"""Project configuration, repository snapshots, and a shared UI/MCP read model."""
from contextlib import contextmanager
from datetime import datetime, timezone
import argparse
import copy
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
sys.path.insert(0, str(Path(__file__).resolve().parent))

NAMES = ('dev', 'main', 'dev.prev', 'main.prev', 'status', 'changes', 'groups', 'flows', 'system', 'system.ai', 'jobs', 'tests')
STATUS_LISTS = ('open_prs','merged_prs','branches','worktrees','issues','overlaps')

def now():return datetime.now(timezone.utc).isoformat()
def home(name):
    import mapcore
    if not isinstance(name,str) or not name or name in ('.','..') or any(x in name for x in ('/','\\','\x00')):
        raise ValueError('Invalid project name')
    return Path(mapcore.ROOT)/name

def read(path, default=None):
    if not path.exists():return copy.deepcopy(default)
    return json.loads(path.read_text())

def atomic(path, value):
    path.parent.mkdir(parents=True,exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix='.write-',dir=path.parent)
    try:
        with os.fdopen(fd,'w') as stream:
            json.dump(value,stream,ensure_ascii=False,indent=1);stream.flush();os.fsync(stream.fileno())
        os.replace(temp,path)
    finally:
        if os.path.exists(temp):os.unlink(temp)

@contextmanager
def locked(name):
    root=home(name);root.mkdir(parents=True,exist_ok=True)
    with (root/'.project.lock').open('a') as stream:
        try:fcntl.flock(stream,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise ValueError('This project is already being updated; try again after it finishes')
        try:yield
        finally:fcntl.flock(stream,fcntl.LOCK_UN)

def config(name):
    value=read(home(name)/'project.json')
    return validate(value) if value is not None else None
def fingerprint(repo):
    return hashlib.sha256(json.dumps({k:repo.get(k) for k in ('path','refs','layout')},sort_keys=True).encode()).hexdigest()

def validate(data):
    if not isinstance(data,dict) or not isinstance(data.get('repositories'),list) or not data['repositories']:
        raise ValueError('Add at least one repository')
    result={'version':1,'repositories':[],'shared_data':copy.deepcopy(data.get('shared_data',[]))}
    ids=set();paths=set()
    for item in data['repositories']:
        rid=item.get('id','')
        if not re.fullmatch(r'[a-z][a-z0-9-]{0,47}',rid) or rid in ids:raise ValueError('Repository IDs must be unique lowercase names')
        raw=item.get('path','')
        if not isinstance(raw,str) or not raw or not os.path.isabs(os.path.expanduser(raw)):raise ValueError('Use an absolute repository folder path')
        path=os.path.realpath(os.path.expanduser(raw))
        if path in paths:raise ValueError('This repository folder is already registered')
        refs=item.get('refs',{'dev':'origin/dev','main':'origin/main'})
        if not isinstance(refs,dict):raise ValueError('Invalid refs')
        refs={key:refs.get(key) for key in ('dev','main')}
        if not any(refs.values()) or any(v is not None and (not isinstance(v,str) or not v or v.startswith('-') or any(c in v for c in '\n\r\x00')) for v in refs.values()):raise ValueError('Choose at least one valid branch ref')
        layout=item.get('layout',{})
        if not isinstance(layout,dict) or any(k not in ('frontend','backend') for k in layout):raise ValueError('Invalid source roots')
        for v in layout.values():
            if v is not None and (not isinstance(v,str) or not v or v.startswith('/') or '..' in v.split('/') or '\\' in v):raise ValueError('Source roots must be repository-relative paths')
        entry={'id':rid,'name':str(item.get('name') or rid),'path':path,'refs':refs,'layout':layout,'api_targets':item.get('api_targets',[])}
        if item.get('legacy'):entry['legacy']=True
        result['repositories'].append(entry);ids.add(rid);paths.add(path)
    for item in result['repositories']:
        targets=item['api_targets']
        if not isinstance(targets,list) or len(targets)!=len(set(targets)) or any(t not in ids or t==item['id'] for t in targets):raise ValueError('API destinations must name other registered repositories')
    shared=set();members=set()
    if not isinstance(result['shared_data'],list):raise ValueError('Invalid shared data mapping')
    for store in result['shared_data']:
        sid=store.get('id','')
        if not re.fullmatch(r'[a-z][a-z0-9-]{0,47}',sid) or sid in shared:raise ValueError('Invalid shared data ID')
        shared.add(sid)
        for member in store.get('members',[]):
            key=(member.get('repository'),member.get('table'))
            if key[0] not in ids or not isinstance(key[1],str) or not key[1] or key in members:raise ValueError('Invalid or duplicate shared data member')
            members.add(key)
    return result

def configure(name, data):
    proposed=validate(data)
    with locked(name):
        existing=read(home(name)/'project.json')
        # IDs remain stable. A legacy association must describe the actual old map.
        for repo in proposed['repositories']:
            if repo.get('legacy'):
                old=read(home(name)/'dev.json') or read(home(name)/'main.json')
                if not old or os.path.realpath(old.get('repo',''))!=repo['path']:raise ValueError('Legacy repository does not match the existing map')
        if not existing and not any(r.get('legacy') for r in proposed['repositories']) and any((home(name)/(role+'.json')).exists() for role in ('dev','main')):
            raise ValueError('Keep the existing repository as a legacy entry when adopting this project')
        atomic(home(name)/'project.json',proposed)
    return proposed

def states(name):return read(home(name)/'repository-state.json',{})
def _publish(name,rid, bundle, meta, collection=True):
    root=home(name);generation=uuid.uuid4().hex
    folder=root/'repositories'/rid/'snapshots'/generation
    folder.mkdir(parents=True)
    for key,value in bundle.items():
        if key in NAMES and value is not None:atomic(folder/(key+'.json'),value)
    state=states(name);record={**state.get(rid,{}),**meta,'generation':generation}
    if collection:record.update(last_attempt=now(),last_success=now(),error=None,in_progress=False)
    state[rid]=record
    atomic(root/'repository-state.json',state)

def publish(name,rid,bundle,meta):
    with locked(name):
        if rid not in {r['id'] for r in (config(name) or {}).get('repositories',[])}:raise ValueError('Unknown repository')
        _publish(name,rid,bundle,meta)

def _failed(name,rid,error):
    state=states(name);state[rid]={**state.get(rid,{}),'last_attempt':now(),'error':str(error),'in_progress':False}
    atomic(home(name)/'repository-state.json',state)

def failed(name,rid,error):
    with locked(name):_failed(name,rid,error)

def repository_folder(name,repo,state):
    generation=state.get(repo['id'],{}).get('generation')
    if generation:
        if not re.fullmatch(r'[a-f0-9]{32}',generation):raise ValueError('Invalid snapshot generation')
        return home(name)/'repositories'/repo['id']/'snapshots'/generation
    return home(name) if repo.get('legacy') else None

def raw_bundle(folder):return {key:read(folder/(key+'.json')) for key in NAMES} if folder else {key:None for key in NAMES}
def empty_map():return {'repo':'','commit':'','screens':[],'api_functions':[],'backend_routes':[],'backend_routes_without_screen':[],'unresolved_calls':[],'models':{},'file_screens':{}}
def qfile(rid,value):return rid+'/'+value if value else value
def qscreen(rid,value):
    if not value:return value
    return '/m/@'+rid+(value[2:] or '/') if value=='/m' or value.startswith('/m/') else '/@'+rid+(value if value.startswith('/') else '/'+value)

def qualify_map(source,repo,table_ids):
    m=copy.deepcopy(source or empty_map());rid=repo['id'];m['repository']=rid
    file=lambda value:qfile(rid,value)
    screen=lambda value:qscreen(rid,value)
    for s in m['screens']:
        s.update(repository=rid,source_path=s['path'],source_file=s.get('file'))
        s['path']=screen(s['path']);s['file']=file(s.get('file'))
        for ev in s.get('evidence') or []:
            if isinstance(ev,dict):ev['file']=file(ev.get('file'))
        for ref in s.get('api_functions',[]):
            ref['file']=file(ref['file']);ref['via']=file(ref.get('via'))
        for a in s.get('actions',[]):
            a['file']=file(a.get('file'));a['via']=file(a.get('via'))
            for t in a.get('targets',[]):
                if t.get('to'):t['to']=screen(t['to'])
    for f in m['api_functions']:
        f.update(repository=rid,source_file=f['file']);f['file']=file(f['file'])
        for call in f.get('calls',[]):
            if call.get('file'):call['file']=file(call['file'])
            for b in call.get('backend',[]):b['file']=file(b['file'])
    for r in m['backend_routes']:
        r.update(repository=rid,source_file=r['file']);r['file']=file(r['file'])
        r['services']=[file(x) for x in r.get('services',[])]
        for ev in [*(r.get('evidence') or []),*(r.get('table_evidence') or [])]:
            if isinstance(ev,dict):ev['file']=file(ev.get('file'))
        if r.get('flow'):
            r['flow']['file']=file(r['flow'].get('file'))
            for step in r['flow'].get('steps',[]):step['file']=file(step.get('file'))
        r['tests']=[file(x) for x in r.get('tests',[])]
        r['source_tables']=r.get('tables',[])
        r['tables']=[table_ids.get((rid,t),rid+'::'+t) for t in r.get('tables',[])]
    m['backend_routes_without_screen']=[copy.deepcopy(next((r for r in m['backend_routes'] if r['source_file']==o['file'] and r['line']==o['line']),o)) for o in m.get('backend_routes_without_screen',[])]
    for u in m.get('unresolved_calls',[]):u['api_function']=file(u['api_function']);u['repository']=rid
    m['models']={file(k):table_ids.get((rid,v),rid+'::'+v) for k,v in m.get('models',{}).items()}
    m['file_screens']={file(k):[screen(p) for p in v] for k,v in m.get('file_screens',{}).items()}
    return m

def _compose(name, conf, state, raws, repository=''):
    selected=[r for r in conf['repositories'] if not repository or r['id']==repository]
    if repository and not selected:raise ValueError('Unknown repository')
    ids={r['id'] for r in selected};allids={r['id'] for r in conf['repositories']}
    metadata=[];tables={}
    for store in conf.get('shared_data',[]):
        for member in store['members']:tables[(member['repository'],member['table'])]='shared::'+store['id']
    for repo in conf['repositories']:
        st=state.get(repo['id'],{});raw=raws[repo['id']]
        interrupted = st.get('in_progress') and not collection_running(name)
        if interrupted:st={**st,'error':'Previous collection was interrupted; last successful snapshot retained','in_progress':False}
        metadata.append({**repo,**st,'configured_path':repo['path'],'path':(raw.get('dev') or raw.get('main') or {}).get('repo',repo['path']),'collected':bool(raw.get('dev') or raw.get('main')),
            'analysis':{role:(raw.get(role) or {}).get('analysis') for role in ('dev','main')},
            'config_changed':bool(st.get('fingerprint') and st['fingerprint']!=fingerprint(repo)),
            'tables':sorted({v for role in ('dev','main') for v in ((raw.get(role) or {}).get('models') or {}).values()} | {t for role in ('dev','main') for route in (raw.get(role) or {}).get('backend_routes',[]) for t in route.get('tables',[])}),
            'commits':{role:(raw.get(role) or {}).get('commit') for role in ('dev','main')}})
    bundle={'project':{'name':name,'repositories':metadata,'selected':repository,'shared_data':conf.get('shared_data',[])},
        'status':{k:[] for k in STATUS_LISTS},'groups':{'names':{},'request_names':{},'groups':[]},
        'flows':{'routes':{}},'system':{'nodes':[],'links':[],'externals':[],'others':[],'unknown':[],'written':'','checked':''},
        'jobs':{'nodes':{}},'changes':{'last_refresh':'','entries':[]}}
    for role in ('dev','main','dev.prev','main.prev'):
        result=empty_map();result['repositories']=metadata;result['multi_repo']=True;result['connection_candidates']=[]
        qualified={r['id']:qualify_map(raws[r['id']].get(role) or (raws[r['id']].get(role.removesuffix('.prev')) if role.endswith('.prev') else None),r,tables) for r in conf['repositories']}
        for repo in conf['repositories']:
            rid=repo['id'];source=qualified[rid]
            if rid in ids:
                for k in ('screens','api_functions','unresolved_calls'):result[k]+=source.get(k,[])
                result['file_screens'].update(source['file_screens'])
            # Keep target routes available while filtering source screens.
            result['backend_routes']+=source['backend_routes'];result['models'].update(source['models'])
        route_index={}
        for r in result['backend_routes']:
            if r.get('mounted'):route_index.setdefault((r['method'],r['path']),[]).append(r)
        for fn in result['api_functions']:
            owner=next(r for r in conf['repositories'] if r['id']==fn['repository'])
            for call in fn.get('calls',[]):
                if call.get('backend') or not call.get('path'):continue
                hits=[r for r in route_index.get((call['method'],call['path']),[]) if r['repository']!=fn['repository']]
                allowed=[r for r in hits if r['repository'] in owner['api_targets']]
                if len(allowed)==1:
                    hit=allowed[0];call['backend']=[{'file':hit['file'],'line':hit['line'],'function':hit['function']}]
                    call['connection_basis']='configured';call['target_repository']=hit['repository']
                    # PR impact needs the frontend screen set for the target files too.
                    for screen in result['screens']:
                        if any(x['file']==fn['file'] and x['name']==fn['name'] for x in screen.get('api_functions',[])):
                            for f in [hit['file'],*hit.get('services',[])]:
                                result['file_screens'].setdefault(f,[])
                                if screen['path'] not in result['file_screens'][f]:result['file_screens'][f].append(screen['path'])
                elif hits:
                    result['connection_candidates'].append({'repository':fn['repository'],'file':fn['file'],'function':fn['name'],
                        'method':call['method'],'path':call['path'],'targets':[{'repository':r['repository'],'file':r['file'],'line':r['line']} for r in hits]})
        used={(b['file'],b['line']) for f in result['api_functions'] for c in f['calls'] for b in c.get('backend',[])}
        result['backend_routes_without_screen']=[r for r in result['backend_routes'] if r.get('mounted') and (r['file'],r['line']) not in used and r['repository'] in ids]
        result['unresolved_calls']=[u for u in result['unresolved_calls'] if any(f['file']+':'+f['name']==u['api_function'] and any(not c.get('backend') and c.get('path')==u.get('path') for c in f['calls']) for f in result['api_functions'])]
        result['available']=any(raws[rid].get(role) for rid in ids)
        result['commit']=hashlib.sha256(json.dumps({rid:(raws[rid].get(role) or {}).get('commit') for rid in sorted(allids)},sort_keys=True).encode()).hexdigest()[:12]
        result['ref']=role;bundle[role]=result
    for repo in conf['repositories']:
        rid=repo['id'];raw=raws[rid];file=lambda x:qfile(rid,x);screen=lambda x:qscreen(rid,x)
        related_issues={}
        active_map=bundle['dev'] if bundle['dev']['available'] else bundle['main']
        for pr in [*(raw.get('status') or {}).get('open_prs',[]),*(raw.get('status') or {}).get('merged_prs',[])]:
            affected={p for f in pr.get('files',[]) for p in active_map['file_screens'].get(file(f),[])}
            for number in {i['number'] for i in pr.get('issues',[])} | set(pr.get('refs',[])):
                if number!=pr['number']:related_issues.setdefault(number,set()).update(affected)
        for k in STATUS_LISTS:
            for item in (raw.get('status') or {}).get(k,[]):
                x=copy.deepcopy(item);x['repository']=rid
                if 'title' in x:x['title']='['+repo['name']+'] '+x['title']
                if 'files' in x:x['files']=[file(f) for f in x['files']]
                # Recompute cross-repository file impact from the composed map.
                x['screens']=sorted(set([screen(p) for p in x.get('screens',[])]+[p for f in [*x.get('files',[]),*[file(f) for f in x.get('uncommitted',[])]] for p in (bundle['dev'] if bundle['dev']['available'] else bundle['main'])['file_screens'].get(f,[])]))
                if k=='issues' and x.get('via')=='pr':
                    x['screens']=sorted(set(x['screens']) | related_issues.get(x['number'],set()))
                if rid in ids or any(p in {s['path'] for s in (bundle['dev'] if bundle['dev']['available'] else bundle['main'])['screens']} for p in x['screens']):bundle['status'][k].append(x)
        g=raw.get('groups') or {}
        bundle['groups']['names'].update({screen(k):v for k,v in g.get('names',{}).items()})
        bundle['groups']['request_names'].update({file(k):v for k,v in g.get('request_names',{}).items()})
        if rid in ids:bundle['groups']['groups'] += [{**g,'name':'['+repo['name']+'] '+g['name'],'screens':[screen(p) for p in g['screens']]} for g in (raw.get('groups') or {}).get('groups',[])]
        for key,value in (raw.get('flows') or {}).get('routes',{}).items():
            flow=copy.deepcopy(value)
            if flow.get('file'):flow['file']=file(flow['file'])
            for step in flow.get('steps',[]):
                if step.get('file'):step['file']=file(step['file'])
            bundle['flows']['routes'][file(key)]=flow
        sy=copy.deepcopy(raw.get('system') or {});prefix=rid+'::'
        def evidence(obj):
            if isinstance(obj,dict):
                if 'file' in obj and ('line' in obj or 'quote' in obj):obj['file']=file(obj['file']);obj['repository']=rid
                for value in obj.values():evidence(value)
            elif isinstance(obj,list):
                for value in obj:evidence(value)
        evidence(sy)
        nodes=sy.get('nodes',[])
        if not nodes:
            nodes=[{'id':'repository','name':repo['name'],'kind':'repository','origin':'repo','origin_text':repo['path'],
                'what':'Repository · '+str(len((raw.get('dev') or {}).get('screens',[])))+' screens',
                'code':[],'uses':[],'ev':[],'unknown':[]}]
        for n in nodes:
            x=copy.deepcopy(n);x.update(id=prefix+n['id'],repository=rid,name='['+repo['name']+'] '+n['name'])
            x['code']=[file(v) for v in n.get('code',[])];x['uses']=[prefix+v for v in n.get('uses',[])]
            x['tables']=[tables.get((rid,t),rid+'::'+t) for t in n.get('tables',[])]
            for c in x.get('copies',[]):
                for f in c.get('files',[]):f['path']=file(f['path'])
            bundle['system']['nodes'].append(x)
        if True:
            bundle['system']['others'] += sy.get('others',[])
            bundle['system']['links'] += [{**l,'from':prefix+l['from'],'to':prefix+l['to']} for l in sy.get('links',[])]
            bundle['system']['externals'] += [{**e,'id':prefix+e['id']} for e in sy.get('externals',[])]
            bundle['system']['unknown'] += sy.get('unknown',[])
        for nid,value in (raw.get('jobs') or {}).get('nodes',{}).items():
            x=copy.deepcopy(value);evidence(x)
            for j in x.get('jobs',[]):
                for r in j.get('routes',[]):r['key']=file(r['key'])
            bundle['jobs']['nodes'][prefix+nid]=x
        if rid in ids:
            ch=raw.get('changes') or {}
            bundle['changes']['last_refresh']=max(bundle['changes']['last_refresh'],ch.get('last_refresh',''))
            for entry in ch.get('entries',[]):
                e=copy.deepcopy(entry);e['repository']=rid
                for delta in e.get('branches',{}).values():
                    for key in ('screens_added','screens_removed'):
                        for v in delta.get(key,[]):v['path']=screen(v['path']);v['name']='['+repo['name']+'] '+v['name']
                    for key in ('requests_added','requests_removed'):
                        for v in delta.get(key,[]):v['screen']=screen(v['screen'])
                    for key in ('flows_added','flows_removed'):
                        for v in delta.get(key,[]):v['from']=screen(v['from']);v['to']=screen(v['to'])
                for pr in e.get('prs',[]):pr['repository']=rid;pr['title']='['+repo['name']+'] '+pr['title'];pr['screens']=[screen(p) for p in pr.get('screens',[])]
                bundle['changes']['entries'].append(e)
    # Explicit repository-level API destinations are not claimed as code-proven.
    for repo in conf['repositories']:
        for target in repo['api_targets']:
            source_node=next((n for n in bundle['system']['nodes'] if n['repository']==repo['id']),None)
            target_node=next((n for n in bundle['system']['nodes'] if n['repository']==target),None)
            if source_node and target_node:bundle['system']['links'].append({'from':source_node['id'],'to':target_node['id'],'label':'Configured API destination','sure':'doc','ev':[]})
    if repository:
        selected_nodes={n['id'] for n in bundle['system']['nodes'] if n['repository']==repository}
        related=set(selected_nodes)
        for link in bundle['system']['links']:
            if link['from'] in selected_nodes or link['to'] in selected_nodes:related.update((link['from'],link['to']))
        bundle['system']['nodes']=[n for n in bundle['system']['nodes'] if n['id'] in related]
        bundle['system']['links']=[l for l in bundle['system']['links'] if l['from'] in related and l['to'] in related]
        used={e for n in bundle['system']['nodes'] for e in n.get('uses',[])}
        bundle['system']['externals']=[e for e in bundle['system']['externals'] if e['id'] in used]
    for role in ('dev','main','dev.prev','main.prev'):
        if not bundle[role]['available']:bundle[role]=None
    bundle['changes']['entries'].sort(key=lambda e:e['at'],reverse=True)
    return bundle

def collection_running(name):
    path=home(name)/'.project.lock'
    if not path.exists():return False
    with path.open('r') as stream:
        try:fcntl.flock(stream,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return True
        fcntl.flock(stream,fcntl.LOCK_UN);return False

def read_bundle(name, repository=''):
    conf=config(name)
    if not conf:
        if repository:raise ValueError('This legacy project has no repository selector')
        result=raw_bundle(home(name));result['project']={'name':name,'repositories':[],'selected':''};return result
    state=states(name)
    raws={r['id']:raw_bundle(repository_folder(name,r,state)) for r in conf['repositories']}
    return _compose(name,conf,state,raws,repository)

def child_environment(root,repo):
    env=dict(os.environ,WHERE_WERE_WE_ROOT=str(root),WHERE_WERE_WE_REFS=json.dumps(repo['refs']),WHERE_WERE_WE_LAYOUT=json.dumps(repo['layout']))
    return env

def _transaction(name,repo,command, reset=False):
    import mapcore
    state=states(name);previous=repository_folder(name,repo,state)
    with tempfile.TemporaryDirectory(prefix='.collect-',dir=home(name)) as temp:
        childroot=Path(temp);stage=childroot/repo['id'];stage.mkdir()
        if previous:
            for key in NAMES:
                path=previous/(key+'.json')
                if path.exists():shutil.copyfile(path,stage/path.name)
        if reset:
            for key in ('dev','main','dev.prev','main.prev','status','changes'):
                (stage/(key+'.json')).unlink(missing_ok=True)
        result=subprocess.run(mapcore.python_command(Path(__file__).with_name(command[0]),repo['id'],*command[1:]),
            env=child_environment(childroot,repo),capture_output=True,text=True,timeout=1800)
        if result.returncode:raise ValueError((result.stderr or result.stdout)[-1600:] or 'Collection failed')
        _publish(name,repo['id'],raw_bundle(stage),{'fingerprint':fingerprint(repo)} if command[0]=='refresh.py' else {},collection=command[0]=='refresh.py')
        return result.stdout

def refresh_project(name, repository='', since='7'):
    with locked(name):
        conf=config(name)
        if not conf:raise ValueError('Configure a project first')
        repos=[r for r in conf['repositories'] if not repository or r['id']==repository]
        if not repos:raise ValueError('Unknown repository')
        messages=[]
        for repo in repos:
            old=states(name).get(repo['id'],{})
            state=states(name);state[repo['id']]={**old,'last_attempt':now(),'in_progress':True};atomic(home(name)/'repository-state.json',state)
            try:
                _transaction(name,repo,['refresh.py',repo['path'],since],reset=old.get('fingerprint')!=fingerprint(repo))
                messages.append(repo['id']+': refreshed')
            except Exception as error:
                _failed(name,repo['id'],str(error));messages.append(repo['id']+': FAILED: '+str(error))
        return '\n'.join(messages)

def selected_repository(name,rid=''):
    conf=config(name)
    if not conf:return None
    repos=conf['repositories']
    if not rid and len(repos)==1:return repos[0]
    hit=next((r for r in repos if r['id']==rid),None)
    if not hit:raise ValueError('Choose a repository: '+', '.join(r['id'] for r in repos))
    return hit

def action(name,rid,script,args=()):
    with locked(name):
        repo=selected_repository(name,rid)
        if not repo:raise ValueError('Use the legacy command for this project')
        if states(name).get(repo['id'],{}).get('fingerprint')!=fingerprint(repo):raise ValueError('Refresh this repository after configuration changes before running AI actions')
        return _transaction(name,repo,[script,*args])

def mutate_tests(name,rid,callback):
    with locked(name):
        repo=selected_repository(name,rid)
        state=states(name).get(repo['id'],{})
        if state.get('fingerprint') and state['fingerprint']!=fingerprint(repo):raise ValueError('Refresh this repository after configuration changes before editing test rules')
        raw=raw_bundle(repository_folder(name,repo,states(name)))
        if not (raw.get("dev") or raw.get("main")):raise ValueError("Refresh this repository first")
        result=callback(raw,repo)
        _publish(name,repo['id'],raw,{},collection=False)
        return result

def record_test(name,rid,route,file,line,quote):
    def update(raw,repo):
        method,_,path=route.partition(' ');m=raw.get('dev') or raw.get('main')
        hits=[r for r in m['backend_routes'] if r['method']==method.upper() and r['path']==path.strip()]
        if len(hits)!=1:raise ValueError('Choose a unique request in this repository')
        source_file=file[len(repo['id'])+1:] if file.startswith(repo['id']+'/') else file
        result=subprocess.run(['git','-C',repo['path'],'show',m['commit']+':'+source_file],capture_output=True,text=True,check=True)
        q=''.join(quote.split());lines=result.stdout.splitlines()
        if len(q)<6 or line<1 or not any(q in ''.join(v.split()) for v in lines[max(0,line-3):line+2]):raise ValueError('Test evidence does not match this repository snapshot')
        value=raw.get('tests') or {};entry={'route':hits[0]['file']+'::'+hits[0]['function'],'file':source_file,'line':line,'quote':quote}
        if entry not in value.setdefault('records',[]):value['records'].append(entry)
        raw['tests']=value
        return 'Saved verified test evidence for '+repo['id']
    return mutate_tests(name,rid,update)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['read','configure','refresh','action']);parser.add_argument('project')
    parser.add_argument('--repository',default='');parser.add_argument('args',nargs='*')
    args=parser.parse_args()
    if args.command=='read':print(json.dumps(read_bundle(args.project,args.repository),ensure_ascii=False))
    elif args.command=='configure':print(json.dumps(configure(args.project,json.loads(args.args[0]) if args.args else json.load(sys.stdin)),ensure_ascii=False))
    elif args.command=='refresh':print(refresh_project(args.project,args.repository))
    else:
        if not args.args:raise ValueError('Choose an action')
        script=args.args[0]
        if script not in ('group.py','steps.py','system.py','jobs.py','ai_extract.py'):raise ValueError('Unknown action')
        print(action(args.project,args.repository,script,args.args[1:]))
if __name__=='__main__':
    try:main()
    except Exception as error:print(str(error),file=sys.stderr);sys.exit(1)
