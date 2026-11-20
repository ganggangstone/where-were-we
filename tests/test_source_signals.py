"""Signal scan of a pinned commit: which lines can hold routes, requests, stores, services, entry points and screens."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import source_signals as ss


def classes(path, text):
    return ss.scan_text(path, text)['classes']


class Rules(unittest.TestCase):
    """The rules read lexical shapes, not frameworks: the same shape in any language is a signal."""

    def test_routes_are_found_in_many_languages_without_a_framework_list(self):
        samples = {
            'api.py': "@app.get('/items')\ndef items(): pass\n",
            'urls.py': "urlpatterns = [path('articles/<int:year>/', views.year), re_path(r'^x/$', v)]\n",
            'router.go': 'r.GET("/items/:id", handler)\nhttp.HandleFunc("/health", h)\n',
            'Items.java': '@GetMapping("/items")\npublic List<Item> all() {}\n',
            'server.rs': '#[get("/items")]\nasync fn items() {}\n',
            'routes.rb': "Rails.application.routes.draw do\n  resources :users\n  get 'ping', to: 'p#show'\nend\n",
            'index.js': "app.post('/orders', create)\nrouter.use('/admin', admin)\n",
            'App.php': "$router->get('/items', 'ItemController@index');\n",
            'svc.ex': 'scope "/api" do\n  get "/items", ItemController, :index\nend\n',
            'openapi.yaml': "paths:\n  /items/{id}:\n    get:\n      summary: One item\n",
        }
        for name, text in samples.items():
            self.assertIn('route', classes(name, text), name)

    def test_other_classes_of_signal(self):
        self.assertIn('client', classes('a.ts', "const r = await fetch('/api/items')\n"))
        self.assertIn('client', classes('a.py', "r = requests.get(url)\n"))
        self.assertIn('store', classes('a.sql', 'CREATE TABLE items (id int);\n'))
        self.assertIn('store', classes('m.py', "class Item(Base):\n    __tablename__ = 'items'\n"))
        self.assertIn('external', classes('a.py', "client = boto3.client('s3')\nDSN = os.environ['SENTRY_DSN']\n"))
        self.assertIn('program', classes('main.go', 'func main() {\n}\n'))
        self.assertIn('program', classes('cli.py', "if __name__ == '__main__':\n    main()\n"))
        self.assertIn('screen', classes('App.tsx', '<Route path="/x" element={<X />} />\n'))

    def test_plain_code_has_no_signal_and_no_window(self):
        row = ss.scan_text('util.py', 'def add(a, b):\n    return a + b\n\n\ndef sub(a, b):\n    return a - b\n')
        self.assertEqual((row['classes'], row['windows']), ({}, []))

    def test_documents_and_support_paths_are_measured_but_never_windowed(self):
        text = "app.get('/items')\n" * 3
        for path, kind in (('README.md', 'doc'), ('data/rows.csv', 'doc'), ('tests/test_api.py', 'support'), ('web/node_modules/x/index.js', 'support'),
                           ('src/api.test.ts', 'support'), ('vendor/lib/router.go', 'support')):
            row = ss.scan_text(path, text)
            self.assertEqual((row['kind'], row['windows'], row['lines']), (kind, [], 3), path)
        self.assertEqual(ss.scan_text('bin/tool', "app.get('/x')\n")['kind'], 'code')  # a bin folder holds programs, not support files

    def test_windows_keep_original_line_numbers_and_merge_neighbours(self):
        body = ['x = 1'] * 40
        body[9] = "@app.get('/a')"
        body[12] = "@app.get('/b')"
        body[30] = "@app.get('/c')"
        row = ss.scan_text('a.py', '\n'.join(body) + '\n')
        self.assertEqual(row['windows'], [[8, 18], [29, 36]])
        self.assertEqual(ss.window_lines(row['windows']) & {10, 13, 31}, {10, 13, 31})

    def test_line_numbers_follow_splitlines_even_with_unusual_breaks(self):
        text = "a = 1\rb = 2\x0cc = 3\n@app.get('/x')\nz\n"
        number = next(i for i, line in enumerate(text.splitlines(), 1) if "/x" in line)
        windows = ss.scan_text('a.py', text)['windows']
        self.assertTrue(any(first <= number <= last for first, last in windows), (number, windows))

    def test_a_very_long_line_is_clipped_around_its_signal_with_the_character_offset(self):
        line = 'x' * 9000 + " app.get('/deep') " + 'y' * 9000
        row = ss.scan_text('bundle.js', line + '\n')
        offset = row['clips'][1]
        self.assertTrue(8000 < offset < 9000)
        rows = ss.window_rows([{'line': 1, 'text': line}], row['windows'], row['clips'])
        self.assertEqual(len(rows), 1)
        self.assertIn("/deep", rows[0]['text']);self.assertEqual(rows[0]['offset'], offset);self.assertEqual(len(rows[0]['text']), ss.LONG_LINE)
        self.assertEqual(line[offset:offset + ss.LONG_LINE], rows[0]['text'])

    def test_a_file_with_very_many_signals_is_cut_and_says_so(self):
        text = ''.join(f"app.get('/r{i}', h)\n\n\n\n\n\n\n\n\n" for i in range(400))
        row = ss.scan_text('routes.js', text)
        self.assertTrue(row['truncated'])
        self.assertLessEqual(sum(last - first + 1 for first, last in row['windows']), ss.MAX_WINDOW_LINES)

    def test_stored_rows_round_trip(self):
        row = {**ss.scan_text('a.js', "fetch('/x')\n" + 'z' * 3000 + " axios.get('/y')\n"), 'size': 10, 'sent': 5}
        self.assertEqual(json.loads(json.dumps(ss.pack(row))) and ss.unpack(json.loads(json.dumps(ss.pack(row)))), row)


class Commit(unittest.TestCase):
    def test_scan_reads_each_text_blob_once_and_sizes_both_ways(self):
        with tempfile.TemporaryDirectory() as folder:
            def git(*args):
                return subprocess.run(['git', '-C', folder, *args], check=True, capture_output=True, text=True).stdout
            git('init', '-q');git('config', 'user.name', 'T');git('config', 'user.email', 't@example.invalid')
            Path(folder, 'api.py').write_text("pad = 1\n" * 50 + "@app.get('/items')\ndef items(): pass\n" + "pad = 2\n" * 50)
            Path(folder, 'README.md').write_text("# title\n" * 10)
            Path(folder, 'blob.bin').write_bytes(b'\x00\x01')
            git('add', '.');git('commit', '-qm', 'x')
            head = git('rev-parse', 'HEAD').strip()
            entries = []
            for row in git('ls-tree', '-r', head).splitlines():
                meta, name = row.split('\t');entries.append((name, meta.split()[2].encode()))
            rows = ss.scan_commit(folder, head, entries, 11)
            self.assertEqual(set(rows), {'api.py', 'README.md'})  # a binary blob is not text
            api = rows['api.py']
            self.assertEqual(api['windows'], [[49, 56]])
            self.assertLess(api['sent'], api['size'] / 5)  # a few window lines of a 102-line file
            self.assertEqual(rows['README.md']['kind'], 'doc')
            self.assertEqual(rows['README.md']['sent'], 0)
            cost = ss.sample_bytes(folder, [e for e in entries if e[0] == 'api.py'])['api.py']
            self.assertLess(cost, 24 * 100)

    def test_a_large_commit_is_split_over_workers_with_the_same_rows_and_falls_back_when_they_cannot_start(self):
        with tempfile.TemporaryDirectory() as folder:
            def git(*args):
                return subprocess.run(['git', '-C', folder, *args], check=True, capture_output=True, text=True).stdout
            git('init', '-q');git('config', 'user.name', 'T');git('config', 'user.email', 't@example.invalid')
            for i in range(24):
                Path(folder, f'm{i}.py').write_text(f"x = {i}\n" * 30 + f"@app.get('/m{i}')\ndef m{i}(): pass\n" + ("é = 1\n" if i % 5 == 0 else ''))
            Path(folder, 'notes.md').write_text("# n\n")
            git('add', '.');git('commit', '-qm', 'x')
            head = git('rev-parse', 'HEAD').strip()
            entries = [(row.split('\t')[1], row.split('\t')[0].split()[2].encode()) for row in git('ls-tree', '-r', head).splitlines()]
            serial = ss._scan_serial(folder, entries, 11, True)
            old = (ss.PARALLEL_MIN, ss.os.cpu_count)
            ss.PARALLEL_MIN = 2;ss.os.cpu_count = lambda: 4
            self.addCleanup(lambda: (setattr(ss, 'PARALLEL_MIN', old[0]), setattr(ss.os, 'cpu_count', old[1])))
            spawned = []
            real = ss._scan_worker
            ss._scan_worker = lambda *a: (spawned.append(1), real(*a))[1]
            self.addCleanup(setattr, ss, '_scan_worker', real)
            parallel = ss.scan_commit(folder, head, entries, 11)
            self.assertEqual(len(spawned), 3);self.assertEqual(parallel, serial);self.assertEqual(list(parallel), list(serial))
            executable = ss.sys.executable
            ss.sys.executable = '/nonexistent/python'
            self.addCleanup(setattr, ss.sys, 'executable', executable)
            self.assertEqual(ss.scan_commit(folder, head, entries, 11), serial)  # workers cannot start: scanned here instead


if __name__ == '__main__':
    unittest.main()
