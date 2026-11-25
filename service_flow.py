"""Static same-repository HTTP matches from literal browser requests and FastAPI registrations."""
import ast
import re
import posixpath
from collections import Counter, defaultdict
from html.parser import HTMLParser

MAX_REGISTERED_ROUTES = 1024
METHODS = {'GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS'}


def _path(value):
    # Preserve slash and case; match only fixed, same-origin URL paths.
    return isinstance(value, str) and re.fullmatch(r'/[A-Za-z0-9_~/.-]*', value) and '//' not in value and not any(part in ('.', '..') for part in value.split('/'))


def _fastapi_path(path):
    if not isinstance(path, str):
        return False
    normalized = '/'.join('param' if re.fullmatch(r'\{[A-Za-z_]\w*\}', segment) else segment
                          for segment in path.split('/'))
    return _path(normalized)


def _literal(call, key, default):
    if any(k.arg is None for k in call.keywords):
        return None
    arg = next((k.value for k in call.keywords if k.arg == key), None)
    if arg is None:
        return default
    return arg.value if isinstance(arg, ast.Constant) and isinstance(arg.value, str) else None


def python_routes(tree, file, external=None):
    """Recognize module-level FastAPI apps and routers included in the same module."""
    aliases = {}
    assignments = Counter()
    imported = Counter()
    for node in tree.body:
        if isinstance(node, (ast.ImportFrom, ast.Import)):
            imported.update(alias.asname or alias.name.split('.')[0] for alias in node.names)
        if isinstance(node, ast.ImportFrom) and node.module == 'fastapi' and not node.level:
            for alias in node.names:
                if alias.name in ('FastAPI', 'APIRouter'):
                    aliases[alias.asname or alias.name] = alias.name
    if not aliases:
        return []
    for node in tree.body:
        for child in ast.walk(node):
            if isinstance(child, ast.Name) and isinstance(child.ctx, (ast.Store, ast.Del)):
                assignments[child.id] += 1
    apps = set()
    routers = {}
    handlers = defaultdict(list)
    routes = []
    import_lines = {}
    import_modules = {}
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                local = alias.asname or alias.name
                if imported[local] == 1 and not assignments[local]:
                    import_lines[local] = (node.lineno, alias.name)
                    if not node.level:
                        import_modules[local] = (node.module,alias.name,node.lineno,alias.lineno)
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name, value = node.targets[0].id, node.value
            if assignments[name] != 1 or not isinstance(value, ast.Call) or not isinstance(value.func, ast.Name):
                continue
            constructor = value.func.id
            if assignments[constructor] or imported[constructor] != 1 or imported[name]:
                continue
            if aliases.get(constructor) == 'FastAPI':
                apps.add(name)
            elif aliases.get(constructor) == 'APIRouter':
                prefix = _literal(value, 'prefix', '')
                if prefix == '' or _path(prefix):
                    routers[name] = prefix
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for deco in node.decorator_list:
                if not isinstance(deco, ast.Call) or not isinstance(deco.func, ast.Attribute) or not isinstance(deco.func.value, ast.Name):
                    continue
                name, method = deco.func.value.id, deco.func.attr.upper()
                path = _literal(deco, 'path', None)
                if len(deco.args) == 1 and isinstance(deco.args[0], ast.Constant):
                    path = deco.args[0].value
                if deco.func.attr != method.lower() or method not in METHODS or not (_fastapi_path(path) or path == '' and routers.get(name)) or (name not in apps and name not in routers):
                    continue
                route = {'method': method, 'path': path, 'server': {'file': file, 'line': deco.lineno, 'function': node.name}, 'mounts': []}
                if '{' in path:
                    route['fastapi_parameters'] = True
                if name in apps:
                    routes.append(route)
                else:
                    handlers[name].append(route)
        elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            call = node.value
            if not isinstance(call.func, ast.Attribute) or call.func.attr != 'include_router' or not isinstance(call.func.value, ast.Name) or call.func.value.id not in apps:
                continue
            if len(call.args) != 1:
                continue
            receiver = call.args[0]
            prefix = _literal(call, 'prefix', '')
            if prefix != '' and not _path(prefix):
                continue
            if (external is not None and isinstance(receiver, ast.Attribute)
                    and isinstance(receiver.value, ast.Name) and receiver.value.id in import_modules):
                external.setdefault('module_mounts',[]).append(
                    (file, *import_modules[receiver.value.id], receiver.attr, prefix, node.lineno))
                continue
            # 'from .routers import items' then include_router(items.router): the import line names the child module.
            if (external is not None and isinstance(receiver, ast.Attribute) and isinstance(receiver.value, ast.Name)
                    and receiver.value.id in import_lines and receiver.value.id not in import_modules):
                external['mounts'].append((file, import_lines[receiver.value.id][0], receiver.attr, prefix, node.lineno))
                continue
            if not isinstance(receiver,ast.Name):
                continue
            name = receiver.id
            if name not in routers:
                if external is not None and name in import_lines:
                    line, symbol = import_lines[name]
                    external['mounts'].append((file, line, symbol, prefix, node.lineno))
                continue
            for route in handlers[name]:
                routes.append({**route, 'path': prefix + routers[name] + route['path'], 'mounts': [{'file': file, 'line': node.lineno}]})
    if external is not None:
        for name, prefix in routers.items():
            external['routers'][file, name] = [{**r, 'path':prefix+r['path']} for r in handlers[name]]
    return routes


