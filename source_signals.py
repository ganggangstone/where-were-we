"""AI-free signal scan of one pinned commit: which source lines can hold what the map looks for.

The map asks for screens, mounted routes, client HTTP calls, data stores, external services and
program entry points. Every eligible text file is read locally and scanned with language-neutral
rules (verbs next to path literals, request clients, DDL/DML, entry points, env-held endpoints...).
Each file lands in exactly one tier:

  windows  signal lines were found: the lines around them go to the AI as numbered windows
  local    read and scanned, but no signal line: stays in the local index and is reachable by the
           AI through the existing file/search read requests (needs)
  support  tests, fixtures, vendored or generated-looking paths: scanned like the rest but only
           sent when the user asks for the whole text

Nothing here narrows what the user can ask for: `coverage=all` sends every eligible file as before.
The scan is derived data of the pinned commit, so it is cached by commit and scanner digest.
"""
import bisect
import concurrent.futures
import functools
import hashlib
import json
import os
import re
import subprocess
import sys
import threading
from pathlib import PurePosixPath

@functools.lru_cache(maxsize=1)
def digest():
    """Identity of this scanner (rules and thresholds), for caches of its output."""
    with open(__file__, 'rb') as handle:
        return hashlib.sha1(handle.read()).hexdigest()


BEFORE = 2          # lines kept before a signal line (decorators, section headers)
AFTER = 5           # lines kept after it (the handler name, the call arguments)
MAX_WINDOW_LINES = 600   # per file; a file past it is marked truncated, never silently cut
DOC_SUFFIXES = {'.md', '.mdx', '.markdown', '.rst', '.txt', '.adoc', '.org', '.rdoc', '.po', '.pot', '.tex', '.csv', '.tsv',
                '.ndjson', '.jsonl', '.log', '.diff', '.patch', '.sum', '.svg', '.ipynb'}
STRUCTURED_SUFFIXES = {'.json', '.yaml', '.yml', '.toml', '.xml', '.ini', '.cfg', '.conf', '.properties', '.env', '.tf', '.hcl'}
SUPPORT_PARTS = {'test', 'tests', '__tests__', 'spec', 'specs', 'e2e', 'fixture', 'fixtures', 'mock', 'mocks', '__mocks__',
                 'testdata', 'testing', 'snapshots', '__snapshots__', 'vendor', 'vendored', 'node_modules', 'third_party',
                 'thirdparty', 'deps'}
SUPPORT_NAME = re.compile(r'(^|[._-])(test|tests|spec|mock|fixture)([._-]|$)|_test\.\w+$|\.test\.\w+$|\.spec\.\w+$')

