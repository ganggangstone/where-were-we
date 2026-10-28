"""One analysis handoff: synthetic Git only, every AI result is a fixed fake JSON."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parent))
import ai_extract
import briefing
import project
import test_ai_extract

class Plan(unittest.TestCase):
    setUp=test_ai_extract.Analysis.setUp
    git=test_ai_extract.Analysis.git
    normalize=test_ai_extract.Analysis.normalize
    EV={'file':'server/items.go','line':2,'quote':'db.Table("items").Create(item)'}
    SYSTEM={'nodes':[{'id':'api','name':'API','kind':'program','code':['server'],'ev':[EV],'jobs':[]}],'links':[],'externals':[],'others':[],'unknown':[]}
    GROUPS={'groups':[{'name':'Items','screens':['/items']}],'names':{},'request_names':{}}

    def tasks(self,plan):return [(t['repository'],t['task']) for t in plan['tasks']]
    def follow(self,plan,rid='service',results=None):
        """Act as the connected agent: re-plan after every save so dependent arguments and new targets are current."""
        results=results or {}
        for _ in range(12):
            todo=[t for t in ai_extract.plan('demo',plan['branch'],plan['lang'],plan['repository'])['tasks'] if t['repository']==rid]
            if not todo:return
            task=todo[0]
            if task['task']=='analysis':
                request=ai_extract.request('demo',plan['branch'],plan['lang'],rid)
                self.assertEqual(request['commit'],task['commit'])
                ai_extract.record(**request['record_arguments'],result_json=json.dumps(test_ai_extract.agent_answer(request,results.get('analysis',self.data))))
            else:
                request=ai_extract.task_request('demo',task['task'],plan['branch'],plan['lang'],rid,task.get('target',''))
                self.assertEqual(request['commit'],task['commit'])
                default=({'routes':{k:{'steps':[],'unknown':'Not established'} for k in request['input']['routes']}} if task['task']=='steps'
                         else self.SYSTEM if task['task']=='system' else self.GROUPS)
                ai_extract.task_record(**request['record_arguments'],result_json=json.dumps(results.get(task['task'],default)))
        self.fail('Plan did not settle')

    def test_handoff_explains_that_source_structure_is_read_from_the_pinned_commit(self):
        for lang,token in (('ko','실제 파일을 읽어'),('en','reading the tracked files')):
            handoff=ai_extract.plan('demo','dev',lang)['handoff']
            self.assertIn(token,handoff,lang);self.assertIn('framework' if lang=='en' else '프레임워크',handoff,lang)
    def test_first_request_queues_map_then_dependents_in_one_handoff(self):
        for lang in ('ko','en'):
            plan=ai_extract.plan('demo','dev',lang)
            self.assertEqual(self.tasks(plan),[('service','analysis'),('service','system'),('service','groups')])
            handoff=plan['handoff']
            self.assertLess(handoff.index('analyze'),handoff.index('request_ai_task'))
            self.assertIn(self.commit,handoff)
            # Dependent arguments are fetched after the map is saved, never precreated.
            self.assertNotIn('snapshot',handoff)
            self.assertFalse(plan['up_to_date'])

    def test_saved_results_need_nothing_and_language_is_not_a_fallback(self):
        self.follow(ai_extract.plan('demo','dev','en'))
        plan=ai_extract.plan('demo','dev','en')
        self.assertEqual(plan['tasks'],[])
        self.assertTrue(plan['up_to_date'])
        self.assertEqual(plan['handoff'],'')
        self.assertEqual([t for _,t in self.tasks(ai_extract.plan('demo','dev','ko'))],['analysis','system','groups'])

    def test_changed_code_requeues_map_first_and_grouping_follows_without_bypassing_guard(self):
        self.follow(ai_extract.plan('demo','dev','en'))
        (self.repo/'server/items.go').write_text((self.repo/'server/items.go').read_text()+'// changed\n')
        self.git('add','.');self.git('commit','-qm','Changed');self.commit=self.git('rev-parse','HEAD').strip()
        with self.assertRaisesRegex(ValueError,'Map commit changed'):ai_extract.task_request('demo','groups','dev','en','service')
        plan=ai_extract.plan('demo','dev','en')
        self.assertEqual([t for _,t in self.tasks(plan)],['analysis','system','groups'])
        self.follow(plan)
        self.assertEqual(ai_extract.plan('demo','dev','en')['tasks'],[])

    def test_only_missing_dependents_are_queued_when_map_is_current(self):
        self.follow(ai_extract.plan('demo','dev','en'))
        folder=project.repository_folder('demo',self.conf['repositories'][0],project.states('demo'))
        raw=project.raw_bundle(folder);raw['dev']['task_outputs'].pop('groups')
        project._publish('demo','service',raw,{},collection=False)
        self.assertEqual(self.tasks(ai_extract.plan('demo','dev','en')),[('service','groups')])

    def test_backend_only_map_does_not_queue_groups_forever(self):
        data={**self.data,'screens':[]};self.data=data
        request=ai_extract.request('demo','dev','en','service')
        ai_extract.record(**request['record_arguments'],result_json=json.dumps(data))
        self.assertEqual([t for _,t in self.tasks(ai_extract.plan('demo','dev','en'))],['system'])

    def test_one_changed_repository_queues_only_its_dependencies(self):
        other=Path(self.temp.name)/'other';shutil.copytree(self.repo,other)
        conf=project.configure('demo',{'repositories':[*self.conf['repositories'],{'id':'web','path':str(other),'refs':{'dev':'HEAD','main':None}}]})
        project.publish('demo','web',{'dev':project.raw_bundle(project.repository_folder('demo',conf['repositories'][0],project.states('demo')))['dev']},
                        {'fingerprint':project.fingerprint(conf['repositories'][1])})
        plan=ai_extract.plan('demo','dev','en')
        self.assertEqual({r for r,_ in self.tasks(plan)},{'service','web'})
        self.follow(plan,'service');self.follow(plan,'web')
        self.assertEqual(ai_extract.plan('demo','dev','en')['tasks'],[])
        (other/'server/items.go').write_text((other/'server/items.go').read_text()+'// web only\n')
        subprocess.run(['git','-C',str(other),'commit','-qam','Web change'],check=True)
        self.assertEqual(self.tasks(ai_extract.plan('demo','dev','en')),[('web','analysis'),('web','system'),('web','groups')])
        self.assertIn(self.commit,ai_extract.plan('demo','dev','en')['handoff'])
        self.assertEqual(self.tasks(ai_extract.plan('demo','dev','en','service')),[])

    def test_plan_and_records_leave_comparison_baseline_untouched(self):
        repo=self.conf['repositories'][0]
        raw=project.raw_bundle(project.repository_folder('demo',repo,project.states('demo')))
        raw['changes']={'last_refresh':'2026-10-01T00:00:00+00:00','entries':[{'at':'kept','prs':[]}],'last_result':{'since':'fixed'}}
        project._publish('demo','service',raw,{},collection=False)
        before=project.read_bundle('demo')['changes'];state=project.states('demo')['service'].get('last_success')
        self.follow(ai_extract.plan('demo','dev','en'))
        self.assertEqual(project.read_bundle('demo')['changes'],before)
        self.assertEqual(project.states('demo')['service'].get('last_success'),state)

    def test_briefing_is_included_from_frozen_evidence_and_preparation_errors_are_reported(self):
        stub={'state':'not_analyzed','input':{'has_changes':True}}
        with patch.object(briefing,'view',return_value=stub),patch.object(briefing,'request',return_value={'commit':'h'*64,'record_arguments':{'input_hash':'h'*64},'result_before':[{'task':'briefing','before':None}]}):
            plan=ai_extract.plan('demo','dev','en')
        self.assertEqual(plan['tasks'][-1]['task'],'briefing')
        self.assertIn('request_briefing',plan['handoff'])
        with patch.object(briefing,'view',return_value=stub),patch.object(briefing,'request',side_effect=ValueError('Code version changed; collect again before requesting a briefing')):
            plan=ai_extract.plan('demo','dev','en')
        self.assertNotIn('briefing',[t['task'] for t in plan['tasks']])
        self.assertEqual(plan['blocked'][0]['task'],'briefing')
        self.assertIn('Code version changed',plan['blocked'][0]['reason'])

    def test_configuration_change_blocks_that_repository_instead_of_queueing_it(self):
        conf=project.config('demo');conf['repositories'][0]['layout']={'frontend':'pages'}
        project.atomic(project.home('demo')/'project.json',conf)
        plan=ai_extract.plan('demo','dev','en')
        self.assertEqual(plan['tasks'],[])
        self.assertEqual(plan['blocked'][0]['repository'],'service')
        self.assertFalse(plan['up_to_date'])

    def raw(self):return project.raw_bundle(project.repository_folder('demo',project.config('demo')['repositories'][0],project.states('demo')))

    def test_source_pins_remain_available_when_all_tasks_are_complete(self):
        initial=ai_extract.plan('demo','dev','en')
        self.follow(initial)
        done=ai_extract.plan('demo','dev','en')
        self.assertEqual(done['pins']['service'],initial['pins']['service'])
        self.assertEqual(done['pins']['service']['commit'],self.commit)

    def test_jobs_for_changed_manual_program_identity_need_review(self):
        raw=self.raw();raw['system']={'source':'manual','nodes':[{'id':'written','kind':'program','code':['server']}]}
        project._publish('demo','service',raw,{},collection=False)
        self.follow(ai_extract.plan('demo','dev','en'))
        result=ai_extract.plan('demo','dev','en')
        self.assertFalse(result['up_to_date'])
        self.assertTrue(any(t['task']=='jobs' and t['target']=='api' for t in result['blocked']))
    def test_map_steps_are_saved_with_metadata_and_missing_steps_are_planned(self):
        self.follow(ai_extract.plan('demo','dev','en'))
        flow=self.raw()['dev']['task_outputs']['flows']['routes']['server/items.go::SaveItem']
        self.assertEqual((flow['language'],flow['branch'],flow['source']),('en','dev','ai'))
        self.assertTrue(flow['configuration'])
        data=json.loads(json.dumps(self.data));data['backend_routes'][0].pop('steps')
        conf=project.config('demo');conf['repositories'][0]['layout']={'backend':'server'};project.atomic(project.home('demo')/'project.json',conf)
        state=project.states('demo');state['service']['fingerprint']=project.fingerprint(conf['repositories'][0]);project.atomic(project.home('demo')/'repository-state.json',state)
        self.follow(ai_extract.plan('demo','dev','en'),results={'analysis':{**data,'screens':[]}})
        steps=[t for t in ai_extract.plan('demo','dev','en')['tasks'] if t['task']=='steps']
        self.assertEqual(steps,[])
        flow=self.raw()['dev']['task_outputs']['flows']['routes']['server/items.go::SaveItem']
        self.assertEqual(flow['steps'],[]);self.assertEqual(flow['unknown'],'Not established')

    def test_route_without_steps_is_planned_with_its_route_key(self):
        data=json.loads(json.dumps(self.data));data['backend_routes'][0].pop('steps')
        request=ai_extract.request('demo','dev','en','service')
        ai_extract.record(**request['record_arguments'],result_json=json.dumps(data))
        steps=[t for t in ai_extract.plan('demo','dev','en')['tasks'] if t['task']=='steps']
        self.assertEqual(steps[0]['target'],'@routes:["server/items.go::SaveItem"]')

    def test_invalid_steps_are_not_saved_as_unknown(self):
        self.follow(ai_extract.plan('demo','dev','en'))
        request=ai_extract.task_request('demo','steps','dev','en','service','@routes:["server/items.go::SaveItem"]')
        with self.assertRaisesRegex(ValueError,'evidence'):
            ai_extract.task_record(**request['record_arguments'],result_json=json.dumps({'routes':{'server/items.go::SaveItem':{'steps':[{**self.EV,'quote':'fabricated text'}]}}}))
        self.assertEqual(self.raw()['dev']['task_outputs']['flows']['routes']['server/items.go::SaveItem']['steps'][0]['text'],'Store the item')

    def test_worker_only_repository_settles_with_explicit_unknown(self):
        empty={'screens':[],'backend_routes':[],'unknown':['No HTTP endpoints; this is a worker.'],'inspected':[self.EV]}
        system={'nodes':[],'links':[],'externals':[],'others':[],'unknown':['Library only; no separately running program.'],'ev':[self.EV]}
        self.follow(ai_extract.plan('demo','dev','en'),results={'analysis':empty,'system':system})
        self.assertTrue(ai_extract.plan('demo','dev','en')['up_to_date'])
        with self.assertRaisesRegex(ValueError,'evidence'):
            request=ai_extract.request('demo','dev','ko','service')
            ai_extract.record(**request['record_arguments'],result_json=json.dumps({**empty,'inspected':[{**self.EV,'quote':'fabricated text'}]}))

    def test_rejected_map_claims_with_inspection_do_not_erase_the_saved_map(self):
        self.follow(ai_extract.plan('demo','dev','en'))
        bad=json.loads(json.dumps(self.data));bad['screens'][0]['quote']='fabricated screen';bad['backend_routes'][0]['quote']='fabricated route'
        request=ai_extract.request('demo','dev','en','service')
        with self.assertRaisesRegex(ValueError,'evidence'):
            ai_extract.record(**request['record_arguments'],result_json=json.dumps({**bad,'inspected':[self.EV],'unknown':['Endpoints were not established.']}))
        self.assertEqual(len(self.raw()['dev']['screens']),1)

    def test_layout_change_after_refresh_requeues_map_saved_for_old_layout(self):
        self.follow(ai_extract.plan('demo','dev','en'))
        conf=project.config('demo');conf['repositories'][0]['layout']={'frontend':'pages'};project.atomic(project.home('demo')/'project.json',conf)
        state=project.states('demo');state['service']['fingerprint']=project.fingerprint(conf['repositories'][0]);project.atomic(project.home('demo')/'repository-state.json',state)
        self.assertEqual(self.tasks(ai_extract.plan('demo','dev','en'))[0],('service','analysis'))

    def test_every_program_with_code_needs_saved_jobs(self):
        self.follow(ai_extract.plan('demo','dev','en'))
        raw=self.raw();raw['dev']['task_outputs']['jobs']['nodes'].pop('api');project._publish('demo','service',raw,{},collection=False)
        self.assertIn(('service','system'),self.tasks(ai_extract.plan('demo','dev','en')))
        self.follow(ai_extract.plan('demo','dev','en'))
        raw=self.raw();raw['dev']['task_outputs']['system']['nodes'].append({**raw['dev']['task_outputs']['system']['nodes'][0],'id':'ui','code':['pages']})
        project._publish('demo','service',raw,{},collection=False)
        self.assertIn(('service','system'),self.tasks(ai_extract.plan('demo','dev','en')))

    def test_briefing_with_no_collected_changes_is_not_requested_and_hash_is_pinned(self):
        with patch.object(briefing,'view',return_value={'state':'stale','input':{'has_changes':False}}):
            self.assertNotIn('briefing',[t['task'] for t in ai_extract.plan('demo','dev','en')['tasks']])
        with patch.object(briefing,'view',return_value={'state':'stale','input':{'has_changes':True}}),patch.object(briefing,'request',return_value={'commit':'h'*64,'record_arguments':{'input_hash':'h'*64},'result_before':[{'task':'briefing','before':{'version':'old'}}]}):
            plan=ai_extract.plan('demo','dev','en')
        self.assertIn('h'*64,plan['handoff'])
        with patch.object(briefing,'view',side_effect=FileNotFoundError('git')):
            self.assertEqual(ai_extract.plan('demo','dev','en')['blocked'][-1]['task'],'briefing')

    def test_unreadable_repository_is_blocked_while_others_are_planned(self):
        other=Path(self.temp.name)/'other';shutil.copytree(self.repo,other)
        conf=project.configure('demo',{'repositories':[*self.conf['repositories'],{'id':'web','path':str(other),'refs':{'dev':'HEAD','main':None}}]})
        project.publish('demo','web',{'dev':self.raw()['dev']},{'fingerprint':project.fingerprint(conf['repositories'][1])})
        shutil.rmtree(other)
        plan=ai_extract.plan('demo','dev','en','*')
        self.assertIn(('service','analysis'),self.tasks(plan))
        self.assertEqual([b['repository'] for b in plan['blocked']],['web'])

    def test_groups_planned_before_a_screenless_map_do_not_stay_missing(self):
        self.assertIn(('service','groups'),self.tasks(ai_extract.plan('demo','dev','en')))
        import mcp_server
        request=ai_extract.request('demo','dev','en','service')
        ai_extract.record(**request['record_arguments'],result_json=json.dumps({**self.data,'screens':[]}))
        replan=json.loads(mcp_server.analysis_plan('demo','dev','en'))
        self.assertNotIn('groups',[t['task'] for t in replan['tasks']])
        self.assertIn('analysis_plan',replan['handoff'])

if __name__=='__main__':unittest.main()
