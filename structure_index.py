"""Local, commit-bound declarations and statically resolvable module imports."""
import ast
import json
import os
import posixpath
from collections import Counter, defaultdict, deque
from functools import lru_cache
from pathlib import PurePosixPath
import re
import subprocess
import warnings

import next_routes
import cobra_commands
import service_flow
import default_flow
import react_actions
import sqlmodel_steps
from express_routes import app_factories, express_routes, factory_routes

MAX_DIRECTORY_FILES = 128
MAX_DIRECTORY_BYTES = 4 * 1024 * 1024
MAX_FILES = 2048
MAX_BYTES = 64 * 1024 * 1024
MAX_FILE_BYTES = 512 * 1024
MAX_DECLARATIONS = 20_000
MAX_IMPORTS = 20_000


VERSION = 30
JS_EXTENSIONS = {'.js', '.jsx', '.mjs', '.cjs'}
LANGUAGES = ('python', 'javascript', 'typescript', 'html', 'go')
TS_EXTENSIONS = {'.ts', '.tsx', '.mts', '.cts'}
SUFFIXES = JS_EXTENSIONS | TS_EXTENSIONS


@lru_cache(maxsize=4)
def _parser(grammar):
    from tree_sitter import Language, Parser
    if grammar == 'go':
        from tree_sitter_go import language
    elif grammar == 'javascript':
        from tree_sitter_javascript import language
    elif grammar == 'tsx':
        from tree_sitter_typescript import language_tsx as language
    else:
        from tree_sitter_typescript import language_typescript as language
    return Parser(Language(language()))


def _script(file, raw, candidates, next_context=None):
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
    routes = express_routes(root,file)
    if next_context:
        routes.extend(next_routes.handlers(root, file, next_context))
    return rows, edges, unresolved, requests, default_flow.sdk_facts(root,file), routes, app_factories(root,file), react_actions.facts(root,requests)


def _go_structure(file, raw, module, directories, blocked):
    root = _parser('go').parse(raw).root_node
    if root.has_error or not any(n.type == 'package_clause' for n in root.named_children):
        return None
    rows, edges, packages, missing = [], [], [], 0
    paths = {}
    for decl in root.named_children:
        if decl.type == 'import_declaration':
            specs = [node for child in decl.named_children
                     for node in (child.named_children if child.type == 'import_spec_list' else [child])
                     if node.type == 'import_spec']
            for spec in specs:
                path = spec.child_by_field_name('path')
                name = path.text[1:-1].decode('utf-8', 'replace')
                members = ()
                if module and (name == module or name.startswith(module + '/')) and chr(92) not in name:
                    folder = '' if name == module else name[len(module) + 1:]
                    if (not folder or all(part not in ('', '.', '..') for part in folder.split('/'))) and not any(base == folder or folder.startswith(base + '/') for base in blocked):
                        members = directories.get(folder, ())
                if not members or posixpath.dirname(file) == folder:
                    missing += 1
                elif len(members) == 1:
                    paths[path.start_point.row + 1, name] = folder
                    edges.append({'file':file,'line':path.start_point.row + 1,'target':members[0]})
                else:
                    paths[path.start_point.row + 1, name] = folder
                    packages.append({'file':file,'line':path.start_point.row + 1,'package':name,
                                     'directory':folder or '.', 'member_count':len(members),'members':members[:8]})
            continue
        nodes = decl.named_children if decl.type == 'type_declaration' else [decl]
        for node in nodes:
            kind = {'function_declaration':'function','method_declaration':'method',
                    'type_spec':'type','type_alias':'type'}.get(node.type)
            if kind:
                name = node.child_by_field_name('name')
                if name:
                    rows.append({'kind':kind,'name':name.text.decode('utf-8','replace'),'line':name.start_point.row+1})
    return rows, edges, packages, missing, cobra_commands.facts(root, file, paths)


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


def _directory_coverage(candidates, parsed):
    """Summarize the same eligible Git paths used by the bounded sampler."""
    def top(file):
        folder, separator, _ = file.partition('/')
        return folder if separator else '.'
    totals = Counter(top(file) for file in candidates)
    indexed = Counter(top(file) for file in parsed)
    rows = [{'directory':folder,'candidate_files':count,'indexed_files':indexed[folder],
             'skipped_files':count-indexed[folder]} for folder,count in totals.items()]
    rows.sort(key=lambda row:(-row['skipped_files'],-row['candidate_files'],row['directory']))
    return {'directories':rows[:24],'directory_count':len(rows)}


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


