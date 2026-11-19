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
})().then(()=>window.uiSystemResult='[]').catch(e=>window.uiSystemResult=JSON.stringify([String(e)]));
"""
        source = (ROOT / 'ui/index.html').read_text().replace('<script>', '<script>' + BOOTSTRAP, 1)
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
