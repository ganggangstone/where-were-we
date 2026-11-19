"""Local, commit-bound declarations and statically resolvable module imports."""
import ast
import json
import os
import posixpath
from collections import defaultdict, deque
from functools import lru_cache
from pathlib import PurePosixPath
import re
import subprocess
import warnings

import service_flow
import default_flow
import react_actions
import sqlmodel_steps
from express_routes import app_factories, express_routes, factory_routes

MAX_FILES = 2048
MAX_BYTES = 64 * 1024 * 1024
MAX_FILE_BYTES = 512 * 1024
MAX_DECLARATIONS = 20_000
MAX_IMPORTS = 20_000


VERSION = 14
JS_EXTENSIONS = {'.js', '.jsx', '.mjs', '.cjs'}
LANGUAGES = ('python', 'javascript', 'typescript', 'html')
TS_EXTENSIONS = {'.ts', '.tsx', '.mts', '.cts'}
SUFFIXES = JS_EXTENSIONS | TS_EXTENSIONS


@lru_cache(maxsize=3)
def _parser(grammar):
    from tree_sitter import Language, Parser
    if grammar == 'javascript':
        from tree_sitter_javascript import language
    elif grammar == 'tsx':
        from tree_sitter_typescript import language_tsx as language
    else:
        from tree_sitter_typescript import language_typescript as language
    return Parser(Language(language()))


def _script(file, raw, candidates):
    suffix = PurePosixPath(file).suffix
    grammar = 'javascript' if suffix in JS_EXTENSIONS else 'tsx' if suffix == '.tsx' else 'typescript'
    try:
        raw.decode('utf-8')
    except UnicodeDecodeError:
        return None
    root = _parser(grammar).parse(raw).root_node
    if root.has_error:
        return None
    kinds = {'function_declaration':'function', 'generator_function_declaration':'function',
             'class_declaration':'class', 'abstract_class_declaration':'class', 'method_definition':'method',
             'interface_declaration':'interface', 'type_alias_declaration':'type', 'enum_declaration':'enum'}
    rows, edges, unresolved = [], [], 0
    cjs = suffix == '.cjs'
    direct_requires = []
    shadowed_require = False
    stack = [(root, '')]
    while stack:
        node, prefix = stack.pop()
        if cjs and (node.type == 'identifier' or node.type == 'shorthand_property_identifier_pattern') and node.text == b'require':
            parent = node.parent
            if parent.type == 'call_expression' and parent.child_by_field_name('function') == node:
                args = parent.child_by_field_name('arguments')
                values = [arg for arg in args.named_children if arg.type != 'comment'] if args else []
                if len(values) == 1 and values[0].type == 'string':
                    direct_requires.append(values[0])
            else:
                # A renamed loader, shadowed binding or assignment clouds provenance.
                shadowed_require = True
        kind = kinds.get(node.type)
        if node.type == 'variable_declarator':
            value = node.child_by_field_name('value')
            if value and value.type in ('arrow_function', 'function_expression', 'generator_function'):
                kind = 'function'
                if any(c.type == 'async' for c in value.children):
                    kind = 'async_function'
        name = node.child_by_field_name('name') if kind else None
        if name and name.type in ('identifier', 'type_identifier', 'property_identifier', 'private_property_identifier'):
            if kind == 'function' and any(c.type == 'async' for c in node.children):
                kind = 'async_function'
            qualified = prefix + name.text.decode()
            rows.append({'name':qualified, 'kind':kind, 'line':name.start_point.row + 1})
            prefix = qualified + '.'
        if node.type in ('import_statement', 'export_statement'):
            source = node.child_by_field_name('source')
            if source:
                spec = source.text[1:-1].decode()
                targets = set()
                if spec.startswith(('./', '../')) and chr(92) not in spec:
                    base = posixpath.normpath(posixpath.join(posixpath.dirname(file), spec))
                    if base in candidates and PurePosixPath(base).suffix in SUFFIXES:
                        targets.add(base)
                    elif not PurePosixPath(base).suffix:
                        targets = {path for ext in SUFFIXES for path in (base + ext, base + '/index' + ext) if path in candidates}
                if len(targets) == 1:
                    target = targets.pop()
                    if target != file:
                        edges.append({'file':file, 'line':source.start_point.row + 1, 'target':target})
                else:
                    unresolved += 1
        stack.extend((child, prefix) for child in reversed(node.named_children))
    if not shadowed_require:
        for argument in direct_requires:
            spec = argument.text[1:-1].decode()
            target = posixpath.normpath(posixpath.join(posixpath.dirname(file),spec))
            if not spec.startswith(('./','../')) or chr(92) in spec or not spec.endswith('.cjs') or target not in candidates:
                unresolved += 1
            elif target != file:
                edges.append({'file':file,'line':argument.start_point.row+1,'target':target})
    requests=service_flow.javascript_requests(root,file)
    return rows, edges, unresolved, requests, default_flow.sdk_facts(root,file), express_routes(root,file), app_factories(root,file), react_actions.facts(root,requests)


