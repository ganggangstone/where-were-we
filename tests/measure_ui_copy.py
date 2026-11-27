"""Counts visible hint/caption characters per default UI state (fictional data, headless Chrome).
Usage: measure_ui_copy.py [ui_dir] [--samples]   ui_dir defaults to the working tree ui/ (use `git archive HEAD ui` for the baseline)."""
import json,re,sys,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
from support import dump_dom,inline_assets
from test_ui_flows import BOOTSTRAP,ANALYZED

ROOT=Path(__file__).resolve().parents[1]
HINT='.s,.hint,.empty,.sub,.meta,.tx,p,.legend,.wn,.module-scope,.note,figcaption,[role=status]'
SKIP='.pill,.chip,.beta,button,h1,h2,h3,h4,summary,.mono,.unit-count'
BOARD=r"""window.unitBoard=(extra={})=>({repositories:[{repository:'web',units:[['route:/orders','route','/orders',3,'saved','new'],['route:/reports','route','/reports',6,'working',''],['folder:lib','folder','lib',9,'pending',''],['folder:tools','folder','tools',3,'failed','']],coverage:{tracked:20,in_units:15,indexed:15,excluded:{secret:1,binary:2},truncated:true}}],totals:{units:4,saved:1,working:1,pending:1,failed:1},calls:3,time_limit_seconds:3600,...extra});"""
COLLECT=r"""
const collect=()=>{const PROSE=window.__PROSE;
 const seen=[];const out=[];
 for(const el of document.querySelectorAll(PROSE?'body *':%r)){
  if(PROSE&&(el.children.length>0&&!/^(P|DIV|SPAN|LABEL)$/.test(el.tagName)))continue;
  const SK=PROSE?%r:%r;
  if(el.matches(SK)||el.closest(SK))continue;
  const chip=PROSE&&el.matches('.chip,.pill');
  if(!el.checkVisibility())continue;
  let hidden=false;for(let p=el.parentElement;p;p=p.parentElement){if(p.tagName==='DETAILS'&&!p.open){hidden=true;break;}if(p.tagName==='DIALOG'&&!p.open){hidden=true;break;}}
  if(hidden)continue;
  if(seen.some(s=>s.contains(el)))continue;
  let t;if(PROSE){const c=el.cloneNode(true);c.querySelectorAll(SK).forEach(n=>n.remove());t=c.textContent.replace(/\s+/g,' ').trim();}else t=(el.innerText??el.textContent).replace(/\s+/g,' ').trim();if(!t)continue;if(PROSE&&(chip?!/[가-힣]/.test(t):(t.length<4||el.querySelector('p,div'))))continue;
  seen.push(el);out.push(t);
 }
 return out;};
""" % (HINT,SKIP.replace('.pill,.chip,',''),SKIP)
STATES={
 'onboarding':("",'?empty=1',"await wait(200);"),
 'registered_before_refresh':("window.noMap=true;","","await loadProject('First');await wait(100);"),
 'basic_map':("","","await loadProject('First');S.view='map';render();await wait(100);"),
 'saved_ai_analysis':(ANALYZED,"","analyzeAll();await loadProject('First');S.view='sys';render();await wait(100);"),
 'changes_view':("","","await loadProject('First');S.view='changes';render();await wait(100);"),
 'analysis_panel':("","","await loadProject('First');S.view='map';render();openAnalysisPanel();await wait(300);"),
 'board_before_start':('window.appAnalysisFixture=true;'+BOARD,"","window.unitBoard=unitBoard();await loadProject('First');S.view='map';render();openAnalysisPanel();await wait(300);await AnalysisRun.check();await wait(200);"),
 'card_unexplained':('window.appAnalysisFixture=true;'+BOARD,"","window.unitBoard=unitBoard();await loadProject('First');S.view='map';render();openAnalysisPanel();await wait(300);await AnalysisRun.check();await wait(200);document.querySelector('[data-unit-open=\"2\"]').click();await wait(300);"),
 'card_saved':('window.appAnalysisFixture=true;'+BOARD,"","window.unitBoard=unitBoard();await loadProject('First');S.view='map';render();openAnalysisPanel();await wait(300);await AnalysisRun.check();await wait(200);document.querySelector('[data-unit-open=\"0\"]').click();await wait(300);"),
 'board_mid_run':('window.appAnalysisFixture=true;'+BOARD,"","window.unitBoard=unitBoard();window.runningAnalysis={id:'r',project:'First',repository:'',branch:'dev',lang:'ko',state:'running',tasks:[{task:'full'}],completed_tasks:[],current_task:{task:'full'},error:null,cancel_requested:false};await loadProject('First');S.view='map';render();openAnalysisPanel();await wait(300);await AnalysisRun.check();await wait(200);"),
 'project_dialog':("","","await loadProject('First');editProject(true);await wait(100);"),
 'settings_dialog':("","","await loadProject('First');$('settings').click();await wait(100);"),
 'board_finished':('window.appAnalysisFixture=true;'+BOARD,"","window.unitBoard=unitBoard({totals:{units:4,saved:4,working:0,pending:0,failed:0}});window.runningAnalysis={id:'r',project:'First',repository:'',branch:'dev',lang:'ko',state:'completed',tasks:[{task:'full'}],completed_tasks:[{task:'full'}],current_task:null,error:null,cancel_requested:false};await loadProject('First');S.view='map';render();openAnalysisPanel();await wait(300);await AnalysisRun.check();await wait(200);"),
}
PROSE=False
def run(ui,name,lang='ko'):
    pre,query,steps=STATES[name]
    if PROSE:pre='window.__PROSE=1;'+pre
    source=(ui/'index.html').read_text()
    html=inline_assets(source.replace('<script>','<script>'+BOOTSTRAP+pre,1),ui)
    check=r"""window.flowCheck=(async()=>{const wait=ms=>new Promise(r=>setTimeout(r,ms));for(let i=0;i<100&&!window.appControlReady;i++)await wait(20);"""+ANALYZED+COLLECT+"""
 try{"""+steps+"""const o=window.__DUMP?[document.body.innerText]:collect();const pre=document.createElement('pre');pre.id='out';pre.textContent=JSON.stringify(o);document.body.append(pre);}catch(e){const pre=document.createElement('pre');pre.id='out';pre.textContent='ERR '+e.stack;document.body.append(pre);}})();"""
    html=html.replace('</body>','<script>'+check+'</script></body>')
    with tempfile.TemporaryDirectory() as tmp:
        t=Path(tmp)/'m.html';t.write_text(html)
        r=dump_dom(t.as_uri()+'?lang='+lang+(query.replace('?','&')),tmp+'/c',budget=8000,window='1280,900',timeout=60)
    m=re.search(r'<pre id="out">(.*?)</pre>',r.stdout,re.S)
    if not m:return ['ERR no output']
    import html as h;s=h.unescape(m.group(1))
    return [s] if s.startswith('ERR') else json.loads(s)
if __name__=='__main__':
    args=[a for a in sys.argv[1:] if not a.startswith('--')]
    ui=Path(args[0]) if args else ROOT/'ui'
    PROSE='--prose' in sys.argv
    lang='en' if '--en' in sys.argv else 'ko'
    res={}
    for n in STATES:
        o=run(ui,n,lang)
        if lang=='en' and PROSE:
            ko=run(ui,n,'ko')
            res[n]=sum(len(re.findall('[A-Za-z]',x)) for x,k in zip(o,ko) if re.search('[가-힣]',re.sub(r'\d+월 \d+일','',k)))
        else:res[n]=sum(len(re.findall('[가-힣]',re.sub(r'\d+월 \d+일','',x))) if PROSE else len(x) for x in o)
        if '--samples' in sys.argv:print(n,json.dumps(o,ensure_ascii=False,indent=0))
    print(json.dumps(res,ensure_ascii=False))
