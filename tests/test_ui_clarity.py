"""Presentation checks use fictional state in Chrome; native calls are blocked."""
import json,re,subprocess,tempfile,unittest
from pathlib import Path

class Clarity(unittest.TestCase):
 def test_results_actions_and_warnings_stay_visible_while_explanations_are_collapsed(self):
  chrome=Path('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome')
  if not chrome.exists():self.skipTest('Chrome is required')
  root=Path(__file__).resolve().parents[1];source=(root/'ui/index.html').read_text()
  script=source.split('<script>',1)[1].split('</script>',1)[0].split("$('q').oninput",1)[0]
  script+=source[source.index('function renderSettings() {'):source.index("$('settings').onclick")]
  script+=source[source.index('function renderAgentPrompt() {'):source.index("$('agent').onclick")]
  script+=(root/'ui/connection.js').read_text()
  bootstrap="window.__TAURI__={core:{invoke:async()=>{throw Error('Unexpected native action');}}};"
  checks=r'''
const assert=(v,m)=>{if(!v)throw Error(m);};
function visibleText(root){
 const walker=document.createTreeWalker(root,NodeFilter.SHOW_TEXT);let text='',node;
 while(node=walker.nextNode()){
  let hidden=false;
  for(let p=node.parentElement;p&&root.contains(p);p=p.parentElement){
   if(p.hidden){hidden=true;break;}
   if(p.tagName==='DETAILS'&&!p.open&&!p.querySelector(':scope > summary')?.contains(node)){hidden=true;break;}
  }
  if(!hidden)text+=node.textContent+' ';
 }
 return text;
}
try{
 S.project='Lumen';S.projectInfo={repositories:[{id:'worker',name:'Worker'}]};S.branch='dev';S.maps={};
 const warnings=[{repository:'legacy',code:'collection_limited',part:'merged_prs'},{repository:'legacy',code:'collection_limited',part:'pr_files'},{repository:'worker',code:'collection_limited',part:'issues'},{repository:'legacy',code:'collection_failed'}];
 const input=JSON.stringify(warnings),changes={entries:[]};S.changes=changes;S.chi=3;const settings=JSON.stringify(S.settings);
 for(const lang of ['ko','en']){
  S.lang=lang;S.briefings={dev:{[lang]:{state:'not_analyzed',warnings,result:null}}};
  const pane=$('insp');pane.innerHTML=briefingPanel();let text=visibleText(pane);
  assert(!text.includes('legacy'),'Internal legacy label must not be displayed');
  const limit=tr('일부 자료가 빠졌을 수 있어요.');assert(text.split(limit).length-1===2,'One limit warning per code connection, not per collection part');
  assert(text.includes('Lumen')&&text.includes('Worker'),'Connection display names must remain distinct');
  assert(text.includes(tr('수집에 실패했습니다. 다시 수집해 주세요.')),'An actionable collection failure remains visible');
  const rule=tr('같은 문제의 PR은 묶고, 다른 문제를 푼 PR은 나눠 설명합니다.');
  assert(!text.includes(rule),'Method explanation should be collapsed');
  const help=[...pane.querySelectorAll('details')].find(d=>d.textContent.includes(rule));assert(help&&!help.open,'Method details are still available');help.querySelector('summary').click();assert(visibleText(pane).includes(rule),'User can open the method details');
  assert(JSON.stringify(warnings)===input,'Presentation does not modify evidence warnings');
  const value={text:'Fictional saved explanation',unknown:false,evidence:[{quote:'Exact fictional evidence',source:'PR #42',url:'https://example.invalid/pull/42'}]};
  const card={title:'Fictional change',merge:'merged',prs:[{repository:'worker',number:42,url:'https://example.invalid/pull/42',branch:'feature/work',base:'main',issues:[]}],terms:[]};
  for(const key of ['problem','why','before','after','resolution','impact','recovery','remaining'])card[key]=value;
  card.remaining={text:'Fictional unresolved fact',unknown:true,evidence:[]};
  S.briefings.dev[lang]={state:'saved',warnings,result:{cards:[card],pr_count:1,branch:'dev',input:{repositories:[{id:'worker',since:'2026-10-01T00:00:00Z',at:'2026-10-21T00:00:00Z',refs:{dev:'feature/work'},commits:{from:'aaaa1111',to:'bbbb2222'}}]},unknown:[]}};
  pane.innerHTML=briefingPanel();text=visibleText(pane);
  assert(text.includes('Fictional unresolved fact'),'Unknown claim stays visible');
  assert(!text.includes('aaaa1111'),'Comparison provenance is collapsed');
  const coverage=[...pane.querySelectorAll('details')].find(d=>d.textContent.includes('aaaa1111'));assert(coverage&&!coverage.open,'Provenance remains available');coverage.querySelector('summary').click();assert(visibleText(pane).includes('aaaa1111'),'Provenance can be opened');
  assert(pane.querySelector('[data-url="https://example.invalid/pull/42"]'),'Original PR action retained');
  const ev=[...pane.querySelectorAll('details')].find(d=>d.textContent.includes('Exact fictional evidence'));assert(ev,'Exact evidence retained');ev.querySelector('summary').click();assert(visibleText(pane).includes('Exact fictional evidence'),'Evidence can be opened');

  S.agentPurpose='setup';S.agentPrompt='LONG SYNTHETIC MCP CONFIGURATION';renderAgentPrompt();
  assert(!visibleText(pane).includes(S.agentPrompt),'Setup instructions are collapsed until requested');assert($('cpAgent')&&!$('cpAgent').disabled,'Copy stays available');assert($('openConnectionDiagnostic'),'Diagnostics stays available');
  S.agentPurpose='analysis';S.analysisRequest={state:'prepared'};renderAgentPrompt();
  text=visibleText(pane);assert(text.includes(tr('1. 요청 복사'))&&text.includes(tr('3. 저장된 결과 확인')),'Chosen three-step actions stay visible');
  assert(!text.includes(tr('분석 결과만 읽습니다. 바뀐 것과 비교 기준은 유지됩니다.')),'Repeated policy text is collapsed');assert($('checkAnalysisResults'),'Result check remains available');
  renderSettings();assert(!visibleText($('settings-dialog')).includes(tr('각 레포의 Git 작성자 이메일로 커밋을 찾습니다.')),'Settings implementation detail is collapsed');assert($('sinceTime')&&$('saveSt'),'Comparison settings remain editable');
  editProject(true);assert(!visibleText($('project-dialog')).includes(tr('프로젝트는 서비스 하나를 뜻합니다. 웹 화면·서버·작업 프로그램의 코드가 나뉘어 있어도 여기에 함께 연결하세요.')),'Repeated project tutorial is collapsed');assert($('saveProject')&&$('addRepository'),'Registration actions remain available');$('project-dialog').close();
  S.agentPurpose='connection';S.connectionDiagnostic={feature:'detail',challenge:'synthetic',fresh_server:{state:'ready'},registration:{state:'not_inspected'},connection:{state:'not_verified'},app:{app_version:'test',python:'/synthetic/python3',server:'/synthetic/mcp_server.py'},handoff:'Synthetic repair'};
  renderConnectionDiagnostic();text=visibleText(pane);assert(!text.includes('/synthetic/mcp_server.py'),'Diagnostic paths are collapsed');assert(text.includes(connectionMessage('not_verified')),'Actual connection is not falsely verified');assert($('copyConnectionRequest')&&$('checkCurrentConnection'),'Recovery actions stay visible');
  S.connectionDiagnostic.fresh_server.state='missing_runtime';renderConnectionDiagnostic();assert(visibleText(pane).includes(connectionMessage('missing_runtime')),'A broken app runtime remains visible');assert($('copyConnectionRequest').disabled,'Broken runtime is not offered as a repair target');
 }
 assert(S.changes===changes&&S.chi===3&&JSON.stringify(S.settings)===settings,'Presentation keeps change history, selected comparison and settings');
 document.body.dataset.clarity='passed';
}catch(error){document.body.dataset.clarity='failed';const pre=document.createElement('pre');pre.textContent=error.stack;document.body.append(pre);}
'''
  with tempfile.TemporaryDirectory() as tmp:
   page=re.sub(r'<script>.*?</script>',lambda m:'<script>'+bootstrap+script+checks+'</script>',source,count=1,flags=re.S)
   page=re.sub(r'<script src="[^\"]+"></script>','',page);target=Path(tmp)/'clarity.html';target.write_text(page)
   syntax=subprocess.run(['/opt/homebrew/bin/node','--check'],input=bootstrap+script+checks,capture_output=True,text=True);self.assertEqual(syntax.returncode,0,syntax.stderr)
   result=subprocess.run([str(chrome),'--headless','--disable-gpu','--no-first-run','--disable-background-networking','--disable-component-update','--user-data-dir='+tmp+'/chrome','--virtual-time-budget=3000','--dump-dom',target.as_uri()],capture_output=True,text=True,timeout=30)
   self.assertTrue('data-clarity="passed"' in result.stdout,str(re.findall(r'<pre>(.*?)</pre>',result.stdout,re.S))[-1800:])

