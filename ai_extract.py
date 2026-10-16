#!/usr/bin/env python3
"""Explicit, language-independent AI maps with commit-bound source evidence.

Accepts results from any connected MCP agent; Claude Code CLI is an optional adapter. Normal refresh never invokes an AI provider.
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

def normalize(data,repo,commit,ref,layout=None):
    if not isinstance(data,dict):raise ValueError('AI output must be an object')
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
        analysis={'source':'ai','version':VERSION,'commit':commit,'generated_at':project.now(),'stale':False,'rejected':rejected,
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

def analyze_raw(raw,repo,refs,branch,lang,runner,layout=None):
    if branch not in ('dev','main') or not refs.get(branch):raise ValueError('Choose an available branch role')
    commit=git(repo,'rev-parse','--verify',refs[branch]+'^{commit}').strip()
    layout=layout or {}
    current=raw.get(branch) or {}
    old=current.get('analysis') or {}
    if old.get('source')=='ai' and old.get('version')==VERSION and current.get('commit')==commit and old.get('language')==lang:
        return None,'AI map is already current; no AI was called.'
    prompt=analysis_prompt(commit,lang,layout)
    command=['claude','-p','--output-format','text','--model','sonnet','--allowedTools',
             'Bash(git ls-tree:*)','Bash(git show:*)','Bash(git grep:*)']
    result=runner(command,input=prompt,cwd=repo,capture_output=True,text=True,timeout=1200)
    if result.returncode:raise ValueError('AI analysis failed: '+result.stderr[-800:])
    return apply_result(raw,repo,refs,branch,lang,result.stdout,commit,layout)

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

def analyze(name,branch='dev',lang='ko',repository='',runner=None):
    runner=runner or subprocess.run
    if lang not in ('ko','en'):raise ValueError('Choose ko or en')
    conf=project.config(name)
    if conf:
        with project.locked(name):
            repo=project.selected_repository(name,repository)
            state=project.states(name)
            if state.get(repo['id'],{}).get('fingerprint')!=project.fingerprint(repo):raise ValueError('Refresh this repository first')
            raw=project.raw_bundle(project.repository_folder(name,repo,state))
            updated,message=analyze_raw(raw,repo['path'],repo['refs'],branch,lang,runner,repo['layout'])
            if updated:project._publish(name,repo['id'],updated,{},collection=False)
            return message
    folder=project.home(name);raw=project.raw_bundle(folder)
    current=raw.get(branch)
    if not current:raise ValueError('Refresh this repository first')
    updated,message=analyze_raw(raw,current['repo'],mapcore.configured_refs(),branch,lang,runner,json.loads(os.environ.get('WHERE_WERE_WE_LAYOUT','{}')))
    if updated:
        for key,value in updated.items():
            if value is not None:project.atomic(folder/(key+'.json'),value)
    return message

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

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request',action='store_true');parser.add_argument('--repository',default='')
    parser.add_argument('project');parser.add_argument('branch',choices=['dev','main']);parser.add_argument('lang',nargs='?',default='ko',choices=['ko','en'])
    args=parser.parse_args()
    print(json.dumps(request(args.project,args.branch,args.lang,args.repository),ensure_ascii=False) if args.request else analyze(args.project,args.branch,args.lang,args.repository))
