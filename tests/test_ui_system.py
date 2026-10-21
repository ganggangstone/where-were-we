"""Computed shared UI contracts, using fictional content and both app engines."""
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
const disclosure=document.querySelector('.group details');disclosure.querySelector('summary').click();check(disclosure.open,'Disclosure cannot open');
const input=document.querySelector('input[type=datetime-local]');input.disabled=false;input.value='2026-10-21T09:00';check(input.value==='2026-10-21T09:00','Date control unusable');
window.uiSystemResult=JSON.stringify(errors);document.body.dataset.result=window.uiSystemResult;
'''
def page():
 links=''.join(f'<link rel="stylesheet" href="{(ROOT/"ui"/n).as_uri()}">' for n in ('tokens.css','app.css'))
 return f'''<!doctype html><meta charset="utf-8">{links}<body><header><details id="menu" open><summary class="btn">Menu</summary><div class="menu-panel"><button class="btn quiet" id="agent">Agent</button></div></details></header><div id="repository-bar"><details class="repository-detail"><summary>Code details</summary>Evidence</details></div><main><div id="map">Map</div><div id="insp"><article class="group"><div class="row"><div class="grow"><h3>Title</h3><h4>Problem</h4><p class="s">Metadata</p><p>Body</p><button class="pill click">PR #828</button></div></div><details><summary>More fields</summary><p>Evidence</p></details></article></div></main><dialog><h2>Settings</h2><input type="datetime-local"><input type="checkbox"><button class="btn primary">Save</button></dialog><script>{CHECKS}</script>'''
class SharedSystem(unittest.TestCase):
 def test_chrome_shared_styles_and_long_content(self):
  chrome=Path('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome')
  if not chrome.exists():self.skipTest('Chrome required')
  with tempfile.TemporaryDirectory() as tmp:
   path=Path(tmp)/'page.html';path.write_text(page())
   for width in (1446,1280,640):
    p=subprocess.run([str(chrome),'--headless','--disable-gpu','--no-first-run','--disable-background-networking','--user-data-dir='+tmp+'/chrome',f'--window-size={width},900','--dump-dom',path.as_uri()],capture_output=True,text=True,timeout=30)
    import html
    result=re.search(r'data-result="([^"]*)"',p.stdout)
    self.assertIsNotNone(result,p.stderr[-1000:]);self.assertEqual(json.loads(html.unescape(result[1])),[],f'Chrome {width}')
 def test_webkit_shared_styles_and_long_content(self):
  if sys.platform!='darwin' or not shutil.which('swiftc'):self.skipTest('macOS WebKit required')
  with tempfile.TemporaryDirectory() as tmp:
   path=Path(tmp)/'page.html';path.write_text(page());probe=Path(tmp)/'probe'
   subprocess.run(['swiftc','-O',str(ROOT/'tests/webkit_style_probe.swift'),'-o',str(probe)],check=True,capture_output=True)
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
 source=(ROOT/'ui/index.html').read_text().replace('<script>','<script>'+BOOTSTRAP,1)
 for name in ('tokens.css','app.css','vendor/dagre.min.js','connection.js','onboarding.js','control.js'):
  source=source.replace('"'+name+'"','"'+(ROOT/'ui'/name).as_uri()+'"')
 return source.replace('</body>','<script>'+ACTUAL_CHECKS+'</script></body>')

class AppSystem(unittest.TestCase):
 def test_actual_renderers_in_chrome_and_webkit_light_and_dark(self):
  chrome=Path('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome')
  if not chrome.exists():self.skipTest('Chrome required')
  with tempfile.TemporaryDirectory() as tmp:
   tmp=Path(tmp);path=tmp/'actual.html';path.write_text(actual_page());probe=tmp/'probe'
   native=sys.platform=='darwin' and shutil.which('swiftc')
   if native:subprocess.run(['swiftc','-O',str(ROOT/'tests/webkit_style_probe.swift'),'-o',str(probe)],check=True,capture_output=True)
   for mode in ('light','dark'):
    for width in (1446,1280,640):
     with self.subTest(engine='Chrome',mode=mode,width=width):
      command=[str(chrome),'--headless','--disable-gpu','--no-first-run','--disable-background-networking','--user-data-dir='+str(tmp/'chrome'),f'--window-size={width},900','--virtual-time-budget=3000','--dump-dom',path.as_uri()+'?mode='+mode]
      # Light is requested explicitly: without it Chrome follows the host appearance (a Dark Mac failed the light case).
      command.insert(1,'--force-dark-mode' if mode=='dark' else '--blink-settings=preferredColorScheme=1')
      output=subprocess.run(command,capture_output=True,text=True,timeout=30)
      import html
      result=re.search(r'data-result="([^"]*)"',output.stdout)
      self.assertIsNotNone(result,output.stderr[-1000:]);self.assertEqual(json.loads(html.unescape(result[1])),[])
     if native:
      with self.subTest(engine='WKWebView',mode=mode,width=width):
       output=subprocess.run([str(probe),str(path),str(width),mode],capture_output=True,text=True,timeout=30,check=True)
       self.assertEqual(json.loads(output.stdout.strip()),[])