_STRING = r"""['"`][^'"`\n]{1,200}['"`]"""
_PATH_LITERAL = r"""['"`]/[\w\-{}$:.*/%?=&<>\[\]]*['"`]|['"`][^'"`\n]*(?:\{\w*\}|<\w+(?::\w+)?>|/:\w+)[^'"`\n]*['"`]"""
# Every rule starts with a literal (or a quote/angle/at-sign) so the regex engine can skip to candidates quickly;
# trailing \b keeps most partial words out. Rules are recall-oriented: a signal line only decides what is sent.
RULES = (
    ('route', re.compile(r'(?:get|post|put|patch|delete|head|options|any|all|api|use|match|http\w*|handle\w*|mapping)\b[^\n]{0,40}?(?:' + _PATH_LITERAL + ')')),
    ('route', re.compile(r'(?:route|routes|router|path|re_path|url|urls|endpoint|mount|include|scope|namespace|resources?|rule|add_url_rule|add_route|add_api_route|add_resource|handle_func|handlefunc|map_?get|map_?post|map_?put|map_?delete)\b\s*[\(\[:=,.]\s*[rbf]?(?:' + _STRING + ')')),
    ('route', re.compile(r"""@\w*(?:Get|Post|Put|Patch|Delete|Request|Route|Controller|Api)\w*\s*[\(\n]|#\[(?:get|post|put|delete|patch|route)\b""")),
    ('route', re.compile(r"""(?m)^[ \t]*(?:resources?|namespace|scope|root|mount|get|post|put|patch|delete|match)[ \t]+[:'"/]""")),
    ('route', re.compile(r"""(?m)^[ \t]*['"]?/[\w\-{}/.:*]+['"]?[ \t]*:[ \t]*[\{\[]?[ \t]*$""")),
    ('client', re.compile(r'(?:fetch|axios|ky|got|superagent|requests|httpx|aiohttp|urllib\d?|urlopen|httpclient|resttemplate|webclient|reqwest|ureq|okhttp|xmlhttprequest|useswr|usequery|http\.(?:get|post|put|delete|newrequest)|net/http|curl_exec|file_get_contents|faraday|httparty)\s*[\.\(<]|\$\.ajax')),
    ('store', re.compile(r'create\s+table|alter\s+table|insert\s+into|delete\s+from|select\s[^;\n]{1,120}?\sfrom\s|update\s+\w+\s+set\s|__tablename__|db_table|create_table\b|createtable\b|has_many\b|belongs_to\b|foreignkey\(|prisma\.\w+\.\w+\(')),
    ('store', re.compile(r'@Entity|@Table\b|Table\(|Column\(|models\.\w+Field\b|collection\(')),
    ('external', re.compile(r'(?:redis|postgres(?:ql)?|mysql|mongodb(?:\+srv)?|amqps?|kafka|nats|sqs|smtp|s3|gs|grpc|wss?)://|[A-Z][A-Z0-9_]*(?:_API_KEY|_TOKEN|_URL|_HOST|_DSN|_ENDPOINT|_BUCKET|_SECRET)\b|boto3\.(?:client|resource)\(|new\s+\w*(?:Client|Sdk|SDK)\(|stripe\b|twilio\b|sendgrid\b|openai\b|anthropic\b|s3\.\w+\(')),
    ('program', re.compile(r'func\s+main\s*\(|fn\s+main\s*\(|def\s+main\s*\(|(?:int|void)\s+main\s*\(|public\s+static\s+void\s+main\b|if\s+__name__\s*==|import\s+argparse|ArgumentParser\(|@click\.|click\.(?:command|group)\b|cobra\.Command\b|clap::|commander\b|yargs\b|optparse\b|OptionParser\b|flag\.(?:String|Bool|Int|Parse)\b|Typer\(|add_subcommand\b|SubCommand\b|cron\b|celery\b|@task\b|Scheduled\b|sidekiq\b|setInterval\s*\(|(?:ListenAndServe|listen|serve|run_server|runserver|bootRun|SpringApplication\.run)\s*\(|uvicorn\.run\b|app\.run\s*\(|consumer\b|subscribe\s*\(|worker\b')),
    ('screen', re.compile(r"""<Route\b|create(?:Browser|Hash|Memory)?Router\b|useNavigate\b|navigate\s*\(|router\.(?:push|replace)\s*\(|NavLink\b|<router-view|<Link\b[^>]*\bto=|startActivity\s*\(|performSegue\b|NavigationLink\b|NavHost\b|composable\s*\(|render_template\s*\(|render\s*\(\s*request\b|TemplateView\b|ModalRoute\b|GoRoute\b|<form\b[^>]*\baction=|href=['"]/""")),
)
# Rules whose literals are lower-case run on the lower-cased text (a plain regex is much faster than re.I); a text whose
# lower-casing changes its length falls back to the re.I form so offsets still map to lines.
LOWER = (0, 1, 5, 6)
_CI = {}


def _pattern(index, pattern, text, low):
    if index not in LOWER or low is not None:
        return pattern, low if index in LOWER else text
    if index not in _CI:
        _CI[index] = re.compile(pattern.pattern, pattern.flags | re.I)
    return _CI[index], text



def _kind(path):
    parts = PurePosixPath(path).parts
    name = parts[-1].lower() if parts else ''
    suffix = PurePosixPath(name).suffix
    if suffix in DOC_SUFFIXES:
        return 'doc'
    if any(p.lower() in SUPPORT_PARTS for p in parts[:-1]) or SUPPORT_NAME.search(name):
        return 'support'
    if suffix in STRUCTURED_SUFFIXES:
        return 'structured'
    return 'code'

kind = _kind  # the tier of a path alone: 'doc', 'support', 'structured' or 'code'


LONG_LINE = 1600     # a longer line is sent as one clipped segment around the first signal, with its character offset
CLIP_BEFORE = 200


_ODD_BREAKS = re.compile('[\r\x0b\x0c\x1c-\x1e\x85\u2028\u2029]')


