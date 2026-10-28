#!/usr/bin/env python3
"""Explicit, language-independent AI maps with commit-bound source evidence.

Accepts results from any connected MCP agent. CLI commands only prepare requests; normal refresh never invokes an AI provider.
"""
import copy
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tempfile
sys.path.insert(0,str(Path(__file__).resolve().parent))
import mapcore
import project

VERSION=2
METHODS={'GET','POST','PUT','PATCH','DELETE','HEAD','OPTIONS'}
EVIDENCE_LISTS=('evidence','table_evidence','service_evidence','external_evidence','dependencies','actions')

def git(repo,*args):
    return subprocess.run(['git','-C',repo,*args],capture_output=True,text=True,check=True).stdout

def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
def route_id(r):
    # Endpoint identity: one per method/path/registration/handler/mount; the handler flow (file::function) is shared.
    mount=next((d['file'] for d in r.get('dependencies') or [] if isinstance(d,dict) and d.get('file')),'')
    return 'r:'+digest([r.get('method'),r.get('path'),r.get('file'),r.get('function'),mount])[:16]
def screen_id(s):return 's:'+digest(s.get('path'))[:16]
def handler(r):return str(r.get('file'))+'::'+str(r.get('function'))

def evidence_reader(repo,commit):
    files=set(git(repo,'ls-tree','-r','--name-only',commit).splitlines());cache={};rejected=0
    def evidence(item):
        nonlocal rejected
        if not isinstance(item,dict):rejected+=1;return None
        file=item.get('file');line=item.get('line');quote=item.get('quote')
        if (not isinstance(file,str) or file not in files or PurePosixPath(file).is_absolute() or '..' in PurePosixPath(file).parts
            or type(line) is not int or line<1 or not isinstance(quote,str) or len(quote.strip())<6):
            rejected+=1;return None
        if file not in cache:cache[file]=git(repo,'show',commit+':'+file).splitlines()
        lines=cache[file]
        # Exact line and literal quote: successful text matching does not prove semantics.
        if line>len(lines) or quote not in lines[line-1]:rejected+=1;return None
        return {'file':file,'line':line,'quote':quote}
    evidence.files=files
    return evidence,cache,lambda:rejected

def parse(data,evidence,commit):
    """Verified AI items only; links between them are computed by link()."""
    if not isinstance(data,dict):raise ValueError('AI output must be an object')
    def rows(obj,key):
        value=obj.get(key,[])
        if not isinstance(value,list) or len(value)>5000:raise ValueError('Invalid AI list: '+key)
        return value
    def text(value):return value if isinstance(value,str) else ''
    def endpoint(item):
        return item.get('method') in METHODS and isinstance(item.get('path'),str) and item['path'].startswith('/')
    stamp={'source':'ai','verified_commit':commit,'checked_commit':commit}
    flows={};seen=set();screens=[];routes=[];functions=[]
    for item in rows(data,'backend_routes'):
        ev=evidence(item)
        if not ev or not endpoint(item) or not text(item.get('function')):continue
        tables=[];table_evidence=[];externals=[];external_evidence=[];services=[];service_evidence=[]
        for table in rows(item,'tables'):
            tev=evidence(table)
            if tev and text(table.get('name')):tables.append(table['name']);table_evidence.append({**tev,'name':table['name']})
        for service in rows(item,'services'):
            if sev:=evidence(service):services.append(sev['file']);service_evidence.append(sev)
        for external in rows(item,'externals'):
            if (xev:=evidence(external)) and text(external.get('name')):externals.append(external['name']);external_evidence.append({**xev,'name':external['name']})
        route={**ev,'method':item['method'],'path':mapcore.normalize_http_path(item['path']),'function':item['function'],'mounted':True,
               'tables':sorted(set(tables)),'table_evidence':table_evidence,'externals':externals,'external_evidence':external_evidence,
               'services':sorted(set(services)),'service_evidence':service_evidence,
               'dependencies':[d for x in rows(item,'dependencies') if (d:=evidence(x))],'tests':[],'evidence':[ev],**stamp}
        route['id']=route_id(route)
        if isinstance(item.get('replaces'),str):route['replaces']=item['replaces']
        if route['id'] in seen:raise ValueError('Duplicate AI route identity')
        seen.add(route['id']);routes.append(route)
        steps=[]
        for step in rows(item,'steps'):
            sev=evidence(step)
            if sev and text(step.get('text')):
                steps.append({**sev,'text':step['text'],'lane':step.get('lane') if step.get('lane') in ('서버','화면','저장소','외부') else '서버',
                              'uncertain':bool(step.get('uncertain'))})
        if steps and handler(route) not in flows:flows[handler(route)]={'name':text(item.get('name')) or item['function'],
            'file':ev['file'],'function':item['function'],'commit':commit,'source':'ai','steps':steps}
    seen=set()
    for item in rows(data,'screens'):
        ev=evidence(item)
        if not ev or not isinstance(item.get('path'),str) or not item['path'].startswith('/'):continue
        if item['path'] in seen:raise ValueError('Duplicate AI screen path')
        seen.add(item['path'])
        screen={**ev,'path':item['path'],'heading':text(item.get('heading')) or None,'component':None,'redirect':False,
                'condition':None,'actions':[],'api_functions':[],'evidence':[ev],
                'dependencies':[d for x in rows(item,'dependencies') if (d:=evidence(x))],**stamp}
        screen['id']=screen_id(screen)
        if isinstance(item.get('replaces'),str):screen['replaces']=item['replaces']
        for index,call in enumerate(rows(item,'calls')):
            cev=evidence(call)
            if not cev or not endpoint(call):continue
            name='ai:'+screen['path']+':'+str(index)
            connection={**cev,'method':call['method'],'path':mapcore.normalize_http_path(call['path']),'kind':'literal','connection_basis':'ai','backend':[]}
            functions.append({'file':cev['file'],'name':name,'line':cev['line'],'calls':[connection],'used_by_screens':True,'source':'ai'})
            screen['api_functions'].append({'file':cev['file'],'name':name,'via':None})
        for action in rows(item,'actions'):
            aev=evidence(action)
            if not aev or action.get('kind') not in ('nav','api','local'):continue
            target=action.get('to')
            screen['actions'].append({**aev,'kind':action['kind'],'label':text(action.get('label')),'to':None,'to_raw':target if isinstance(target,str) else None,
                'targets':[],'api_functions':[],'calls':[],'via':None,'source':'ai'})
        screens.append(screen)
    inspected=[ev for item in rows(data,'inspected') if (ev:=evidence(item))]
    unknown=[v for v in rows(data,'unknown') if isinstance(v,str) and v.strip()]
    supplied=len(rows(data,'screens'))+len(rows(data,'backend_routes'))
    return {'screens':screens,'api_functions':functions,'backend_routes':routes,'flows':flows,'inspected':inspected,'unknown':unknown,
            'supplied':bool(supplied),'dropped':supplied-len(screens)-len(routes)}

def item_files(item,functions=None):
    """Files a saved item cites. Not a semantic dependency proof: every changed file is accounted separately."""
    files={item.get('file')}
    for key in EVIDENCE_LISTS:
        for ev in item.get(key) or []:
            if isinstance(ev,dict):files.add(ev.get('file'))
    files.update(item.get('services') or []);files.update(item.get('dependency_files') or [])
    for ref in item.get('api_functions') or []:
        fn=(functions or {}).get((ref.get('file'),ref.get('name')))
        files.update([ref.get('file'),ref.get('via')]+[c.get('file') for c in (fn or {}).get('calls',[])])
    return {f for f in files if isinstance(f,str) and f}

def link(screens,functions,routes):
    """Connections are always recomputed over the whole merged map."""
    index={}
    for r in routes:
        if r.get('mounted'):index.setdefault((r['method'],r['path']),[]).append(r)
    used=set();unresolved=[];refs={(f['file'],f['name']):f for f in functions};hit={}
    for f in functions:
        for call in f.get('calls',[]):
            hits=index.get((call.get('method'),call.get('path')),[]) if call.get('path') else []
            if f.get('source')=='ai' and len(hits)!=1:hits=[]
            call['backend']=[{'file':r['file'],'line':r['line'],'function':r['function']} for r in hits]
            hit[id(call)]=hits;used.update(id(r) for r in hits)
            if not hits:unresolved.append({'api_function':f['file']+':'+f['name'],**call})
    file_screens={};paths={s['path'] for s in screens};referenced=set()
    for s in screens:
        files=item_files(s,refs)
        for ref in s.get('api_functions',[]):
            referenced.add((ref['file'],ref['name']))
            for call in (refs.get((ref['file'],ref['name'])) or {}).get('calls',[]):
                for r in hit.get(id(call),[]):files.update([r['file'],*r.get('services',[])])
        for f in sorted(files):file_screens.setdefault(f,[]).append(s['path'])
        for a in s.get('actions',[]):
            if a.get('source')!='ai':continue
            a['to']=a.get('to_raw') if a.get('to_raw') in paths else None
            a['targets']=[{'to':a['to'],'label':a['label']}] if a['to'] and a['kind']=='nav' else []
    for f in functions:f['used_by_screens']=(f['file'],f['name']) in referenced
    return {'file_screens':file_screens,'unresolved_calls':unresolved,
            'backend_routes_without_screen':[r for r in routes if r.get('mounted') and id(r) not in used]}

def assemble(repo,commit,ref,screens,functions,routes,models,analysis):
    output={**project.empty_map(),'repo':repo,'commit':commit,'ref':ref,'extractor':mapcore.extractor_id('')}
    output.update(screens=screens,api_functions=functions,backend_routes=routes,models=models,**link(screens,functions,routes),
        coverage={'frontend':bool(screens),'backend':bool(routes)},analysis=analysis)
    return output

def normalize(data,repo,commit,ref,layout=None):
    evidence,cache,rejections=evidence_reader(repo,commit)
    got=parse(data,evidence,commit)
    # No endpoints is a finished answer only when the agent says so and cites code it inspected.
    # Rejected claims are never an empty answer: the supplied lists themselves must be empty.
    if not got['screens'] and not got['backend_routes'] and not (got['inspected'] and got['unknown'] and not got['supplied']):raise ValueError('No usable AI map evidence; previous map was preserved')
    flows={'routes':got['flows']}
    for key,flow in flows['routes'].items():flow['hash']=hashlib.sha1('\n'.join(cache[flow['file']]).encode()).hexdigest()[:12]
    analysis={'source':'ai','version':VERSION,'commit':commit,'generated_at':project.now(),'stale':False,'rejected':rejections(),
              'unknown':[v for v in (data.get('unknown') or []) if isinstance(v,str)],'inspected':got['inspected'],'basis':'full',
              'sources':{'ai':len(got['screens'])+len(got['backend_routes']),'basic':0},'evidence_check':'literal-source-match; semantics are AI-inferred'}
    return assemble(repo,commit,ref,got['screens'],got['api_functions'],got['backend_routes'],{t:t for r in got['backend_routes'] for t in r['tables']},analysis),flows

