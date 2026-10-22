"""Bundled-server diagnostics and a live MCP confirmation exchange.

No client configuration is read or written here. Only a selected registration's
command/script paths are accepted for classification; env and extra argv are
never copied into a report or stored challenge. Only our own server is probed.
"""
import argparse
import asyncio
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import sys
import tempfile
import time
import uuid
sys.path.insert(0,str(Path(__file__).resolve().parent))
import mapcore
import project

BACKEND_FILES=('mapcore.py','project.py','mcp_server.py','extract.py','ai_extract.py','briefing.py','connections.py','app_control.py','connection.py','refresh.py','collect.py','group.py','steps.py','system.py','jobs.py')
FEATURES={
 'maps':('projects','overview','changes','find','impact','refresh','record_test','set_test_rules'),
 'detail':('analyze','analysis_source','record_analysis','request_ai_task','record_ai_task','analysis_plan'),
 'briefing':('request_briefing','briefing_source','record_briefing','change_briefing'),
 'app':('app_state','app_targets','app_control','app_command_result'),
 # The first-run request registers the service through projects and app_control (see mapcore.setup_prompt onboarding).
 'onboarding':('projects','refresh','app_state','app_control','app_command_result'),
}

def required(feature):
 if feature not in FEATURES:raise ValueError('Choose a supported feature')
 return sorted(set(FEATURES[feature])|{'server_info','confirm_connection'})

def snapshot():
 base=Path(__file__).resolve().parent
 hashes={name:hashlib.sha256((base/name).read_bytes()).hexdigest() if (base/name).is_file() else None for name in BACKEND_FILES}
 version=None
 bundle=next((p for p in base.parents if p.suffix=='.app'),None)
 if bundle:
  try:version=plistlib.loads((bundle/'Contents/Info.plist').read_bytes()).get('CFBundleShortVersionString')
  except (OSError,ValueError):pass
 elif (base/'src-tauri/tauri.conf.json').is_file():version=json.loads((base/'src-tauri/tauri.conf.json').read_text()).get('version')
 return {'python':str(Path(sys.executable).absolute()),'server':str(base/'mcp_server.py'),
         'digest':hashlib.sha256(json.dumps(hashes,sort_keys=True).encode()).hexdigest(),
         'files':hashes,'pid':os.getpid(),'started_at':datetime.now(timezone.utc).isoformat(),
         'app_version':version,'python_version':sys.version.split()[0]}

def path_state(path):
 try:return 'exists' if Path(path).is_file() else 'missing'
 except PermissionError:return 'permission_denied'

def registration(value,expected):
 if not value:return {'state':'not_inspected'}
 if not isinstance(value,dict):return {'state':'unsupported_registration'}
 command=value.get('command');args=value.get('args',[])
 if not isinstance(command,str) or not isinstance(args,list) or not all(isinstance(a,str) for a in args):return {'state':'unsupported_registration'}
 # Never return arbitrary CLI text, flags, environment, headers or credentials.
 scripts=[a for a in args if os.path.isabs(a) and Path(a).name=='mcp_server.py']
 if not os.path.isabs(command) or len(scripts)!=1:return {'state':'unresolved_registration','custom_settings':'retained; not included in diagnostics'}
 script=scripts[0];states=[path_state(p) for p in (command,script)]
 if 'permission_denied' in states:state='permission_denied'
 elif 'missing' in states:state='app_moved_or_missing' if '.app/' in script else 'missing_runtime_or_server'
 elif os.path.realpath(command)==os.path.realpath(expected['python']) and os.path.realpath(script)==os.path.realpath(expected['server']):state='matches_app'
 else:state='different_path'
 return {'state':state,'command':command,'server':script,'custom_settings':'retained; not included in diagnostics'}

def folder():return Path(mapcore.ROOT)/'.connection-checks'
def challenge_path(challenge):
 if not isinstance(challenge,str) or not re.fullmatch(r'[a-f0-9]{32}',challenge):raise ValueError('Invalid connection check')
 return folder()/(challenge+'.json')

