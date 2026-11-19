"""Local, commit-bound declarations and statically resolvable module imports."""
import ast
import os
import posixpath
from functools import lru_cache
from itertools import zip_longest
from pathlib import PurePosixPath
import re
import subprocess
import warnings

import service_flow
import default_flow
from express_routes import app_factories, express_routes, factory_routes

MAX_FILES = 2048
MAX_BYTES = 64 * 1024 * 1024
MAX_FILE_BYTES = 512 * 1024
MAX_DECLARATIONS = 20_000
MAX_IMPORTS = 20_000


VERSION = 6
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
    stack = [(root, '')]
    while stack:
        node, prefix = stack.pop()
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
    return rows, edges, unresolved, service_flow.javascript_requests(root, file), default_flow.sdk_facts(root,file), express_routes(root,file), app_factories(root,file)


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


def build(repo, commit, excluded=None):
    if not re.fullmatch(r'(?:[a-f0-9]{40}|[a-f0-9]{64})', commit):
        raise ValueError('Structure indexing requires a full commit ID')
    if excluded is None:
        from analysis_run import _secret as excluded
    env = {**os.environ, 'GIT_NO_LAZY_FETCH': '1'}
    git = ['git', '-C', repo]
    tree = subprocess.check_output([*git, 'ls-tree', '-rlz', '--full-tree', commit], env=env)
    candidates = {}
    languages = {}
    unsupported = 0
    denied = set()
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
            unsupported += 1
            continue
        if excluded(file):
            denied.add(oid)
            continue
        suffix = PurePosixPath(file).suffix
        lang = 'python' if suffix == '.py' else 'javascript' if suffix in JS_EXTENSIONS else 'typescript' if suffix in TS_EXTENSIONS else 'html' if suffix in ('.html','.htm') else None
        if lang:
            languages[file] = lang
            candidates[file] = (oid, int(size))
        else:
            unsupported += 1

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
    sdk_modules = {}
    factory_modules = {}
    imports = []
    parsed = set()
    consumed = declarations = unresolved = 0
    selected = []
    truncated = False
    # A large repository can exhaust the file limit within a single language.
    groups = [[(f, e) for f, e in candidates.items() if languages[f] == lang]
              for lang in LANGUAGES]
    ordered = (pair for group in zip_longest(*groups) for pair in group if pair is not None)
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
            rows, edges, missing, file_requests, sdk, server_routes, factories = script
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
                tree = ast.parse(raw)
        except (SyntaxError, ValueError, UnicodeError, RecursionError):
            continue
        parsed.add(file)
        python_modules[file]=default_flow.python_facts(tree)
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
    resolved = [edge for edge in imports if edge['target'] in parsed]
    routes.extend(factory_routes(factory_modules,resolved))
    routes.extend(service_flow.mounted_routes(external,resolved))
    routes.extend(default_flow.default_routes(python_modules,external['routers']))
    requests.extend(default_flow.sdk_requests(sdk_modules))
    unresolved += len(imports) - len(resolved)
    coverage = {'candidate_files': len(candidates), 'indexed_files': len(files),
                'skipped_files': len(candidates) - len(files), 'unsupported_files': unsupported,
                'unresolved_imports': unresolved, 'truncated': truncated}
    coverage['languages'] = {lang:{'candidate_files':sum(languages[f]==lang for f in candidates),
                                   'indexed_files':sum(languages[f]==lang for f in parsed)}
                             for lang in LANGUAGES}
    coverage['unavailable_languages'] = sorted(unavailable)
    return {'version':VERSION,'commit': commit, 'files': files, 'imports': resolved, 'coverage': coverage,
            'service_flow':service_flow.connect(routes, requests)}