class NativeLayout(unittest.TestCase):
 def test_inspector_stays_beside_the_map_in_webkit_after_its_content_changes(self):
  # Chrome re-matches main:has(#insp…) but WebKit (the macOS app) kept the stale one-column layout.
  import shutil,sys
  if sys.platform!='darwin' or not shutil.which('swiftc'):self.skipTest('macOS WebKit and swiftc are required')
  root=Path(__file__).resolve().parents[1]
  with tempfile.TemporaryDirectory() as tmp:
   tmp=Path(tmp);page=tmp/'page.html';probe=tmp/'probe'
   links=''.join(f'<link rel="stylesheet" href="{(root/"ui"/n).as_uri()}">' for n in ('tokens.css','app.css'))
   page.write_text(f'<!doctype html><meta charset="utf-8">{links}<body><main><div id="map"></div><div id="insp"></div></main>')
   subprocess.run(['swiftc','-O',str(root/'tests/webkit_layout_probe.swift'),'-o',str(probe)],check=True,capture_output=True)
   rows=[json.loads(line) for line in subprocess.run([str(probe),str(page)],check=True,capture_output=True,text=True,timeout=60).stdout.split()]
  empty,content,hint,empty2,content2=rows
  for row in (content,content2):
   self.assertEqual(row['insp_y'],0,row);self.assertGreater(row['insp_x'],0,row);self.assertEqual(row['map_w']+row['insp_w'],1446,row)
  self.assertEqual(hint['insp_y'],0,hint);self.assertLess(hint['insp_w'],content['insp_w'],hint)
  for row in (empty,empty2):self.assertEqual((row['map_w'],row['insp_w']),(1446,0),row)