def _python_tree(raw):
    try:
        return ast.parse(raw)
    except SyntaxError as error:
        # The bundled 3.13 parser predates PEP 758. Add the optional parentheses
        # only to the simple exception list on the line rejected by that parser.
        if 'multiple exception types' not in error.msg or not error.lineno:raise
        lines=raw.splitlines(keepends=True)
        index=error.lineno-1
        pattern=rb'^([ \t]*except\*?[ \t]+)([A-Za-z_]\w*(?:[ \t]*,[ \t]*[A-Za-z_]\w*)+)([ \t]*:)'
        revised,n=re.subn(pattern,rb'\1(\2)\3',lines[index],count=1)
        if not n:raise
        lines[index]=revised
        return ast.parse(b''.join(lines))


def _blobs(git, env, selected):
    if not selected:
        return
    with subprocess.Popen([*git, 'cat-file', '--batch'], env=env,
                          stdin=subprocess.PIPE, stdout=subprocess.PIPE) as reader:
        try:
            for file, (oid, size) in selected:
                reader.stdin.write(oid + b'\n')
                reader.stdin.flush()
                if reader.stdout.readline().split() != [oid, b'blob', str(size).encode()]:
                    raise ValueError('Pinned structure source is unavailable')
                raw = reader.stdout.read(size)
                if len(raw) != size or reader.stdout.read(1) != b'\n':
                    raise ValueError('Pinned structure source was incomplete')
                yield file, raw
        finally:
            reader.stdin.close()
            reader.stdout.close()


_SUPPORT_DIRS = frozenset({
    'test','tests','__tests__','fixture','fixtures','__fixtures__','testdata','__snapshots__',
    'example','examples','demo','demos','docs','bench','benchmark','benchmarks','evals',
    'node_modules','vendor','dist','build','coverage','generated','compiled',
})


def _interleave(groups):
    queue=deque(iter(group) for group in groups)
    while queue:
        group=queue.popleft()
        try:
            yield next(group)
        except StopIteration:
            continue
        queue.append(group)


def _spread_paths(items, depth=0):
    # Round-robin through directory levels. A giant early package or fixture
    # cannot take all the slots before a sibling package contributes a file.
    if depth==8 or len(items)<2:return items
    local=[]
    buckets=defaultdict(list)
    for item in items:
        parts=item[0].split('/',depth+1)
        if len(parts)<=depth+1:local.append(item)
        else:buckets[parts[depth]].append(item)
    return _interleave([local,*(_spread_paths(buckets[k],depth+1) for k in sorted(buckets))])


def _bounded_order(items):
    primary=[]
    support=[]
    for file,entry in sorted(items):
        parts=file.lower().split('/')
        auxiliary=any(p.startswith('.') or p in _SUPPORT_DIRS for p in parts[:-1])
        auxiliary |= bool(re.search(r'(?:^test_|_test\.|\.(?:spec|test)\.)',parts[-1]))
        (support if auxiliary else primary).append((file,entry))
    # Reserve a slot for supporting examples and tests in each group of eight.
    main_iter=iter(_spread_paths(primary))
    aux_iter=iter(_spread_paths(support))
    while True:
        for _ in range(7):
            item=next(main_iter,None)
            if item is None:
                yield from aux_iter
                return
            yield item
        item=next(aux_iter,None)
        if item is None:
            yield from main_iter
            return
        yield item


