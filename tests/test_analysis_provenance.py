"""Synthetic evidence records retain the provider that generated each output."""
import copy
import json
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ai_extract
import briefing
import project
import test_ai_extract as map_fixture
import test_briefing as briefing_fixture


class MapProvenance(unittest.TestCase):
    setUp = map_fixture.Analysis.setUp
    git = map_fixture.Analysis.git

    def raw(self):
        repo = self.conf['repositories'][0]
        return project.raw_bundle(project.repository_folder('demo', repo, project.states('demo')))

    def save_map(self, provider=None):
        request = ai_extract.request('demo', 'dev', 'en', 'service')
        kwargs = {} if provider is None else {'provider': provider}
        data = map_fixture.agent_answer(request, copy.deepcopy(self.data))
        ai_extract.record(**request['record_arguments'], result_json=json.dumps(data), **kwargs)

    def save_task(self, task, data, target='', provider=None):
        request = ai_extract.task_request('demo', task, 'dev', 'en', 'service', target)
        kwargs = {} if provider is None else {'provider': provider}
        ai_extract.task_record(**request['record_arguments'], result_json=json.dumps(data), **kwargs)

    def test_default_and_cli_full_map_provenance(self):
        self.save_map('claude-cli')
        raw = self.raw()['dev']
        self.assertEqual(raw['analysis']['provider'], 'claude-cli')
        self.assertEqual(raw['task_outputs']['flows']['routes']['server/items.go::SaveItem']['provider'], 'claude-cli')
        self.save_task('groups', {'groups':[{'name':'Items', 'screens':['/items']}], 'names':{}, 'request_names':{}})
        self.assertEqual(self.raw()['dev']['task_outputs']['groups']['provider'], 'mcp-agent')
        self.assertEqual(self.raw()['dev']['analysis']['provider'], 'claude-cli')

    def test_cli_patch_keeps_manual_flow_attribution(self):
        self.save_map()
        before = self.raw()['dev']['task_outputs']['flows']['routes']['server/items.go::SaveItem']
        self.assertEqual(before['provider'], 'mcp-agent')
        source = self.repo/'pages/items.vue'
        source.write_text(source.read_text()+'<!-- presentation comment -->\n')
        self.git('add', '.'); self.git('commit', '-qm', 'Change presentation only')
        self.save_map('claude-cli')
        raw = self.raw()['dev']
        self.assertEqual(raw['analysis']['provider'], 'claude-cli')
        self.assertEqual(raw['task_outputs']['flows']['routes']['server/items.go::SaveItem']['provider'], 'mcp-agent')

    def test_new_cli_steps_and_kept_system_have_distinct_provenance(self):
        self.save_map()
        ev = {'file':'server/items.go', 'line':2, 'quote':'db.Table("items").Create(item)'}
        self.save_task('system', {'nodes':[{'id':'api', 'name':'API', 'kind':'program', 'code':['server'], 'ev':[ev]}],
                                 'links':[], 'externals':[], 'others':[], 'unknown':[]})
        self.save_task('system', {'keep':'all', 'accounted':[]}, provider='claude-cli')
        self.assertEqual(self.raw()['dev']['task_outputs']['system']['provider'], 'mcp-agent')
        self.save_task('steps', {'routes':{'server/items.go::SaveItem':{'name':'Save item',
                       'steps':[{**ev, 'lane':'저장소', 'text':'Store the item'}]}}},
                       '@routes:["server/items.go::SaveItem"]', 'claude-cli')
        self.assertEqual(self.raw()['dev']['task_outputs']['flows']['routes']['server/items.go::SaveItem']['provider'], 'claude-cli')
        self.assertEqual(self.raw()['dev']['task_outputs']['system']['provider'], 'mcp-agent')

    def test_invalid_provider_does_not_publish(self):
        before = project.states('demo')['service']['generation']
        with self.assertRaisesRegex(ValueError, 'provider'):
            self.save_map('unknown-cli')
        self.assertEqual(project.states('demo')['service']['generation'], before)
        with self.assertRaisesRegex(ValueError, 'provider'):
            self.save_task('groups', {}, provider='unknown-cli')
        self.assertEqual(project.states('demo')['service']['generation'], before)


class BriefingProvenance(unittest.TestCase):
    setUp = briefing_fixture.Briefing.setUp
    publish = briefing_fixture.Briefing.publish
    response = briefing_fixture.Briefing.response

    def test_default_manual_and_cli_briefings_keep_other_results(self):
        for repository, provider in [('web', None), ('api', 'claude-cli')]:
            request = briefing.request('demo', repository, 'dev', 'en')
            kwargs = {} if provider is None else {'provider': provider}
            briefing.record(**request['record_arguments'], result_json=json.dumps(self.response(request)), **kwargs)
        self.assertEqual(briefing.view('demo', 'web', 'dev', 'en')['result']['provider'], 'mcp-agent')
        self.assertEqual(briefing.view('demo', 'api', 'dev', 'en')['result']['provider'], 'claude-cli')
        before = (self.root/'demo/briefing.json').read_bytes()
        request = briefing.request('demo', 'api', 'dev', 'en')
        with self.assertRaisesRegex(ValueError, 'provider'):
            briefing.record(**request['record_arguments'], result_json=json.dumps(self.response(request)), provider='other')
        self.assertEqual((self.root/'demo/briefing.json').read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