def _starts(text):
    """Offsets where each line begins, numbered exactly like str.splitlines (the numbering the AI cites)."""
    if _ODD_BREAKS.search(text):
        starts, at = [0], 0
        for row in text.splitlines(keepends=True):
            at += len(row)
            starts.append(at)
        return starts[:-1] or [0], len(text.splitlines())
    starts = [0]
    starts.extend(m.end() for m in re.finditer('\n', text))
    return starts, (len(starts) if text and not text.endswith('\n') else len(starts) - 1)


def _hits(text):
    """({class: [one-based line, ...]}, line count, {line: first signal column of a long line})."""
    starts, total = _starts(text)
    found, cols = {}, {}
    low = text.lower()
    low = low if len(low) == len(text) else None
    for index, (name, pattern) in enumerate(RULES):
        pattern, haystack = _pattern(index, pattern, text, low)
        for match in pattern.finditer(haystack):
            line = bisect.bisect_right(starts, match.start())
            found.setdefault(name, set()).add(line)
            if line not in cols:
                col = match.start() - starts[line - 1]
                end = starts[line] if line < len(starts) else len(text)
                if end - starts[line - 1] > LONG_LINE:
                    cols[line] = col
    return {name: sorted(lines) for name, lines in found.items()}, total, cols


def _windows(lines, total):
    spans = []
    for line in lines:
        start, end = max(1, line - BEFORE), min(total, line + AFTER)
        if spans and start <= spans[-1][1] + 1:
            spans[-1][1] = max(spans[-1][1], end)
        else:
            spans.append([start, end])
    return spans


def scan_text(path, text):
    """One file: {'kind','lines','classes':{name:count},'windows':[[start,end]],'clips':{line:offset},'truncated':bool}.
    Documents and support paths are only measured: they are never sent unless the whole text is requested."""
    kind = _kind(path)
    if kind in ('doc', 'support'):
        return {'kind': kind, 'lines': len(text.splitlines()), 'classes': {},
                'windows': [], 'clips': {}, 'truncated': False}
    classes, total, cols = _hits(text)
    lines = sorted({n for rows in classes.values() for n in rows})
    spans = _windows(lines, total)
    truncated = sum(end - start + 1 for start, end in spans) > MAX_WINDOW_LINES
    if truncated:
        budget, cut = MAX_WINDOW_LINES, []
        for start, end in spans:
            if budget <= 0:
                break
            end = min(end, start + budget - 1)
            cut.append([start, end])
            budget -= end - start + 1
        spans = cut
    return {'kind': kind, 'lines': total, 'classes': {k: len(v) for k, v in classes.items()}, 'windows': spans,
            'clips': {n: max(0, c - CLIP_BEFORE) for n, c in cols.items() if any(a <= n <= b for a, b in spans)}, 'truncated': truncated}


def window_lines(spans):
    return {n for start, end in spans for n in range(start, end + 1)}


def clip(text, offset=None):
    """The text a window row carries for a line: whole, or one LONG_LINE segment from the clip offset."""
    if offset is None and len(text) <= LONG_LINE:
        return text
    start = offset or 0
    return text[start:start + LONG_LINE]


def row_bytes(text):
    return len(text.encode()) + text.count('"') + text.count('\\') + text.count('\t')


def stream(repo, entries):
    """(path, text, raw bytes) of every regular UTF-8 text blob among entries, through one git cat-file process."""
    if not entries:
        return
    process = subprocess.Popen(['git', '-C', repo, 'cat-file', '--batch'], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL)
    feeder = threading.Thread(target=lambda: (process.stdin.write(b''.join(oid + b'\n' for _, oid in entries)), process.stdin.close()),
                              daemon=True)
    feeder.start()
    try:
        for file, _ in entries:
            header = process.stdout.readline().split()
            if len(header) != 3:
                continue
            data = process.stdout.read(int(header[2]))
            process.stdout.read(1)
            if b'\x00' in data:
                continue
            try:
                text = data.decode('utf-8')
            except UnicodeError:
                continue
            yield file, text, data
    finally:
        process.stdout.close()
        process.wait()


PARALLEL_MIN = 600   # files; a smaller commit is scanned in this process (starting workers would cost more than it saves)
MAX_WORKERS = 6


def _scan_serial(repo, entries, overhead):
    rows = {}
    for file, text, data in stream(repo, entries):
        row = scan_text(file, text)
        lines = text.splitlines() if row['windows'] else ()
        wrapper = len(file) + 34
        row['size'] = len(data) + (data.count(b'\n') + (1 if data and not data.endswith(b'\n') else 0)) * overhead + data.count(b'"') + data.count(b'\\') + data.count(b'\t') + wrapper
        kept = window_lines(row['windows'])
        row['sent'] = (sum(row_bytes(clip(lines[n - 1], row['clips'].get(n))) + overhead for n in kept if n <= len(lines)) + wrapper) if kept else 0
        rows[file] = row
    return rows


