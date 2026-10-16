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
sys.path.insert(0,str(Path(__file__).resolve().parent))
import mapcore
import project

VERSION=1
METHODS={'GET','POST','PUT','PATCH','DELETE','HEAD','OPTIONS'}

def git(repo,*args):
    return subprocess.run(['git','-C',repo,*args],capture_output=True,text=True,check=True).stdout

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
    return evidence,cache,lambda:rejected

def normalize(data,repo,commit,ref,layout=None):
    if not isinstance(data,dict):raise ValueError('AI output must be an object')
    evidence,cache,rejections=evidence_reader(repo,commit)
    def rows(obj,key):
        value=obj.get(key,[])
        if not isinstance(value,list) or len(value)>5000:raise ValueError('Invalid AI list: '+key)
        return value
    def text(value):return value if isinstance(value,str) else ''
    def endpoint(item):
        return item.get('method') in METHODS and isinstance(item.get('path'),str) and item['path'].startswith('/')
    output={**project.empty_map(),'repo':repo,'commit':commit,'ref':ref,'extractor':mapcore.extractor_id('')}
    flows={'routes':{}};seen=set();screens=[];routes=[];functions=[];file_screens={}
    def touch(file,path):
        if path not in file_screens.setdefault(file,[]):file_screens[file].append(path)
    for item in rows(data,'backend_routes'):
        ev=evidence(item)
        if not ev or not endpoint(item) or not text(item.get('function')):continue
        key=(ev['file'],ev['line'])
        if key in seen:raise ValueError('Duplicate AI route identity')
        seen.add(key)
        tables=[];table_evidence=[];externals=[];services=[]
        for table in rows(item,'tables'):
            tev=evidence(table)
            if tev and text(table.get('name')):tables.append(table['name']);table_evidence.append({**tev,'name':table['name']})
        for service in rows(item,'services'):
            sev=evidence(service)
            if sev:services.append(sev['file'])
        for external in rows(item,'externals'):
            if evidence(external) and text(external.get('name')):externals.append(external['name'])
        route={**ev,'method':item['method'],'path':mapcore.normalize_http_path(item['path']),'function':item['function'],'mounted':True,
               'tables':sorted(set(tables)),'table_evidence':table_evidence,'externals':externals,'services':services,
               'tests':[],'source':'ai','evidence':[ev]}
        routes.append(route)
        steps=[]
        for step in rows(item,'steps'):
            sev=evidence(step)
            if sev and text(step.get('text')):
                steps.append({**sev,'text':step['text'],'lane':step.get('lane') if step.get('lane') in ('서버','화면','저장소','외부') else '서버',
                              'uncertain':bool(step.get('uncertain'))})
        if steps:flows['routes'][ev['file']+'::'+item['function']]={'name':text(item.get('name')) or item['function'],
            'file':ev['file'],'function':item['function'],'commit':commit,'source':'ai','steps':steps,
            'hash':hashlib.sha1('\n'.join(cache[ev['file']]).encode()).hexdigest()[:12]}
    route_index={}
    for r in routes:route_index.setdefault((r['method'],r['path']),[]).append(r)
    seen=set();used=set();unresolved=[]
    for item in rows(data,'screens'):
        ev=evidence(item)
        if not ev or not isinstance(item.get('path'),str) or not item['path'].startswith('/'):continue
        if item['path'] in seen:raise ValueError('Duplicate AI screen path')
        seen.add(item['path'])
        screen={**ev,'path':item['path'],'heading':text(item.get('heading')) or None,'component':None,'redirect':False,
                'condition':None,'actions':[],'api_functions':[],'source':'ai','evidence':[ev]}
        touch(ev['file'],screen['path'])
        for dependency in rows(item,'dependencies'):
            dev=evidence(dependency)
            if dev:touch(dev['file'],screen['path'])
        for index,call in enumerate(rows(item,'calls')):
            cev=evidence(call)
            if not cev or not endpoint(call):continue
            name='ai:'+screen['path']+':'+str(index)
            call_path=mapcore.normalize_http_path(call['path'])
            hits=route_index.get((call['method'],call_path),[])
            hits=hits if len(hits)==1 else []
            connection={**cev,'method':call['method'],'path':call_path,'kind':'literal','connection_basis':'ai',
                'backend':[{'file':r['file'],'line':r['line'],'function':r['function']} for r in hits]}
            functions.append({'file':cev['file'],'name':name,'line':cev['line'],'calls':[connection],'used_by_screens':True,'source':'ai'})
            screen['api_functions'].append({'file':cev['file'],'name':name,'via':None})
            touch(cev['file'],screen['path'])
            for hit in hits:
                used.add((hit['file'],hit['line']))
                for f in [hit['file'],*hit['services']]:touch(f,screen['path'])
            if not hits:unresolved.append({'api_function':cev['file']+':'+name,**connection})
        for action in rows(item,'actions'):
            aev=evidence(action)
            if not aev or action.get('kind') not in ('nav','api','local'):continue
            target=action.get('to')
            screen['actions'].append({**aev,'kind':action['kind'],'label':text(action.get('label')),'to':target if isinstance(target,str) else None,
                'targets':[],'api_functions':[],'calls':[],'via':None,'source':'ai'})
        screens.append(screen)
    if not screens and not routes:raise ValueError('No usable AI map evidence; previous map was preserved')
    for screen in screens:
        for action in screen['actions']:
            if action['to'] not in seen:action['to']=None
            elif action['kind']=='nav':action['targets']=[{'to':action['to'],'label':action['label']}]
    output.update(screens=screens,api_functions=functions,backend_routes=routes,file_screens=file_screens,
        backend_routes_without_screen=[r for r in routes if (r['file'],r['line']) not in used],unresolved_calls=unresolved,
        models={t:t for r in routes for t in r['tables']},coverage={'frontend':bool(screens),'backend':bool(routes)},
        analysis={'source':'ai','version':VERSION,'commit':commit,'generated_at':project.now(),'stale':False,'rejected':rejections(),
                  'unknown':[v for v in rows(data,'unknown') if isinstance(v,str)],'evidence_check':'literal-source-match; semantics are AI-inferred'})
    return output,flows

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
                    'services':[],'externals':[],'steps':[{'file':'server/main.go','line':8,'quote':'literal source','lane':'저장소',
                    'text':'Store item','uncertain':False}]}], 'unknown':['Anything not established from code']}