def refresh_test_links(snapshot,conf):
    repo=snapshot['repo'];commit=snapshot['commit']
    files=set(git(repo,'ls-tree','-r','--name-only',commit).splitlines());cache={}
    def source(file):
        if file not in files:return ''
        if file not in cache:cache[file]=git(repo,'show',commit+':'+file)
        return cache[file]
    hits,stale=mapcore.backend_test_links(snapshot['backend_routes'],files,source,conf)
    for route in snapshot['backend_routes']:route['tests']=sorted(hits.get((route['file'],route['line']),[]))
    snapshot['analysis']['stale_test_records']=stale

SCHEMA={
 'screens':[{'path':'/items','heading':'Items','file':'pages/items.vue','line':1,'quote':'literal source text',
             'dependencies':[{'file':'lib/client.ts','line':1,'quote':'literal source text'}],
             'calls':[{'file':'pages/items.vue','line':2,'quote':'literal source text','method':'POST','path':'/items'}],
             'actions':[{'file':'pages/items.vue','line':3,'quote':'literal source text','kind':'nav','label':'Items','to':'/items'}]}],
 'backend_routes':[{'file':'server/main.go','line':4,'quote':'literal registration source','method':'POST','path':'/items',
                    'function':'SaveItem','name':'Save item','tables':[{'name':'items','file':'server/main.go','line':8,'quote':'literal source'}],
                    'dependencies':[{'file':'server/routes.go','line':2,'quote':'literal mount or prefix source'}],
                    'services':[],'externals':[],'steps':[{'file':'server/main.go','line':8,'quote':'literal source','lane':'저장소',
                    'text':'Store item','uncertain':False}]}], 'unknown':['Anything not established from code'],
 'inspected':[{'file':'path/in/repository','line':1,'quote':'literal source text; required only when no screens or routes exist'}]}

def analysis_prompt(commit,lang,layout,sc=None):
    return f'''Analyze the tracked source at commit {commit} of this repository, regardless of programming language or framework.
Read only this immutable commit using git ls-tree -r --name-only {commit}, git show {commit}:<path>, and git grep -n <pattern> {commit}.
Do not read working-tree files, credentials, or environment files. Do not modify any files or execute application code.
Find screens, navigation actions, client HTTP calls, mounted backend endpoints, tables, external services, and request steps.
Configured source roots: {json.dumps(layout)}. A null frontend/backend disables that area; other roots restrict that area to the configured directory.
Trace actual registration and imports; do not assume a convention or identify two databases by table name alone.
For each item and relationship provide a tracked file, exact one-based line and literal single-line quote (at least 6 characters).
Use repository-relative file paths. Normalize dynamic URL segments to {{}}. HTTP methods must be uppercase.
Only include items and relations supported by code; list unresolved or omitted areas in unknown. An empty list is valid for an absent area.
Labels, descriptions and unknown entries must be in {'English' if lang=='en' else 'Korean'}. Keep identifiers and paths unchanged.
{mapcore.reply_language(lang,'en',saved_results=True)}
Each step uses lane 서버, 저장소, 외부 or 화면. Tables, services and externals require their own evidence.
For a route whose path or mount comes from other lines (router include, prefix, base path), cite those lines in dependencies.
{mode_text(commit,sc)}
Return exactly one JSON object with this schema (examples are illustrative, do not copy them):
{json.dumps(SCHEMA,ensure_ascii=False)}'''

def mode_text(commit,sc):
    sc=sc or {'mode':'full','base':''};base=f'Always put "base": "{sc["base"]}" in the result.'
    if sc['mode']=='review':
        return (f'Mode review ({sc["reason"]}): known lists items already saved, as [id, method or SCREEN, path, function, file, source]; source basic is the '
                'deterministic collector, ai is an earlier AI analysis. Read the whole commit as usual but do not output known items again. '
                'Return "keep":"all", "drop":[ids of known items the code does not support], new or corrected items in the schema lists '
                '(a corrected item with a different identity needs its old id in drop), every recheck id either again or in drop, and unknown. '
                'Kept items are recorded as literal-checked at this commit, not as newly analyzed. '+base)
    if sc['mode']=='patch':
        return (f'Mode patch: since {sc["base_commit"]} only the files in inspect changed and the files in deleted were removed; '
                f'read them at {commit} (and at {sc["base_commit"]} through analysis_source when needed). Dispose every recheck id exactly once: return it again '
                '(same method, path, file, function and mount), return its successor with "replaces": the old id, or list it in removed. '
                'Other items are kept as saved; do not repeat them and do not use drop. Only files in inspect may register new items. '
                'Account for every inspect file exactly once in accounted as {"file":path,"kind":"items"|"affects"|"none","ids":[...]}: items when it registers '
                'items you return, affects when it changes saved items you then return or remove (ids), none when it registers or changes no map item. '
                'If you cannot tell, return only {"base":...,"full_required":"reason"}. '+base)
    return 'Mode full: return the complete schema. '+base


def apply_result(raw,repo,refs,branch,lang,response,commit,layout,configuration=None):
    current=raw.get(branch) or {}
    text=response.strip()
    if len(text)>8_000_000:raise ValueError('AI output was too large')
    if text.startswith('```'):text=re.sub(r'^```(?:json)?\s*|\s*```$','',text)
    try:data=json.loads(text)
    except (ValueError,TypeError) as error:raise ValueError('AI output was not valid JSON; previous map was preserved') from error
    m,flows=normalize(layout_filter(data,layout),repo,commit,refs[branch]);m['analysis'].update(language=lang,configuration=configuration)
    meta={'source':'ai','provider':'mcp-agent','commit':commit,'branch':branch,'language':lang,'configuration':configuration,'generated_at':m['analysis']['generated_at']}
    for flow in flows['routes'].values():flow.update(meta)
    if flows['routes']:m['task_outputs']={'flows':flows}
    conf={**mapcore.TESTS_DEFAULT,'records':[],**(raw.get('tests') or {})}
    refresh_test_links(m,conf)
    updated=copy.deepcopy(raw)
    if current and current.get('commit')!=commit:updated[branch+'.prev']=current
    for route in m['backend_routes']:
        route['flow']=flows['routes'].get(route['file']+'::'+route['function'])
    updated[branch]=m
    return updated,f"AI map: {len(m['screens'])} screens, {len(m['backend_routes'])} requests; {m['analysis']['rejected']} rejected evidence items."

def context(name,repository,branch):
    if branch not in ('dev','main'):raise ValueError('Choose dev or main')
    conf=project.config(name)
    if conf:
        repo=project.selected_repository(name,repository);state=project.states(name)
        raw=project.raw_bundle(project.repository_folder(name,repo,state))
        selected=repo['id']
    else:
        if repository:raise ValueError('This legacy project has no repository selector')
        raw=project.raw_bundle(project.home(name));current=raw.get(branch)
        if not current:raise ValueError('Refresh this repository first')
        repo={'path':current['repo'],'refs':{branch:current.get('ref') or mapcore.configured_refs().get(branch)},'layout':{}}
        selected=''
    if not raw.get(branch) or not repo['refs'].get(branch):raise ValueError('Refresh an available branch role first')
    commit=git(repo['path'],'rev-parse','--verify',repo['refs'][branch]+'^{commit}').strip()
    return repo,raw,selected,commit

SPARSE=('keep','drop','removed','accounted','full_required')
_BASIC={};_TREES={}

class ReviewRequired(ValueError):
    """A changed file could not be classified: the next request reads the whole commit again."""
    def __init__(self,reason,message):super().__init__(message);self.reason=reason

def same(a,b):return bool(a and b) and (str(a).startswith(str(b)) or str(b).startswith(str(a)))
def within(file,area,layout):
    return area not in layout or layout[area] is not None and isinstance(file,str) and file.startswith(layout[area].rstrip('/')+'/')
def layout_filter(data,layout):
    for key,area in [('screens','frontend'),('backend_routes','backend')]:
        if area in layout:data[key]=[item for item in data.get(key,[]) if isinstance(item,dict) and within(item.get('file'),area,layout)]
    return data

def commit_exists(repo,commit):
    return bool(commit) and subprocess.run(['git','-C',repo,'cat-file','-e',str(commit)+'^{commit}'],capture_output=True).returncode==0
def tree_blobs(repo,commit):
    if (repo,commit) not in _TREES:
        if len(_TREES)>16:_TREES.clear()
        _TREES[(repo,commit)]={path:meta.split()[2] for meta,_,path in (line.partition('\t') for line in git(repo,'ls-tree','-r',commit).splitlines())}
    return _TREES[(repo,commit)]
def same_tree(repo,old,new):
    if not commit_exists(repo,old):return False
    trees=git(repo,'rev-parse',old+'^{tree}',new+'^{tree}').split()
    return len(trees)==2 and trees[0]==trees[1]
def changes(repo,old,new):
    """Every changed path, outside the configured roots too; git records renames and deletions."""
    parts=git(repo,'diff','-z','--name-status','-M',old,new).split('\0');changed=set();deleted=set();present=set();i=0
    while i<len(parts) and parts[i]:
        status=parts[i]
        if status[0] in 'RC':
            a,b=parts[i+1],parts[i+2];i+=3;changed|={a,b};present.add(b)
            if status[0]=='R':deleted.add(a)
        else:
            path=parts[i+1];i+=2;changed.add(path);(deleted if status[0]=='D' else present).add(path)
    return changed,sorted(deleted),sorted(present)