def _plain_description(value):
    return (isinstance(value, str) and 8 <= len(value) <= 320 and value.isprintable()
            and not any(char in value for char in '<>[]`') and any(c.isalpha() for c in value))


def _project_description(git, env, candidates):
    for file, raw in _blobs(git, env, candidates):
        try:
            text = raw.decode('utf-8-sig')
            if file == 'package.json':
                package = json.loads(text)
                value = package.get('description') if isinstance(package, dict) else None
            elif file == 'pyproject.toml':
                import tomllib
                project = tomllib.loads(text).get('project')
                value = project.get('description') if isinstance(project, dict) else None
            else:
                # Only the introduction before a second heading or a code block is eligible.
                heading = False
                lines = text.splitlines()[:80]
                for index, line in enumerate(lines):
                    body = line.strip()
                    if not body:
                        continue
                    if body.startswith('#'):
                        if heading or not body.startswith('# '):
                            break
                        heading = True
                        continue
                    if re.fullmatch(r'[=-]{3,}', body):
                        continue
                    if index + 1 < len(lines) and re.fullmatch(r'[=-]{3,}', lines[index + 1].strip()):
                        if heading:
                            break
                        heading = True
                        continue
                    if body.startswith(('![', '[![')):
                        continue
                    if line != body or not body[0].isalnum() or not _plain_description(body):
                        break
                    return {'file':file, 'line':index + 1, 'text':body}
                continue
        except (ImportError, ValueError, UnicodeError, RecursionError):
            continue
        if _plain_description(value):
            if file == 'package.json':
                literal = r'"description"\s*:\s*' + re.escape(json.dumps(value, ensure_ascii=False))
            else:
                literal = r'^\s*description\s*=\s*(?:' + re.escape('"' + value + '"') + '|' + re.escape("'" + value + "'") + ')'
            matches = [n for n, source in enumerate(text.splitlines(), 1) if re.search(literal, source)]
            if len(matches) == 1:
                return {'file':file, 'line':matches[0], 'text':value}
    return None


def _documented_features(git, env, sources):
    """Read top-level Markdown bullets under an explicitly named capabilities heading."""
    labels = {'features', 'key features', 'capabilities', '기능', '주요 기능'}
    for file, raw in _blobs(git, env, sources):
        try:
            lines = raw.decode('utf-8-sig').splitlines()[:240]
        except UnicodeError:
            continue
        active = False
        fence = ''
        comment = False
        rows = []
        for index, line in enumerate(lines):
            if fence:
                if len(line.strip()) >= len(fence) and set(line.strip()) == {fence[0]}:
                    fence = ''
                continue
            if comment:
                comment = '-->' not in line
                continue
            if '<!--' in line:
                comment = '-->' not in line.split('<!--', 1)[1]
                continue
            marker = re.match(r'^ {0,3}(`{3,}|~{3,})', line)
            if marker:
                fence = marker[1]
                active = False
                continue
            heading = re.fullmatch(r'#{1,6}[ \t]+(.+?)\s*#*\s*', line)
            if heading:
                active = heading[1].casefold() in labels
                continue
            if not active or not line.strip():
                continue
            bullet = re.fullmatch(r'[-*+] (\S.*)', line)
            if not bullet:
                continue
            text = bullet[1]
            # A wrapped sentence needs all its lines to preserve the author's claim.
            following = lines[index + 1] if index + 1 < len(lines) else ''
            if following.strip() and not re.match(r'^(?:[-*+] |#{1,6} )', following):
                continue
            if (len(text) <= 320 and text.isprintable() and any(c.isalpha() for c in text)
                    and not any(c in text for c in '<>[]') and '://' not in text):
                rows.append({'file':file, 'line':index + 1, 'text':text})
                if len(rows) == 16:
                    break
        if rows:
            return rows
    return []