def _js_string(node):
    if node is None or node.type != 'string':
        return None
    value = node.text.decode('utf-8')
    if len(value) > 1 and value[0] == value[-1] and value[0] in ('"', "'") and '\\' not in value:
        return value[1:-1]
    return None


def _template_url(node, constants):
    if node.type != 'template_string':
        return None, None
    pieces = []
    declaration = None
    for index, part in enumerate(node.named_children):
        if part.type == 'string_fragment':
            pieces.append(part.text.decode())
        elif part.type == 'template_substitution' and len(part.named_children) == 1:
            value = part.named_children[0]
            if value.type != 'identifier':
                return None, None
            if index == 0 and value.text in constants:
                prefix, declaration = constants[value.text]
                if declaration.end_byte >= node.start_byte:return None, None
                pieces.append(prefix)
            elif re.fullmatch(rb'[A-Za-z_][A-Za-z_0-9]*', value.text):
                pieces.append('{'+value.text.decode()+'}')
            else:return None, None
        else:return None, None
    path = ''.join(pieces)
    segments = path.split('/')
    if not any(re.fullmatch(r'[{][A-Za-z_]\w*[}]',segment) for segment in segments):
        return None, None
    fixed = '/'.join('param' if re.fullmatch(r'[{][A-Za-z_]\w*[}]',seg) else seg for seg in segments)
    if not _path(fixed) or not segments[1] or segments[1].startswith('{'):
        return None, None
    return path, declaration


def _walk(root, prune=()):
    """Tree-sitter nodes in source order; children of a pruned type (other than root) are skipped."""
    stack = [root]
    while stack:
        node = stack.pop()
        yield node
        if node == root or node.type not in prune:
            stack.extend(reversed(node.named_children))