def basic_catalog(repo,commit,layout):
    """The existing deterministic collector at this exact commit. Its items stay source basic."""
    key=(repo,commit,json.dumps(layout,sort_keys=True))
    if key not in _BASIC:
        with tempfile.TemporaryDirectory(prefix='where-were-we-basic-') as folder:
            out=Path(folder)/'basic.json'
            env={**os.environ,'WHERE_WERE_WE_LAYOUT':json.dumps(layout),'WHERE_WERE_WE_REFS':json.dumps({'dev':commit,'main':None})}
            done=subprocess.run(mapcore.python_command(str(Path(__file__).with_name('extract.py')),repo,commit,str(out)),capture_output=True,text=True,env=env,timeout=900)
            # An unsupported or unreadable layout is an empty catalog, never a reason to trust an old map.
            value=json.loads(out.read_text()) if not done.returncode and out.exists() else project.empty_map()
        if len(_BASIC)>8:_BASIC.clear()
        _BASIC[key]=value
    value=copy.deepcopy(_BASIC[key]);screens_of=value.get('file_screens',{})
    for s in value['screens']:s.update(source='basic',id=screen_id(s),dependency_files=sorted(f for f,paths in screens_of.items() if s['path'] in paths))
    for r in value['backend_routes']:r.update(source='basic',id=route_id(r))
    value['backend_routes']=list({r['id']:r for r in reversed(value['backend_routes'])}.values())[::-1]
    for f in value['api_functions']:f['source']='basic'
    return value

def ai_catalog(prev):
    verified=(prev.get('analysis') or {}).get('commit') or prev.get('commit')
    def ready(item,make):
        item=copy.deepcopy(item);item.setdefault('id',make(item));item.setdefault('verified_commit',verified)
        for action in item.get('actions') or []:
            # v1 saved only the resolved target; an explicit v2 to_raw (even None) is kept as written.
            if action.get('source')=='ai' and 'to_raw' not in action:action['to_raw']=action.get('to')
        return item
    return ([ready(r,route_id) for r in prev.get('backend_routes',[]) if r.get('source')=='ai'],
            [ready(s,screen_id) for s in prev.get('screens',[]) if s.get('source')=='ai'],
            {(f['file'],f['name']):f for f in prev.get('api_functions',[]) if f.get('source')=='ai'})

def unsuperseded(basic,routes,screens):
    """Only an AI item for the exact same endpoint (method, path, registration file, handler) or screen path replaces a basic one.
    The collector records no mount, so another mount or prefix stays until a review drops it explicitly."""
    keys={(r['method'],r['path'],r['file'],r['function']) for r in routes};paths={s['path'] for s in screens}
    return ([r for r in basic['backend_routes'] if (r['method'],r['path'],r['file'],r['function']) not in keys],
            [s for s in basic['screens'] if s['path'] not in paths])

def literal_ok(item,evidence,functions):
    checks=[{k:item.get(k) for k in ('file','line','quote')}]
    for key in EVIDENCE_LISTS:checks+=[e for e in item.get(key) or [] if isinstance(e,dict) and 'quote' in e]
    for ref in item.get('api_functions') or []:
        checks+=[c for c in (functions.get((ref.get('file'),ref.get('name'))) or {}).get('calls',[]) if 'quote' in c]
    return all(evidence(e) for e in checks) and all(f in evidence.files for f in item.get('services') or [])

def review_flag(name,rid,branch,prev):
    entry=project.states(name).get('@review',{}).get(rid+':'+branch) or {}
    return entry.get('reason') if entry.get('map')==digest(prev) else None
def set_review_flag(name,rid,branch,prev,reason):
    state=project.states(name);state.setdefault('@review',{})[rid+':'+branch]={'reason':reason,'map':digest(prev)}
    project.atomic(project.home(name)/'repository-state.json',state)

def scope(repo,raw,branch,lang,head,configuration,flag=None):
    """What the next analysis must cover. Deterministic, so request and record compute the same base."""
    path=repo['path'];layout=repo['layout'];prev=raw.get(branch) or {};a=prev.get('analysis') or {};ai=a.get('source')=='ai'
    basic=basic_catalog(path,head,layout);dropped=set(prev.get('basic_drop') or []) if ai else set()
    basic['screens']=[s for s in basic['screens'] if s['id'] not in dropped]
    basic['backend_routes']=[r for r in basic['backend_routes'] if r['id'] not in dropped]
    routes,screens,functions=ai_catalog(prev) if ai else ([],[],{})
    routes=[r for r in routes if within(r['file'],'backend',layout)];screens=[s for s in screens if within(s['file'],'frontend',layout)]
    if ai and a.get('language')!=lang:mode,reason='full','language_changed'
    elif not ai:mode,reason=('review','basic_catalog') if basic['screens'] or basic['backend_routes'] else ('full','no_catalog')
    elif a.get('version',1)<VERSION:mode,reason='review','v1_snapshot'
    elif a.get('configuration')!=configuration:mode,reason='review','configuration_changed'
    elif flag:mode,reason='review',flag
    elif not commit_exists(path,prev.get('commit')):mode,reason='review','base_commit_missing'
    elif prev.get('commit')==head:mode,reason='review','same_commit'
    else:mode,reason='patch','changed_files'
    recheck=[];inspect=[];deleted=[]
    if mode!='full':
        evidence,_,_=evidence_reader(path,head);changed=set();collected={}
        if mode=='patch':
            changed,deleted,inspect=changes(path,prev['commit'],head)
            # Existing collector knowledge widens the cited files; it never narrows them.
            for r in basic['backend_routes']:collected.setdefault((r['method'],r['path']),set()).update([r['file'],*r.get('services',[])])
            for s in basic['screens']:collected.setdefault(s['path'],set()).update([s.get('file'),*s['dependency_files']])
        for kind,items in (('route',routes),('screen',screens)):
            for item in items:
                files=item_files(item,functions)|collected.get((item.get('method'),item.get('path')) if kind=='route' else item.get('path'),set())
                why='dependency_changed' if files&changed else None if literal_ok(item,evidence,functions) else 'evidence_changed'
                if why:recheck.append({'id':item['id'],'kind':kind,'file':item.get('file'),'method':item.get('method'),'path':item.get('path'),'function':item.get('function'),'reason':why})
    public={'mode':mode,'reason':reason,'recheck':recheck,'inspect':inspect,'deleted':deleted,'base_commit':prev.get('commit') if mode=='patch' else None}
    if mode=='review':
        b_routes,b_screens=unsuperseded(basic,routes,screens)
        public['known']=([[r['id'],r['method'],r['path'],r.get('function') or '',r['file'],r['source']] for r in routes+b_routes]+
                         [[s['id'],'SCREEN',s['path'],'',s.get('file') or '',s['source']] for s in screens+b_screens])
    public['base']=digest({'map':digest(prev),'head':head,'lang':lang,'configuration':configuration,**public})
    return public,{'basic':basic,'routes':routes,'screens':screens,'functions':functions}

def account(data,sc,ai_ids):
    rows=data.get('accounted',[])
    if not isinstance(rows,list):raise ValueError('accounted must be a list')
    seen={}
    for entry in rows:
        if not isinstance(entry,dict) or not isinstance(entry.get('file'),str):raise ValueError('Invalid accounted entry')
        if entry['file'] in seen:raise ValueError('Duplicate accounted file: '+entry['file'])
        if entry['file'] not in sc['inspect']:raise ValueError('accounted names a file outside inspect: '+entry['file'])
        seen[entry['file']]=entry
    missing=[f for f in sc['inspect'] if seen.get(f,{}).get('kind') not in ('items','affects','none')]
    if missing:raise ReviewRequired('unaccounted:'+missing[0],'Changed files were not classified ('+', '.join(missing[:5])+'); the previous map was preserved and the next analysis request is a full-context review.')
    for entry in seen.values():
        if entry['kind']=='affects' and (not isinstance(entry.get('ids'),list) or not entry['ids'] or not set(entry['ids'])<=ai_ids):
            raise ValueError('affects must list saved AI item IDs')
    return seen

def cited(value):
    if isinstance(value,dict):return ([value] if 'quote' in value and 'file' in value else [])+[e for v in value.values() for e in cited(v)]
    if isinstance(value,list):return [e for v in value for e in cited(v)]
    return []

def files_in(value):
    if isinstance(value,dict):return ({value['file']} if isinstance(value.get('file'),str) else set()).union(*[files_in(v) for v in value.values()])
    if isinstance(value,list):return set().union(*[files_in(v) for v in value]) if value else set()
    return set()

def groups_input(m):
    routes={r['file']+'::'+r['function']:r for r in m['backend_routes'] if r.get('mounted') and r.get('function')}
    screens=[s for s in m['screens'] if not s.get('redirect')]
    paths={s['path'] for s in screens}
    screens=[s for s in screens if not s['path'].startswith('/m/') or s['path'][2:] not in paths]
    return {'screens':sorted(({'path':s['path'],'title':s.get('heading'),'buttons':list(dict.fromkeys(
                a['label'] for a in s.get('actions',[]) if a.get('label') and not a.get('via')))[:10]} for s in screens),key=lambda x:x['path']),
            'routes':[{k:routes[key].get(k) for k in ('file','function','method','path','tables','externals')} for key in sorted(routes)]}