def _pnpm_patterns(raw):
    """Read only pnpm's plain block list of literal or single-segment wildcard globs."""
    try:
        lines = raw.decode('utf-8-sig').splitlines()
    except UnicodeError:
        return []
    headers = [i for i,line in enumerate(lines) if re.fullmatch(r'packages:[ \t]*(?:#.*)?',line)]
    if len(headers) != 1 or sum(bool(re.match(r'^packages\s*:',line)) for line in lines)!=1 or any(line.startswith(('---','...','<<:', '"packages"', "'packages'")) for line in lines):
        return []
    patterns = []
    for index in range(headers[0]+1,len(lines)):
        line = lines[index]
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        if not line.startswith((' ', '-')):
            break
        item = re.fullmatch(r""" *- +(['"]?)(!?[A-Za-z0-9_@.*!/-]+)\1\s*(?:#.*)?""",line)
        if not item or len(patterns)>=128:
            return []
        path = item[2].removeprefix('!')
        parts = path.removeprefix('./').split('/')
        if any(part in ('','.','..') or (part != '*' and not re.fullmatch(r'[A-Za-z0-9_@.-]+',part)) for part in parts):
            return []
        patterns.append((item[2].startswith('!'),parts,index+1))
    return patterns


def _package_workspace_patterns(raw):
    def unique(pairs):
        value = dict(pairs)
        if len(value) != len(pairs):
            raise ValueError('Duplicate manifest key')
        return value
    try:
        text = raw.decode('utf-8-sig')
        manifest = json.loads(text,object_pairs_hook=unique)
    except (ValueError, UnicodeError, RecursionError):
        return []
    if not isinstance(manifest,dict) or str(manifest.get('packageManager','')).startswith('pnpm@'):
        return []
    values = manifest.get('workspaces')
    declarations = list(re.finditer(r'"workspaces"\s*:\s*',text))
    if len(declarations)!=1:
        return []
    offset = declarations[0].end()
    decoder = json.JSONDecoder()
    if isinstance(values,dict):
        if manifest.get('private') is not True:
            return []
        _,end = decoder.raw_decode(text,offset)
        fields = list(re.finditer(r'"packages"\s*:\s*',text[offset:end]))
        if len(fields)!=1:
            return []
        offset += fields[0].end()
        values = values.get('packages')
    if not isinstance(values,list) or len(values)>128 or text[offset:offset+1]!='[':
        return []
    offset += 1
    patterns = []
    for value in values:
        if not isinstance(value,str):
            return []
        while text[offset] in ' \t\r\n,':
            offset += 1
        token,end = decoder.raw_decode(text,offset)
        if token != value:
            return []
        parts = value.removeprefix('./').split('/')
        if any(part in ('','.','..') or (part != '*' and not re.fullmatch(r'[A-Za-z0-9_@.-]+',part)) for part in parts):
            return []
        patterns.append((False,parts,text.count('\n',0,offset)+1))
        offset = end
    return patterns


