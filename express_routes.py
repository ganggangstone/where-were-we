"""Static Express application routes with a same-module listener, without evaluating JS."""
from service_flow import METHODS, _js_string, _path


def _identifier(node):
    return node.text.decode() if node and node.type == 'identifier' else None


def _args(call):
    args = call.child_by_field_name('arguments')
    return [child for child in args.named_children if child.type != 'comment'] if args else []


def express_routes(root, file):
    if root.has_error or b'express' not in root.text:
        return []
    constructors = {}
    apps = {}
    handlers = {}
    statements = []
    commonjs = {}
    for statement in root.named_children:
        if statement.type == 'export_statement':
            statement = statement.child_by_field_name('declaration')
            if not statement:
                continue
        if statement.type == 'import_statement' and _js_string(statement.child_by_field_name('source')) == 'express':
            if any(child.type == 'type' for child in statement.children):
                continue
            clause = next((c for c in statement.named_children if c.type == 'import_clause'), None)
            if clause:
                for child in clause.named_children:
                    if name := _identifier(child):
                        constructors[name] = -1  # Module imports are available before module statements.
        if statement.type == 'function_declaration':
            name = _identifier(statement.child_by_field_name('name'))
            if name:
                handlers[name] = statement
        if statement.type == 'lexical_declaration' and statement.children[0].type == 'const':
            for binding in statement.named_children:
                name = _identifier(binding.child_by_field_name('name'))
                value = binding.child_by_field_name('value')
                if not name or not value:
                    continue
                if value.type in ('arrow_function', 'function_expression'):
                    handlers[name] = value
                elif value.type == 'call_expression':
                    constructor = _identifier(value.child_by_field_name('function'))
                    args = _args(value)
                    if constructor == 'require' and len(args) == 1 and _js_string(args[0]) == 'express':
                        commonjs[name] = value.end_byte
                    elif constructor and not args:
                        apps[name] = (constructor, value.end_byte)
        if statement.type == 'expression_statement' and statement.named_children:
            call = statement.named_children[0]
            if call.type == 'call_expression':
                member = call.child_by_field_name('function')
                if member and member.type == 'member_expression':
                    receiver = _identifier(member.child_by_field_name('object'))
                    prop = member.child_by_field_name('property')
                    if receiver and prop and prop.type == 'property_identifier':
                        statements.append((receiver, prop.text.decode(), call))
    if not apps or not (constructors or commonjs):
        return []

    # A locally defined require or an overwritten method cannot establish Express provenance.
    modified = set()
    shadowed_require = False
    stack = [root]
    while stack:
        node = stack.pop()
        if commonjs and _identifier(node) == 'require':
            parent = node.parent
            if parent.type != 'call_expression' or parent.child_by_field_name('function') != node:
                shadowed_require = True
        if node.type in ('assignment_expression', 'augmented_assignment_expression', 'update_expression'):
            target = node.child_by_field_name('left') or node.child_by_field_name('argument')
            if target and target.type in ('member_expression','subscript_expression'):
                target = target.child_by_field_name('object')
            name = _identifier(target)
            if name:
                modified.add(name)
        stack.extend(node.named_children)
    if not shadowed_require:
        constructors.update(commonjs)
    apps = {name:end for name,(constructor,end) in apps.items() if name not in modified
            and constructor in constructors and constructor not in modified and constructors[constructor] < end}
    listeners = {name for name, prop, call in statements if name in apps and prop == 'listen'
                 and _args(call) and call.start_byte >= apps[name]}
    routes = []
    for name, prop, call in statements:
        method = prop.upper()
        if (name not in listeners or call.start_byte < apps[name]
                or prop != prop.lower() or method not in METHODS):
            continue
        args = _args(call)
        if len(args) != 2:
            continue
        path = _js_string(args[0])
        handler = args[1]
        if not _path(path):
            continue
        if handler.type in ('arrow_function','function_expression'):
            function = _identifier(handler.child_by_field_name('name')) or ''
        else:
            function = _identifier(handler)
            if function not in handlers or function in modified:
                continue
        routes.append({'method':method, 'path':path, 'server':{'file':file, 'line':call.start_point.row + 1,
                                                               'function':function}, 'mounts':[]})
    return routes
