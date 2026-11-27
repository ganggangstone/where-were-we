"""Computed shared UI contracts, using fictional content and both app engines."""
import support  # blocks real AI CLIs; drops an inherited WHERE_WERE_WE_SETTINGS
from support import CHROME,compiled_probe,dump_dom
import json, subprocess, tempfile, unittest, re, sys, shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
CHECKS=r'''
const errors=[];const check=(v,m)=>{if(!v)errors.push(m)};
const style=s=>getComputedStyle(document.querySelector(s));
const bounds=s=>document.querySelector(s).getBoundingClientRect();
check(style('button.pill').borderBottomStyle==='none','Action chip retains native bevel');
check(style('#agent').borderTopStyle==='none','Menu inherits toolbar border');
check(style('h3').fontWeight==='600' && style('h4').fontWeight==='600','Headings retain UA bold');
check(style('.s').fontSize==='12px','Metadata has no shared secondary role');
check(style('dialog').borderTopWidth==='1px','Dialog retains native thick border');
check(bounds('.group > details > summary').left>bounds('.group').left+4,'Disclosure meets clipped rounded edge');
check(style('.repository-detail > summary').marginTop==='0px','Inline disclosure has prose margin');
const long='FictionalRepositoryWithAnIntentionallyLongUnbrokenName'.repeat(4);
document.querySelector('button.pill').textContent=long;document.querySelector('h3').textContent=long;
for(const zoom of [1,1.5]){
 document.body.style.zoom=zoom;
 check(document.documentElement.scrollWidth<=innerWidth+1,'Window overflow at zoom '+zoom);
 check(bounds('#insp').y===bounds('#map').y && bounds('#map').width>0,'Inspector stacked/lost map');
 for(const sel of ['button.pill','h3']){const e=document.querySelector(sel);check(e.scrollWidth<=e.clientWidth+1,'Clipped long content '+sel+' zoom '+zoom);}
}
document.body.style.zoom='';
check(style('#unitBody').color!==style('.unit-card .unit-state').color,'A saved unit card colours its body, not only its state mark');
check(new Set([...document.querySelectorAll('.step-lanes span')].map(e=>getComputedStyle(e).color)).size===1,'Lane legend labels differ in colour');
const lanes=[...document.querySelectorAll('.step-lanes span')].map(e=>{const r=document.createRange();r.selectNodeContents(e);const t=r.getBoundingClientRect(),box=e.getBoundingClientRect();return {left:box.left,right:t.right,top:box.top,height:box.height};}),gaps=lanes.slice(1).map((r,i)=>Math.abs(r.top-lanes[i].top)<1?Math.round(r.left-lanes[i].right):null).filter(g=>g!==null);
// A narrow panel may put a label on the next row (flex-wrap); a label itself never wraps under its dot.
check(lanes.every(r=>Math.abs(r.height-lanes[0].height)<1),'Lane legend label wraps under its dot');
check(gaps.every(g=>Math.abs(g-gaps[0])<=1),'Lane legend gaps are uneven '+gaps);
check(parseFloat(style('#quote').fontSize)<=parseFloat(style('#quoteBody').fontSize) && style('#quote').color!==style('#quoteBody').color,'Quoted code is larger than body text or not secondary');
check(bounds('#longSelect').right<=bounds('#insp').right+1,'Long select overflows the panel');
check(style('.step.unsure .tx').fontStyle==='italic' && style('.step.unsure .tx').color!==style('.s').color,'Uncertain step is not distinct or is faint');
const laneX=[...document.querySelectorAll('#laneSteps .step')].map(e=>Math.round(e.getBoundingClientRect().left));check(laneX[0]<laneX[1] && laneX[1]<laneX[2] && laneX[3]===laneX[1] && laneX[4]===laneX[0],'Screen, server and data steps do not indent by lane going and coming back '+laneX);
const disclosure=document.querySelector('.group details');disclosure.querySelector('summary').click();check(disclosure.open,'Disclosure cannot open');
const input=document.querySelector('input[type=datetime-local]');input.disabled=false;input.value='2026-10-21T09:00';check(input.value==='2026-10-21T09:00','Date control unusable');
window.uiSystemResult=JSON.stringify(errors);document.body.dataset.result=window.uiSystemResult;
'''
def page():
 links=''.join(f'<link rel="stylesheet" href="{(ROOT/"ui"/n).as_uri()}">' for n in ('tokens.css','app.css'))
 return f'''<!doctype html><meta charset="utf-8">{links}<body><header><details id="menu" open><summary class="btn">Menu</summary><div class="menu-panel"><button class="btn quiet" id="agent">Agent</button></div></details></header><div id="repository-bar"><details class="repository-detail"><summary>Code details</summary>Evidence</details></div><main><div id="map">Map</div><div id="insp"><article class="group"><div class="row"><div class="grow"><h3>Title</h3><h4>Problem</h4><p class="s">Metadata</p><p>Body</p><button class="pill click">PR #828</button></div></div><details><summary>More fields</summary><p>Evidence</p></details></article><section class="unit-board"><ul class="unit-cards"><li class="unit-card" data-state="saved"><button class="unit-head"><span class="unit-state">Saved</span></button><p id="unitBody">Body</p></li></ul></section><div class="step-lanes"><span class="screen">Screens</span><span class="server">Server</span><span class="store">Data</span><span class="external">External services</span></div><div class="step unsure"><div class="tx">Maybe</div></div><div id="laneSteps"><div class="step l0"><span class="from">↓</span><span class="n">0</span><div class="grow"><div class="tx">Step 0</div></div></div><div class="step l1"><span class="from">↓</span><span class="n">1</span><div class="grow"><div class="tx">Step 1</div></div></div><div class="step l2"><span class="from">↓</span><span class="n">2</span><div class="grow"><div class="tx">Step 2</div></div></div><div class="step l1"><span class="from">↓</span><span class="n">3</span><div class="grow"><div class="tx">Step 3</div></div></div><div class="step l0"><span class="from">↓</span><span class="n">4</span><div class="grow"><div class="tx">Step 4</div></div></div></div><section class="overview-tree"><p id="quoteBody">Body</p><pre id="quote">const quoted = true</pre></section><div class="ctl"><label>Server routes outside this overview <select id="longSelect"><option>/admin/fictional-endpoints/item-id/with/an/intentionally/long/fictional/path/segment/that/keeps/going</option></select></label><button class="btn quiet">Open in map</button></div></div></main><dialog><h2>Settings</h2><input type="datetime-local"><input type="checkbox"><button class="btn primary">Save</button></dialog><script>{CHECKS}</script>'''
