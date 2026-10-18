"""Change briefings use synthetic GitHub evidence; no model or network is called."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import mapcore
import project
import briefing
from test_multi_repo import sample

class Briefing(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.patch=patch.object(mapcore,'ROOT',str(self.root));self.patch.start();self.addCleanup(self.patch.stop)
        project.configure('demo',{'repositories':[{'id':rid,'path':'/demo/'+rid,'refs':{'dev':'HEAD','main':None}} for rid in ('web','api')]})
        self.heads=patch.object(briefing,'check_heads',return_value=None);self.heads.start();self.addCleanup(self.heads.stop)
        for rid in ('web','api'):
            self.publish(rid)
    def publish(self,rid,body='Previously retries created duplicate jobs. Now retries reuse the existing job.'):
        repo=next(r for r in project.config('demo')['repositories'] if r['id']==rid)
        pr={'number':7,'title':'Reuse job on retry','body':body,'url':f'https://github.com/example/{rid}/pull/7',
            'base':'main','branch':'fix/retry','merged_at':'2026-10-19T08:00:00+00:00','files':['jobs.py'],'issues':[]}
        status={'merged_prs':[pr],'issues':[],'linked_issues':[],'generated_at':'2026-10-19T09:00:00+00:00','collection':{'merged_prs':{'possibly_truncated':False}}}
        entry={'at':'2026-10-19T09:00:00+00:00','since':'2026-10-18T09:00:00+00:00','branches':{},'prs':[pr],'ai_stale':{}}
        evidence=briefing.freeze(status,entry,{'dev':'b'*40},{'dev':'a'*40})
        raw={'dev':sample('/demo/'+rid,'b'*40),'status':status,'changes':{'last_refresh':entry['at'],'entries':[entry],
             'last_result':{'at':entry['at'],'since':entry['since'],'changed':True,'scope':'basic','evidence':evidence}}}
        project.publish('demo',rid,raw,{'fingerprint':project.fingerprint(repo)})
    def request(self,repository=''):
        return briefing.request('demo',repository,'dev','en')
    def response(self,request):
        prs=request['input']['prs'];source=prs[0]['body_source']
        claim=lambda text:{'text':text,'evidence':[{'source':source,'quote':'retries reuse the existing job'}],'unknown':False}
        unknown={'text':'Not established from the collected evidence.','evidence':[],'unknown':True}
        card={'id':'retry','title':'Retries keep one job','prs':[p['id'] for p in prs],
              'problem':claim('Retry could create another job.'),'why':claim('Avoid duplicate work.'),
              'before':claim('Retry created another job.'),'after':claim('Retry reuses the job.'),
              'resolution':claim('Reuse the existing job.'),'impact':unknown,'recovery':unknown,'remaining':unknown,
              'terms':[],'priority':'high'}
        return {'cards':[card],'unknown':['Runtime behavior has not been verified.']}
    def record(self,request,data=None):
        return briefing.record(**request['record_arguments'],result_json=json.dumps(data or self.response(request)))
    def test_freezes_bodies_and_qualifies_equal_pr_numbers_without_mutating_changes(self):
        before=copy.deepcopy(project.read_bundle('demo')['changes'])
        request=self.request();self.assertEqual(len(request['input']['prs']),2)
        self.assertEqual(len({p['id'] for p in request['input']['prs']}),2)
        self.assertIn('record_briefing',request['handoff']);self.assertIn('Do not call refresh',request['handoff'])
        p=request['input']['prs'][0]
        source=briefing.source(**request['source_arguments'],source_id=p['body_source'])
        self.assertIn('Previously retries',source['text'])
        self.record(request)
        view=briefing.view('demo','','dev','en')
        self.assertEqual(view['state'],'saved');self.assertEqual(view['result']['pr_count'],2)
        self.assertEqual(view['result']['cards'][0]['deployment'],'not_verified')
        self.assertEqual(project.read_bundle('demo')['changes'],before)
    def test_one_problem_can_group_prs_and_one_pr_can_appear_on_multiple_cards(self):
        request=self.request();data=self.response(request)
        extra=copy.deepcopy(data['cards'][0]);extra.update(id='recovery',title='Recovery behavior')
        data['cards'].append(extra);self.record(request,data)
        result=briefing.view('demo','','dev','en')['result']
        self.assertEqual(len(result['cards']),2);self.assertEqual(result['pr_count'],2)
    def test_invalid_quote_or_missing_pr_preserves_last_success(self):
        first=self.request();self.record(first)
        before=(self.root/'demo/briefing.json').read_bytes()
        for kind in ('quote','missing','invented'):
            request=self.request();bad=self.response(request)
            if kind=='quote':bad['cards'][0]['after']['evidence'][0]['quote']='not in any original source'
            elif kind=='missing':bad['cards'][0]['prs']=bad['cards'][0]['prs'][:1]
            else:bad['cards'][0]['prs']=['web:pr:999']
            with self.assertRaises(ValueError):self.record(request,bad)
            self.assertEqual((self.root/'demo/briefing.json').read_bytes(),before)
    def test_refresh_or_settings_or_newer_result_rejects_late_record(self):
        request=self.request();self.record(request)
        with self.assertRaises(ValueError):self.record(request)
        request=self.request();self.publish('web','Updated description changes the frozen evidence.')
        with self.assertRaises(ValueError):self.record(request)
        self.assertEqual(briefing.view('demo','','dev','en')['state'],'stale')
        request=self.request();mapcore.save_settings({'since':'time','since_time':'2026-10-01T18:30','open_refresh':False})
        with self.assertRaises(ValueError):self.record(request)
    def test_partial_failure_is_visible_and_preserves_previous_briefing(self):
        self.record(self.request());project.failed('demo','api','Synthetic access failure')
        view=briefing.view('demo','','dev','en');self.assertEqual(view['state'],'stale')
        self.assertTrue(view['input']['repositories'][1]['error'])
        self.assertTrue(view['result']['cards'])
        self.record(self.request())
        view=briefing.view('demo','','dev','en')
        self.assertEqual(view['state'],'saved');self.assertTrue(view['warnings'])
    def test_missing_legacy_evidence_needs_collection_not_no_changes(self):
        repo=project.config('demo')['repositories'][0]
        project.publish('demo','web',{'dev':sample('/demo/web')},{'fingerprint':project.fingerprint(repo)})
        view=briefing.view('demo','web','dev','en')
        self.assertEqual(view['state'],'needs_collection')
        with self.assertRaises(ValueError):self.request('web')
    def test_collection_limit_and_missing_body_are_explicit(self):
        self.publish('web','')
        request=self.request('web');data=self.response(request)
        with self.assertRaises(ValueError):self.record(request,data)
        self.assertTrue(request['input']['warnings'])
    def test_saved_scope_and_languages_are_separate(self):
        self.record(self.request('web'))
        self.assertIsNone(briefing.view('demo','api','dev','en')['result'])
        self.assertIsNone(briefing.view('demo','web','dev','ko')['result'])

    def test_legacy_project_keeps_comparison_files_unchanged(self):
        repo=project.config('demo')['repositories'][0]
        raw=project.raw_bundle(project.repository_folder('demo',repo,project.states('demo')))
        for field,value in raw.items():
            if value is not None:project.atomic(self.root/'legacy'/(field+'.json'),value)
        changes=(self.root/'legacy/changes.json').read_bytes()
        request=briefing.request('legacy',lang='en')
        self.record(request)
        view=briefing.view('legacy',lang='en')
        self.assertEqual(view['state'],'saved')
        self.assertEqual(view['result']['cards'][0]['prs'][0]['repository'],'legacy')
        self.assertEqual((self.root/'legacy/changes.json').read_bytes(),changes)

    def test_linked_issue_failure_is_visible_per_source(self):
        repo=project.config('demo')['repositories'][0]
        raw=project.raw_bundle(project.repository_folder('demo',repo,project.states('demo')))
        raw['changes']['last_result']['evidence']['issues']=[{'number':9,'title':'Retry bug','url':'https://github.com/example/web/issues/9','body':'','unavailable':True}]
        project.publish('demo','web',raw,{'fingerprint':project.fingerprint(repo)})
        request=self.request('web')
        self.assertEqual(request['input']['warnings'][0]['code'],'issue_unavailable')
        sid=next(s['id'] for s in request['input']['sources'] if s.get('unavailable'))
        source=briefing.source(**request['source_arguments'],source_id=sid)
        self.assertTrue(source.get('unavailable'))

    def test_actual_head_check_rejects_changed_code_at_request_and_record(self):
        import subprocess
        self.record(self.request('web'))
        before=(self.root/'demo/briefing.json').read_bytes()
        request=self.request('web')
        self.heads.stop()
        real_run=subprocess.run
        def git(command,**kwargs):
            if command[0]=='git' and 'rev-parse' in command:
                return subprocess.CompletedProcess(command,0,'c'*40+'\n','')
            return real_run(command,**kwargs)
        with patch('subprocess.run',side_effect=git):
            with self.assertRaisesRegex(ValueError,'Code version changed'):self.request('web')
            with self.assertRaisesRegex(ValueError,'Code version changed'):self.record(request)
        self.assertEqual((self.root/'demo/briefing.json').read_bytes(),before)

    def test_source_pagination_and_changed_input_are_checked(self):
        request=self.request('web');sid=request['input']['prs'][0]['body_source']
        page=briefing.source(**request['source_arguments'],source_id=sid,limit=10)
        self.assertEqual(page['next'],10)
        self.assertEqual(page['text'],'Previously')
        self.publish('web','A newer collected body.')
        with self.assertRaises(ValueError):briefing.source(**request['source_arguments'],source_id=sid)

    def test_window_edges_and_collection_limit(self):
        start='2026-10-18T09:00:00+00:00';end='2026-10-19T09:00:00+00:00'
        status={'merged_prs':[{'number':i,'merged_at':at} for i,at in [(1,start),(2,end),(3,'2026-10-19T09:00:01+00:00')]]}
        value=briefing.freeze(status,{'since':start,'at':end}, {},{})
        self.assertEqual([p['number'] for p in value['prs']],[2])
        repo=project.config('demo')['repositories'][0]
        raw=project.raw_bundle(project.repository_folder('demo',repo,project.states('demo')))
        raw['changes']['last_result']['evidence']['collection']['merged_prs']['possibly_truncated']=True
        project.publish('demo','web',raw,{'fingerprint':project.fingerprint(repo)})
        self.assertTrue(any(w['code']=='collection_limited' for w in self.request('web')['input']['warnings']))

    def test_changed_comparison_policy_requires_collection_before_new_request(self):
        mapcore.save_settings({'since':'time','since_time':'2026-10-01T18:30','open_refresh':False})
        with self.assertRaisesRegex(ValueError,'comparison settings'):self.request()
        self.assertTrue(any(w['code']=='comparison_changed' for w in briefing.view('demo')['warnings']))

    def test_no_changes_and_direct_code_changes_are_distinct(self):
        for rid in ('web','api'):
            repo=next(r for r in project.config('demo')['repositories'] if r['id']==rid)
            raw=project.raw_bundle(project.repository_folder('demo',repo,project.states('demo')))
            result=raw['changes']['last_result'];result['changed']=False
            result['evidence']['prs']=[];result['evidence']['commits']['dev']['from']='b'*40
            project.publish('demo',rid,raw,{'fingerprint':project.fingerprint(repo)})
        self.assertEqual(briefing.view('demo',lang='en')['state'],'no_changes')
        repo=project.config('demo')['repositories'][0]
        raw=project.raw_bundle(project.repository_folder('demo',repo,project.states('demo')))
        raw['changes']['last_result']['evidence']['commits']['dev']['from']='a'*40
        project.publish('demo','web',raw,{'fingerprint':project.fingerprint(repo)})
        self.assertEqual(briefing.view('demo',lang='en')['state'],'not_analyzed')

    def test_mcp_request_source_record_and_read_use_the_same_contract(self):
        import mcp_server
        request=json.loads(mcp_server.request_briefing('demo','web','dev','en'))
        sid=request['input']['prs'][0]['body_source']
        page=json.loads(mcp_server.briefing_source(**request['source_arguments'],source_id=sid))
        self.assertIn('Previously retries',page['text'])
        mcp_server.record_briefing(**request['record_arguments'],result_json=json.dumps(self.response(request)))
        self.assertEqual(json.loads(mcp_server.change_briefing('demo','web','dev','en'))['state'],'saved')

    def test_real_browser_shows_cards_and_confirms_results_without_collection(self):
        import subprocess
        chrome=Path('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome')
        if not chrome.is_file():self.skipTest('Chrome is required for the real briefing UI check')
        request=self.request()
        before=project.read_bundle('demo')
        data=self.response(request);data['cards'][0]['title']='Retries <img data-injected src=x onerror="document.body.dataset.injected=1">'
        data['cards'][0]['terms']=[{'term':'<img data-injected src=x onerror="document.body.dataset.injected=1">','explanation':data['cards'][0]['impact']}]
        self.record(request,data);after=project.read_bundle('demo')
        ko_request=briefing.request('demo','','dev','ko')
        briefing.record(**ko_request['record_arguments'],result_json=json.dumps(self.response(ko_request)))
        korean=project.read_bundle('demo')
        source=(Path(project.__file__).parent/'ui/index.html').read_text()
        script=source.split('<script>',1)[1].split('</script>',1)[0].split("$('q').oninput",1)[0]
        script+=source[source.index('function renderAgentPrompt() {'):source.index("$('agent').onclick")]
        fixtures=json.dumps({'request':request,'before':before,'after':after,'korean':korean}).replace('</','<\\/')
        bootstrap='const fixtures='+fixtures+r''';
let saved=fixtures.before;const calls=[];
window.__TAURI__={core:{invoke:async(command,args)=>{
 calls.push(command);
 if(command==='briefing_request')return JSON.stringify(fixtures.request);
 if(command==='read_project')return JSON.stringify(saved);
 if(command==='open_url')return '';
 throw Error('Unexpected backend operation: '+command);
}}};
'''
        checks=r'''
(async()=>{
 const assert=(condition,message)=>{if(!condition)throw Error(message);};
 S.project='demo';S.repository='';S.desiredProject='demo';S.desiredRepository='';S.branch='dev';S.lang='en';S.view='changes';
 S.projectInfo=fixtures.before.project;S.briefings=fixtures.before.briefings;
 S.maps={dev:fixtures.before.dev,main:fixtures.before.main};S.branchDetails=fixtures.before.branch_details;
 S.changes={entries:[],last_refresh:'2026-10-19T09:00:00+00:00'};S.chi=3;
 const changes=S.changes,settings=S.settings;
 render();
 assert($('requestBriefing') && !$('requestBriefing').disabled,'A collected project can request a briefing for all repositories');
 assert(tr('같은 문제의 PR은 묶고, 다른 문제를 푼 PR은 나눠 설명합니다.').includes('distinct problems'),'New copy must not be overridden by an old translation key');
 Object.defineProperty(navigator,'clipboard',{value:{writeText:async()=>{}},configurable:true});
 await $('requestBriefing').onclick();
 assert(S.analysisRequest.command==='briefing_request' && S.analysisRequest.scope.repository==='','Keep project-wide scope');
 await $('cpAgent').onclick();
 assert(S.analysisRequest.state==='prepared','Copying is not analysis completion');
 await $('checkAnalysisResults').onclick();
 assert(S.analysisRequest.state==='missing','No recorded cards is not completion');
 saved=fixtures.after;
 await $('checkAnalysisResults').onclick();
 assert(S.analysisRequest.state==='saved','Only a recorded result completes the request');
 assert(S.changes===changes && S.settings===settings && S.chi===3,'Preserve changes and the comparison baseline');
 $('viewAnalysisResults').click();
 assert(S.view==='changes' && $('map').textContent.includes('Distinct PRs 2'),'Cards and PRs are counted independently');
 assert($('map').textContent.includes('Before') && $('map').textContent.includes('Data impact'),'Show the before/after and impact fields');
 assert($('map').textContent.includes('Deployment and runtime behavior not verified'),'Do not turn merged PRs into deployment confirmation');
 assert(!document.querySelector('[data-injected]') && !document.body.dataset.injected,'Escape generated descriptions');
 const sourceButton=$('map').querySelector('[data-url]');sourceButton.click();
 assert(calls.includes('open_url'),'Original evidence links remain available');
 S.briefings=fixtures.korean.briefings;S.lang='ko';render();
 assert($('map').textContent.includes('변경 설명') && $('map').textContent.includes('바뀌기 전'),'The same card layout is localized');
 assert(!calls.includes('refresh'),'Generating and confirming explanations must not collect or move the comparison window');
 document.body.dataset.briefingTest='passed';
})().catch(error=>{document.body.dataset.briefingTest='failed';const pre=document.createElement('pre');pre.textContent=error.stack;document.body.append(pre);});
'''
        page=source.split('<script>',1)[0]+'<script>'+bootstrap+script+checks+'</script></body></html>'
        for name in ('tokens.css','app.css'):page=page.replace('href="'+name+'"','href="'+(Path(project.__file__).parent/'ui'/name).as_uri()+'"')
        target=self.root/'briefing-check.html';target.write_text(page)
        result=subprocess.run([str(chrome),'--headless','--disable-gpu','--no-first-run','--disable-background-networking','--disable-component-update',
            '--user-data-dir='+str(self.root/'chrome'),'--virtual-time-budget=1000','--dump-dom',target.as_uri()],capture_output=True,text=True,timeout=40)
        self.assertEqual(result.returncode,0,result.stderr[-1000:])
        self.assertTrue('data-briefing-test="passed"' in result.stdout,result.stdout[-2000:])

    def test_isolated_cli_and_standard_mcp_protocol_with_actual_synthetic_git(self):
        import asyncio,os,subprocess
        from mcp import ClientSession,StdioServerParameters
        from mcp.client.stdio import stdio_client
        code=self.root/'code';code.mkdir()
        def git(*args):return subprocess.run(['git','-C',str(code),*args],check=True,capture_output=True,text=True).stdout.strip()
        git('init','-q');git('config','user.name','Demo');git('config','user.email','demo@example.invalid')
        (code/'jobs.py').write_text('def retry():\n    return existing_job\n')
        git('add','.');git('commit','-qm','Synthetic code');commit=git('rev-parse','HEAD')
        conf=project.configure('protocol',{'repositories':[{'id':'code','path':str(code),'refs':{'dev':'HEAD','main':None}}]})
        original=project.config('demo')['repositories'][0]
        raw=project.raw_bundle(project.repository_folder('demo',original,project.states('demo')))
        raw['dev']['repo']=str(code);raw['dev']['commit']=commit
        raw['changes']['last_result']['evidence']['commits']['dev']['to']=commit
        project.publish('protocol','code',raw,{'fingerprint':project.fingerprint(conf['repositories'][0])})
        before=copy.deepcopy(project.read_bundle('protocol')['changes'])
        base=Path(project.__file__).parent
        env=dict(os.environ,WHERE_WERE_WE_ROOT=str(self.root),PATH='/usr/bin:/bin')
        result=subprocess.run([sys.executable,'-I','-B',str(base/'briefing.py'),'request','protocol','--branch','dev','--lang','en'],env=env,capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('record_briefing',json.loads(result.stdout)['handoff'])
        async def exercise():
            params=StdioServerParameters(command=sys.executable,args=['-I','-B',str(base/'mcp_server.py')],env=env,cwd=str(self.root))
            async with stdio_client(params) as streams:
                async with ClientSession(*streams) as session:
                    await session.initialize()
                    names={tool.name for tool in (await session.list_tools()).tools}
                    self.assertTrue({'request_briefing','briefing_source','record_briefing','change_briefing'}<=names)
                    reply=await session.call_tool('request_briefing',{'project':'protocol','branch':'dev','lang':'en'})
                    self.assertFalse(reply.is_error,reply.content)
                    request=json.loads(reply.content[0].text)
                    reply=await session.call_tool('briefing_source',{**request['source_arguments'],'source_id':request['input']['prs'][0]['body_source']})
                    self.assertFalse(reply.is_error);self.assertIn('retries reuse',reply.content[0].text)
                    reply=await session.call_tool('record_briefing',{**request['record_arguments'],'result_json':json.dumps(self.response(request))})
                    self.assertFalse(reply.is_error,reply.content)
                    reply=await session.call_tool('change_briefing',{'project':'protocol','branch':'dev','lang':'en'})
                    self.assertFalse(reply.is_error)
                    self.assertEqual(json.loads(reply.content[0].text)['state'],'saved')
        asyncio.run(exercise())
        self.assertEqual(project.read_bundle('protocol')['changes'],before)