def carry(raw,branch,prev,m,flows,repo,head):
    """Dependent results survive only when their actual inputs are proven unchanged."""
    old=prev.get('commit');selected=project.branch_bundle(raw,branch);outputs={}
    if not prev or not commit_exists(repo,old):return {'flows':{'routes':flows}} if flows else {}
    before,after=tree_blobs(repo,old),tree_blobs(repo,head);tree=same_tree(repo,old,head)
    def stamp(value):return {**value,'commit':head,'verified_commit':value.get('verified_commit') or value.get('commit'),'carried_from':value.get('commit')}
    def current(value):return bool(value) and same(value.get('commit'),old) and not value.get('stale')
    def flow_input(routes,key,flow,blobs):
        rs=[r for r in routes if r.get('function') and handler(r)==key];files={s.get('file') for s in flow.get('steps',[])}
        for r in rs:files|=item_files(r)
        return digest([sorted(json.dumps([r.get('method'),r.get('path'),sorted(r.get('tables') or []),sorted(r.get('externals') or []),sorted(r.get('services') or []),r.get('mounted')]) for r in rs),
                       {f:blobs.get(f) for f in sorted(x for x in files if x)}])
    prior=(selected.get('flows') or {}).get('routes',{})
    for key in {handler(r) for r in m['backend_routes'] if r.get('function')}-set(flows):
        flow=prior.get(key)
        if current(flow) and flow_input(prev.get('backend_routes',[]),key,flow,before)==flow_input(m['backend_routes'],key,flow,after):flows[key]=stamp(flow)
    if flows:outputs['flows']={'routes':flows}
    groups=selected.get('groups')
    if groups:outputs['groups']=stamp(groups) if current(groups) and digest(groups_input(prev))==digest(groups_input(m)) else groups
    for key in ('system','system.ai'):
        # A new program can appear anywhere; only an identical tree proves the architecture unchanged.
        if selected.get(key):outputs[key]=stamp(selected[key]) if tree and current(selected[key]) else selected[key]
    jobs=selected.get('jobs')
    if jobs:
        proposal=(selected.get('system.ai') or {}).get('source')=='ai'
        code={n.get('id'):[c.rstrip('/') for c in n.get('code') or []] for n in ((selected.get('system.ai') if proposal else selected.get('system')) or {}).get('nodes',[])}
        def job_input(nid,value,blobs,routes):
            dirs=code.get(nid) or []
            served=sorted(json.dumps([handler(r),r.get('method'),r.get('path'),sorted(r.get('services') or []),sorted(r.get('tables') or [])]) for r in routes if r.get('mounted') and r.get('function'))
            return digest([nid,dirs,served,{f:b for f,b in blobs.items() if any(c in ('','.') or f==c or f.startswith(c+'/') for c in dirs)},{f:blobs.get(f) for f in sorted(files_in(value))}])
        outputs['jobs']={**jobs,'nodes':{nid:stamp(v) if current(v) and code.get(nid) and job_input(nid,v,before,prev.get('backend_routes',[]))==job_input(nid,v,after,m['backend_routes']) else v
                                        for nid,v in jobs.get('nodes',{}).items()}}
    return outputs

def merge(raw,repo,branch,lang,data,head,configuration,sc,catalog):
    path=repo['path'];layout=repo['layout'];prev=raw.get(branch) or {};mode=sc['mode']
    full=mode=='full'
    if 'full_required' in data:
        if mode=='patch':raise ReviewRequired('full_required','The agent could not bound the change; the previous map was preserved and the next analysis request is a full-context review.')
        raise ValueError('This request is already a full-context review; return keep:"all" with drop and corrected or new items only')
    if full and any(k in data for k in SPARSE):raise ValueError('This request needs the full schema; sparse fields are not accepted')
    def ids(key):
        value=data.get(key,[])
        if not isinstance(value,list) or any(not isinstance(v,str) for v in value) or len(set(value))!=len(value):raise ValueError('Invalid or duplicate IDs in '+key)
        return set(value)
    drop=ids('drop');removed=ids('removed')
    evidence,cache,rejections=evidence_reader(path,head)
    got=parse(layout_filter(data,layout),evidence,head)
    routes,screens,functions,basic=catalog['routes'],catalog['screens'],catalog['functions'],catalog['basic']
    kept_routes=[];kept_screens=[];kept_functions=[];basic_routes=[];basic_screens=[];basic_functions=[];accounted=None
    if full:
        if not got['screens'] and not got['backend_routes'] and not (got['inspected'] and got['unknown'] and not got['supplied']):raise ValueError('No usable AI map evidence; previous map was preserved')
        basic_routes,basic_screens=unsuperseded(basic,got['backend_routes'],got['screens']);basic_functions=basic['api_functions']
    else:
        # A review or patch is applied whole or not at all: no supplied item or nested evidence may be skipped silently.
        # The counter covers only this submission's parse; saved evidence is checked separately by the scope.
        if got['dropped'] or rejections():raise ValueError(str(rejections())+' supplied evidence entries failed the literal check; previous map was preserved')
        if mode=='review' and data.get('keep')!='all':raise ValueError('Review results must state keep:"all", list wrong catalog IDs in drop and return only corrected or new items; a full schema is not accepted in review mode')
        if mode=='review' and removed:raise ValueError('Review results use drop, not removed')
        if mode=='patch' and 'keep' in data:raise ValueError('Patch results dispose recheck IDs with replacements or removed, not keep')
        ai_ids={x['id'] for x in routes+screens};basic_ids={x['id'] for x in basic['backend_routes']+basic['screens']}
        if not drop<=ai_ids|basic_ids:raise ValueError('drop names IDs outside the catalog; previous map was preserved')
        if mode=='patch' and drop:raise ValueError('Patch results cannot drop catalog items; dispose recheck IDs with replacements or removed, and drop wrong basic items in a review')
        targets={r['id'] for r in sc['recheck']}
        if mode=='patch':
            accounted=account(data,sc,ai_ids)
            for entry in accounted.values():targets|=set(entry.get('ids') or [])
        new={x['id']:x for x in got['backend_routes']+got['screens']};gone=removed|drop;replacing={}
        for item in new.values():
            if 'replaces' in item:
                if item['replaces'] not in targets or item['replaces'] in replacing:raise ValueError('replaces must name one recheck ID once: '+str(item['replaces'])+'; previous map was preserved')
                replacing[item['replaces']]=item
        # Checked after evidence validation: a replacement with rejected evidence is no disposition.
        for target in sorted(targets):
            if (target in new)+(target in replacing)+(target in gone)!=1:
                raise ValueError(('More than one disposition' if (target in new)+(target in replacing)+(target in gone) else 'No valid replacement or removal')+' for '+target+'; previous map was preserved')
        if not removed<=targets:raise ValueError('removed names IDs outside this request; previous map was preserved')
        if mode=='patch':
            for key,item in new.items():
                if key in ai_ids and key not in targets:raise ValueError('Replacement outside this request: '+key+'; previous map was preserved')
                if key not in ai_ids and 'replaces' not in item and item['file'] not in sc['inspect']:raise ValueError('New item outside the changed files: '+key+'; previous map was preserved')
            for file,entry in accounted.items():
                if entry['kind']=='items' and not any(file in item_files(x) for x in new.values()):raise ValueError('No valid item from '+file+'; previous map was preserved')
        for item in new.values():item.pop('replaces',None)
        kept_routes=[r for r in routes if r['id'] not in targets|drop|set(new)];kept_screens=[s for s in screens if s['id'] not in targets|drop|set(new)]
        for item in kept_routes+kept_screens:item['checked_commit']=head
        kept_functions=[copy.deepcopy(functions[(ref['file'],ref['name'])]) for s in kept_screens for ref in s.get('api_functions',[]) if (ref['file'],ref['name']) in functions]
        b_routes,b_screens=unsuperseded(basic,kept_routes+got['backend_routes'],kept_screens+got['screens'])
        basic_routes=[r for r in b_routes if r['id'] not in drop];basic_screens=[s for s in b_screens if s['id'] not in drop];basic_functions=basic['api_functions']
    all_screens=kept_screens+got['screens']+basic_screens;all_routes=kept_routes+got['backend_routes']+basic_routes
    count=lambda source:sum(1 for x in all_screens+all_routes if x.get('source')==source)
    earlier=[] if full else (prev.get('analysis') or {}).get('unknown',[]) if (prev.get('analysis') or {}).get('source')=='ai' else []
    unknown=got['unknown'] if full or mode=='review' and 'unknown' in data else list(dict.fromkeys([*earlier,*got['unknown']]))
    analysis={'source':'ai','version':VERSION,'commit':head,'generated_at':project.now(),'stale':False,'rejected':rejections(),'unknown':unknown,
              'inspected':got['inspected'],'basis':'full' if full else mode,'reason':sc['reason'],'sources':{'ai':count('ai'),'basic':count('basic')},
              'carried':{'routes':len(kept_routes),'screens':len(kept_screens)},'language':lang,'configuration':configuration,
              'evidence_check':'literal-source-match; semantics are AI-inferred; carried items were literal-checked at this commit, not re-analyzed'}
    if accounted is not None:analysis['accounted']={**{k:sum(1 for e in accounted.values() if e['kind']==k) for k in ('items','affects','none')},'source':'ai'}
    models=dict(basic.get('models') or {})
    models.update({t:t for r in all_routes if r.get('source')=='ai' for t in r.get('tables',[])})
    m=assemble(path,head,repo['refs'].get(branch) or prev.get('ref'),all_screens,kept_functions+got['api_functions']+basic_functions,all_routes,models,analysis)
    m['basic_drop']=sorted((set(prev.get('basic_drop') or []) if (prev.get('analysis') or {}).get('source')=='ai' else set())|(drop&{x['id'] for x in basic['backend_routes']+basic['screens']}))
    meta={'source':'ai','provider':'mcp-agent','commit':head,'branch':branch,'language':lang,'configuration':configuration,'generated_at':analysis['generated_at']}
    flows={key:{**flow,**meta,'hash':hashlib.sha1('\n'.join(cache[flow['file']]).encode()).hexdigest()[:12]} for key,flow in got['flows'].items()}
    outputs=carry(raw,branch,prev,m,flows,path,head)
    if outputs:m['task_outputs']=outputs
    analysis['carried']['flows']=sum(1 for f in (outputs.get('flows') or {}).get('routes',{}).values() if f.get('carried_from'))
    refresh_test_links(m,{**mapcore.TESTS_DEFAULT,'records':[],**(raw.get('tests') or {})})
    for route in all_routes:route['flow']=((outputs.get('flows') or {}).get('routes') or {}).get(handler(route))
    updated=copy.deepcopy(raw)
    if prev and prev.get('commit')!=head:updated[branch+'.prev']=prev
    updated[branch]=m
    return updated,(f"AI map ({analysis['basis']}): {len(all_screens)} screens, {len(all_routes)} requests; AI {analysis['sources']['ai']}, basic collector {analysis['sources']['basic']}; "
                    f"carried {len(kept_routes)+len(kept_screens)} literal-checked items; {analysis['rejected']} rejected evidence items.")

def carry_unchanged(m,repo,head):
    """An identical tree proves every input unchanged: the only AI-free carry."""
    old=m.get('commit');a=m.get('analysis') or {}
    if a.get('source')!='ai' or not old or old==head or not same_tree(repo,old,head):return False
    def stamp(value):
        if isinstance(value,dict) and same(value.get('commit'),old):
            value.update(commit=head,verified_commit=value.get('verified_commit') or value.get('commit'),carried_from=value.get('commit'))
    m['commit']=head;a.update(commit=head,carried_from=old,stale=False);a.pop('observed_commit',None)
    for item in m.get('screens',[])+m.get('backend_routes',[]):
        if item.get('source')=='ai':item['checked_commit']=head
    outputs=m.get('task_outputs') or {}
    for flow in (outputs.get('flows') or {}).get('routes',{}).values():stamp(flow)
    for key in ('groups','system','system.ai'):stamp(outputs.get(key))
    for value in (outputs.get('jobs') or {}).get('nodes',{}).values():stamp(value)
    for route in m.get('backend_routes',[]):stamp(route.get('flow'))
    return True