class SharedSystem(unittest.TestCase):
 def test_chrome_shared_styles_and_long_content(self):
  if not CHROME.exists():self.skipTest('Chrome required')
  with tempfile.TemporaryDirectory() as tmp:
   path=Path(tmp)/'page.html';path.write_text(page())
   for width in (1446,1280,640):
    p=dump_dom(path.as_uri(),tmp+'/chrome',window=f'{width},900')
    import html
    result=re.search(r'data-result="([^"]*)"',p.stdout)
    self.assertIsNotNone(result,p.stderr[-1000:]);self.assertEqual(json.loads(html.unescape(result[1])),[],f'Chrome {width}')
 def test_webkit_shared_styles_and_long_content(self):
  if sys.platform!='darwin' or not shutil.which('swiftc'):self.skipTest('macOS WebKit required')
  with tempfile.TemporaryDirectory() as tmp:
   path=Path(tmp)/'page.html';path.write_text(page());probe=compiled_probe('webkit_style_probe.swift')
   for width in (1446,1280,640):
    p=subprocess.run([str(probe),str(path),str(width)],capture_output=True,text=True,timeout=30,check=True)
    self.assertEqual(json.loads(p.stdout.strip()),[],f'WKWebView {width}')


# Actual app renderers (not a second implementation of the component markup).
ACTUAL_CHECKS=r'''
(async()=>{
 const errors=[],check=(v,m)=>{if(!v)errors.push(m)},long='FictionalRepositoryWithAnIntentionallyLongUnbrokenName'.repeat(3);
 try{
  for(let i=0;i<100&&!window.appControlReady;i++)await new Promise(r=>setTimeout(r,20));
  check(window.appControlReady,'Fixture did not boot');
  const dark=window.uiExpectedDark ?? (new URLSearchParams(location.search).get('mode')==='dark');check(matchMedia('(prefers-color-scheme: dark)').matches===dark,'Requested color scheme not active');
  S.projectInfo.repositories[0].name=long;S.projectInfo.repositories[0].refs.dev=long;
  S.projectInfo.repositories.push({id:'queue',name:'Queue',refs:{dev:'feature/jobs',main:'v1.0'}},{id:'store',name:'Shared data',refs:{dev:'feature/data',main:'v1.0'}});
  const geometry=stage=>{
   check(document.documentElement.scrollWidth<=innerWidth+1,'Window overflows '+stage);
   const m=$('map').getBoundingClientRect(),r=$('insp').getBoundingClientRect();
   if(r.width)check(Math.abs(r.y-m.y)<1&&m.width>0,'Split lost '+stage);
  };
  for(const lang of ['ko','en']){
   S.lang=lang;renderHeader();
   for(const zoom of [1,1.5]){
    document.body.style.zoom=zoom;renderRepositories();
    for(const view of ['sys','feat','map','focus','changes']){S.view=view;S.focus=null;S.sel=null;S.agentPrompt=null;render();geometry(lang+view+zoom);}
    S.view='map';S.sel=null;render();const card=document.querySelector('[data-scr="web::/items"]');card.focus();card.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true}));check(S.sel==='web::/items','Keyboard Enter lost screen');
    const request=document.querySelector('[data-req]');request.focus();request.dispatchEvent(new KeyboardEvent('keydown',{key:' ',bubbles:true}));check(S.open,'Keyboard Space lost request');
    // A long step picture: at its last step ◀ / 다음 ▶ and the counter stay in the right panel and the current step is not under them.
    S.maps.dev.backend_routes[0].flow={steps:Array.from({length:30},(_,i)=>({lane:'서버',text:'Step '+i,file:'api/app/items.py',line:4,quote:'x'}))};render();
    for(let i=0;i<31;i++)$('next').click();
    {const c=$('insp').querySelector('.step-ctl').getBoundingClientRect(),p=$('insp').getBoundingClientRect(),cur=$('insp').querySelector('.step.cur').getBoundingClientRect();
     // body zoom skews rects (the stacked 1.5 layout reported the bar above the panel it sits in); geometry is read at zoom 1.
     if(zoom===1)check(S.step===30 && c.top>=p.top && c.bottom<=p.bottom+1 && cur.bottom<=c.top+1,'Step controls left the panel '+lang+zoom+' '+[S.step,p.top,c.top,c.bottom,p.bottom,cur.bottom].join('/'));}
    delete S.maps.dev.backend_routes[0].flow;S.step=-1;render();
    S.agentPurpose='analysis';S.agentPrompt='Fictional request';S.analysisRequest=null;renderAgentPrompt();geometry('analysis'+lang+zoom);
    const row=$('insp').querySelector('.row'),name=row.querySelector('.grow'),action=row.querySelector('button');if(name&&action)check(name.getBoundingClientRect().width>=action.getBoundingClientRect().width || action.getBoundingClientRect().top>=name.getBoundingClientRect().bottom,'Action squeezes label into a narrow column');
    $('menu').open=true;geometry('menu'+lang+zoom);check(getComputedStyle($('agent')).borderTopStyle==='none','Actual menu has toolbar border');check(getComputedStyle($('agent')).backgroundColor==='rgba(0, 0, 0, 0)','Menu action is not a plain list item');
    $('menuButton').focus();$('menuButton').dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}));check(!$('menu').open&&document.activeElement===$('menuButton'),'Menu Escape/focus');if($('menuButton').matches(':focus-visible'))check(getComputedStyle($('menuButton')).outlineStyle==='solid','Keyboard focus indicator missing');
    renderSettings();$('settings-dialog').showModal();geometry('settings'+lang+zoom);
    const dialog=$('settings-dialog').getBoundingClientRect();check(dialog.left>=0&&dialog.right<=innerWidth+1,'Dialog outside viewport');
    const ds=getComputedStyle($('settings-dialog'));check(ds.borderTopStyle==='solid'&&parseFloat(ds.borderTopWidth)>0&&parseFloat(ds.borderTopWidth)<=1,'Actual settings native border');
    const date=$('sinceTime');check(date.disabled,'Inactive date remains disabled');$('settings-dialog').querySelector('input[value=time]').click();check(!date.disabled,'Date radio interaction lost');date.value='2026-10-21T09:00';check(date.value==='2026-10-21T09:00','Actual date edit');
    $('settings-dialog').close();editProject(true);geometry('project'+lang+zoom);const field=$('project-dialog').querySelector('.repository-fields label input');check(Math.abs(field.getBoundingClientRect().width-field.parentElement.getBoundingClientRect().width)<2,'Stacked field fails to fill its label');$('project-dialog').close();
    openGuide();for(const step of [0,1,2,3]){G.step=step;if(step===1)G.connection={feature:'detail',challenge:'x',fresh_server:{state:'ready'},registration:{state:'not_inspected'},connection:{state:'not_verified'},handoff:long};renderGuide();
     const g=$('guide'),card=g.querySelector('.guide-step').getBoundingClientRect(),gs=getComputedStyle(g);
     // Visible width: innerWidth also counts a page scrollbar (Chrome 640px at zoom 1.5 measured 625 vs 640).
     const view=document.documentElement.clientWidth,gw=g.getBoundingClientRect().width;check(Math.abs(gw-view)<2,'Guide does not fill the window '+lang+step+zoom+' '+gw+'/'+view);
     check(g.scrollWidth<=g.clientWidth+1&&card.left>=0&&card.right<=view+1,'Guide overflows the viewport '+lang+step+zoom+' '+card.right+'/'+view);
     {const w=parseFloat(getComputedStyle(g.querySelector('.guide-step')).borderTopWidth);check(parseFloat(gs.borderTopWidth||0)===0&&w>0&&w<=1,'Guide uses hairlines only '+w+' '+gs.borderTopWidth);}
     g.querySelectorAll('button').forEach(b=>check(b.scrollWidth<=b.clientWidth+1,'Clipped guide button '+b.id+lang+zoom));}
    closeGuide();geometry('afterGuide'+lang+zoom);
   }
  }
  check(!window.errors.length,'Uncaught fixture errors '+window.errors.join(' | '));
 }catch(e){errors.push(e.stack)}
 window.uiSystemResult=JSON.stringify(errors);document.body.dataset.result=window.uiSystemResult;
})();
'''

