"""Exercise stored and fresh maps with a detached WebKit view and fake native calls."""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from test_ui_flows import BOOTSTRAP, ROOT


@unittest.skipUnless(sys.platform == 'darwin' and shutil.which('swiftc'), 'Requires Swift and WebKit')
class RefreshFirstWebKit(unittest.TestCase):
    def test_local_first_and_optional_evidenced_ai(self):
        checks = r"""
(async()=>{
 const check=(value,why)=>{if(!value)throw Error(why)};
 for(let i=0;i<100&&!window.appControlReady;i++)await new Promise(r=>setTimeout(r,20));
 const pin='aaaaaaaa1111', file='worker.cjs';
 const index={repository:'web',commit:pin,version:11,coverage:{indexed_files:1,candidate_files:1,languages:{javascript:{indexed_files:1,candidate_files:1}}},
   files:[{file,language:'javascript',declarations:[{kind:'function',name:'work',line:1}]}],imports:[],
   service_flow:{connections:[],coverage:{requests:0,routes:0},feature_groups:[]}};
 window.mutateBundle=b=>{b.dev.structure_indexes=[index];b.project.repositories[0].fingerprint='pin'};
 await doRefresh();
 check(S.view==='sys' && $('map').innerText.includes('work'),'A CLI refresh must open local declarations');
 check(!$('map').querySelector('[data-http-flow]') && !$('automaticAnalysis'),'Empty HTTP graph and optional AI stay hidden');
 check(!calls.some(c=>['analysis_run_start','analysis_plan','analysis_providers'].includes(c.command)),'Refresh must not prepare AI');
 S.project=null;S.view='changes';await loadProject('First');
 check(S.view==='sys' && $('map').innerText.includes('worker.cjs'),'Opening a saved local map shows its structure');
 index.files=Array.from({length:160},(_,i)=>({file:'module'+i+'.cjs',language:'javascript',declarations:[]}));
 index.imports=[{file:'module0.cjs',target:'module150.cjs',line:1},{file:'module45.cjs',target:'module150.cjs',line:3}];
 index.commit='bbbbbbbb2222';await doRefresh();
 check($('moduleFile').value==='module150.cjs' && $('moduleFile').options.length<=64,'Large maps open a highly referenced module with a bounded picker');
 $('moduleRange').selectedIndex=0;$('moduleRange').dispatchEvent(new Event('change'));
 check($('moduleFile').value==='module0.cjs','Other ranges remain reachable');
 $('map').querySelector('[data-module-neighbor]').click();
 check($('moduleFile').value==='module150.cjs' && $('moduleRange').selectedIndex===2,'Import navigation crosses ranges without losing the destination');
 index.commit=pin;
 index.cli_entries=[{command:'alpha',kind:'python_script',file:'pyproject.toml',line:8,target:'tool/cli.py',symbol:'main',target_line:14},
    ...Array.from({length:12},(_,i)=>({command:'tool-'+i,kind:'npm_bin',file:'package.json',target:'bin/tool.js'}))];
 await doRefresh();
 const cli=()=>$('map').querySelector('[data-cli-entries]');
 check(cli().querySelectorAll('details').length===12 && !$('moduleDetails').open,'CLI commands precede module internals');
 const firstCommand=cli().querySelector('details');firstCommand.querySelector('summary').click();
 check(firstCommand.innerText.includes('pyproject.toml:8') && firstCommand.innerText.includes('tool/cli.py:14') && firstCommand.innerText.includes('main'),'Python command shows actual registration and callable');
 cli().querySelector('[data-cli-page="1"]').click();const npm=cli().querySelector('details');npm.querySelector('summary').click();
 check(npm.innerText.includes('tool-11') && npm.querySelectorAll('a')[1].dataset.url.endsWith('/bin/tool.js') && !npm.innerText.includes('undefined'),'Missing locations remain file-only');
 check(!calls.some(c=>c.command==='analysis_run_start'),'Command inspection has no model call');
 index.cli_entries=[];
 const client={file:'client.js',line:5,quote:'fetch("/items")'},server={file:'api.py',line:9,quote:'@router.get("/items")',function:'items'};
 const edge={id:1,method:'GET',path:'/items',client,server,data_steps:[{operation:'read',model:'Item',file:'api.py',line:11,evidence:[]}]};
 index.service_flow={connections:[edge],feature_groups:[{resource:'/items',connection_indexes:[0]}],coverage:{requests:1,routes:1,unresolved_requests:0}};
 await doRefresh();check($('map').querySelector('[data-local-resource]'),'Local resource groups appear first');
 window.runningAnalysis={id:'saved',state:'completed',project:'First',repository:'',branch:'dev',lang:S.lang,intent:{task:'overview',targets:[]},completed_tasks:[],tasks:[],saved_overviews:[{
  repository:'web',configuration:'pin',commit:pin,format:'overview-v1',files:[client.file,server.file],
  items:[{name:'Browse',description:'Read stored items.',...client}],connections:[edge],feature_groups:[{name:'Saved items',connection_ids:[1]}]}]};
 Object.defineProperty(document,'hidden',{configurable:true,value:false});
 S.agentPurpose='analysis';S.agentPrompt='';renderAgentPrompt();await AnalysisRun.check();
 check(!$('automaticAnalysis').open && $('insp').innerText.includes('Saved items'),'Optional saved group appears without opening AI controls');
 const button=$('insp').querySelector('[data-overview-feature]');button.click();
 const storage=$('insp').querySelector('[data-flow-storage] details');check(storage,'Opening the saved feature shows its model step');
 storage.querySelector('summary').click();check(storage.open && storage.innerText.includes('api.py:11'),'Model citation remains discoverable');
 check(!calls.some(c=>c.command==='analysis_run_start'),'Viewing saved evidence starts no AI');
 S.agentPrompt=null;
 const paths=['src/nested/<example name>.go','src/nested/worker.ts',...Array.from({length:80},(_,i)=>'src/item'+String(i).padStart(2,'0')+'.go')];
 window.mutateBundle=b=>{b.dev.structure_indexes=[{...index,files:[],imports:[],service_flow:null}];b.dev.inventories=[{repository:'web',commit:pin,files:82,paths,paths_truncated:true,directories:[['src',82]]}]};
 await doRefresh();
 const box=()=>$('map').querySelector('[data-inventory]');
 check(box().open && box().innerText.includes(pin) && box().innerText.includes(tr('파일 경로 표시 한도 도달')),'Unsupported repositories open a pinned, explicitly partial path inventory');
 box().querySelector('[data-inventory-dir="src"]').click();
 check(box().querySelectorAll('li').length===40 && !box().innerText.includes('item79.go'),'Directory pages have a bounded DOM');
 box().querySelector('[data-inventory-page="1"]').click();box().querySelector('[data-inventory-page="2"]').click();
 check(box().innerText.includes('item79.go'),'Final partial page is reachable');
 box().querySelector('[data-inventory-page="1"]').click();box().querySelector('[data-inventory-page="0"]').click();
 box().querySelector('[data-inventory-dir="src/nested"]').click();
 const fileLink=box().querySelector('[data-inventory-file]');check(fileLink.textContent==='<example name>.go','Paths remain text');
 fileLink.click();check(calls.at(-1).command==='open_url' && calls.at(-1).args.url==='zed://file/fictional/web/src/nested/%3Cexample%20name%3E.go','Editor opens the qualified working file without inventing a line');
 const inspect=path=>box().querySelector('[data-inspect-path="'+path+'"]').click();
 inspect('src/nested/<example name>.go');await new Promise(r=>setTimeout(r,10));check(box().innerText.includes(tr('지원하지 않는 파일 형식')),'Unsupported paths do not invent declarations');
 inspect('src/nested/worker.ts');await new Promise(r=>setTimeout(r,10));
 const args=calls.filter(c=>c.command==='file_structure').at(-1).args;
 check(args.commit===pin && args.repository==='web' && args.file==='src/nested/worker.ts','Detail reads only the selected file and full commit');
 check(box().innerText.includes('doWork0') && box().innerText.includes(tr('대상 미확인 import')) && box().innerText.includes(tr('분석 한도 도달')),'Declarations and coverage limits appear together');
 box().querySelector('[data-structure-page="1"]').click();
 check(box().innerText.includes('import → utility.ts') && box().innerText.includes('src/nested/worker.ts:33'),'Bounded paging retains outgoing import evidence');
 box().querySelector('[data-inventory-dir="src"]').click();check(box().querySelector('[data-inventory-dir="src/nested"]'),'Parent navigation is reversible');
})().then(()=>window.uiSystemResult='[]').catch(e=>window.uiSystemResult=JSON.stringify([String(e)]));
"""
        fake_file = r'''
const originalNative=window.__TAURI__.core.invoke;
window.__TAURI__.core.invoke=async(command,args)=>{
 if(command!=='file_structure')return originalNative(command,args);
 calls.push({command,args});
 return JSON.stringify({...args,status:args.file.endsWith('.go')?'unsupported':'indexed',language:'typescript',
   declarations:Array.from({length:21},(_,i)=>({name:'doWork'+i,kind:'function',line:i+1})),imports:[{target:'utility.ts',line:33}],
   coverage:{indexed_files:1,unresolved_imports:1,truncated:true}});
};
'''
        source = (ROOT / 'ui/index.html').read_text().replace('<script>', '<script>' + BOOTSTRAP + fake_file, 1)
        for name in ('tokens.css', 'app.css', 'vendor/dagre.min.js', 'connection.js', 'onboarding.js', 'control.js', 'analysis-run.js'):
            source = source.replace(f'"{name}"', f'"{(ROOT / "ui" / name).as_uri()}"')
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            page = folder / 'flow.html'
            page.write_text(source.replace('</body>', '<script>' + checks + '</script></body>'))
            probe = folder / 'probe'
            subprocess.run(['swiftc', str(ROOT / 'tests/webkit_style_probe.swift'), '-o', str(probe)], check=True, capture_output=True)
            result = subprocess.run([str(probe), str(page), '1280'], check=True, capture_output=True, text=True, timeout=30)
            self.assertEqual(json.loads(result.stdout), [])
