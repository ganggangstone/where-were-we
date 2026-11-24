#!/usr/bin/env python3
"""Measure 분석하기 on local repositories with a fake executor. Never calls real AI.

    python3 tests/measure_full_analysis.py --root /tmp/empty-folder REPO [REPO ...]

Prints one JSON line per repository: seconds to the local map, AI calls by kind, total and largest call bytes,
and whether the structure index stopped at its limits. The fake answers every labeling call with a name for each
listed unit and fails every reading-rules call, so rules cost their call plus the one retry."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

parser=argparse.ArgumentParser();parser.add_argument('--root',required=True);parser.add_argument('repos',nargs='+')
args=parser.parse_args()
os.environ['WHERE_WERE_WE_ROOT']=args.root;os.environ['WHERE_WERE_WE_SETTINGS']=str(Path(args.root)/'settings.json')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import analysis_run  # noqa: E402
import project  # noqa: E402

real_run=subprocess.run
def guard(command,**kwargs):
    if Path(str(command[0])).name=='claude':raise AssertionError('Real AI calls are forbidden here')
    return real_run(command,**kwargs)
subprocess.run=guard

def fake(prompt,**_):
    if not prompt.startswith('You label') and not prompt.startswith('You build'):return '{}'
    payload=json.loads(prompt[prompt.index('{"description"'):])
    refs=[r for g in payload['groups'] for r in g['units']] if 'groups' in payload else [u[0] for u in payload['units']]
    return {'units':[{'ref':r,'name':f'u{r}','what':'x'} for r in refs],'groups':[{'name':'g','units':refs}],
            'programs':[{'name':'p','units':refs[:5]}],'links':[]}

for i,repo in enumerate(args.repos):
    name=f'm{i}'
    project.configure(name,{'repositories':[{'id':'service','path':str(Path(repo).resolve()),'refs':{'dev':'HEAD','main':None}}]})
    start=time.monotonic();project.refresh_project(name)
    analysis_run.unit_signals(name,'service','dev','ko');board=analysis_run.unit_board(name,'service','dev','ko')
    local=round(time.monotonic()-start,1)
    job=analysis_run.prepare(name,lang='ko',repository='service',intent={'task':'full','targets':[]})
    done=analysis_run.run(job['id'],fake)
    stats=done.get('input_stats') or {}
    cover=board['repositories'][0]['coverage']
    print(json.dumps({'repo':Path(repo).name,'local_map_s':local,'units':len(board['repositories'][0]['units'])-2,'announced':job['announced'],
                      'calls':stats.get('by_kind',{}),'bytes':stats.get('bytes',0),'largest':stats.get('max_prompt_bytes',0),'state':done['state'],
                      'summary_bytes':len(json.dumps(analysis_run._full_scope({**job})['service']['summary'],ensure_ascii=False,separators=(',',':')).encode()),
                      **{k:cover.get(k) for k in ('tracked','in_units','indexed','plain','truncated','index_candidates','index_skipped')},'gaps':[g['part'] for g in done.get('gaps',[])]},ensure_ascii=False),flush=True)