def javascript_requests(root, file):
    """Read bare fetch calls, ignoring files where fetch may be rebound."""
    if root.has_error:
        return []
    constants = {}
    for statement in root.named_children:
        if statement.type != 'lexical_declaration' or statement.children[0].type != 'const':
            continue
        for decl in statement.named_children:
            name = decl.child_by_field_name('name')
            path = _js_string(decl.child_by_field_name('value'))
            if name and name.type == 'identifier' and _path(path):
                constants[name.text] = (path, name)
    calls = []
    for node in _walk(root):
        if node.type in ('identifier','shorthand_property_identifier_pattern') and node.text in constants:
            _, declared = constants[node.text]
            # Accept only simple reads. Any additional binding or write makes the name ambiguous.
            if node != declared and node.parent.type not in ('arguments','template_substitution'):
                del constants[node.text]
        if node.type in ('identifier', 'shorthand_property_identifier_pattern') and node.text == b'fetch':
            parent = node.parent
            if parent is None or parent.type != 'call_expression' or parent.child_by_field_name('function') != node:
                return []
            calls.append(parent)
    requests = []
    for call in calls:
        args = [n for n in call.child_by_field_name('arguments').named_children if n.type != 'comment']
        if not args:
            continue
        path = _js_string(args[0])
        declaration = None
        if args[0].type == 'identifier' and args[0].text in constants:
            path, declaration = constants[args[0].text]
            if declaration.end_byte >= call.start_byte:continue
        template = args[0].type == 'template_string'
        if template:
            path, declaration = _template_url(args[0], constants)
        if not path or (not template and not _path(path)) or len(args) > 2:
            continue
        method = 'GET'
        if len(args) == 2:
            if args[1].type != 'object':
                continue
            for prop in args[1].named_children:
                if prop.type == 'comment':
                    continue
                if prop.type != 'pair':
                    method = None
                    break
                key = prop.child_by_field_name('key')
                if key.type not in ('property_identifier', 'string') or b'\\' in key.text:
                    method = None
                    break
                if key.text in (b'method', b'"method"', b"'method'"):
                    method = _js_string(prop.child_by_field_name('value'))
        if method and method.upper() in METHODS:
            request={'method': method.upper(), 'path': path, 'client': {'file': file, 'line': call.start_point[0] + 1}}
            if template:request['basis']='path_template'
            if declaration:request['evidence']=[{'file':file,'line':declaration.start_point.row+1}]
            requests.append(request)
    return requests