def _manifest_lines(raw):
    # Record literal, single-line values only. Repeated values link to the manifest as a whole.
    literals = {}
    for line, text in enumerate(raw.splitlines(), 1):
        for match in re.finditer(rb"""(?:[:=]\s*)("[^"\\]*"|'[^'\\]*')""", text):
            value = match[1][1:-1]
            literals[value] = None if value in literals else line
    return literals


def _cli_entries(git, env, manifests, tracked, files):
    """Resolve tracked package commands without running an installer or importing code."""
    declarations = {row['file']: row['declarations'] for row in files}
    eligible = [(f, entry) for f, entry in manifests.items() if entry[1] <= 64 * 1024]
    selected = sorted(eligible, key=lambda item: (item[0].count('/'), item[0]))[:64]
    result = []
    for file, raw in _blobs(git, env, selected):
        folder = posixpath.dirname(file)
        lines_by_value = _manifest_lines(raw)
        if posixpath.basename(file) == 'package.json':
            try:
                package = json.loads(raw)
            except (ValueError, UnicodeError, RecursionError):
                continue
            if not isinstance(package, dict):
                continue
            bins = package.get('bin')
            if isinstance(bins, str) and isinstance(package.get('name'), str):
                bins = {package['name'].rsplit('/', 1)[-1]: bins}
            if not isinstance(bins, dict):
                continue
            for command, path in bins.items():
                if not command or not isinstance(path, str):
                    continue
                relative = path.removeprefix('./')
                if any(part in ('', '.', '..') for part in relative.split('/')) or chr(92) in relative:
                    continue
                target = posixpath.join(folder, relative)
                if target in tracked:
                    row = dict(command=command, kind='npm_bin', file=file, target=target)
                    line = lines_by_value.get(path.encode()) if path.isascii() else None
                    if line:
                        row['line'] = line
                    result.append(row)
        else:
            try:
                import tomllib
                project = tomllib.loads(raw.decode()).get('project')
            except (ImportError, ValueError, UnicodeError, RecursionError):
                continue
            scripts = project.get('scripts') if isinstance(project, dict) else None
            if not isinstance(scripts, dict):
                continue
            for command, spec in scripts.items():
                if not command or not isinstance(spec, str):
                    continue
                parts = spec.split(':')
                if len(parts) != 2 or not all(p.isidentifier() for s in parts for p in s.split('.')):
                    continue
                module, symbol = parts
                stem = module.replace('.', '/')
                matches = [path for base in (folder, posixpath.join(folder, 'src'))
                           for tail in (stem + '.py', stem + '/__init__.py')
                           if (path := posixpath.join(base, tail)) in tracked]
                if len(matches) != 1:
                    continue
                target = matches[0]
                row = dict(command=command, kind='python_script', file=file, target=target, symbol=symbol)
                line = lines_by_value.get(spec.encode())
                if line:
                    row['line'] = line
                lines = [d['line'] for d in declarations.get(target, []) if d['name'] == symbol]
                if len(lines) == 1:
                    row['target_line'] = lines[0]
                result.append(row)
    return result, len(selected)