def _scan_worker(repo, entries, overhead):
    """One scan in a separate interpreter (the regex work holds the GIL, so threads cannot share it)."""
    process = subprocess.run([sys.executable, '-I', '-B', __file__, repo, str(overhead)], input=json.dumps([[f, o.decode()] for f, o in entries]).encode(),
                             capture_output=True, check=True)
    return {f: unpack(r) for f, r in json.loads(process.stdout).items()}


def scan_commit(repo, commit, entries, overhead):
    """Scan every (path, oid) once through git cat-file streams.

    Returns {path: scan row, with 'size' (bytes of the whole serialized text) and 'sent' (bytes of the windows)}.
    Only regular UTF-8 text blobs are scanned; the caller decides which paths are eligible. A large commit is split
    over a few worker interpreters; any worker failure falls back to scanning it all here, so the result is the same."""
    workers = min(MAX_WORKERS, (os.cpu_count() or 1) - 1)
    if workers < 2 or len(entries) < PARALLEL_MIN or not sys.executable:
        return _scan_serial(repo, entries, overhead)
    chunks = [entries[i::workers] for i in range(workers)]
    try:
        with concurrent.futures.ThreadPoolExecutor(workers) as pool:
            parts = list(pool.map(lambda chunk: _scan_worker(repo, chunk, overhead), chunks))
    except (OSError, ValueError, KeyError, subprocess.SubprocessError):
        return _scan_serial(repo, entries, overhead)
    found = {f: r for part in parts for f, r in part.items()}
    return {f: found[f] for f, _ in entries if f in found}


SAMPLE_ROWS = 24     # a unit explanation reads at most this many usable lines of a file
SAMPLE_TEXT = 160    # ... each cut to this many characters
SAMPLE_ROW_OVERHEAD = 24  # JSON the unit packet adds around each compact row (ref, line number, separators)


def sample_bytes(repo, entries):
    """{path: bytes a unit sample takes from the file}: its usable lines (six or more characters), evenly spread, at most 24."""
    cost = {}
    for file, text, _ in stream(repo, entries):
        lines = [line.strip() for line in text.splitlines() if len(line.strip()) >= 6]
        spread = sorted({i * (len(lines) - 1) // (SAMPLE_ROWS - 1) for i in range(SAMPLE_ROWS)}) if len(lines) > SAMPLE_ROWS else range(len(lines))
        cost[file] = sum(len(lines[i][:SAMPLE_TEXT].encode()) + SAMPLE_ROW_OVERHEAD for i in spread) + len(file) + 40
    return cost


def pack(row):
    """The compact stored form of a scan row (empty parts are left out)."""
    out = {'k': row['kind'], 'n': row['lines'], 'z': row['size']}
    if row['windows']:
        out.update(w=row['windows'], c=row['classes'], s=row['sent'])
        if row['clips']:
            out['l'] = [[n, o] for n, o in row['clips'].items()]
        if row['truncated']:
            out['t'] = 1
    return out


def unpack(row):
    return {'kind': row['k'], 'lines': row['n'], 'size': row['z'], 'windows': row.get('w', []), 'classes': row.get('c', {}),
            'sent': row.get('s', 0), 'clips': {n: o for n, o in row.get('l', [])}, 'truncated': bool(row.get('t'))}


def window_rows(lines, spans, clips):
    """The numbered rows of one file that its windows keep; long lines are clipped around the signal they carry.
    spans: [[first, last], ...] (1-based, inclusive); clips: {line: character offset of the clipped segment}."""
    keep = window_lines(spans)
    rows = []
    for row in lines:
        if row['line'] not in keep:
            continue
        text = row['text']
        if len(text) > LONG_LINE:
            offset = clips.get(row['line'], 0)
            row = {'line': row['line'], 'text': text[offset:offset + LONG_LINE], **({'offset': offset} if offset else {})}
        rows.append(row)
    return rows


if __name__ == '__main__':
    entries = [(f, o.encode()) for f, o in json.load(sys.stdin)]
    print(json.dumps({f: pack(r) for f, r in _scan_serial(sys.argv[1], entries, int(sys.argv[2])).items()}))
