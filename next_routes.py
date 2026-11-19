"""Literal HTTP exports under a dependency-backed Next.js App Router root."""
import json
import posixpath
import re

from service_flow import METHODS


def config_line(raw, parse):
    root = parse(raw).root_node
    nodes = [n for n in root.named_children if n.type != 'comment']
    if root.has_error or len(nodes) != 1:
        return None
    statement = nodes[0]
    obj = statement.child_by_field_name('value')
    if statement.type == 'expression_statement' and statement.named_child_count == 1:
        assignment = statement.named_children[0]
        left = assignment.child_by_field_name('left')
        if assignment.type == 'assignment_expression' and left and left.text == b'module.exports':
            obj = assignment.child_by_field_name('right')
    if not obj or obj.type != 'object':
        return None
    # A direct literal containing only non-routing settings cannot change the URL or extensions.
    for child in obj.named_children:
        if child.type == 'comment':
            continue
        key = child.child_by_field_name('key')
        if child.type != 'pair' or not key or key.text not in (b'images', b'reactStrictMode', b'poweredByHeader'):
            return None
    literals = {'object','array','pair','property_identifier','string','string_fragment','escape_sequence',
                'number','true','false','null','comment'}
    stack = [obj]
    while stack:
        node = stack.pop()
        if node.type not in literals:
            return None
        stack.extend(node.named_children)
    return obj.start_point.row + 1


def dependency_line(raw):
    try:
        manifest = json.loads(raw)
    except (ValueError, UnicodeError, RecursionError):
        return None
    if not isinstance(manifest, dict):
        return None
    versions = [group['next'] for key in ('dependencies','devDependencies')
                if isinstance(group := manifest.get(key), dict) and isinstance(group.get('next'), str)]
    if not versions:
        return None
    coordinates = [n for n,line in enumerate(raw.splitlines(),1)
                   if re.search(rb'"next"\s*:\s*' + re.escape(json.dumps(versions[0]).encode()), line)]
    return coordinates[0] if len(coordinates) == 1 else None


def context(files, configs, tracked, denied, read, parser):
    routes = {}
    if 'app' in files or any(file.startswith('app/') for file in files):
        root = 'app/'
    else:
        root = 'src/app/'
    for file in files:
        if not file.startswith(root) or posixpath.basename(file) not in ('route.ts', 'route.js'):
            continue
        segments = file[len(root):].split('/')[:-1]
        if any(not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]*', part)
               or part.lower() in ('fixtures','fixture','tests','test','examples') for part in segments):
            continue
        parent = posixpath.dirname(file) + '/'
        neighbors = [parent+n for n in ('page.ts','page.js','page.jsx','page.tsx','route.ts','route.js')]
        if sum(n in files for n in neighbors) != 1:
            continue
        routes[file] = '/' + '/'.join(segments)
    if not routes or len(configs) > 1:
        return {}
    names = ['package.json', *configs]
    entries = [(name, tracked[name]) for name in names if name in tracked and tracked[name][0] not in denied]
    if len(entries) != len(names):
        return {}
    mounts = []
    for name,raw in read(entries):
        if name == 'package.json':
            line = dependency_line(raw)
        else:
            line = config_line(raw, parser('typescript' if name.endswith('.ts') else 'javascript').parse)
        if not line:
            return {}
        mounts.append({'file':name,'line':line})
    return {file:(path,mounts) for file,path in routes.items()}


def handlers(root, file, context):
    path, mounts = context
    routes = []
    for statement in root.named_children:
        if statement.type != 'export_statement' or any(n.type == 'default' for n in statement.children):
            continue
        decl = statement.child_by_field_name('declaration')
        if not decl:
            continue
        if decl.type == 'function_declaration':
            names = [decl.child_by_field_name('name')]
        elif decl.type == 'lexical_declaration' and decl.children[0].type == 'const':
            names = [node.child_by_field_name('name') for node in decl.named_children
                     if (value := node.child_by_field_name('value')) and value.type in ('arrow_function','function_expression')]
        else:
            continue
        for name in names:
            method = name.text.decode('utf-8','replace') if name else ''
            if method in METHODS:
                routes.append({'framework':'next_app_router','path':path,'method':method,'mounts':mounts,
                               'server':{'file':file,'line':name.start_point.row+1,'function':method}})
    return routes