def analysis_prompt(commit,lang,layout):
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
Each step uses lane 서버, 저장소, 외부 or 화면. Tables, services and externals require their own evidence.
Return exactly one JSON object with this schema (examples are illustrative, do not copy them):
{json.dumps(SCHEMA,ensure_ascii=False)}'''


def apply_result(raw,repo,refs,branch,lang,response,commit,layout):
    current=raw.get(branch) or {}
    text=response.strip()
    if len(text)>8_000_000:raise ValueError('AI output was too large')
    if text.startswith('```'):text=re.sub(r'^```(?:json)?\s*|\s*```$','',text)
    try:data=json.loads(text)
    except (ValueError,TypeError) as error:raise ValueError('AI output was not valid JSON; previous map was preserved') from error
    for key,area in [('screens','frontend'),('backend_routes','backend')]:
        if area in layout:
            data[key]=[] if layout[area] is None else [item for item in data.get(key,[]) if isinstance(item,dict) and isinstance(item.get('file'),str) and item['file'].startswith(layout[area].rstrip('/')+'/')]
    m,flows=normalize(data,repo,commit,refs[branch]);m['analysis']['language']=lang
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

def request(name,branch='dev',lang='ko',repository=''):
    if lang not in ('ko','en'):raise ValueError('Choose ko or en')
    with project.locked(name):
        repo,raw,rid,commit=context(name,repository,branch)
        fingerprint=project.fingerprint(repo)
        if rid and project.states(name).get(rid,{}).get('fingerprint')!=fingerprint:raise ValueError('Refresh after configuration changes first')
        arguments={'project':name,'repository':rid,'branch':branch,'lang':lang,'commit':commit,'configuration':fingerprint}
        scope=json.dumps({'project':name,'repository':rid,'branch':branch,'lang':lang},ensure_ascii=False)
        handoff=(f"where-were-we MCP로 이 프로젝트의 상세 지도를 분석해 주세요. 먼저 analyze를 {scope} 인자로 호출하세요. "
                 "반환된 커밋과 schema를 기준으로 반환된 source_arguments를 넣어 analysis_source 도구로 코드를 읽고, 지금 사용하는 에이전트의 모델로 분석하세요. "
                 "다른 AI CLI를 실행하지 마세요. 원문 근거를 붙이고 모르는 부분은 unknown에 남기세요. "
                 "결과 JSON은 반환된 record_arguments와 함께 record_analysis의 result_json으로 저장하세요.") if lang=='ko' else (
                 f"Analyze this project with the where-were-we MCP tools. First call analyze with {scope}. "
                 "Use analysis_source with the returned source_arguments to read the immutable commit and use your current agent/model to produce the returned schema. "
                 "Do not launch another AI CLI. Include literal evidence and unknown areas. Submit result_json to record_analysis with the returned record_arguments.")
        return {'commit':commit,'record_arguments':arguments,'repository_path':repo['path'],
                'source_arguments':{'project':name,'repository':rid,'branch':branch,'commit':commit},
                'prompt':analysis_prompt(commit,lang,repo['layout']),'schema':SCHEMA,'handoff':handoff}

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

def record(project,repository,branch,lang,commit,configuration,result_json):
    import project as store
    if lang not in ('ko','en'):raise ValueError('Choose ko or en')
    with store.locked(project):
        repo,raw,rid,head=context(project,repository,branch)
        if configuration!=store.fingerprint(repo):raise ValueError('Repository configuration changed; request a new analysis')
        if commit!=head:raise ValueError('Repository commit changed; request a new analysis')
        updated,message=apply_result(raw,repo['path'],repo['refs'],branch,lang,result_json,commit,repo['layout'])
        updated[branch]['analysis']['provider']='mcp-agent'
        if rid:store._publish(project,rid,updated,{},collection=False)
        else:
            for key,value in updated.items():
                if value is not None:store.atomic(store.home(project)/(key+'.json'),value)
        return message

EV_SCHEMA={'file':'path/in/repository','line':1,'quote':'literal source text'}
UNKNOWN_SCHEMA={'text':'Unverified fact','needs':'read'}
TASK_SCHEMAS={
    'groups':{'groups':[{'name':'Name','description':'Description','screens':['/path']}],
              'names':{'/path':'Screen name'},'request_names':{'file::function':'Request name'}},
    'system':{'nodes':[{'id':'program','name':'Program','kind':'program','what':'Purpose','origin':'repo',
                        'origin_text':'Source location','code':['src'],'uses':[],'unknown':[UNKNOWN_SCHEMA],'ev':[EV_SCHEMA]}],
              'links':[{'from':'program','to':'store','label':'Exchange','style':'','sure':'code','ev':[EV_SCHEMA]}],
              'externals':[{'id':'cloud','name':'Cloud','what':'External service','ev':[EV_SCHEMA]}],
              'others':[{'name':'Other program','what':'Purpose','ev':[EV_SCHEMA]}],'unknown':[UNKNOWN_SCHEMA]},
    'jobs':{'jobs':[{'name':'Job','what':'Purpose','starts_when':'Trigger condition','trigger':EV_SCHEMA,
                    'made_by':[{**EV_SCHEMA,'routes':['file::function']}],
                    'steps':[{**EV_SCHEMA,'lane':'프로그램','text':'Step'}]}]},
    'steps':{'routes':{'file::function':{'name':'Request name','steps':[{**EV_SCHEMA,'lane':'서버','text':'Step','uncertain':False}]}}}
}

def task_input(raw,task,branch,target):
    raw=project.branch_bundle(raw,branch)
    m=raw[branch]
    routes={r['file']+'::'+r['function']:r for r in m['backend_routes'] if r.get('mounted') and r.get('function')}
    if task=='groups':
        screens=[s for s in m['screens'] if not s.get('redirect')]
        paths={s['path'] for s in screens}
        screens=[s for s in screens if not s['path'].startswith('/m/') or s['path'][2:] not in paths]
        return {'screens':[{'path':s['path'],'title':s.get('heading'),'buttons':list(dict.fromkeys(
                    a['label'] for a in s.get('actions',[]) if a.get('label') and not a.get('via')))[:10]} for s in screens],
                'routes':[{k:r.get(k) for k in ('file','function','method','path','tables','externals')} for r in routes.values()]}
    if task=='system':return {'previous':raw.get('system') or {},'routes':list(routes)}
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
    return {'routes':{key:routes[key] for key in keys}}

def task_snapshot(raw,task,branch):
    raw=project.branch_bundle(raw,branch)
    keys={'groups':['groups'],'system':['system','system.ai'],'jobs':['system','jobs'],'steps':['flows']}[task]
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
        inputs=task_input(raw,task,branch,target)
        args={'project':name,'repository':rid,'task':task,'branch':branch,'lang':lang,'target':target,
              'commit':commit,'configuration':project.fingerprint(repo),'snapshot':task_snapshot(raw,task,branch)}
        scope={k:args[k] for k in ('project','repository','task','branch','lang','target')}
        rules={
            'groups':'Group all supplied screens exactly once by user activity. Keep screen paths and route keys unchanged. Name mounted requests too. Use only supplied metadata, not source code.',
            'system':'Describe separately running programs, users, stores and copied code, their connections and external services. Each node, link, external and other item needs ev evidence. Give repository-relative code directories for each program. Keep unknown operational facts in unknown. Do not invent nodes or connections.',
            'jobs':'Describe jobs of the selected node. Trigger and step evidence must be within its code directories. made_by evidence identifies server code that creates the trigger; attach existing route keys only when the relation is supported. Unresolved producers stay unknown; never infer a relation from a shared table name alone.',
            'steps':'Describe ordered request steps for the supplied route keys only. Each step needs its own file, exact line and quote. Include service calls and return values, mark uncertain interpretation. Keep route keys unchanged.'}[task]
        prompt=(f'Produce {task} for commit {commit}. {rules}\nUse analysis_source with source_arguments for immutable source reads; never launch another AI CLI, execute application code or edit files. '
                f'Use {"English" if lang=="en" else "Korean"} for names and explanations; keep identifiers unchanged. '
                'Evidence must use tracked relative file paths, exact one-based lines and literal single-line quotes of at least 6 characters. Text matching does not establish semantic correctness. '
                'Return a JSON object using schema. Preserve unknown facts explicitly.')
        handoff=(f'where-were-we MCP의 request_ai_task를 {json.dumps(scope,ensure_ascii=False)} 인자로 호출하세요. '
                 '반환된 input·prompt·schema를 기준으로 현재 에이전트의 모델로 작업하세요. 필요한 코드는 source_arguments를 넣어 analysis_source로 읽으세요. '
                 '다른 AI CLI를 실행하지 마세요. 결과 JSON을 record_arguments와 함께 record_ai_task의 result_json으로 제출하세요. 저장 후 앱을 새로고침하세요.') if lang=='ko' else (
                 f'Call where-were-we MCP request_ai_task with {json.dumps(scope)}. Use your current agent/model with the returned input, prompt and schema. '
                 'Read pinned source with analysis_source and source_arguments as needed. Do not launch another AI CLI. '
                 'Submit result_json to record_ai_task with record_arguments, then refresh the app.')
        return {'commit':commit,'input':inputs,'prompt':prompt,'schema':TASK_SCHEMAS[task],'handoff':handoff,
                'record_arguments':args,'source_arguments':{'project':name,'repository':rid,'branch':branch,'commit':commit}}

def task_result(raw,task,branch,target,data,repo,commit,lang):
    original=raw;raw=project.branch_bundle(raw,branch)
    inputs=task_input(raw,task,branch,target)
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
    meta={'source':'ai','provider':'mcp-agent','commit':commit,'branch':branch,'language':lang}
    updated=copy.deepcopy(raw)
    if task=='groups':
        known={s['path'] for s in inputs['screens']};seen=set();groups=[]
        for g in rows(data,'groups'):
            if not text(g,'name') or not isinstance(g.get('screens'),list):raise ValueError('Invalid group')
            paths=[]
            for path in g['screens']:
                if not isinstance(path,str) or path not in known or path in seen:raise ValueError('Unknown or duplicate grouped screen')
                seen.add(path);paths.append(path)
            if paths:groups.append({'name':g['name'],'description':text(g,'description'),'screens':paths})
        if known!=seen:raise ValueError('Group every known screen exactly once')
        routes={r['file']+'::'+r['function'] for r in inputs['routes']}
        def names(key,allowed):
            value=data.get(key,{})
            if not isinstance(value,dict):raise ValueError('Invalid names')
            return {p:n.strip() for p,n in value.items() if p in allowed and isinstance(n,str) and n.strip()}
        updated['groups']={**meta,'groups':groups,'names':names('names',known),'request_names':names('request_names',routes)}
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
        if not nodes:raise ValueError('No usable system evidence; previous system preserved')
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
        result={**meta,'written':'MCP agent · source text checked','checked':commit,'nodes':nodes,'links':links,
                'externals':externals,'others':others,'unknown':unknown(data.get('unknown',[]))}
        dest='system.ai' if raw.get('system') and raw['system'].get('source')!='ai' else 'system'
        updated[dest]=result
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
            if not steps:raise ValueError('No usable step evidence; previous steps preserved')
            flow={**meta,'name':text(got,'name'),'file':route['file'],'function':route['function'],'steps':steps,
                  'hash':hashlib.sha1(git(repo,'show',commit+':'+route['file']).encode()).hexdigest()[:12]}
            flows[key]=flow
            for r in updated[branch]['backend_routes']:
                if r['file']+'::'+str(r.get('function'))==key:r['flow']=flow
    else:
        code=inputs['node']['code'];jobs=[]
        def within(ev):return any(c in ('','.','/') or ev['file']==c.rstrip('/') or ev['file'].startswith(c.rstrip('/')+'/') for c in code)
        routes={r['file']+'::'+r['function']:r for r in inputs['routes']}
        for job in rows(data,'jobs'):
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
        if not jobs:raise ValueError('No usable job trigger evidence; previous jobs preserved')
        updated['jobs']=updated.get('jobs') or {'nodes':{}}
        updated['jobs']['nodes'][target]={**meta,'jobs':jobs}
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
        updated=task_result(raw,task,branch,target,data,repo['path'],commit,lang)
        if rid:store._publish(project,rid,updated,{},collection=False)
        else:
            for key,value in updated.items():
                if value!=raw.get(key):store.atomic(store.home(project)/(key+'.json'),value)
        return 'Saved '+task+' from connected MCP agent'

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
    parser.add_argument('--request',action='store_true');parser.add_argument('--repository',default='')
    parser.add_argument('--task',choices=list(TASK_SCHEMAS));parser.add_argument('--target',default='')
    parser.add_argument('project');parser.add_argument('branch',choices=['dev','main']);parser.add_argument('lang',nargs='?',default='ko',choices=['ko','en'])
    args=parser.parse_args(argv)
    if args.task:return task_request(args.project,args.task,args.branch,args.lang,args.repository,args.target)
    return request(args.project,args.branch,args.lang,args.repository)

if __name__=='__main__':
    print(json.dumps(analysis_cli(),ensure_ascii=False))