def request(name,branch='dev',lang='ko',repository=''):
    if lang not in ('ko','en'):raise ValueError('Choose ko or en')
    with project.locked(name):
        repo,raw,rid,commit=context(name,repository,branch)
        fingerprint=project.fingerprint(repo)
        if rid and project.states(name).get(rid,{}).get('fingerprint')!=fingerprint:raise ValueError('Refresh after configuration changes first')
        sc,_=scope(repo,raw,branch,lang,commit,fingerprint,review_flag(name,rid,branch,raw.get(branch) or {}))
        arguments={'project':name,'repository':rid,'branch':branch,'lang':lang,'commit':commit,'configuration':fingerprint,'base':sc['base']}
        scope_text=json.dumps({'project':name,'repository':rid,'branch':branch,'lang':lang},ensure_ascii=False)
        handoff=(f"where-were-we MCP로 이 프로젝트의 상세 지도를 분석해 주세요. 먼저 analyze를 {scope_text} 인자로 호출하세요. "
                 "반환된 커밋과 mode·schema를 기준으로 반환된 source_arguments를 넣어 analysis_source 도구로 코드를 읽고, 지금 사용하는 에이전트의 모델로 분석하세요. "
                 "다른 AI CLI를 실행하지 마세요. 원문 근거를 붙이고 모르는 부분은 unknown에 남기세요. "
                 "결과 JSON에는 반환된 base를 넣고, 반환된 record_arguments와 함께 record_analysis의 result_json으로 저장하세요.") if lang=='ko' else (
                 f"Analyze this project with the where-were-we MCP tools. First call analyze with {scope_text}. "
                 "Use analysis_source with the returned source_arguments to read the immutable commit and use your current agent/model to produce the returned mode and schema. "
                 "Do not launch another AI CLI. Include literal evidence and unknown areas. Put the returned base in result_json and submit it to record_analysis with the returned record_arguments.")
        system_scope=json.dumps({'project':name,'repository':rid,'task':'system','branch':branch,'lang':lang},ensure_ascii=False)
        handoff += (f' 지도 저장이 끝나면 request_ai_task를 {system_scope} 인자로 호출해 전체 구조와 각 프로그램이 하는 일을 함께 분석하세요. '
                    '반환된 schema의 프로그램별 jobs에 근거를 포함하고, 모르는 내용은 unknown에 적으세요. '
                    '반환된 record_arguments와 결과를 record_ai_task로 저장하세요. 별도 사용자 요청을 기다리지 말고 이 분석을 마무리하세요.') if lang=='ko' else (
                    f' After saving the map, call request_ai_task with {system_scope} to analyze architecture and the jobs of every program together. '
                    'Include source evidence in each program’s jobs using the returned schema; record unknowns explicitly. '
                    'Submit the result and returned record_arguments to record_ai_task to finish this analysis without another user request.')
        handoff += (' 저장 후 앱으로 돌아가라고 안내하세요. 앱이 저장된 결과를 읽습니다. 결과 확인을 위해 refresh 도구를 실행하지 마세요.' if lang=='ko' else ' Tell the user to return to the app, which reads the saved result. Do not call refresh to display the result.')
        handoff += ' '+mapcore.reply_language(lang,saved_results=True)
        results=project.analysis_results(raw,branch)
        return {'commit':commit,'record_arguments':arguments,'repository_path':repo['path'],
                'result_before':[{'task':task,'before':results[task]} for task in ('analysis','system')],
                'source_arguments':{'project':name,'repository':rid,'branch':branch,'commit':commit},**sc,
                'prompt':analysis_prompt(commit,lang,repo['layout'],sc),'schema':SCHEMA,'handoff':handoff}

def source(name,repository,commit,file='',start=1,limit=200,branch='dev'):
    if not re.fullmatch(r'[0-9a-f]{40}|[0-9a-f]{64}',commit):raise ValueError('Use the full commit from analyze')
    if start<1 or limit<1 or limit>400:raise ValueError('Use start >= 1 and 1 <= limit <= 400')
    with project.locked(name):
        repo,raw,rid,_=context(name,repository,branch)
        files=sorted(git(repo['path'],'ls-tree','-r','--name-only',commit).splitlines())
        if not file:return {'files':files[start-1:start-1+limit],'total':len(files),'next':start+limit if start-1+limit<len(files) else None}
        if file not in files or file.startswith('/') or '..' in PurePosixPath(file).parts:raise ValueError('Choose a tracked repository-relative file')
        if PurePosixPath(file).name.startswith('.env') and not file.endswith(('.example','.sample','.template')):raise ValueError('Environment credential files are not analysis source')
        lines=git(repo['path'],'show',commit+':'+file).splitlines()
        return {'file':file,'commit':commit,'lines':[{'line':i+1,'text':text} for i,text in enumerate(lines[start-1:start-1+limit],start-1)],
                'total':len(lines),'next':start+limit if start-1+limit<len(lines) else None}

def record(project,repository,branch,lang,commit,configuration,result_json,base=''):
    import project as store
    if lang not in ('ko','en'):raise ValueError('Choose ko or en')
    with store.locked(project):
        repo,raw,rid,head=context(project,repository,branch)
        if configuration!=store.fingerprint(repo):raise ValueError('Repository configuration changed; request a new analysis')
        if commit!=head:raise ValueError('Repository commit changed; request a new analysis')
        text=result_json.strip() if isinstance(result_json,str) else ''
        if len(text)>8_000_000:raise ValueError('AI output was too large')
        if text.startswith('```'):text=re.sub(r'^```(?:json)?\s*|\s*```$','',text)
        try:data=json.loads(text)
        except (ValueError,TypeError) as error:raise ValueError('AI output was not valid JSON; previous map was preserved') from error
        if not isinstance(data,dict):raise ValueError('AI output must be an object')
        previous=(raw.get(branch) or {}).get('analysis') or {}
        if base and data.get('base',base)!=base:raise ValueError('result_json and record_arguments name different bases; request the analysis again')
        if base:data['base']=base
        def save(updated):
            if rid:store._publish(project,rid,updated,{},collection=False)
            else:
                for key,value in updated.items():
                    if value is not None:store.atomic(store.home(project)/(key+'.json'),value)
        if 'base' not in data:
            # Pre-v2 compatibility: an explicit full JSON may replace a basic or v1 map, never a pinned v2 map.
            if any(k in data for k in SPARSE):raise ValueError('Sparse results need the base returned by analyze; request the analysis again')
            if previous.get('source')=='ai' and previous.get('version',1)>=VERSION:raise ValueError('This map was saved from a pinned request; put the base returned by analyze in result_json')
            updated,message=apply_result(raw,repo['path'],repo['refs'],branch,lang,text,commit,repo['layout'],configuration)
        else:
            sc,catalog=scope(repo,raw,branch,lang,head,configuration,review_flag(project,rid,branch,raw.get(branch) or {}))
            if data['base']!=sc['base']:raise ValueError('The saved map, commit or request scope changed; request the analysis again')
            try:updated,message=merge(raw,repo,branch,lang,data,head,configuration,sc,catalog)
            except ReviewRequired as error:
                set_review_flag(project,rid,branch,raw.get(branch) or {},error.reason)  # the map bundle stays byte-identical
                raise ValueError(str(error)) from None
        updated[branch]['analysis']['provider']='mcp-agent'
        save(updated)
        return message

EV_SCHEMA={'file':'path/in/repository','line':1,'quote':'literal source text'}
UNKNOWN_SCHEMA={'text':'Unverified fact','needs':'read'}
JOB_SCHEMA={'name':'Job','what':'Purpose','starts_when':'Trigger condition','trigger':EV_SCHEMA,
            'made_by':[{**EV_SCHEMA,'routes':['file::function']}],
            'steps':[{**EV_SCHEMA,'lane':'프로그램','text':'Step'}]}
TASK_SCHEMAS={
    'groups':{'groups':[{'name':'Name','description':'Description','screens':['/path']}],
              'names':{'/path':'Screen name'},'request_names':{'file::function':'Request name'}},
    'system':{'nodes':[{'id':'program','name':'Program','kind':'program','what':'Purpose','origin':'repo',
                        'origin_text':'Source location','code':['src'],'uses':[],'unknown':[UNKNOWN_SCHEMA],'ev':[EV_SCHEMA],
                        'jobs':[JOB_SCHEMA]}],
              'links':[{'from':'program','to':'store','label':'Exchange','style':'','sure':'code','ev':[EV_SCHEMA]}],
              'externals':[{'id':'cloud','name':'Cloud','what':'External service','ev':[EV_SCHEMA]}],
              'others':[{'name':'Other program','what':'Purpose','ev':[EV_SCHEMA]}],'unknown':[UNKNOWN_SCHEMA],
              'ev':[{**EV_SCHEMA,'quote':'inspected code; required only when nodes is empty'}]},
    'jobs':{'jobs':[JOB_SCHEMA]},
    'steps':{'routes':{'file::function':{'name':'Request name','steps':[{**EV_SCHEMA,'lane':'서버','text':'Step','uncertain':False}],
                                         'unknown':'Only with steps:[] when the code does not establish the steps'}}}
}

def screen_digests(inputs):return {x['path']:digest([x['title'],x['buttons']]) for x in inputs['screens']}
def route_keys(inputs):return [r['file']+'::'+r['function'] for r in inputs['routes']]

