"""AI-free catalog of the analysis units of one pinned repository.

A unit is the smallest thing a user can read as one explanation: a request path group,
a screen, a program, a workspace package, a command family, or a plain folder. Units
come from the local structure index only, so the same catalog applies to web services,
libraries and command-line tools. Every tracked file is either inside a unit or counted
under one named exclusion reason, so missing coverage is visible instead of implied.
Files outside the structure index (documents, configuration, scripts, languages the
indexer does not read, files past its limit) are plain files: they stay in folder units
and are sampled from their text, so only secrets, binaries and oversized files are excluded.
"""
import hashlib
import posixpath
from collections import defaultdict

VERSION = 2
FOLDER_MAX_FILES = 12
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


def _folders(files):
    units = []

    def emit(prefix, members, direct_only):
        base = (prefix.rstrip('/') or '(root)') + ('/*' if direct_only and prefix else '')
        members = sorted(members)
        # A flat folder cannot split by directory; consecutive name ranges keep every unit small.
        for start in range(0, len(members), FOLDER_MAX_FILES):
            part = members[start:start + FOLDER_MAX_FILES]
            name = base if len(members) <= FOLDER_MAX_FILES else f'{base} [{start + 1}-{start + len(part)}]'
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
        if not subtree or (prefix and len(members) <= FOLDER_MAX_FILES):
            emit(prefix, members, False)
            return
        if direct:
            emit(prefix, direct, True)
        for name, rows in sorted(subtree.items()):
            split(prefix + name + '/', rows)

    if files:
        split('', sorted(files))
    return units


def catalog(index, tracked, exclusion, screens=(), programs=()):
    """index: pinned structure index. tracked: {path: bytes} of regular tracked blobs.
    exclusion(path, size) -> reason or None. screens/programs come from the saved map when it exists."""
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
    for unit in _folders(sorted(eligible - claimed)):
        add('folder', unit['id'][7:], unit['name'], unit['files'])
    in_units = set().union(*owned.values()) if owned else set()
    reasons = defaultdict(int)
    for file, size in tracked.items():
        if file not in eligible:
            reasons[exclusion(file, size)] += 1
    counts = index.get('coverage', {})
    return {'version': VERSION, 'units': units,
            'coverage': {'tracked': len(tracked), 'indexed': len(indexed), 'plain': len(eligible) - len(indexed),
                         'in_units': len(in_units), 'excluded': {k: v for k, v in sorted(reasons.items()) if v},
                         'truncated': bool(counts.get('truncated')),
                         'index_candidates': counts.get('candidate_files'), 'index_skipped': counts.get('skipped_files', 0)}}
