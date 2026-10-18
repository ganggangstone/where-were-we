"""Standard MCP client for the running app's private local command socket.

The socket accepts commands; only the app UI can confirm application. Command
IDs can be queried without replaying a refresh, update or configuration write.
"""
import json
import socket
import subprocess
import time
import uuid
from pathlib import Path
import mapcore

ACTIONS={
 'state':{},'targets':{'query':'text','project':'optional project','repository':'optional scope','branch':'dev|main'},
 'focus_app':{},'navigate':{'project':'project','repository':'scope','branch':'dev|main','view':'changes|sys|feat|map|focus'},
 'select':{'project':'project','repository':'scope','branch':'dev|main','target':'ID from app_targets','revision':'revision from app_targets','relations':'optional boolean'},
 'clear':{},'search':{'query':'text'},'step':{'index':'zero-based request step'},
 'dialog':{'name':'code|settings|agent|updates|create|close'},
 'settings':{'value':'comparison/auto-refresh settings object'},'language':{'lang':'ko|en'},
 'configure':{'project':'project','configuration':'repositories/shared_data object'},
 'github_logins':{},'update_settings':{'automatic':'boolean'},
 'github_accounts':{'project':'project','repository':'ID'},'github_account':{'project':'project','repository':'ID','account':'login'},
 'refresh':{'project':'project','repository':'optional scope'},
 'prepare_analysis':{'project':'project','repository':'scope','branch':'dev|main','task':'analysis|system|groups|jobs|steps|briefing','target':'program ID or screen path where needed'},
 'read_results':{},'update_state':{},'check_update':{},'start_update':{},
}

def exchange(request):
    try:
        meta=json.loads((Path(mapcore.ROOT)/'.app-control.json').read_text())
        if meta.get('protocol')!=1:return {'status':'incompatible_app','message':'Update and reopen the app.'}
        data=(json.dumps(request,ensure_ascii=False)+'\n').encode()
        if len(data)>1_048_576:return {'status':'invalid_command','message':'Command exceeds 1 MiB.'}
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as stream:
            stream.settimeout(3);stream.connect(meta['socket']);stream.sendall(data)
            parts=bytearray()
            while not parts.endswith(b'\n'):
                chunk=stream.recv(65536)
                if not chunk:raise OSError('Disconnected')
                parts.extend(chunk)
                if len(parts)>16_777_216:raise ValueError('Reply too large')
        return json.loads(parts)
    except FileNotFoundError:return {'status':'app_closed','message':'Open where-were-we, then retry.'}
    except (OSError,ValueError,KeyError,TypeError):return {'status':'app_unreachable','message':'Open or restart where-were-we. No new command was confirmed.'}

def outcome(command_id):return exchange({'op':'result','id':command_id})

def command(action,arguments=None,command_id='',wait=1.5):
    if action not in ACTIONS:return {'status':'invalid_action','actions':ACTIONS}
    if arguments is not None and not isinstance(arguments,dict):return {'status':'invalid_arguments'}
    if not command_id:
        try:instance=json.loads((Path(mapcore.ROOT)/'.app-control.json').read_text()).get('instance','')
        except (OSError,ValueError):instance=''
        command_id=instance+'-'+uuid.uuid4().hex
    elif '-' not in command_id:return {'status':'invalid_command_id','message':'Reuse the full ID returned by this app instance.'}
    result=exchange({'op':'submit','command':{'id':command_id,'action':action,'arguments':arguments or {}}})
    end=time.monotonic()+wait
    while result.get('status') in ('queued','running') and time.monotonic()<end:
        time.sleep(.05);result=outcome(command_id)
    return result

def open_app():
    # Open only this app; arbitrary executables or shell text are never accepted.
    bundled=next((p for p in Path(__file__).resolve().parents if p.suffix=='.app'),Path('/Applications/where-were-we.app'))
    try:
        if subprocess.run(['open',str(bundled)],capture_output=True,timeout=10).returncode:return {'status':'launch_failed'}
    except (OSError,subprocess.TimeoutExpired):return {'status':'launch_failed'}
    end=time.monotonic()+8
    while time.monotonic()<end:
        value=command('focus_app')
        if value.get('status') not in ('app_closed','app_unreachable','app_not_ready'):return value
        time.sleep(.1)
    return {'status':'app_not_ready','message':'Launch requested; no ready UI confirmed. Update/reopen the app if this continues.'}