def task_input(raw,task,branch,target,repo=None,head=None):
    raw=project.branch_bundle(raw,branch)
    m=raw[branch]
    routes={r['file']+'::'+r['function']:r for r in m['backend_routes'] if r.get('mounted') and r.get('function')}
    if task=='groups':
        inputs=groups_input(m);previous=raw.get('groups') or {}
        if previous.get('source')!='ai' or not previous.get('inputs'):return inputs
        # Delta: only screens whose metadata changed and routes without a saved name; removals are applied by the server.
        old=previous['inputs'];changed=[p for p,d in screen_digests(inputs).items() if old['screens'].get(p)!=d]
        new=[k for k in route_keys(inputs) if k not in set(old['routes'])]
        return {'screens':[x for x in inputs['screens'] if x['path'] in changed],'routes':[r for r in inputs['routes'] if r['file']+'::'+r['function'] in new],
                'previous_groups':[{'name':g['name'],'description':g.get('description','')} for g in previous.get('groups',[])],
                'changed_screens':changed,'new_routes':new}
    if task=='system':
        previous=(raw.get('system.ai') if (raw.get('system.ai') or {}).get('source')=='ai' else raw.get('system')) or {}
        changed=None
        if previous.get('source')=='ai' and repo and head and commit_exists(repo,previous.get('commit')):
            changed=sorted(changes(repo,previous['commit'],head)[0])
        return {'previous':raw.get('system') or {},'routes':list(routes),'changed_files':changed}
    if task=='jobs':
        node=next((n for n in (raw.get('system') or {}).get('nodes',[]) if n.get('id')==target),None)
        if not node or not node.get('code'):raise ValueError('Choose a node with repository code')
        return {'node':node,'routes':list(routes.values())}
    if not target:raise ValueError('Choose a screen or route target')
    if target.startswith('@routes:'):
        keys=json.loads(target[len('@routes:'):])
        if not isinstance(keys,list) or not keys or any(not isinstance(k,str) or k not in routes for k in keys):
            raise ValueError('Choose known route targets')
    else:
        screens=[s for s in m['screens'] if s['path'] in (target,'/m'+target)]
        if not screens:raise ValueError('Choose a known screen target')
        refs={(f['file'],f['name']) for s in screens for f in s.get('api_functions',[])}
        hits={(b['file'],b['line']) for f in m['api_functions'] if (f['file'],f['name']) in refs
              for c in f.get('calls',[]) for b in c.get('backend',[])}
        keys=[key for key,r in routes.items() if (r['file'],r['line']) in hits]
    if not keys:raise ValueError('No server route targets in this snapshot')
    return {'routes':{key:{k:routes[key].get(k) for k in ('file','function','method','path','line')} for key in keys}}

def task_snapshot(raw,task,branch):
    raw=project.branch_bundle(raw,branch)
    keys={'groups':['groups'],'system':['system','system.ai','jobs'],'jobs':['system','jobs'],'steps':['flows']}[task]
    return hashlib.sha256(json.dumps({k:raw.get(k) for k in [branch,*keys]},sort_keys=True,ensure_ascii=False).encode()).hexdigest()

def task_context(name,task,branch,repository):
    if task not in TASK_SCHEMAS:raise ValueError('Choose groups, system, jobs or steps')
    repo,raw,rid,commit=context(name,repository,branch)
    if rid and project.states(name).get(rid,{}).get('fingerprint')!=project.fingerprint(repo):
        raise ValueError('Configuration changed; refresh first')
    if git(repo['path'],'rev-parse',raw[branch]['commit']+'^{commit}').strip()!=commit:
        raise ValueError('Map commit changed; refresh or analyze the map first')
    return repo,raw,rid,commit

def task_request(name,task,branch='dev',lang='ko',repository='',target=''):
    if lang not in ('ko','en'):raise ValueError('Choose ko or en')
    with project.locked(name):
        repo,raw,rid,commit=task_context(name,task,branch,repository)
        inputs=task_input(raw,task,branch,target,repo['path'],commit)
        args={'project':name,'repository':rid,'task':task,'branch':branch,'lang':lang,'target':target,
              'commit':commit,'configuration':project.fingerprint(repo),'snapshot':task_snapshot(raw,task,branch)}
        scope={k:args[k] for k in ('project','repository','task','branch','lang','target')}
        rules={
            'groups':'Group all supplied screens exactly once by user activity. Keep screen paths and route keys unchanged. Name mounted requests too. Use only supplied metadata, not source code. When input has changed_screens, saved groups stay: return "keep":"previous", place only the changed_screens (into previous_groups names or new groups), and name only them and new_routes.',
            'system':'Describe separately running programs, users, stores and copied code, their connections and external services. Each node, link, external and other item needs ev evidence. Give repository-relative code directories for each program. Include jobs for every program with repository code, including the API server and frontend: explain its purpose, trigger and steps with evidence within its code directories. made_by evidence may link supplied route keys only when supported by source. Keep existing node IDs for the same program. Use jobs:[] only when no jobs can be established and explain missing knowledge in unknown. Keep unknown operational facts in unknown. Do not invent nodes, jobs or connections. When changed_files is a list, read those changes first: if none adds, removes or changes a program, connection, store or external service, return only {"keep":"all","accounted":[{"file":path,"kind":"none"} for every changed file]}; otherwise return the full schema.',
            'jobs':'Describe jobs of the selected node. When the code establishes none, return jobs:[] with unknown explaining why. Trigger and step evidence must be within its code directories. made_by evidence identifies server code that creates the trigger; attach existing route keys only when the relation is supported. Unresolved producers stay unknown; never infer a relation from a shared table name alone.',
            'steps':'Describe ordered request steps for the supplied route keys only. Each step needs its own file, exact line and quote. Include service calls and return values, mark uncertain interpretation. Keep route keys unchanged.'}[task]
        prompt=(f'Produce {task} for commit {commit}. {rules}\nUse analysis_source with source_arguments for immutable source reads; never launch another AI CLI, execute application code or edit files. '
                f'Use {"English" if lang=="en" else "Korean"} for names and explanations; keep identifiers unchanged. '
                'Evidence must use tracked relative file paths, exact one-based lines and literal single-line quotes of at least 6 characters. Text matching does not establish semantic correctness. '
                'Return a JSON object using schema. Preserve unknown facts explicitly. '+mapcore.reply_language(lang,'en',saved_results=True))
        handoff=(f'where-were-we MCP의 request_ai_task를 {json.dumps(scope,ensure_ascii=False)} 인자로 호출하세요. '
                 '반환된 input·prompt·schema를 기준으로 현재 에이전트의 모델로 작업하세요. 필요한 코드는 source_arguments를 넣어 analysis_source로 읽으세요. '
                 '다른 AI CLI를 실행하지 마세요. 결과 JSON을 record_arguments와 함께 record_ai_task의 result_json으로 제출하세요. 저장 후 앱으로 돌아가라고 안내하세요. 앱이 저장된 결과를 읽습니다. 결과 확인을 위해 refresh 도구를 실행하지 마세요.') if lang=='ko' else (
                 f'Call where-were-we MCP request_ai_task with {json.dumps(scope)}. Use your current agent/model with the returned input, prompt and schema. '
                 'Read pinned source with analysis_source and source_arguments as needed. Do not launch another AI CLI. '
                 'Submit result_json to record_ai_task with record_arguments. Tell the user to return to the app, which reads the saved result. Do not call refresh to display the result.')
        handoff+=' '+mapcore.reply_language(lang,saved_results=True)
        results=project.analysis_results(raw,branch)
        before=([{'task':task,'key':key,'before':results[task].get(key)} for key in (inputs['routes'] if task=='steps' else [target])]
                if task in ('steps','jobs') else [{'task':task,'before':results[task]}])
        return {'commit':commit,'input':inputs,'prompt':prompt,'schema':TASK_SCHEMAS[task],'handoff':handoff,
                'result_before':before,
                'record_arguments':args,'source_arguments':{'project':name,'repository':rid,'branch':branch,'commit':commit}}