def actual_page():
 from test_ui_flows import BOOTSTRAP
 from support import inline_assets
 source=inline_assets((ROOT/'ui/index.html').read_text().replace('<script>','<script>'+BOOTSTRAP,1))
 return source.replace('</body>','<script>'+ACTUAL_CHECKS+'</script></body>')

class AppSystem(unittest.TestCase):
 def test_actual_renderers_in_chrome_and_webkit_light_and_dark(self):
  if not CHROME.exists():self.skipTest('Chrome required')
  with tempfile.TemporaryDirectory() as tmp:
   tmp=Path(tmp);path=tmp/'actual.html';path.write_text(actual_page());probe=tmp/'probe'
   native=sys.platform=='darwin' and shutil.which('swiftc')
   if native:probe=compiled_probe('webkit_style_probe.swift')
   for mode in ('light','dark'):
    for width in (1446,1280,640):
     with self.subTest(engine='Chrome',mode=mode,width=width):
      # Light is requested explicitly: without it Chrome follows the host appearance (a Dark Mac failed the light case).
      output=dump_dom(path.as_uri()+'?mode='+mode,tmp/'chrome',budget=3000,window=f'{width},900',flags=('--force-dark-mode' if mode=='dark' else '--blink-settings=preferredColorScheme=1',))
      import html
      result=re.search(r'data-result="([^"]*)"',output.stdout)
      self.assertIsNotNone(result,output.stderr[-1000:]);self.assertEqual(json.loads(html.unescape(result[1])),[])
     if native:
      with self.subTest(engine='WKWebView',mode=mode,width=width):
       output=subprocess.run([str(probe),str(path),str(width),mode],capture_output=True,text=True,timeout=30,check=True)
       self.assertEqual(json.loads(output.stdout.strip()),[])


