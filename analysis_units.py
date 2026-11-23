"""AI-free catalog of the analysis units of one pinned repository.

A unit is the smallest thing a user can read as one explanation: a request path group,
a screen, a program, a workspace package, a command family, or a plain folder. Units
come from the local structure index only, so the same catalog applies to web services,
libraries and command-line tools. Every tracked file is either inside a unit or counted
under one named exclusion reason, so missing coverage is visible instead of implied.
Files outside the structure index (documents, configuration, scripts, languages the
indexer does not read, files past its limit) are plain files: they stay in folder units
and are sampled from their text, so only secrets, binaries and oversized files are excluded.

Folders that hold only documents, data, tests or vendored code become `local` units: they are
counted and listed from the local read, and the AI explains them only when the user chooses to
send every text file. Import edges between units are kept as links, so the board can draw how
units connect without asking the AI.
"""
import hashlib
import posixpath
from collections import defaultdict

VERSION = 3
FOLDER_MAX_FILES = 12
LOCAL_MAX_FILES = 200   # a local unit costs no call, so one card can stand for a whole documents or tests area
LINKS_PER_UNIT = 6
STORED_FILES = 64
KINDS = ('route', 'package', 'cli', 'screen', 'program', 'folder')


def _route_files(service, indexed):
    groups = {}
    for group in service.get('feature_groups', []):
        files = groups.setdefault(group['resource'], set())
        for i in group['connection_indexes']:
            edge = service['connections'][i]
            files.update(site['file'] for site in (edge.get('client'), edge.get('server')) if site)
    for group in service.get('registered_route_groups', []):
        files = groups.setdefault(group['resource'], set())
        for i in group['registered_route_indexes']:
            route = service['registered_routes'][i]
            if route.get('server'):
                files.add(route['server']['file'])
    return {name: sorted(f for f in files if f in indexed) for name, files in groups.items()}


def _under(indexed, prefixes):
    prefixes = [p.strip('/') for p in prefixes if isinstance(p, str) and p.strip('/') and not p.startswith('..')]
    return sorted(f for f in indexed if any(f == p or f.startswith(p + '/') for p in prefixes))


def _folders(files, limit=FOLDER_MAX_FILES):
    units = []

    def emit(prefix, members, direct_only):
        base = (prefix.rstrip('/') or '(root)') + ('/*' if direct_only and prefix else '')
        members = sorted(members)
        # A flat folder cannot split by directory; consecutive name ranges keep every unit small.
        for start in range(0, len(members), limit):
            part = members[start:start + limit]
            name = base if len(members) <= limit else f'{base} [{start + 1}-{start + len(part)}]'
            units.append({'id': 'folder:' + name, 'kind': 'folder', 'name': name, 'files': part})

    def split(prefix, members):
        subtree = defaultdict(list)
        direct = []
        for file in members:
            rest = file[len(prefix):]
            if '/' in rest:
                subtree[rest.split('/', 1)[0]].append(file)
            else:
                direct.append(file)
        if not subtree or (prefix and len(members) <= limit):
            emit(prefix, members, False)
            return
        if direct:
            emit(prefix, direct, True)
        for name, rows in sorted(subtree.items()):
            split(prefix + name + '/', rows)

    if files:
        split('', sorted(files))
    return units


def catalog(index, tracked, exclusion, screens=(), programs=(), local=None):
    """index: pinned structure index. tracked: {path: bytes} of regular tracked blobs.
    exclusion(path, size) -> reason or None. screens/programs come from the saved map when it exists.
    local(path) -> True for a document, data, test or vendored file that is read locally only."""
    eligible = {file for file, size in tracked.items() if not exclusion(file, size)}
    indexed = {row['file'] for row in index.get('files', []) if row['file'] in eligible}
    weight = defaultdict(int)
    for row in index.get('files', []):
        weight[row['file']] += len(row.get('declarations', []))
    incoming = defaultdict(int)
    imports = defaultdict(list)
    for edge in index.get('imports', []):
        if edge['file'] in indexed and edge['target'] in indexed:
            incoming[edge['target']] += 1
            imports[edge['file']].append(edge['target'])
    rank = lambda files: sorted(set(files), key=lambda f: (-weight[f] - incoming[f], f))
    units = []
    owned = {}

    def add(kind, key, name, files, **extra):
        files = rank(files)
        unit_id = kind + ':' + key
        if not files or unit_id in owned:
            return
        owned[unit_id] = set(files)
        units.append({'id': unit_id, 'kind': kind, 'name': name, 'file_count': len(files),
                      'digest': hashlib.sha1('\0'.join(sorted(files)).encode()).hexdigest()[:16],
                      'files': files[:STORED_FILES], **extra})

    for resource, files in sorted(_route_files(index.get('service_flow') or {}, indexed).items()):
        add('route', resource, resource, files, resource=resource)
    package_files = set()
    for package in index.get('workspace_packages', []):
        folder = posixpath.dirname(package.get('file', ''))
        if folder:
            members = _under(eligible, [folder])
            package_files.update(members)
            add('package', package['name'], package['name'], members)
    families = defaultdict(set)
    for entry in index.get('cli_entries', []):
        families[entry['command'].split()[0]].update(f for f in (entry.get('file'), entry.get('target')) if f in indexed)
    for family, files in sorted(families.items()):
        add('cli', family, family, files)
    for screen in screens:
        file = screen.get('file') if isinstance(screen, dict) else None
        if file in indexed and not screen.get('redirect'):
            add('screen', file, screen.get('heading') or screen.get('component') or screen.get('path') or file,
                [file, *imports[file][:3]], path=screen.get('path'))
    for program in programs:
        inside = _under(eligible, program.get('code') or [])
        if inside and not set(inside) <= package_files:
            add('program', program['id'], program.get('name') or program['id'], inside)
    claimed = set().union(*owned.values()) if owned else set()
    rest = eligible - claimed
    aside = {f for f in rest if local and local(f)}
    for unit in _folders(sorted(rest - aside)):
        add('folder', unit['id'][7:], unit['name'], unit['files'])
    for unit in _folders(sorted(aside), LOCAL_MAX_FILES):
        # The name says what it is, so a documents area never collides with the code folder beside it.
        add('folder', 'local:' + unit['id'][7:], unit['name'], unit['files'], reading='local')
    in_units = set().union(*owned.values()) if owned else set()
    # Import edges between units, strongest first. A file in several units links each of them.
    owners = defaultdict(list)
    for unit_id, files in owned.items():
        for file in files:
            owners[file].append(unit_id)
    edges = defaultdict(lambda: defaultdict(int))
    for file, targets in imports.items():
        for target in targets:
            for a in owners[file]:
                for b in owners[target]:
                    if a != b:
                        edges[a][b] += 1
    links = {a: [[b, n] for b, n in sorted(row.items(), key=lambda x: (-x[1], x[0]))[:LINKS_PER_UNIT]] for a, row in sorted(edges.items())}
    reasons = defaultdict(int)
    for file, size in tracked.items():
        if file not in eligible:
            reasons[exclusion(file, size)] += 1
    counts = index.get('coverage', {})
    return {'version': VERSION, 'units': units, 'links': links,
            'coverage': {'tracked': len(tracked), 'indexed': len(indexed), 'plain': len(eligible) - len(indexed),
                         'in_units': len(in_units), 'local': len(aside), 'excluded': {k: v for k, v in sorted(reasons.items()) if v},
                         'truncated': bool(counts.get('truncated')),
                         'index_candidates': counts.get('candidate_files'), 'index_skipped': counts.get('skipped_files', 0)}}