def task_result(raw,task,branch,target,data,repo,commit,lang,configuration=None):
    original=raw;raw=project.branch_bundle(raw,branch)
    inputs=task_input(raw,task,branch,target,repo,commit)
    evidence,cache,rejected=evidence_reader(repo,commit)
    def rows(obj,key):
        value=obj.get(key,[])
        if not isinstance(value,list) or len(value)>5000 or any(not isinstance(v,dict) for v in value):raise ValueError('Invalid task list: '+key)
        return value
    def text(obj,key):return obj.get(key) if isinstance(obj.get(key),str) else ''
    def verified(items):return [{**evidence_item,'ok':True} for item in items if (evidence_item:=evidence(item))]
    def unknown(value):
        if not isinstance(value,list):raise ValueError('Unknown facts must be a list')
        result=[]
        for item in value:
            if isinstance(item,str):result.append({'text':item,'needs':'read'})
            elif isinstance(item,dict) and text(item,'text'):
                result.append({'text':item['text'],'needs':item.get('needs') if item.get('needs') in ('ops','read') else 'read'})
            else:raise ValueError('Use text and needs for unknown facts')
        return result
    meta={'source':'ai','provider':'mcp-agent','commit':commit,'branch':branch,'language':lang,'configuration':configuration,'generated_at':project.now()}
    updated=copy.deepcopy(raw)
    def program_jobs(node,payload):
        code=node['code'];jobs=[]
        def within(ev):return any(c in ('','.','/') or ev['file']==c.rstrip('/') or ev['file'].startswith(c.rstrip('/')+'/') for c in code)
        routes={r['file']+'::'+r['function']:r for r in raw[branch]['backend_routes'] if r.get('function')}
        for job in rows(payload,'jobs'):
            trigger=evidence(job.get('trigger'))
            if not trigger or not within(trigger):continue
            made=[];links={};steps=[]
            for item in rows(job,'made_by'):
                ev=evidence(item)
                if not ev:continue
                made.append(ev)
                for key in item.get('routes',[]):
                    route=routes.get(key)
                    if route and ev['file'] in [route['file'],*route.get('services',[])]:links[key]={'key':key,'exact':False,'source':'ai'}
            for step in rows(job,'steps'):
                ev=evidence(step)
                if ev and within(ev) and text(step,'text'):steps.append({**ev,'lane':step.get('lane') if step.get('lane') in ('프로그램','저장소','외부') else '프로그램','text':step['text']})
            jobs.append({'name':text(job,'name'),'what':text(job,'what'),'starts_when':text(job,'starts_when'),
                         'trigger':trigger,'made_by':made,'steps':steps,'routes':list(links.values())})
        if not jobs and rows(payload,'jobs'):raise ValueError('No usable job trigger evidence; previous jobs preserved')
        return {**meta,'jobs':jobs}
    if task=='groups':
        full_input=groups_input(raw[branch]);known={x['path'] for x in full_input['screens']};seen=set();groups=[]
        delta=data.get('keep')=='previous';previous=raw.get('groups') or {}
        if delta and 'changed_screens' not in inputs:raise ValueError('No saved groups to keep; group every screen')
        allowed=set(inputs['changed_screens']) if delta else known
        if delta:
            for g in previous.get('groups',[]):
                paths=[p for p in g['screens'] if p in known and p not in allowed]
                if paths:groups.append({'name':g['name'],'description':g.get('description',''),'screens':paths});seen.update(paths)
        for g in rows(data,'groups'):
            if not text(g,'name') or not isinstance(g.get('screens'),list):raise ValueError('Invalid group')
            paths=[]
            for path in g['screens']:
                if not isinstance(path,str) or path not in allowed or path in seen:raise ValueError('Unknown or duplicate grouped screen')
                seen.add(path);paths.append(path)
            if not paths:continue
            same_name=next((x for x in groups if x['name']==g['name']),None)
            if same_name:same_name['screens']+=paths
            else:groups.append({'name':g['name'],'description':text(g,'description'),'screens':paths})
        if known!=seen:raise ValueError('Group every known screen exactly once')
        routes=set(route_keys(full_input))
        def names(key,allowed):
            value=data.get(key,{})
            if not isinstance(value,dict):raise ValueError('Invalid names')
            got={p:n.strip() for p,n in value.items() if p in allowed and isinstance(n,str) and n.strip()}
            return {**{p:n for p,n in previous.get(key,{}).items() if p in allowed},**got} if delta else got
        updated['groups']={**meta,'groups':groups,'names':names('names',known),'request_names':names('request_names',routes),
                           'inputs':{'screens':screen_digests(full_input),'routes':sorted(routes)}}
    elif task=='system' and data.get('keep')=='all':
        dest='system.ai' if (raw.get('system.ai') or {}).get('source')=='ai' else 'system';previous=raw.get(dest) or {}
        if previous.get('source')!='ai' or inputs['changed_files'] is None:raise ValueError('No reviewable saved structure; submit the full system schema')
        entries=data.get('accounted',[]);files=[e.get('file') for e in entries if isinstance(e,dict)]
        if not isinstance(entries,list) or sorted(files)!=inputs['changed_files'] or any(e.get('kind')!='none' for e in entries):
            raise ValueError('Account every changed file once with kind none, or submit the full system schema')
        if any(not evidence(ev) for ev in cited(previous)):raise ValueError('Saved structure evidence changed; submit the full system schema')
        updated[dest]={**previous,**meta,'verified_commit':previous.get('verified_commit') or previous.get('commit'),'checked':commit,
                       'kept_after_review':True,'accounted':{'none':len(files),'source':'ai'}}
    elif task=='system':
        def items(key):
            fields={'nodes':('id','name','kind','what','origin','origin_text','code','uses','unknown'),
                    'links':('from','to','label','style','sure'),'externals':('id','name','what'),
                    'others':('name','what')}[key]
            result=[]
            for item in rows(data,key):
                ev=verified(item.get('ev',[]))
                if ev:result.append({**{k:item[k] for k in fields if k in item},'ev':ev})
            return result
        nodes=items('nodes');externals=items('externals');ids=[n.get('id') for n in nodes]
        # nodes:[] is a finished answer only with stated unknowns and cited code; rejected nodes never are.
        empty=not rows(data,'nodes') and unknown(data.get('unknown',[])) and verified(data.get('ev',[]) if isinstance(data.get('ev',[]),list) else [])
        if not nodes and not empty:raise ValueError('No usable system evidence; previous system preserved')
        if any(not isinstance(v,str) or not v for v in ids) or len(set(ids))!=len(ids):raise ValueError('Invalid or duplicate node identity')
        extids=[x.get('id') for x in externals]
        if any(not isinstance(v,str) or not v for v in extids) or len(set(extids))!=len(extids):raise ValueError('Invalid external identity')
        for i,node in enumerate(nodes):
            if not text(node,'name'):raise ValueError('Name each node')
            node['kind']=node.get('kind') if node.get('kind') in ('user','program','store','copy') else 'program'
            if not isinstance(node.get('uses',[]),list):raise ValueError('Uses must be external IDs')
            node['uses']=[v for v in node.get('uses',[]) if v in extids]
            code=node.get('code',[])
            if not isinstance(code,list) or any(not isinstance(c,str) or c.startswith('/') or '..' in PurePosixPath(c).parts for c in code):raise ValueError('Use relative code directories')
            node['code']=code;node['unknown']=unknown(node.get('unknown',[]));node['what']=text(node,'what')
            node['origin']=node.get('origin') if node.get('origin') in ('repo','other','copy','none') else 'repo'
            node['origin_text']=text(node,'origin_text')
            node['col']=1 if node['kind']=='user' else 2;node['row']=i+1
        links=[l for l in items('links') if l.get('from') in ids and l.get('to') in ids and l['from']!=l['to']]
        for link in links:
            link['label']=text(link,'label');link['style']='copy' if link.get('style')=='copy' else ''
            link['sure']='doc' if link.get('sure')=='doc' else 'code'
        for external in externals:external['name']=text(external,'name') or external['id'];external['what']=text(external,'what')
        others=items('others')
        for item in others:
            if not text(item,'name'):raise ValueError('Name each other program')
            item['what']=text(item,'what')
        result={**meta,'written':'MCP agent · source text checked','checked':commit,'nodes':nodes,'ev':verified(data.get('ev',[])) if empty else [],'links':links,
                'externals':externals,'others':others,'unknown':unknown(data.get('unknown',[]))}
        dest='system.ai' if raw.get('system') and raw['system'].get('source')!='ai' else 'system'
        updated[dest]=result
        supplied={n['id']:n for n in rows(data,'nodes') if isinstance(n.get('id'),str)}
        previous={n['id']:n for n in (raw.get('system') or {}).get('nodes',[])}
        jobs=copy.deepcopy(raw.get('jobs') or {'nodes':{}})
        if dest=='system':
            # Reused identities with different code must not display old jobs.
            jobs['nodes']={key:value for key,value in jobs['nodes'].items()
                           if key in ids and previous.get(key,{}).get('code')==next(n for n in nodes if n['id']==key).get('code')}
        for node in nodes:
            payload=supplied[node['id']]
            if node['kind']!='program' or not node['code'] or 'jobs' not in payload:continue
            normalized=program_jobs(node,payload)
            if dest=='system' or previous.get(node['id'],{}).get('code')==node['code']:
                jobs['nodes'][node['id']]=normalized
        if jobs!=raw.get('jobs'):updated['jobs']=jobs
    elif task=='steps':
        outputs=data.get('routes')
        if not isinstance(outputs,dict) or not outputs or any(k not in inputs['routes'] for k in outputs):raise ValueError('Choose known route targets')
        updated['flows']=updated.get('flows') or {'routes':{}};flows=updated['flows']['routes']
        for key,got in outputs.items():
            if not isinstance(got,dict):raise ValueError('Invalid route steps')
            route=inputs['routes'][key];steps=[]
            for step in rows(got,'steps'):
                ev=evidence({**step,'file':step.get('file',route['file'])})
                if ev and text(step,'text'):steps.append({**ev,'lane':step.get('lane') if step.get('lane') in ('서버','저장소','외부','화면') else '서버',
                                                         'text':step['text'],'uncertain':bool(step.get('uncertain'))})
            reason=text(got,'unknown').strip()
            # Steps the code does not establish are recorded as unknown; supplied steps must still verify.
            if not steps and (got.get('steps') or not reason):raise ValueError('No usable step evidence; previous steps preserved')
            flow={**meta,**({'unknown':reason} if not steps else {}),'name':text(got,'name'),'file':route['file'],'function':route['function'],'steps':steps,
                  'hash':hashlib.sha1(git(repo,'show',commit+':'+route['file']).encode()).hexdigest()[:12]}
            flows[key]=flow
            for r in updated[branch]['backend_routes']:
                if r['file']+'::'+str(r.get('function'))==key:r['flow']=flow
    else:
        jobs=program_jobs(inputs['node'],data)
        if not jobs['jobs']:
            # No jobs is a finished answer only when stated with unknown, never when supplied jobs were rejected.
            reason=unknown(data.get('unknown',[]))
            if rows(data,'jobs') or not reason:raise ValueError('No usable job trigger evidence; previous jobs preserved')
            jobs['unknown']=reason
        updated['jobs']=updated.get('jobs') or {'nodes':{}}
        updated['jobs']['nodes'][target]=jobs
    # Task results travel with their exact branch map, rather than overwriting
    # the shared legacy auxiliary files used by the other branch.
    result=copy.deepcopy(original)
    result[branch]=updated[branch]
    outputs=result[branch].setdefault('task_outputs',{})
    for key in project.DETAILS:
        if updated.get(key)!=raw.get(key):outputs[key]=updated[key]
    return result

def task_record(project,repository,task,branch,lang,target,commit,configuration,snapshot,result_json):
    import project as store
    if lang not in ('ko','en'):raise ValueError('Choose ko or en')
    if not isinstance(result_json,str) or len(result_json)>8_000_000:raise ValueError('Invalid task JSON')
    data=json.loads(result_json)
    if not isinstance(data,dict):raise ValueError('Task result must be an object')
    with store.locked(project):
        repo,raw,rid,head=task_context(project,task,branch,repository)
        if configuration!=store.fingerprint(repo) or commit!=head or snapshot!=task_snapshot(raw,task,branch):
            raise ValueError('Task source or stored input changed; request it again')
        updated=task_result(raw,task,branch,target,data,repo['path'],commit,lang,configuration)
        if rid:store._publish(project,rid,updated,{},collection=False)
        else:
            for key,value in updated.items():
                if value!=raw.get(key):store.atomic(store.home(project)/(key+'.json'),value)
        return 'Saved '+task+' from connected MCP agent'