def begin(expected,feature):
 required(feature);challenge=uuid.uuid4().hex
 folder().mkdir(parents=True,exist_ok=True);folder().chmod(0o700)
 project.atomic(challenge_path(challenge),{'expected':expected,'feature':feature,'expires':time.time()+1800,'result':None})
 challenge_path(challenge).chmod(0o600)
 return challenge

def load(challenge):
 value=project.read(challenge_path(challenge))
 if not value:raise ValueError('Connection check not found')
 return value

def check(challenge,current=None):
 value=load(challenge)
 if time.time()>value['expires']:return {'state':'expired'}
 if current and any(current.get(k)!=value['expected'].get(k) for k in ('python','server','digest')):return {'state':'app_changed'}
 return value.get('result') or {'state':'not_verified'}

def confirm(challenge,identity,tools,configuration=None):
 # identity is a snapshot captured by the actual server at startup; tools come
 # from its live MCP registry, never from agent-provided capability claims.
 with project.locked('.connection-checks'):
  value=load(challenge)
  if time.time()>value['expires']:return {'state':'expired'}
  expected=value['expected'];missing=sorted(set(required(value['feature']))-set(tools))
  if any(identity.get(k)!=expected.get(k) for k in ('python','server')):state='different_server'
  elif identity.get('digest')!=expected.get('digest'):state='running_old_server'
  elif missing:state='missing_tools'
  else:state='verified'
  result={'state':state,'missing':missing,'feature':value['feature'],'verified_at':datetime.now(timezone.utc).isoformat(),
          'server':{k:identity.get(k) for k in ('python','server','digest','pid','started_at','app_version','python_version')},
          'registration':registration(configuration,expected)}
  value['result']=result;project.atomic(challenge_path(challenge),value);challenge_path(challenge).chmod(0o600)
  return result

def probe(expected):
 """Start only the app-owned interpreter/server; never execute pasted argv."""
 for path in (expected['python'],expected['server']):
  state=path_state(path)
  if state!='exists':return {'error':'permission_denied' if state=='permission_denied' else 'missing_runtime'}
 async def run():
  from mcp import ClientSession,StdioServerParameters
  from mcp.client.stdio import stdio_client
  # Inherited credentials and client/project selection are unnecessary here.
  env={k:v for k,v in os.environ.items() if k in ('HOME','PATH','TMPDIR','LANG','WHERE_WERE_WE_ROOT')}
  args=StdioServerParameters(command=expected['python'],args=['-I','-B',expected['server']],env=env)
  with tempfile.TemporaryFile(mode='w+') as errors:
   async with stdio_client(args,errlog=errors) as streams:
    async with ClientSession(*streams) as session:
     await session.initialize();tools=[t.name for t in (await session.list_tools()).tools]
     if 'server_info' not in tools:return {'tools':tools,'identity':None}
     result=await session.call_tool('server_info',{})
     if result.is_error:return {'error':'server_info_unavailable','tools':tools}
     return {'tools':tools,'identity':json.loads(result.content[0].text)}
 try:return asyncio.run(asyncio.wait_for(run(),timeout=12))
 except BaseException as error:
  if isinstance(error,(KeyboardInterrupt,SystemExit)):raise
  def permission(e):return isinstance(e,PermissionError) or any(permission(x) for x in getattr(e,'exceptions',[]))
  return {'error':'permission_denied' if permission(error) else 'server_unavailable'}

