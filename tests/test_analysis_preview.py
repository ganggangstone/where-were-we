"""Exercise the live preview through the worker with a synthetic Git repository."""
import json
import time
import unittest

from test_analysis_run import AnalysisRun as _Fixture
import analysis_run


class Preview(unittest.TestCase):
    setUp = _Fixture.setUp
    git = _Fixture.git
    raw = _Fixture.raw
    prepare = _Fixture.prepare

    def test_verified_preview_precedes_final_map_and_cancel_preserves_baseline(self):
        # Keep a real route beyond line 500 in an unrecognized file type and use
        # distinct filler lines so that compression of repeated text cannot pass.
        self.git('mv', 'server/items.go', 'server/work.entry')
        self.git('mv', 'pages/items.vue', 'pages/items.screen')
        for path in ('server/work.entry', 'pages/items.screen'):
            source = self.repo / path
            source.write_text(''.join(f'prefix {i}\n' for i in range(501)) + source.read_text())
        (self.repo/'zzz-padding.other').write_text(''.join(f'padding {i}\n' for i in range(10000)))
        self.git('add', '.')
        self.git('commit', '-qm', 'Register custom service')
        baseline = self.raw()
        intent = {'task': 'analysis', 'targets': []}

        for cancel in (True, False):
            run = self.prepare(intent=intent)
            previews = []
            def executor(prompt, **kwargs):
                payload = json.loads(prompt.split('\n', 1)[1])
                preview = analysis_run.status(run_id=run['id']).get('preview')
                if preview:
                    self.assertEqual(preview['commit'], self.git('rev-parse', 'HEAD').strip())
                    self.assertEqual(preview['repository'], 'service')
                    self.assertEqual(self.raw(), baseline)
                    for item in preview['items']:
                        self.assertIn(item['quote'], (self.repo/item['file']).read_text().splitlines()[item['line']-1])
                    previews.extend(preview['items'])
                    if cancel:
                        analysis_run.cancel(run['id'])
                result = {'screens': [], 'backend_routes': [], 'unknown': []}
                for snapshot in payload.get('snapshots', []):
                    for file in snapshot['files']:
                        for line in file['lines']:
                            evidence = dict(file=file['file'], line=line['line'], quote=line['text'])
                            if '<button @click="saveItem">' in line['text']:
                                result['screens'].append(dict(evidence, path='/items'))
                            if line['text'] == 'router.POST("/items", SaveItem)':
                                result['backend_routes'].append(dict(evidence, path='/items', method='POST', function='SaveItem'))
                batch = payload.get('batch')
                return dict(batch=batch['id'], covered=batch['units'], result=result) if batch else result
            done = analysis_run.run(run['id'], executor)
            self.assertTrue(previews, done.get('error'))
            self.assertFalse(done.get('preview'))
            if cancel:
                self.assertEqual(done['state'], 'cancelled', done.get('error'))
                self.assertEqual(self.raw(), baseline)
            else:
                self.assertEqual(done['state'], 'completed', done.get('error'))
                mapped = self.raw()['dev']
                self.assertEqual([s['path'] for s in mapped['screens']], ['/items'])
                self.assertEqual([r['path'] for r in mapped['backend_routes']], ['/items'])

    def test_first_batch_only_sends_source_and_defers_review_metadata(self):
        for i in range(64):
            (self.repo/f'part{i}.odd').write_text(f'ordinary module {i}\n')
        self.git('add', '.')
        self.git('commit', '-qm', 'Large file inventory')
        run = self.prepare(intent={'task': 'analysis', 'targets': []})
        task = run['tasks'][0]
        request = analysis_run._request(run, task)
        known = [[f'id{i}', 'GET', f'/item/{i}', 'example', 'server/items.go', 'basic'] for i in range(600)]
        request.update(mode='review', known=known, recheck=[{'id': 'existing'}])
        first_id = None
        seen_pages = set()
        extra_read = False
        final_sources = set()

        def executor(prompt, **kwargs):
            nonlocal first_id, extra_read
            packet = json.loads(prompt.split('\n', 1)[1])
            batch = packet['batch']
            reply = {'batch': batch['id'], 'covered': batch['units'], 'result': {}}
            pages = packet.get('context_pages', [])
            sources = {f['file'] for snap in packet.get('snapshots', []) for f in snap['files']}
            final_sources.update(sources)
            if first_id is None:
                first_id = batch['id']
                self.assertTrue(sources)
                self.assertFalse(pages)
                self.assertNotIn('known', packet)
                self.assertNotIn('recheck', packet)
                self.assertLessEqual(len(batch['units']), 8)
                reply['needs'] = [{'metadata': ['known'], 'start': 5, 'limit': 1}]
            elif batch['id'] == first_id:
                self.assertTrue(any(p['path'] == ['known'] and p['value'] == [known[4]] for p in pages))
                extra_read = True
            else:
                self.assertEqual(packet['recheck'], request['recheck'])
                seen_pages.update(p['path'][1] for p in pages if p['path'][:1] == ['known'])
            return reply

        analysis_run.generate(run, task, request, executor, lambda: False,
                              time.monotonic()+60, lambda: None, {})
        self.assertTrue(extra_read)
        self.assertEqual(seen_pages, set(range(len(known))))
        self.assertEqual(final_sources, set(self.git('ls-files').splitlines()))

    def test_web_free_command_with_unknown_extension_has_early_local_evidence(self):
        self.git('rm', '-q', 'pages/items.vue', 'server/items.go')
        source = self.repo/'work'/'app.odd'
        source.parent.mkdir()
        command = 'command sync executes worker'
        source.write_text(command + '\n' + 'x'*995)
        for i in range(64):
            other = self.repo/'rest'/f'part{i}.odd'
            other.parent.mkdir(exist_ok=True)
            other.write_text(f'unrelated module number {i}\n')
        self.git('add', '.')
        self.git('commit', '-qm', 'Command only; unfamiliar file format')
        run = self.prepare(intent={'task': 'analysis', 'targets': []})
        observed = []

        def executor(prompt, **kwargs):
            p = json.loads(prompt.split('\n', 1)[1])
            batch = p['batch']
            preview = (analysis_run.status(run_id=run['id']).get('preview') or {}).get('items', [])
            if preview and not observed:
                observed.extend(preview)
            items = []
            for snapshot in p.get('snapshots', []):
                for file in snapshot['files']:
                    for line in file['lines']:
                        if line['text'] == command:
                            items = [dict(name='Sync', file=file['file'], line=line['line'], quote=command),
                                     dict(name='Unsupported claim', file=file['file'], line=line['line'], quote='wrong evidence')]
            evidence = [{'file': source['file'], 'line': source['line'], 'quote': source['quote']} for source in items[:1]]
            result = {'inspected': evidence, 'unknown': ['No screens or server endpoints established.'] if evidence else []}
            return dict(batch=batch['id'], covered=batch['units'], result=result, preview_programs=items)

        done = analysis_run.run(run['id'], executor)
        self.assertEqual(observed, [dict(name='Sync', file='work/app.odd', line=1, quote=command, kind='program')], done.get('error'))
        self.assertEqual(done['state'], 'completed', done.get('error'))
        self.assertFalse(done.get('preview'))
        self.assertEqual(done['program_observations'], [
            {'repository': 'service', 'commit': self.git('rev-parse', 'HEAD').strip(), 'items': observed}
        ])


# Imported fixture is not itself a test class in this module's discovery.
del _Fixture