PLAN_TEXT={
 'ko':{'head':'where-were-we MCP로 이 프로젝트에 필요한 분석을 모두 마치세요. 지금 사용하는 에이전트의 모델로 분석하고 다른 AI CLI를 실행하지 마세요. '
              '먼저 analysis_plan을 {scope} 인자로 호출하고, 돌려받은 tasks의 첫 작업만 아래 방법으로 저장한 뒤 analysis_plan을 다시 호출하세요. tasks가 빌 때까지 반복합니다. '
              '저장된 최신 결과는 목록에 나오지 않으니 다시 분석하지 마세요. 각 도구가 돌려준 handoff 안내 대신 이 방법을 따르세요. '
              '돌려받은 commit·configuration·input_hash가 아래 기준값과 다르면 그 코드의 남은 작업을 멈추고 알려 주세요.',
       'how':'작업별 방법: analysis는 analyze를 호출하고 source_arguments로 analysis_source를 읽어 record_analysis로 저장합니다. '
             'analyze가 돌려준 mode(full·review·patch)를 따르고 결과 JSON에 base를 넣습니다. review와 patch는 저장된 항목을 다시 쓰지 않고 바뀐 것만 냅니다. '
             'system·groups·steps·jobs는 그때 request_ai_task를 task와 target 그대로 호출해 받은 input·schema·record_arguments로 record_ai_task에 저장합니다. '
             'briefing은 request_briefing을 호출하고 briefing_source로 근거를 읽어 record_briefing으로 저장합니다. '
             '소스 구조(화면·서버·데이터 코드가 어디 있는지)는 프레임워크 이름이 아니라 고정된 커밋의 실제 파일을 읽어 찾습니다. '
             '원문 근거를 붙이고, 코드로 확인되지 않는 것은 지어내지 말고 schema의 unknown으로 남기세요.',
       'pins':'매번 작업 전에 반환된 pins 전체를 이 기준과 대조하세요. 저장소가 추가·제거되거나 값이 달라지면 작업을 멈추고 새 요청이 필요하다고 알려 주세요. 기준 pins: ',
       'now':'지금 필요한 작업과 기준값:','tail':'한 작업이 실패해도 이미 저장된 결과는 남습니다. 실패한 작업과 이유를 알려 주세요. 모두 끝나면 앱으로 돌아가라고 안내하세요. 앱이 저장된 결과를 읽습니다. 결과 확인을 위해 refresh 도구를 실행하지 마세요.'},
 'en':{'head':'Complete all the analysis this project needs with the where-were-we MCP tools. Use your current agent/model and do not launch another AI CLI. '
              'First call analysis_plan with {scope}, save only the first returned task as described below, then call analysis_plan again. Repeat until tasks is empty. '
              'Current saved results are never listed; do not reanalyze them. Follow this method instead of the handoff text a tool returns. '
              'If a returned commit, configuration or input_hash differs from the reference values below, stop the remaining work for that code and report it.',
       'how':'Per task: analysis calls analyze, reads source with analysis_source and source_arguments, and saves with record_analysis. '
             'Follow the mode analyze returns (full, review or patch) and put its base in result_json; review and patch never repeat saved items, only changes. '
             'system, groups, steps and jobs call request_ai_task then, with the task and target unchanged, and save to record_ai_task with the returned input, schema and record_arguments. '
             'briefing calls request_briefing, reads evidence with briefing_source and saves with record_briefing. '
             'Find the source structure (where screen, server and data code live) by reading the tracked files at the pinned commit, not from a framework name. '
             'Include literal evidence; record what the code does not establish as unknown in the schema instead of inventing it.',
       'pins':'Before every task, compare the entire returned pins object with this reference. If a repository is added or removed, or a value changes, stop and report that a new request is needed. Reference pins: ',
       'now':'Tasks needed now and reference values:','tail':'A failed task leaves saved results intact; report which task failed and why. When all are done, tell the user to return to the app, which reads the saved results. Do not call refresh to display the result.'}}
READ_ERRORS=(ValueError,subprocess.CalledProcessError,OSError)

def plan(name,branch='dev',lang='ko',repository=''):
    """Only missing or outdated analysis, for the connected agent to repeat after each save. Reads only."""
    import briefing
    if lang not in ('ko','en'):raise ValueError('Choose ko or en')
    repository='' if repository=='*' else repository
    conf=project.config(name)
    if conf:
        repos=[r for r in conf['repositories'] if not repository or r['id']==repository]
        if repository and not repos:raise ValueError('Unknown repository')
    else:repos=[None]
    tasks=[];blocked=[];skipped=[];pins={}
    same=lambda a,b:bool(a and b) and (str(a).startswith(str(b)) or str(b).startswith(str(a)))
    for repo in repos:
        rid=repo['id'] if repo else ''
        if repo and not repo['refs'].get(branch):skipped.append({'repository':rid,'reason':'no_branch'});continue
        try:
            req=request(name,branch,lang,rid)
            with project.locked(name):_,raw,_,head=context(name,rid,branch)
            if head!=req['commit']:raise ValueError('Repository commit changed while preparing; request again')
        except READ_ERRORS as error:blocked.append({'repository':rid,'task':'analysis','reason':str(error)});continue
        config=req['record_arguments']['configuration'];pin={'commit':head,'configuration':config};pins[rid]=pin
        res=project.analysis_results(raw,branch);sel=project.branch_bundle(raw,branch);m=raw[branch]
        fresh=lambda meta:bool(meta) and not meta['stale'] and meta.get('language')==lang and same(meta.get('commit'),head) and meta.get('configuration')==config
        add=lambda task,before,target='':tasks.append({'repository':rid,'task':task,'target':target,'before':before,**pin})
        if not fresh(res['analysis']):
            # Dependents are known only after the new map is saved; the agent re-plans then.
            add('analysis',res['analysis']);tasks[-1].update(mode=req['mode'],reason=req['reason'],recheck_count=len(req['recheck']),inspect_count=len(req['inspect']))
            add('system',res['system']);add('groups',res['groups']);continue
        proposal=(sel.get('system.ai') or {}).get('source')=='ai'
        nodes=(sel.get('system.ai') if proposal else sel.get('system') or {}).get('nodes',[])
        human={n.get('id'):n.get('code') for n in (sel.get('system') or {}).get('nodes',[])} if proposal else None
        missing=[]
        for node in nodes:
            if node.get('kind','program')!='program' or not node.get('code'):continue
            if proposal and human.get(node['id'])!=node['code']:
                blocked.append({'repository':rid,'task':'jobs','target':node['id'],'review_required':True,
                                'reason':'Review the saved AI structure proposal; its program identity differs from the written structure.'});continue
            if not fresh(res['jobs'].get(node['id'])):missing.append(node['id'])
        # A program whose code changed while the structure stayed current only needs its own jobs again.
        rerun=[n for n in missing if n in (sel.get('jobs') or {}).get('nodes',{})]  # a saved record, even empty, is re-asked per program
        if not fresh(res['system']) or set(missing)-set(rerun):add('system',res['system'])
        else:
            for n in rerun:add('jobs',res['jobs'].get(n),n)
        if any(not s.get('redirect') for s in m.get('screens',[])) and not fresh(res['groups']):add('groups',res['groups'])
        keys=[r['file']+'::'+r['function'] for r in m.get('backend_routes',[]) if r.get('mounted') and r.get('function')]
        keys=[k for k in dict.fromkeys(keys) if not fresh(res['steps'].get(k))]
        if keys:add('steps',{k:res['steps'].get(k) for k in keys},'@routes:'+json.dumps(keys,ensure_ascii=False))
    try:
        view=briefing.view(name,repository,branch,lang)
        if view.get('input_hash'):pins['@briefing']={'input_hash':view['input_hash']}
        # A new window without collected changes is not a reason to explain again.
        if view['state'] in ('not_analyzed','stale') and (view.get('input') or {}).get('has_changes'):
            b=briefing.request(name,repository,branch,lang)
            tasks.append({'repository':repository,'task':'briefing','target':'','before':b['result_before'][0]['before'],'commit':b['commit'],'input_hash':b['record_arguments']['input_hash']})
        elif view['state']=='needs_collection':skipped.append({'repository':repository,'task':'briefing','reason':'needs_collection'})
    except READ_ERRORS as error:blocked.append({'repository':repository,'task':'briefing','reason':str(error)})
    text=PLAN_TEXT[lang];scope=json.dumps({'project':name,'repository':repository,'branch':branch,'lang':lang},ensure_ascii=False)
    lines=[f"- {t['repository'] or name} · {t['task']}"+(f" · target {t['target']}" if t['target'] else '')+
           (f" · input_hash {t['input_hash']}" if t['task']=='briefing' else f" · commit {t['commit']} · configuration {t['configuration']}") for t in tasks]
    handoff='\n'.join([text['head'].format(scope=scope),text['how'],text['pins']+json.dumps(pins,ensure_ascii=False,sort_keys=True),text['now'],*lines,text['tail']+' '+mapcore.reply_language(lang,saved_results=True)]) if tasks else ''
    return {'project':name,'repository':repository,'branch':branch,'lang':lang,'tasks':tasks,'blocked':blocked,'skipped':skipped,'pins':pins,
            'up_to_date':not tasks and not blocked,'handoff':handoff,
            'requirements':[{k:t.get(k) for k in ('task','repository','target','before','commit')} for t in tasks]}

def task_cli(task,argv=None,emit=True):
    """Compatibility commands prepare MCP requests; they never invoke AI."""
    import argparse
    parser=argparse.ArgumentParser(description='Prepare a connected-agent MCP task')
    parser.add_argument('project')
    if task in ('groups','steps'):parser.add_argument('branch',nargs='?',default='dev',choices=['dev','main'])
    else:parser.add_argument('--branch',default=None,choices=['dev','main'])
    if task in ('steps','jobs'):parser.add_argument('target')
    parser.add_argument('--lang',default='ko',choices=['ko','en']);parser.add_argument('--repository',default='')
    args=parser.parse_args(argv)
    branch=args.branch
    if branch is None:
        conf=project.config(args.project)
        if conf:
            repo=project.selected_repository(args.project,args.repository);branch='dev' if repo['refs'].get('dev') else 'main'
        else:branch='dev' if project.raw_bundle(project.home(args.project)).get('dev') else 'main'
    result=task_request(args.project,task,branch,args.lang,args.repository,getattr(args,'target',''))
    if emit:print(json.dumps(result,ensure_ascii=False))
    return result

def analysis_cli(argv=None):
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request',action='store_true');parser.add_argument('--plan',action='store_true');parser.add_argument('--repository',default='')
    parser.add_argument('--task',choices=list(TASK_SCHEMAS));parser.add_argument('--target',default='')
    parser.add_argument('project');parser.add_argument('branch',choices=['dev','main']);parser.add_argument('lang',nargs='?',default='ko',choices=['ko','en'])
    args=parser.parse_args(argv)
    if args.plan:return plan(args.project,args.branch,args.lang,args.repository)
    if args.task:return task_request(args.project,args.task,args.branch,args.lang,args.repository,args.target)
    return request(args.project,args.branch,args.lang,args.repository)

if __name__=='__main__':
    print(json.dumps(analysis_cli(),ensure_ascii=False))