class _InlineScripts(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.inert = []
        self.script = False
        self.sources = []

    def handle_starttag(self, tag, attrs):
        if tag in ('template', 'noscript', 'textarea', 'style', 'title', 'iframe'):
            self.inert.append(tag)
        if tag == 'script':
            attrs = dict(attrs)
            kind = (attrs.get('type') or '').strip().lower()
            self.script = not self.inert and 'src' not in attrs and kind in ('', 'module', 'application/javascript', 'text/javascript')

    def handle_endtag(self, tag):
        if tag == 'script':
            self.script = False
        if self.inert and tag == self.inert[-1]:
            self.inert.pop()

    def handle_data(self, data):
        if self.script:
            self.sources.append((self.getpos()[0]-1, data))


def html_requests(raw, file, parse):
    try:
        text = raw.decode('utf-8')
    except UnicodeError:
        return []
    html = _InlineScripts()
    try:
        html.feed(text)
        html.close()
    except (ValueError, AssertionError):
        # HTMLParser rejects unknown marked sections; keep malformed inputs unresolved.
        return []
    requests = []
    for offset, source in html.sources:
        for request in javascript_requests(parse(source.encode()).root_node, file):
            request['client']['line'] += offset
            for site in request.get('evidence',[]):site['line'] += offset
            requests.append(request)
    return requests


_BASE = re.compile(r'(?:https?://)?(?:localhost|127\.0\.0\.1|[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*):\d{2,5}')


def python_requests(tree, file):
    """Python HTTP calls (requests/httpx/aiohttp methods, urllib Request/urlopen, a curl argument list) whose URL is a literal
    http address with a port, or an f-string starting with a module constant holding one (an env default counts).
    A path segment built from a value is kept as {param}; the query and the rest after a non-literal part are dropped."""
    bases = {}
    counts = Counter(t.id for node in tree.body if isinstance(node, (ast.Assign, ast.AnnAssign))
                     for t in (node.targets if isinstance(node, ast.Assign) else [node.target]) if isinstance(t, ast.Name))
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name) or counts[node.targets[0].id] != 1:
            continue
        value = node.value
        if isinstance(value, ast.BoolOp) and isinstance(value.op, ast.Or):value = value.values[-1]
        if isinstance(value, ast.Call) and len(value.args) == 2 and not value.keywords and ast.unparse(value.func) in ('os.environ.get', 'os.getenv'):
            value = value.args[1]
        if isinstance(value, ast.Constant) and isinstance(value.value, str) and _BASE.fullmatch(value.value.rstrip('/')):
            bases[node.targets[0].id] = value.value.rstrip('/')

    def url(node):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            m = _BASE.match(node.value)
            return node.value[m.end():].split('?')[0].split('#')[0] if m else None
        if not isinstance(node, ast.JoinedStr) or not node.values:
            return None
        first, *rest = node.values
        if isinstance(first, ast.FormattedValue) and isinstance(first.value, ast.Name) and first.value.id in bases and first.conversion == -1 and not first.format_spec:
            text = ''
        elif isinstance(first, ast.Constant) and (m := _BASE.match(first.value)):
            text = first.value[m.end():]
        else:
            return None
        for part in rest:
            if '?' in text or '#' in text:break
            if isinstance(part, ast.Constant):text += part.value
            elif text.endswith('/'):text += '{param}'
            else:return None  # a value glued into a segment ('/a{b}') leaves the path unknown
        path = text.split('?')[0].split('#')[0]
        return path if all(seg == '{param}' or '{' not in seg for seg in path.split('/')) else None

    requests = []
    def add(method, node, path):
        if path and method in METHODS:
            shaped = path.replace('{param}', 'param')
            if _path(shaped) and path != '/':
                request = {'method': method, 'path': path, 'client': {'file': file, 'line': node.lineno}}
                if '{param}' in path:request['basis'] = 'path_template'
                requests.append(request)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and node.args:
            name = node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id if isinstance(node.func, ast.Name) else ''
            if name.upper() in METHODS:
                add(name.upper(), node, url(node.args[0]))
            elif name in ('Request', 'urlopen'):
                method = next((k.value.value for k in node.keywords if k.arg == 'method' and isinstance(k.value, ast.Constant)), None)
                data = len(node.args) > 1 or any(k.arg == 'data' for k in node.keywords)
                add(str(method or ('POST' if data else 'GET')).upper(), node, url(node.args[0]))
        elif isinstance(node, ast.List) and node.elts and isinstance(node.elts[0], ast.Constant) and node.elts[0].value == 'curl':
            words = [e.value if isinstance(e, ast.Constant) and isinstance(e.value, str) else None for e in node.elts]
            paths = [p for e in node.elts if (p := url(e))]
            method = next((words[i+1] for i, w in enumerate(words[:-1]) if w in ('-X', '--request')), None)
            if method is None:
                method = 'POST' if any(w in ('-d', '--data', '--data-raw', '--data-binary', '-F', '--form', '--json') for w in words) else 'GET'
            if len(paths) == 1 and method:add(method.upper(), node, paths[0])
    return sorted(requests, key=lambda r: r['client']['line'])


def mounted_routes(external, imports, python_paths=(), parsed=()):
    targets = {(edge['file'],edge['line']):edge['target'] for edge in imports}
    result = []
    for file, line, symbol, prefix, mount_line in external['mounts']:
        target = targets.get((file, line))
        for route in external['routers'].get((target, symbol), []):
            result.append({**route, 'path':prefix+route['path'],
                           'mounts':[{'file': file, 'line': line}, {'file':file, 'line':mount_line}]})
    module_mounts = external.get('module_mounts',[])
    if not module_mounts:
        return result
    by_name = defaultdict(list)
    for path in python_paths:
        by_name[posixpath.basename(path)].append(path)
    for file, package, child, imp, binding, symbol, prefix, mount in module_mounts:
        # Anchor the absolute import to the importing app's own top-level package.
        parts = package.split('.')
        owner = file.split('/')[:-1]
        if owner.count(parts[0]) != 1:
            continue
        base = '/'.join(owner[:owner.index(parts[0])])
        package_root = posixpath.join(base, parts[0])
        root_initializers = [f for f in by_name['__init__.py'] if f.endswith('/'+parts[0]+'/__init__.py')
                             or f == parts[0]+'/__init__.py']
        if root_initializers != [package_root+'/__init__.py'] or root_initializers[0] not in parsed:
            continue
        directory = posixpath.join(base,*parts)
        target = posixpath.join(directory,child+'.py')
        suffix = '/'.join([*parts,child])
        matches = [path for path in by_name[child+'.py'] if ('/'+path).endswith('/'+suffix+'.py')]
        if any(('/'+p).endswith('/'+suffix+'/__init__.py') for p in by_name['__init__.py']):
            continue
        # A namespace directory without an initializer cannot re-export a different child.
        if (matches != [target] or target not in parsed or directory+'/__init__.py' in python_paths
                or any(posixpath.join(base,*parts[:i])+'.py' in python_paths for i in range(1,len(parts)+1))):
            continue
        for route in external['routers'].get((target,symbol),[]):
            proof = [{'file':file,'line':n} for n in dict.fromkeys((imp,binding,mount))]
            result.append({**route,'path':prefix+route['path'],'mounts':proof})
    return result