def build(repo, commit, excluded=None, *, only_file=None):
    if not re.fullmatch(r'(?:[a-f0-9]{40}|[a-f0-9]{64})', commit):
        raise ValueError('Structure indexing requires a full commit ID')
    if only_file is not None:
        if not isinstance(only_file,str) or any(x in ('','.','..') for x in only_file.split('/')) or '\x00' in only_file:
            raise ValueError('Choose a repository-relative tracked file')
        file_result={'commit':commit,'file':only_file,'language':None,'declarations':[],'imports':[],
                     'status':'unavailable','coverage':{'indexed_files':0,'unresolved_imports':0,'truncated':False}}
    if excluded is None:
        from analysis_run import _secret as excluded
    env = {**os.environ, 'GIT_NO_LAZY_FETCH': '1'}
    git = ['git', '-C', repo]
    tree = subprocess.check_output([*git, 'ls-tree', '-rlz', '--full-tree', commit], env=env)
    candidates = {}
    languages = {}
    unsupported = 0
    denied = set()
    tracked = {}
    manifests = {}
    unsupported_oid = None
    for entry in tree.split(b'\0'):
        if not entry:
            continue
        meta, raw_file = entry.split(b'\t', 1)
        mode, kind, oid, size = meta.split()
        if mode not in (b'100644', b'100755') or kind != b'blob':
            continue
        try:
            file = raw_file.decode()
        except UnicodeDecodeError:
            # Git permits arbitrary path bytes. A private directory can contain a
            # non-UTF-8 filename whose blob also appears at an eligible path.
            if excluded(os.fsdecode(raw_file)):
                denied.add(oid)
                continue
            unsupported += 1
            continue
        if excluded(file):
            denied.add(oid)
            continue
        if only_file is None:
            tracked[file] = oid
            if posixpath.basename(file) in ('package.json', 'pyproject.toml'):
                manifests[file] = (oid, int(size))
        suffix = PurePosixPath(file).suffix
        lang = 'python' if suffix == '.py' else 'javascript' if suffix in JS_EXTENSIONS else 'typescript' if suffix in TS_EXTENSIONS else 'html' if suffix in ('.html','.htm') else None
        if lang:
            languages[file] = lang
            candidates[file] = (oid, int(size))
        else:
            unsupported += 1
            if file == only_file:
                unsupported_oid = oid

    candidates = {file: entry for file, entry in candidates.items() if entry[0] not in denied}

    def module_file(base, roots):
        matches = {file for root in roots for suffix in ('.py', '/__init__.py')
                   if (file := root + base + suffix) in candidates}
        return next(iter(matches)) if len(matches) == 1 else None

    files = []
    routes = []
    requests = []
    external = {'routers':{}, 'mounts':[]}
    python_modules = {}
    sql_modules = {}
    sdk_modules = {}
    action_modules = {}
    factory_modules = {}
    imports = []
    parsed = set()
    consumed = declarations = unresolved = 0
    selected = []
    truncated = False
    # A large repository can exhaust the file limit within a single language.
    groups = [[(f, e) for f, e in candidates.items() if languages[f] == lang]
              for lang in LANGUAGES]
    bounded = len(candidates)>MAX_FILES or sum(size for _,size in candidates.values())>MAX_BYTES
    if only_file is not None:
        if only_file not in candidates:
            if unsupported_oid and unsupported_oid not in denied:
                file_result['status'] = 'unsupported'
            return file_result
        file_result['language']=languages[only_file]
        if candidates[only_file][1]>MAX_FILE_BYTES:
            file_result['status']='too_large'
            file_result['coverage']['truncated']=True
            return file_result
        ordered=[(only_file,candidates[only_file])]
    else:
        if bounded:groups=[_bounded_order(items) for items in groups]
        ordered=_interleave(groups)
    for file, entry in ordered:
        size = entry[1]
        if size > MAX_FILE_BYTES or consumed + size > MAX_BYTES or len(selected) >= MAX_FILES:
            truncated = True
            continue
        selected.append((file, entry))
        consumed += size
    unavailable = set()
    for file, raw in _blobs(git, env, selected):
        language = languages[file]
        if language == 'html':
            try:
                requests.extend(service_flow.html_requests(raw,file,_parser('javascript').parse))
            except ImportError:
                unavailable.add(language)
                continue
            files.append({'file':file, 'language':'html', 'declarations':[]})
            parsed.add(file)
            continue
        if language != 'python':
            try:
                script = _script(file, raw, candidates)
            except ImportError:
                unavailable.add(language)
                continue
            if script is None:
                continue
            rows, edges, missing, file_requests, sdk, server_routes, factories, actions = script
            if any(actions):action_modules[file]=actions
            if any(factories):factory_modules[file]=factories
            routes.extend(server_routes)
            if sdk:sdk_modules[file]=sdk
            requests.extend(file_requests)
            unresolved += missing
            limited_rows = rows[:MAX_DECLARATIONS - declarations]
            limited_edges = edges[:MAX_IMPORTS - len(imports)]
            truncated |= len(rows) != len(limited_rows) or len(edges) != len(limited_edges)
            imports.extend(limited_edges)
            declarations += len(limited_rows)
            files.append({'file':file, 'language':language, 'declarations':limited_rows})
            parsed.add(file)
            continue
        try:
            with warnings.catch_warnings():
                warnings.simplefilter('ignore', SyntaxWarning)
                tree = _python_tree(raw)
        except (SyntaxError, ValueError, UnicodeError, RecursionError):
            continue
        parsed.add(file)
        python_modules[file]=default_flow.python_facts(tree)
        sql_modules[file]=sqlmodel_steps.facts(tree)
        routes.extend(service_flow.python_routes(tree, file, external))
        rows = []
        stack = [(tree, '')]
        while stack:
            node, prefix = stack.pop()
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                prefix += node.name
                if declarations < MAX_DECLARATIONS:
                    kind = 'class' if isinstance(node, ast.ClassDef) else 'async_function' if isinstance(node, ast.AsyncFunctionDef) else 'function'
                    rows.append({'kind': kind, 'name': prefix, 'line': node.lineno})
                    declarations += 1
                else:
                    truncated = True
                prefix += '.'
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                roots = ('', 'src/')
                if isinstance(node, ast.Import):
                    modules = [item.name for item in node.names]
                else:
                    # 'from . import x' may name a package attribute or a submodule.
                    if not node.module:
                        unresolved += 1
                        continue
                    modules = [node.module]
                    if node.level:
                        parents = PurePosixPath(file).parents
                        if node.level > len(parents) or not all(
                            str(parent / '__init__.py') in candidates for parent in list(parents)[:node.level]
                        ):
                            unresolved += 1
                            continue
                        root = parents[node.level - 1].as_posix()
                        roots = ('' if root == '.' else root + '/',)
                for module in modules:
                    target = module_file(module.replace('.', '/'), roots)
                    if not target:
                        unresolved += 1
                    elif target != file:
                        if len(imports) < MAX_IMPORTS:
                            imports.append({'file': file, 'line': node.lineno, 'target': target})
                        else:
                            truncated = True
            stack.extend((child, prefix) for child in reversed(list(ast.iter_child_nodes(node))))
        files.append({'file': file, 'language':'python', 'declarations': rows})
    if only_file is not None:
        # Imports point to unique eligible paths in the same tree. Their blobs are not read.
        if files:
            file_result.update(status='indexed',declarations=files[0]['declarations'],imports=imports)
        elif not unavailable:
            file_result['status']='unparsed'
        file_result['coverage']={'indexed_files':len(files),'unresolved_imports':unresolved,'truncated':truncated}
        return file_result
    resolved = [edge for edge in imports if edge['target'] in parsed]
    routes.extend(factory_routes(factory_modules,resolved))
    routes.extend(service_flow.mounted_routes(external,resolved))
    routes.extend(default_flow.default_routes(python_modules,external['routers']))
    requests.extend(default_flow.sdk_requests(sdk_modules))
    react_actions.attach(action_modules,resolved,requests)
    sqlmodel_steps.attach(sql_modules,routes)
    unresolved += len(imports) - len(resolved)
    coverage = {'candidate_files': len(candidates), 'indexed_files': len(files),
                'skipped_files': len(candidates) - len(files), 'unsupported_files': unsupported,
                'unresolved_imports': unresolved, 'truncated': truncated}
    coverage['languages'] = {lang:{'candidate_files':sum(languages[f]==lang for f in candidates),
                                   'indexed_files':sum(languages[f]==lang for f in parsed)}
                             for lang in LANGUAGES}
    coverage['unavailable_languages'] = sorted(unavailable)
    if bounded:coverage['selection']='bounded_directory_sample'
    eligible_manifests = {path: entry for path, entry in manifests.items() if entry[0] not in denied}
    cli_entries, manifests_read = _cli_entries(git, env, eligible_manifests, {f for f, oid in tracked.items() if oid not in denied}, files)
    coverage['cli_manifests_read'] = manifests_read
    coverage['cli_manifests_total'] = len(eligible_manifests)
    return {'version':VERSION,'commit': commit,'cli_entries':cli_entries, 'files': files, 'imports': resolved, 'coverage': coverage,
            'service_flow':service_flow.connect(routes, requests)}