# The smallest window (960×600) and a wide one: toolbar and repository status stay short, the step picture's
# ◀ / 다음 ▶ row stays at the panel bottom with no step readable below it, and a start button waiting for the
# account check looks disabled.
WINDOW_CHECKS=r'''
(async()=>{
 const errors=[],check=(v,m)=>{if(!v)errors.push(m)},wait=(ms=50)=>new Promise(r=>setTimeout(r,ms)),W=innerWidth+'x'+innerHeight;
 try{
  for(let i=0;i<100&&!window.appControlReady;i++)await wait(20);
  S.projectInfo.repositories=[{id:'web',name:'Fictional web screens',collected:true,commits:{dev:'aaaaaaaa1111'},error:'fictional fetch error',refs:{dev:'HEAD'}},
   ...['api','queue','store'].map(id=>({id,name:'Fictional '+id+' service',collected:true,config_changed:true,commits:{dev:'cccccccc3333'},refs:{dev:'HEAD'}}))];
  for(const lang of ['ko','en']){
   S.lang=lang;S.view='map';render();renderHeader();renderRepositories();$('project').selectedOptions[0].text='Fictional studio';await wait();
   const shown=e=>e.offsetWidth>0&&e.offsetHeight>0,mid=e=>{const r=e.getBoundingClientRect();return r.top+r.height/2;};
   const head=[...document.querySelector('header').children].filter(e=>shown(e)&&!e.classList.contains('spacer'));
   check(head.every(e=>Math.abs(mid(e)-mid(head[0]))<2),'Toolbar wraps '+lang+W);
   let rows=0,bottom=-1;for(const r of [...$('repository-bar').querySelectorAll(':scope > *, .chips > *')].filter(shown).map(e=>e.getBoundingClientRect()).sort((a,b)=>a.top-b.top)){if(r.top>=bottom-1){rows++;bottom=r.bottom;}else bottom=Math.max(bottom,r.bottom);}
   check(rows<=2,'Repository status takes more than one line '+lang+W+' '+rows);
   check(document.querySelector('main').getBoundingClientRect().height>=innerHeight*0.6,'The map gets too little room '+lang+W);
  }
  S.lang='ko';renderHeader();renderRepositories();
  S.view='map';S.sel=null;render();
  const card=document.querySelector('[data-scr="web::/items"]');card.focus();card.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true}));
  const request=document.querySelector('[data-req]');request.focus();request.dispatchEvent(new KeyboardEvent('keydown',{key:' ',bubbles:true}));
  const route=S.maps.dev.backend_routes[0];
  for(const length of [30,2]){
   route.flow={steps:Array.from({length},(_,i)=>({lane:'서버',text:'Fictional step '+i+' reads the saved record and answers.',file:'api/app/items.py',line:4,quote:'x'}))};
   for(const at of [0,Math.floor(length/2),length]){
    S.step=at;S.ev=-1;render();showStep();await wait();
    const insp=$('insp'),p=insp.getBoundingClientRect(),floor=p.top+insp.clientTop+insp.clientHeight,c=insp.querySelector('.step-ctl').getBoundingClientRect(),cur=insp.querySelector('.step.cur').getBoundingClientRect(),where=W+' '+length+'/'+at;
    check(c.bottom<=floor+1 && cur.top>=p.top-1 && cur.bottom<=c.top+1,'The step controls cover the current step or leave the panel '+where+' '+[p.top,cur.top,cur.bottom,c.top,c.bottom,floor].map(Math.round));
    check([...insp.querySelectorAll('.step')].every(s=>{const r=s.getBoundingClientRect();return Math.min(r.bottom,floor)-Math.max(r.top,c.bottom)<=1;}),'A step shows below the step controls '+where);
    check($('prev').disabled===(at===0) && $('next').disabled===(at===length),'Only a control that cannot move is disabled '+where);
    if(at===0||at===length){const [off,on]=at===0?[$('prev'),$('next')]:[$('next'),$('prev')];check(getComputedStyle(off).opacity!==getComputedStyle(on).opacity,'A disabled step control looks pressable '+where);}
   }
  }
  // The account check after opening the panel: the start waits and looks it, in a single-task and the general open.
  delete route.flow;S.step=-1;render();
  window.appAnalysisFixture=true;window.unitBoard={repositories:[{repository:'web',units:[['folder:lib','folder','lib',3,'pending','']],coverage:{tracked:3,in_units:3,indexed:3,excluded:{},truncated:false}}],totals:{units:1,pending:1},calls:{rules:0,labeling:1,structure:0,unit:0,total:1}};
  for(const [name,opening,id] of [['single',()=>document.querySelector('[data-mk]').click(),'startAppAnalysis'],['general',()=>{openAnalysisPanel();AnalysisRun.checkAccount();},'startFullAnalysis']]){
   let release;window.holdProviders=new Promise(r=>release=r);opening();await wait(300);
   const start=()=>$(id)||$('startAppAnalysis'),waiting=start();check(waiting&&waiting.disabled,'The start is pressable during the account check '+name+W);
   const style=waiting&&getComputedStyle(waiting).opacity;release();window.holdProviders=null;await wait(300);
   const ready=start();check(ready&&!ready.disabled&&getComputedStyle(ready).opacity!==style,'The start looks the same during the account check '+name+W);
   S.agentPrompt=null;render();
  }
  check(!window.errors.length,'Uncaught fixture errors '+window.errors.join(' | '));
 }catch(e){errors.push(e.stack)}
 window.uiSystemResult=JSON.stringify(errors);document.body.dataset.result=window.uiSystemResult;
})();
'''

