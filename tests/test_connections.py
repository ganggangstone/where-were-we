"""URL connections use temporary Git repositories and fake GitHub identity only."""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import mapcore
import project

class Connections(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.real_run=subprocess.run
        self.patcher=patch.object(mapcore,'ROOT',str(self.root/'data'));self.patcher.start();self.addCleanup(self.patcher.stop)
        self.source=self.root/'source';self.source.mkdir()
        def git(*args):return self.real_run(['git','-C',str(self.source),*args],check=True,capture_output=True,text=True).stdout.strip()
        self.git=git;git('init','-b','trunk');git('config','user.name','Example');git('config','user.email','example@example.invalid')
        (self.source/'README.md').write_text('Synthetic code');git('add','.');git('commit','-m','Initial')
        self.calls=[];self.denied=False;self.clone_failure=False
        def run(args,**kw):
            self.calls.append((args,kw));out=''
            if args[0]=='gh':
                if args[1:3]==['api','user']:out='alice'
                elif args[1:3]==['auth','token']:out='fake-secret'
                elif args[1:3]==['auth','status']:out='["alice","bob"]'
                elif self.denied:return subprocess.CompletedProcess(args,1,'','fake-secret')
                return subprocess.CompletedProcess(args,0,out,'')
            if args[:2]==['git','clone']:
                if self.clone_failure:return subprocess.CompletedProcess(args,1,'','fake-secret')
                result=self.real_run([*args[:-2],str(self.source),args[-1]],**kw)
                if not result.returncode:self.real_run(['git','-C',args[-1],'remote','set-url','origin',args[-2]],check=True)
                return result
            return self.real_run(args,**kw)
        self.runner=patch('subprocess.run',side_effect=run);self.runner.start();self.addCleanup(self.runner.stop)
    def entry(self,url='https://github.com/example/web'):
        return {'id':'web','name':'Web','url':url,'refs':{'dev':'origin/HEAD','main':None},'layout':{},'api_targets':[]}
    def test_url_forms_and_invalid_addresses(self):
        import connections
        for value in ('https://github.com/Example/Web.git','https://github.com/Example/Web/','git@github.com:Example/Web.git','Example/Web'):
            self.assertEqual(connections.parse_url(value),'https://github.com/example/web.git')
        for value in ('https://evil.test/a/b','https://token@github.com/a/b','https://github.com/a/b/tree/main','https://github.com/a/b?token=secret','../x','file:///tmp/a','--option'):
            with self.assertRaises(ValueError):connections.parse_url(value)
    def test_clone_identity_persist_and_reuse_without_touching_user_folder(self):
        value=project.configure('demo',{'repositories':[self.entry()]});repo=value['repositories'][0]
        self.assertTrue(Path(repo['path']).is_dir());self.assertTrue(repo['managed'])
        self.assertEqual(repo['github']['account'],'alice');self.assertEqual(repo['refs']['dev'],'origin/HEAD')
        self.assertEqual(self.real_run(['git','-C',repo['path'],'rev-parse','origin/HEAD'],capture_output=True,text=True).stdout.strip(),self.git('rev-parse','HEAD'))
        self.assertNotIn('fake-secret',json.dumps(value));self.assertFalse(any('switch' in args for args,kw in self.calls))
        project.configure('demo',value)
        self.assertEqual(sum(args[:2]==['git','clone'] for args,kw in self.calls),1)
        project.configure('demo',{'repositories':[{'id':'local','path':str(self.source),'refs':{'dev':'HEAD','main':None}}]})
        self.assertTrue(Path(repo['path']).exists());self.assertEqual((self.source/'README.md').read_text(),'Synthetic code')
        again=project.configure('demo',{'repositories':[self.entry()]})
        self.assertEqual(again['repositories'][0]['path'],repo['path'])
        self.assertEqual(sum(args[:2]==['git','clone'] for args,kw in self.calls),1)
    def test_duplicate_or_bad_settings_do_not_download(self):
        for entries in ([self.entry(),dict(self.entry('Example/Web.git'),id='other')],[dict(self.entry(),refs={'dev':'--bad'})]):
            with self.assertRaises(ValueError):project.configure('demo',{'repositories':entries})
        self.assertFalse(any(args[:2]==['git','clone'] for args,kw in self.calls))
    def test_access_and_clone_failure_preserve_previous_configuration_and_retry(self):
        project.configure('demo',{'repositories':[{'id':'local','path':str(self.source)}]})
        path=project.home('demo')/'project.json';before=path.read_bytes()
        self.denied=True
        with self.assertRaisesRegex(ValueError,'GITHUB_ACCESS'):project.configure('demo',{'repositories':[self.entry()]})
        self.assertEqual(path.read_bytes(),before);self.denied=False;self.clone_failure=True
        with self.assertRaises(ValueError) as error:project.configure('demo',{'repositories':[self.entry()]})
        self.assertNotIn('fake-secret',str(error.exception));self.assertEqual(path.read_bytes(),before)
        self.clone_failure=False;project.configure('demo',{'repositories':[self.entry()]})
        self.assertEqual(project.config('demo')['repositories'][0]['github']['account'],'alice')
    def test_unrelated_folder_cannot_be_claimed_as_managed(self):
        import connections
        item=self.entry();item['path']=str(self.source);item['managed']=True
        with self.assertRaises(ValueError):project.configure('demo',{'repositories':[item]})
        self.assertEqual((self.source/'README.md').read_text(),'Synthetic code')

    def test_first_map_next_refresh_default_branch_move_and_no_false_local_changes(self):
        import os
        value=project.configure('demo',{'repositories':[self.entry()]});repo=value['repositories'][0]
        tools=self.root/'bin';tools.mkdir()
        git=tools/'git';git.write_text('#!/usr/bin/python3\nimport os,sys\nos.execv("/usr/bin/git",["git"]+(["-c",'+repr('url.file://'+str(self.source)+'.insteadOf=https://github.com/example/web.git')+'] if "fetch" in sys.argv or "set-head" in sys.argv else [])+sys.argv[1:])\n');git.chmod(0o755)
        gh=tools/'gh';gh.write_text('#!/usr/bin/python3\nimport sys\na=sys.argv[1:]\nprint("alice" if a[:2]==["api","user"] else "fake-secret" if a[:2]==["auth","token"] else "{}" if a[:2]==["repo","view"] else "[]")\n');gh.chmod(0o755)
        # Parent GitHub calls are fake; the actual Python collector uses these two
        # local executables. Git transport is redirected to the temporary source.
        with patch.dict(os.environ,{'PATH':str(tools)+os.pathsep+os.environ['PATH'],'WHERE_WERE_WE_SETTINGS':str(self.root/'settings.json'),'PYTHONWARNINGS':'ignore::ResourceWarning'}):
            first=project.refresh_project('demo','web');self.assertNotIn('FAILED',first,first)
            bundle=project.read_bundle('demo','web');first_commit=bundle['dev']['commit']
            self.assertEqual(bundle['status']['worktrees'],[])
            self.assertFalse(bundle['status']['overlaps'])
            self.git('checkout','-b','next-default');(self.source/'README.md').write_text('Next synthetic code');self.git('add','.');self.git('commit','-m','Next')
            second=project.refresh_project('demo','web');self.assertNotIn('FAILED',second,second)
            bundle=project.read_bundle('demo','web');self.assertNotEqual(bundle['dev']['commit'],first_commit)
            self.assertTrue(self.git('rev-parse','HEAD').startswith(bundle['project']['repositories'][0]['commits']['dev']))
            self.assertEqual(bundle['status']['worktrees'],[])

    def test_real_browser_url_retry_first_collection_and_existing_connections_unchanged(self):
        import re
        chrome=Path('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome')
        if not chrome.exists():self.skipTest('Chrome is needed for the registration UI check')
        source=(Path(project.__file__).parent/'ui/index.html').read_text()
        script=source.split('<script>',1)[1].rsplit('</script>',1)[0].split("$('q').oninput",1)[0]
        bootstrap=r'''
const calls=[],saved=[],loads=[];let deny=true,refreshFail=false;
window.__TAURI__={core:{invoke:async(command,args)=>{
 calls.push({command,args});
 if(command==='save_project'){
  const config=JSON.parse(args.configuration);saved.push(config);
  if(deny)throw Error('GITHUB_ACCESS|github.com|alice|repository|'+config.repositories[1].id);
  return JSON.stringify(config);
 }
 if(command==='github_logins')return JSON.stringify({accounts:['alice','bob']});
 if(command==='refresh'){if(refreshFail)throw Error('Synthetic collection failure');return 'refreshed';}
 if(command==='list_projects')return ['demo'];
 throw Error('Unexpected command '+command);
}}};
'''
        checks=r'''
(async()=>{
 const assert=(value,message)=>{if(!value)throw Error(message);};
 loadProject=async(...args)=>loads.push(args);
 S.lang='en';S.project='demo';S.maps={};S.settings={open_refresh:true};
 S.projectInfo={repositories:[{id:'existing',name:'Existing',url:'https://github.com/example/old.git',managed:true,path:'/app/code/old',configured_path:'/app/code/old',collected:true,refs:{dev:'origin/trunk',main:null},layout:{frontend:null},api_targets:[],github:{host:'github.com',account:'alice'}}],shared_data:[]};
 const original=JSON.stringify(S.projectInfo);editProject(false);$('addRepository').click();
 const row=document.querySelector('[data-repository-row="1"]'),field=key=>row.querySelector(`[data-field="${key}"]`);
 field('path').value='https://github.com/example/new.git';field('path').dispatchEvent(new Event('change'));
 assert(field('name').value==='new','URL fills a readable name');
 assert(field('dev').value==='origin/HEAD','Default branch remains current on later refreshes');
 await $('saveProject').onclick();
 assert($('project-dialog').open,'Access failure keeps the editable form');
 assert($('projectName').disabled,'Existing project name stays disabled after a failure');
 assert(!$('saveProject').disabled,'Access failure allows a retry');
 const account=document.querySelector('[data-registration-login]');assert(account,'Choose an account only after failure');
 account.value='bob';account.dispatchEvent(new Event('change'));deny=false;
 await $('saveProject').onclick();
 assert(saved.at(-1).repositories[1].github.account==='bob','Retry uses selected identity');
 assert(saved.at(-1).repositories[0].refs.dev==='origin/trunk','Existing versions survive');
 assert(saved.at(-1).repositories[0].layout.frontend===null,'Explicit layout exclusion survives');
 const refreshes=calls.filter(c=>c.command==='refresh');
 assert(refreshes.length===1 && refreshes[0].args.repository===saved.at(-1).repositories[1].id,'First collection affects only new code');
 assert(loads.length===1 && loads[0][1]===false,'Opening the result must not trigger open-refresh');
 assert(JSON.stringify(S.projectInfo)===original,'Editing does not mutate current project state');
 assert(tr('GitHub 주소 또는 코드 폴더')==='GitHub URL or code folder','Real English translation');
 assert(document.body.textContent.includes('Reconnecting the same GitHub URL reuses'),'Retention explanation in English');
 // A collector process error after saving is visible and can be retried from Refresh.
 S.projectInfo={repositories:[],shared_data:[]};editProject(false);
 const fresh=document.querySelector('[data-field="path"]');fresh.value='example/again';fresh.dispatchEvent(new Event('change'));refreshFail=true;
 await $('saveProject').onclick();assert($('status').textContent.includes('Choose Refresh to retry'),'Collection failure is not hidden: '+$('status').textContent);
 S.lang='ko';editProject(true);assert(document.body.textContent.includes('GitHub 주소 또는 코드 폴더'),'Korean labels');
 document.body.dataset.urlTest='passed';
})().catch(error=>{document.body.dataset.urlTest='failed';const pre=document.createElement('pre');pre.textContent=error.stack;document.body.append(pre);});
'''
        page=re.sub(r'<script>.*?</script>',lambda m:'<script>'+bootstrap+script+checks+'</script>',source,count=1,flags=re.S)
        target=self.root/'url-check.html';target.write_text(page)
        result=self.real_run([str(chrome),'--headless','--disable-gpu','--no-first-run','--disable-background-networking','--disable-component-update','--no-default-browser-check','--user-data-dir='+str(self.root/'chrome'),'--virtual-time-budget=6000','--dump-dom',target.as_uri()],capture_output=True,text=True,timeout=30)
        self.assertTrue('data-url-test="passed"' in result.stdout,result.stdout[-2500:])
