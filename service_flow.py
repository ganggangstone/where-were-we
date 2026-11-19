"""Static same-repository HTTP matches from literal browser requests and FastAPI registrations."""
import ast
import re
from collections import Counter, defaultdict

METHODS = {'GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS'}


def _path(value):
    # Preserve slash and case; match only fixed, same-origin URL paths.
    return isinstance(value, str) and re.fullmatch(r'/[A-Za-z0-9_~/.-]*', value) and '//' not in value and not any(part in ('.', '..') for part in value.split('/'))


def _literal(call, key, default):
    if any(k.arg is None for k in call.keywords):
        return None
    arg = next((k.value for k in call.keywords if k.arg == key), None)
    if arg is None:
        return default
    return arg.value if isinstance(arg, ast.Constant) and isinstance(arg.value, str) else None


def python_routes(tree, file):
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
        for child in ast.walk(node):
            if isinstance(child, ast.Name) and isinstance(child.ctx, (ast.Store, ast.Del)):
                assignments[child.id] += 1
    apps = set()
    routers = {}
    handlers = defaultdict(list)
    routes = []
    for node in tree.body:
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
                if deco.func.attr != method.lower() or method not in METHODS or not _path(path) or (name not in apps and name not in routers):
                    continue
                route = {'method': method, 'path': path, 'server': {'file': file, 'line': deco.lineno, 'function': node.name}, 'mounts': []}
                if name in apps:
                    routes.append(route)
                else:
                    handlers[name].append(route)
        elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            call = node.value
            if not isinstance(call.func, ast.Attribute) or call.func.attr != 'include_router' or not isinstance(call.func.value, ast.Name) or call.func.value.id not in apps:
                continue
            if len(call.args) != 1 or not isinstance(call.args[0], ast.Name) or call.args[0].id not in routers:
                continue
            name = call.args[0].id
            prefix = _literal(call, 'prefix', '')
            if prefix != '' and not _path(prefix):
                continue
            for route in handlers[name]:
                routes.append({**route, 'path': prefix + routers[name] + route['path'], 'mounts': [{'file': file, 'line': node.lineno}]})
    return routes


def _js_string(node):
    if node is None or node.type != 'string':
        return None
    value = node.text.decode('utf-8')
    if len(value) > 1 and value[0] == value[-1] and value[0] in ('"', "'") and '\\' not in value:
        return value[1:-1]
    return None


def javascript_requests(root, file):
    """Read bare fetch calls, ignoring files where fetch may be rebound."""
    if root.has_error:
        return []
    stack = [root]
    calls = []
    while stack:
        node = stack.pop()
        if node.type in ('identifier', 'shorthand_property_identifier_pattern') and node.text == b'fetch':
            parent = node.parent
            if parent is None or parent.type != 'call_expression' or parent.child_by_field_name('function') != node:
                return []
            calls.append(parent)
        stack.extend(reversed(node.named_children))
    requests = []
    for call in calls:
        args = [n for n in call.child_by_field_name('arguments').named_children if n.type != 'comment']
        if not args:
            continue
        path = _js_string(args[0])
        if not _path(path) or len(args) > 2:
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
            requests.append({'method': method.upper(), 'path': path, 'client': {'file': file, 'line': call.start_point[0] + 1}})
    return requests


def connect(routes, requests):
    """Resolve only unique, fixed method/path pairs. This is static correspondence."""
    by_endpoint = defaultdict(list)
    for route in routes:
        by_endpoint[route['method'], route['path']].append(route)
    connections = []
    for request in requests:
        matches = by_endpoint[request['method'], request['path']]
        if len(matches) == 1:
            connections.append({**matches[0], **request})
    return {'connections': connections, 'coverage': {'requests': len(requests), 'routes': len(routes),
            'unresolved_requests': len(requests) - len(connections)}}