def _workspace_packages(git,env,config,manifests):
    if not config:
        return [],0,[]
    workspace_file,entry = config
    raw = next(_blobs(git,env,[(workspace_file,entry)]))[1]
    patterns = _pnpm_patterns(raw) if workspace_file=='pnpm-workspace.yaml' else _package_workspace_patterns(raw)
    if not patterns:
        return [],0,[]
    matched = {}
    for file,entry in manifests.items():
        if file == 'package.json' or not file.endswith('/package.json'):
            continue
        parts = file.split('/')[:-1]
        if 'node_modules' in parts:
            continue
        hits = [(negative,line) for negative,pattern,line in patterns if len(parts)==len(pattern)
                and all(p==s or p=='*' and not s.startswith('.') for p,s in zip(pattern,parts))]
        if hits and not any(negative for negative,_ in hits):
            matched[file] = (entry,hits[0][1])
    selected = [(file,matched[file][0]) for file in sorted(matched) if matched[file][0][1]<=64*1024][:64]
    packages = []
    declared = []
    for file,raw in _blobs(git,env,selected):
        try:
            text = raw.decode('utf-8-sig')
            manifest = json.loads(text)
        except (UnicodeError,ValueError,RecursionError):
            continue
        if not isinstance(manifest,dict):
            continue
        name = manifest.get('name')
        if not isinstance(name,str) or not re.fullmatch(r'(?:@[a-z0-9_.-]+/)?[a-z0-9][a-z0-9._-]{0,213}',name):
            continue
        def field_line(key,value):
            literal = re.escape(json.dumps(key,ensure_ascii=False)) + r'\s*:\s*' + re.escape(json.dumps(value,ensure_ascii=False))
            rows = [n for n,line in enumerate(text.splitlines(),1) if re.search(literal,line)]
            return rows[0] if len(rows)==1 else None
        line = field_line('name',name)
        if not line:
            continue
        row = {'name':name,'directory':posixpath.dirname(file),'file':file,'line':line,
               'workspace':{'file':workspace_file,'line':matched[file][1]}}
        description = manifest.get('description')
        if _plain_description(description) and (where := field_line('description',description)):
            row.update(description=description,description_line=where)
        packages.append(row)
        coordinates = {}
        for number,source in enumerate(text.splitlines(),1):
            for hit in re.finditer(r'"([a-z0-9_@./-]+)"\s*:\s*"(workspace:[^"\\]*)"',source):
                key = hit.groups()
                coordinates[key] = number if key not in coordinates else None
        for kind in ('dependencies','devDependencies','peerDependencies','optionalDependencies'):
            group = manifest.get(kind)
            if not isinstance(group,dict):
                continue
            for target,spec in group.items():
                # Aliases and relative paths name a different resolution mechanism.
                if (target == name or not isinstance(spec,str) or
                        not re.fullmatch(r'workspace:(?:[~^*]|[~^]?\d+(?:\.\d+){0,2}(?:-[0-9A-Za-z.-]+)?)',spec)):
                    continue
                if (where := coordinates.get((target,spec))):
                    declared.append({'source':name,'target':target,'kind':kind,'specifier':spec,
                                     'file':file,'line':where})
    names = Counter(p['name'] for p in packages)
    links = []
    if len(packages) == len(matched):
        links = [d for d in declared if names[d['source']] == names[d['target']] == 1][:512]
    return packages,len(matched),links


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


def _directory_page(ordered, page, file_limit, byte_limit):
    """Partition pinned tree metadata first, then read only the requested page's blobs."""
    if type(page) is not int or page < 1:
        raise ValueError('Choose a positive directory page')
    current, count, size, oversized, eligible = 1, 0, 0, 0, 0
    selected = []
    for file, entry in ordered:
        length = entry[1]
        if length > min(MAX_FILE_BYTES, byte_limit):
            oversized += 1
            continue
        if count >= file_limit or size + length > byte_limit:
            current += 1
            count = size = 0
        if current == page:
            selected.append((file,entry))
        count += 1
        eligible += 1
        size += length
    if page > current:
        raise ValueError('Directory page is out of range')
    return selected, {'page':page, 'total_pages':current, 'selected_files':len(selected),
                      'total_eligible_files':eligible, 'oversized_files':oversized, 'file_limit':file_limit,
                      'byte_limit':byte_limit, 'per_file_byte_limit':MAX_FILE_BYTES,
                      'selected_bytes':sum(entry[1] for _,entry in selected)}