class WindowSizes(unittest.TestCase):
 def test_minimum_and_wide_windows_in_chrome_and_webkit_light_and_dark(self):
  if not CHROME.exists():self.skipTest('Chrome required')
  import html
  with tempfile.TemporaryDirectory() as tmp:
   tmp=Path(tmp);path=tmp/'window.html';path.write_text(actual_page().replace(ACTUAL_CHECKS,WINDOW_CHECKS))
   native=sys.platform=='darwin' and shutil.which('swiftc')
   probe=native and compiled_probe('webkit_style_probe.swift')
   for mode in ('light','dark'):
    for width,height in ((960,600),(1800,1000)):
     with self.subTest(engine='Chrome',mode=mode,size=(width,height)):
      output=dump_dom(path.as_uri()+'?mode='+mode,tmp/'chrome',budget=6000,window=f'{width},{height}',flags=('--force-dark-mode' if mode=='dark' else '--blink-settings=preferredColorScheme=1',))
      result=re.search(r'data-result="([^"]*)"',output.stdout)
      self.assertIsNotNone(result,output.stderr[-1000:]);self.assertEqual(json.loads(html.unescape(result[1])),[])
     if native:
      with self.subTest(engine='WKWebView',mode=mode,size=(width,height)):
       output=subprocess.run([str(probe),str(path),str(width),mode,str(height)],capture_output=True,text=True,timeout=30,check=True)
       self.assertEqual(json.loads(output.stdout.strip()),[])
