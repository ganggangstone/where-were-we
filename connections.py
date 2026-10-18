"""GitHub URL connections stored under a project's private .code directory.

Disconnecting never deletes code. Only a temporary clone created by this call is
removed on failure. Existing user folders and retained managed clones are kept.
"""
import copy
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile
from urllib.parse import urlsplit


def parse_url(value):
    if not isinstance(value,str):raise ValueError('Use a GitHub repository URL')
    value=value.strip()
    if value.startswith('git@github.com:'):slug=value[len('git@github.com:'):]
    elif '://' in value:
        u=urlsplit(value)
        if u.scheme!='https' or u.netloc!='github.com' or u.query or u.fragment:raise ValueError('Use a GitHub repository URL')
        slug=u.path.lstrip('/')
    else:slug=value
    slug=slug.rstrip('/').removesuffix('.git')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9_.-]{1,100}',slug) or slug.split('/')[1] in ('.','..'):
        raise ValueError('Use a GitHub repository URL')
    return 'https://github.com/'+slug.lower()+'.git'


def location(name,url):
    import project
    return (project.home(name)/'.code'/hashlib.sha256(url.encode()).hexdigest()[:24]/'repository').resolve()


def prepare(name,data):
    """Validate the whole form before any network or disk download."""
    import project
    value=copy.deepcopy(data)
    if not isinstance(value,dict) or not isinstance(value.get('repositories'),list):return project.validate(value)
    urls=set()
    for item in value['repositories']:
        if item.get('url'):
            url=parse_url(item['url']);path=location(name,url)
            if url in urls:raise ValueError('This GitHub repository is already connected')
            urls.add(url)
            if item.get('managed') and Path(item.get('path',''))!=path:raise ValueError('Managed code location does not match this project')
            item.update(url=url,path=str(path),managed=True)
            if not item.get('refs'):item['refs']={'dev':'origin/HEAD','main':None}
        elif item.get('managed'):raise ValueError('Managed code needs a GitHub URL')
    return project.validate(value)


def ensure(name,repo):
    import project
    if not repo.get('managed'):return
    url=parse_url(repo['url']);path=location(name,url)
    if Path(repo['path'])!=path or path.parent.is_symlink() or path.is_symlink():raise ValueError('Managed code location does not match this project')
    env=project.github_environment(repo,origin={'host':'github.com','repository':url.split('github.com/')[1].removesuffix('.git'),'https':True})
    repo['github']=json.loads(env['WHERE_WERE_WE_GITHUB'])
    if path.exists():
        if project.read(path.parent/'connection.json')!={'url':url} or project.github_origin(str(path))!={'host':'github.com','repository':url.split('github.com/')[1].removesuffix('.git'),'https':True}:
            raise ValueError('Managed code location was changed; reconnect using a new connection')
        return
    path.parent.mkdir(parents=True,exist_ok=True)
    # An abandoned download is never treated as a complete clone.
    with tempfile.TemporaryDirectory(prefix='.download-',dir=path.parent) as temp:
        target=Path(temp)/'repository'
        try:result=subprocess.run(['git','clone','--no-checkout','--',url,str(target)],env=env,capture_output=True,text=True,timeout=1800)
        except (OSError,subprocess.TimeoutExpired):raise project.github_error(repo['github'],'download') from None
        if result.returncode:raise project.github_error(repo['github'],'download')
        # Empty repositories have no code to analyze.
        result=subprocess.run(['git','-C',str(target),'rev-parse','--verify','origin/HEAD^{commit}'],capture_output=True,text=True)
        if result.returncode:raise ValueError('This GitHub repository has no default branch with code')
        project.atomic(path.parent/'connection.json',{'url':url})
        target.rename(path)


def accounts():
    import project
    import os
    env=dict(os.environ)
    for key in ('GH_TOKEN','GITHUB_TOKEN','GH_DEBUG','DEBUG','GH_HOST','GH_REPO'):env.pop(key,None)
    value=project.github_run(['auth','status','--hostname','github.com','--json','hosts','--jq','[.hosts[][] | .login] | unique'],env,{'host':'github.com'},'login')
    return {'accounts':[a for a in json.loads(value) if isinstance(a,str) and re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9-]{0,38}',a)]}