def build(repo, commit, excluded=None, *, only_file=None, directory=None, page=1):
    if not re.fullmatch(r'(?:[a-f0-9]{40}|[a-f0-9]{64})', commit):
        raise ValueError('Structure indexing requires a full commit ID')
    if only_file is not None and directory is not None:
        raise ValueError('Choose either one file or one directory')
    scope = only_file if only_file is not None else directory
    if scope is not None and (not isinstance(scope,str) or any(x in ('','.','..') for x in scope.split('/')) or '\x00' in scope):
        raise ValueError('Choose a repository-relative tracked path')
    if only_file is not None:
        file_result={'commit':commit,'file':only_file,'language':None,'declarations':[],'imports':[],
                     'package_imports':[],'status':'unavailable','coverage':{'indexed_files':0,'unresolved_imports':0,'truncated':False}}
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
    descriptions = {}
    unsupported_oid = None
    go_modules = set()
    python_paths = set()
    go_files = defaultdict(list)
    go_config = None
    next_files = set()
    next_config_names = []
    next_sources = {}
    workspace = False
    pnpm_workspace = None
    has_pnpm_workspace = False
    for entry in tree.split(b'\0'):
        if not entry:
            continue
        meta, raw_file = entry.split(b'\t', 1)
        mode, kind, oid, size = meta.split()
        # A nested module, workspace or second package file is a boundary even if its
        # contents are excluded. Use names only and never open an excluded blob.
        go_path = os.fsdecode(raw_file)
        folder, name = posixpath.split(go_path)
        if go_path.endswith('.py'):
            python_paths.add(go_path)
        if scope is None:
            if go_path.startswith(('app/','src/app/')) or go_path == 'app':
                next_files.add(go_path)
            if not folder and name.startswith('next.config.'):
                next_config_names.append(name)
        if go_path == 'pnpm-workspace.yaml':
            has_pnpm_workspace = True
        if name == 'go.mod' and folder:
            go_modules.add(folder)
        if go_path == 'go.work':
            workspace = True
        if name.endswith('.go') and not name.endswith('_test.go') and not name.startswith(('.', '_')):
            go_files[folder].append(go_path)
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
        if scope is None:
            tracked[file] = oid
            if file == 'pnpm-workspace.yaml' and int(size) <= 64 * 1024:
                pnpm_workspace = (oid,int(size))
            if (file == 'package.json' or file in next_config_names) and int(size) <= 64 * 1024:
                next_sources[file] = (oid, int(size))
            if file.lower() in ('readme.md','readme.rst','readme.txt','readme') or file in ('package.json','pyproject.toml'):
                if int(size) <= 64 * 1024:
                    descriptions[file] = (oid, int(size))
            if posixpath.basename(file) in ('package.json', 'pyproject.toml'):
                manifests[file] = (oid, int(size))
        if file == 'go.mod' and int(size) <= 64 * 1024:
            go_config = (oid, int(size))
        suffix = PurePosixPath(file).suffix
        lang = 'go' if suffix == '.go' else 'python' if suffix == '.py' else 'javascript' if suffix in JS_EXTENSIONS else 'typescript' if suffix in TS_EXTENSIONS else 'html' if suffix in ('.html','.htm') else None
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
    scoped = candidates if directory is None else {f:e for f,e in candidates.items() if f.startswith(directory + '/')}
    file_limit = MAX_FILES if directory is None else min(MAX_DIRECTORY_FILES, MAX_FILES)
    byte_limit = MAX_BYTES if directory is None else min(MAX_DIRECTORY_BYTES, MAX_BYTES)
    groups = [[(f, e) for f, e in scoped.items() if languages[f] == lang]
              for lang in LANGUAGES]
    bounded = len(scoped)>file_limit or sum(size for _,size in scoped.values())>byte_limit
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
    if directory is not None:
        selected, pagination = _directory_page(ordered,page,file_limit,byte_limit)
        truncated = len(selected) < len(scoped)
    else:
        for file, entry in ordered:
            size = entry[1]
            if size > MAX_FILE_BYTES or consumed + size > byte_limit or len(selected) >= file_limit:
                truncated = True
                continue
            selected.append((file, entry))
            consumed += size
    module = None
    package_imports = []
    cobra_facts = {}
    go_targets = {folder:paths for folder, paths in go_files.items() if all(path in candidates for path in paths)}
    if any(languages[f] == 'go' for f, _ in selected) and go_config and go_config[0] not in denied and not workspace:
        config = next(_blobs(git, env, [('go.mod', go_config)]))[1]
        modules = re.findall(rb'^module[ \t]+([\w./~-]+)[ \t]*(?://[^\n]*)?$', config, re.M)
        if len(modules) == 1:
            module = modules[0].decode('ascii')
            # A dependency with a matching prefix can override root-module ownership.
            for path in re.findall(rb'(?:^|\s)' + re.escape(modules[0]) + rb'/([\w./~-]+)', config):
                go_modules.add(path.decode('ascii'))
    try:
        next_contexts = next_routes.context(next_files, next_config_names, next_sources, denied,
                                          lambda entries:_blobs(git, env, entries), _parser) if scope is None else {}
    except ImportError:
        next_contexts = {}
    unavailable = set()
    for file, raw in _blobs(git, env, selected):
        language = languages[file]
        if language == 'go':
            inside_module = not any(file.startswith(base + '/') for base in go_modules) and 'vendor' not in file.split('/')
            try:
                result = _go_structure(file, raw, module if inside_module else None, go_targets, go_modules | {'vendor'})
            except ImportError:
                unavailable.add(language)
                continue
            if result is None:
                continue
            rows, edges, packages, missing, facts = result
            if inside_module and module and not file.endswith('_test.go'):
                cobra_facts[file] = facts
            limited_packages = packages[:MAX_IMPORTS - len(package_imports)]
            truncated |= len(limited_packages) != len(packages)
            package_imports.extend(limited_packages)
            limited_rows = rows[:MAX_DECLARATIONS - declarations]
            limited_edges = edges[:MAX_IMPORTS - len(imports)]
            truncated |= len(rows) != len(limited_rows) or len(edges) != len(limited_edges)
            files.append({'file':file,'language':language,'declarations':limited_rows})
            parsed.add(file)
            imports.extend(limited_edges)
            unresolved += missing
            declarations += len(limited_rows)
            continue
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
                script = _script(file, raw, candidates, next_contexts.get(file))
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
            # Definitions and imports occur in statement suites, never inside expressions.
            # Preserve statement order, including exception handlers and match cases.
            for field in reversed(node._fields):
                if field in ('body', 'handlers', 'orelse', 'finalbody', 'cases'):
                    stack.extend((child, prefix) for child in reversed(getattr(node, field)))
        files.append({'file': file, 'language':'python', 'declarations': rows})
    if only_file is not None:
        # Imports point to unique eligible paths in the same tree. Their blobs are not read.
        if files:
            file_result.update(status='indexed',declarations=files[0]['declarations'],imports=imports)
        elif not unavailable:
            file_result['status']='unparsed'
        file_result['package_imports'] = package_imports
        file_result['coverage']={'indexed_files':len(files),'unresolved_imports':unresolved,'truncated':truncated}
        return file_result
    if directory is not None:
        pagination['unparsed_files'] = len(selected) - len(files)
        return {'directory':directory, 'commit':commit, 'pagination':pagination, 'status':'indexed' if files else 'unavailable',
                'files':files, 'imports':imports, 'package_imports':package_imports,
                'coverage':{'candidate_files':len(scoped), 'indexed_files':len(files),
                            'skipped_files':len(scoped)-len(files), 'unresolved_imports':unresolved,
                            'truncated':truncated, 'unavailable_languages':sorted(unavailable)}}
    resolved = [edge for edge in imports if edge['target'] in parsed]
    routes.extend(factory_routes(factory_modules,resolved))
    routes.extend(service_flow.mounted_routes(external,resolved,python_paths,parsed))
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
    if bounded:
        coverage['selection']='bounded_directory_sample'
        coverage.update(_directory_coverage(candidates, parsed))
    eligible_manifests = {path: entry for path, entry in manifests.items() if entry[0] not in denied}
    cli_entries, manifests_read = _cli_entries(git, env, eligible_manifests, {f for f, oid in tracked.items() if oid not in denied}, files)
    cli_entries.extend(cobra_commands.connect(cobra_facts, go_targets, 1024))
    workspace_config = None
    if has_pnpm_workspace:
        if pnpm_workspace and pnpm_workspace[0] not in denied:
            workspace_config = ('pnpm-workspace.yaml',pnpm_workspace)
    elif 'package.json' in eligible_manifests and eligible_manifests['package.json'][1]<=64*1024:
        workspace_config = ('package.json',eligible_manifests['package.json'])
    workspace_packages,workspace_total,workspace_dependencies = _workspace_packages(git,env,workspace_config,eligible_manifests)
    coverage['workspace_manifests_matched'] = workspace_total
    coverage['cli_manifests_read'] = manifests_read
    coverage['cli_manifests_total'] = len(eligible_manifests)
    preferred = ['package.json','pyproject.toml','readme.md','readme.rst','readme.txt','readme']
    sources = sorted(((p,e) for p,e in descriptions.items() if e[0] not in denied),
                     key=lambda item:(preferred.index(item[0].lower()),item[0]))
    description = _project_description(git, env, sources)
    features = _documented_features(git, env, [item for item in sources if item[0].lower() == 'readme.md'])
    return {'version':VERSION,'commit': commit,'project_description':description,'workspace_packages':workspace_packages,'workspace_dependencies':workspace_dependencies,'documented_features':features,'cli_entries':cli_entries, 'files': files, 'imports': resolved, 'package_imports':package_imports, 'coverage': coverage,
            'service_flow':service_flow.connect(routes, requests)}