def handoff(challenge,expected,feature,lang):
 target=json.dumps({'command':expected['python'],'args':['-I','-B',expected['server']]},ensure_ascii=False,indent=2)
 needed=', '.join(required(feature))
 if lang=='en':
  return f'''Check only the where-were-we MCP registration used by this agent. Do not edit settings until showing the selected client, registration scope/name and proposed changes for approval. The app selected diagnostics and guided repair, not automatic config rewriting.
Expected app registration (paths remain valid after updates at the same install location):
{target}
Required tools for {feature}: {needed}
Inspect the selected registration's command and arguments. Preserve unrelated registrations, project overrides, extra arguments and environment settings. Never print credentials or send env/header/token values to diagnostics. If an intentional development server is selected, explain the difference and ask which server to keep. If the app moved or its runtime is missing, resolve that before changing the connection.
Reconnect this MCP server using the client's reconnect function, or start a new agent session if it cannot rediscover tools. Do not kill unrelated sessions or processes. Config edits and a newly spawned test server do not prove the current connection changed.
AFTER reconnecting, use confirm_connection(challenge="{challenge}", registration_json=<ONLY command and args of the selected registration>) through THIS agent's connected MCP. The server reports its own startup fingerprint and actual tools. Do not launch a separate server/CLI or call the app's diagnostic probe to simulate this confirmation. If confirm_connection is unavailable, report that and leave it unverified. After a verified result, invoke server_info once through the same connection. Tell me the result; I will use Check the connection in the app. Do not refresh project data or change comparison settings.
{mapcore.reply_language(lang)}'''
 return f'''지금 이 에이전트가 사용하는 where-were-we MCP 연결 하나만 확인해 주세요. 선택한 클라이언트·등록 범위·연결 이름과 고칠 내용을 먼저 보여 주고 허락받은 뒤 설정을 수정하세요. 앱은 진단·수정 안내 방식을 사용하며 설정을 자동으로 덮어쓰지 않습니다.
앱에 포함된 서버의 연결 설정(같은 설치 위치에서 업데이트하면 경로가 유지됩니다):
{target}
선택한 기능 {feature}에 필요한 도구: {needed}
선택한 연결의 command와 args를 확인하세요. 다른 연결·프로젝트별 설정·추가 인자·환경 설정은 보존하세요. 자격 증명을 출력하거나 env·헤더·토큰을 진단으로 보내지 마세요. 의도해서 개발 서버를 사용 중이면 차이를 설명하고 어느 쪽을 유지할지 물어보세요. 앱이 이동했거나 런타임이 없으면 먼저 해결하세요.
클라이언트의 MCP 재연결 기능을 사용하세요. 새 도구를 찾지 못하면 새 에이전트 세션이 필요할 수 있습니다. 무관한 세션·프로세스는 종료하지 마세요. 설정 수정이나 별도로 실행한 시험 서버만으로 현재 연결이 바뀌었다고 말하지 마세요.
재연결한 뒤 반드시 이 에이전트에 연결된 MCP의 confirm_connection(challenge="{challenge}", registration_json=<선택한 연결의 command·args만>)를 호출하세요. 서버가 시작할 때의 코드 정보와 실제 도구를 직접 확인합니다. 별도 서버나 CLI를 실행해 확인을 대신하지 마세요. 도구가 없으면 없다고 보고하고 미확인으로 남기세요. 확인에 성공하면 같은 연결의 server_info도 한 번 호출하세요. 결과를 알려 주면 앱에서 ‘연결됐는지 확인’을 누르겠습니다. 프로젝트 새로고침과 비교 설정 변경은 하지 마세요.
{mapcore.reply_language(lang)}'''

def diagnose(feature='detail',lang='ko',configuration=None):
 expected=snapshot();fresh=probe(expected);missing=sorted(set(required(feature))-set(fresh.get('tools',[])))
 identity=fresh.get('identity')
 state=fresh.get('error')
 if not state:
  if not isinstance(identity,dict):state='server_info_unavailable'
  elif any(identity.get(k)!=expected.get(k) for k in ('python','server')):state='different_server'
  elif identity.get('digest')!=expected.get('digest'):state='app_changed'
  else:state='missing_tools' if missing else 'ready'
 challenge=begin(expected,feature)
 return {'challenge':challenge,'feature':feature,'app':{k:expected.get(k) for k in ('python','server','app_version','digest')},
         'fresh_server':{'state':state,'missing':missing},
         'registration':registration(configuration,expected),'connection':{'state':'not_verified'},
         'handoff':handoff(challenge,expected,feature,lang)}

def main():
 parser=argparse.ArgumentParser();parser.add_argument('command',choices=['diagnose','check']);parser.add_argument('--feature',default='detail');parser.add_argument('--lang',default='ko');parser.add_argument('--challenge',default='')
 a=parser.parse_args();print(json.dumps(diagnose(a.feature,a.lang) if a.command=='diagnose' else check(a.challenge,snapshot()),ensure_ascii=False))
if __name__=='__main__':
 try:main()
 except Exception:print('Connection diagnostics unavailable; no client settings were changed.',file=sys.stderr);sys.exit(1)