def connect(routes, requests):
    """Resolve exact paths, or one unique compatible parameter shape with a conditional label."""
    by_endpoint = defaultdict(list)
    by_shape = defaultdict(list)
    parameter_routes = defaultdict(list)
    for route in routes:
        if route.get('fastapi_parameters'):
            continue  # Registration evidence only; matching depends on router order.
        by_endpoint[route['method'], route['path']].append(route)
        segments = route['path'].split('/')
        key = route['method'], segments[1], len(segments)
        shape=[None if s.startswith(':') and route.get('express_parameters') else s for s in segments]
        by_shape[key].append((route,shape))
        if None in shape:parameter_routes[key].append((route,shape))
    connections = []
    for request in requests:
        template = request.get('basis') == 'path_template'
        segments = [None if template and s.startswith('{') else s for s in request['path'].split('/')]
        key = request['method'], segments[1], len(segments)
        exact = by_endpoint.get((request['method'],request['path']), [])
        # Other registered shapes can overlap even if their parameter names differ.
        candidates = by_shape[key] if template else [(r,segments) for r in exact]+parameter_routes[key]
        compatible = [(route, shape) for route, shape in candidates
                      if all(a is None or b is None or a == b for a,b in zip(segments,shape))]
        if len(compatible) != 1:continue
        route, shape = compatible[0]
        if template and shape == segments:
            connections.append({**route, **request, 'server_path':route['path']})
        elif not template and len(exact) == 1:
            connections.append({**route, **request})
    # Group exact endpoint paths across methods. A terminal Express parameter
    # also belongs to its literal collection path; nested fixed paths stay distinct.
    resources = {}
    for index, connection in enumerate(connections):
        path = connection.get('server_path', connection['path'])
        parent, _, last = path.rpartition('/')
        resource = parent if connection.get('express_parameters') and last.startswith(':') and parent else path
        resources.setdefault(resource, []).append(index)
    groups = [{'resource':resource, 'connection_indexes':indexes} for resource,indexes in resources.items()]
    # Keep the registration and its own evidence independently of client matching.
    # Unmatched handlers come first so the bounded list adds information to connections.
    linked = {(c['method'],c.get('server_path',c['path']),c['server']['file'],c['server']['line']) for c in connections}
    def route_order(route):
        signature = (route['method'],route['path'],route['server']['file'],route['server']['line'])
        return (signature in linked, *signature)
    registered = sorted(routes,key=route_order)[:MAX_REGISTERED_ROUTES]
    standalone={}
    for i,route in enumerate(registered):
        if not route_order(route)[0]:
            standalone.setdefault(route['path'],[]).append(i)
    registered_groups=[{'resource':resource,'registered_route_indexes':indexes} for resource,indexes in standalone.items()]
    literal_requests = [{'method':r['method'], 'path':r['path'], 'client':r['client'], **({'basis':r['basis']} if r.get('basis') else {})} for r in requests
                        if r.get('basis') in (None, 'path_template') and _path(re.sub(r'\{[A-Za-z_]\w*\}', 'param', r['path']))]
    return {'literal_requests':literal_requests[:256],'registered_route_groups':registered_groups,'registered_routes':registered,'connections': connections, 'feature_groups': groups, 'coverage': {'requests': len(requests), 'routes': len(routes),
            'unresolved_requests': len(requests) - len(connections)}}
