"""Literal Cobra command definitions and explicit parent.AddCommand registrations."""
import posixpath
import re
from collections import defaultdict


def _text(node):
    return node.text.decode('utf-8', 'replace') if node else ''


def _single(node):
    return node.named_children[0] if node and node.named_child_count == 1 else None


def _walk(node):
    stack = [node]
    while stack:
        current = stack.pop()
        yield current
        if current.type != 'func_literal':
            stack.extend(current.named_children)


def _fields(literal):
    values = {}
    for row in literal.child_by_field_name('body').named_children:
        key = _text(_single(row.child_by_field_name('key')))
        value = _single(row.child_by_field_name('value'))
        if key in ('Use', 'Short') and value and value.type in ('interpreted_string_literal', 'raw_string_literal'):
            text = _text(value)[1:-1]
            if key in values or not text.strip() or len(text) > 320 or not text.isprintable() or chr(92) in text:
                return {}
            values[key] = (text, value.start_point.row + 1)
    return values


def facts(root, file, import_paths):
    package = next((_text(_single(n)) for n in root.named_children if n.type == 'package_clause'), '')
    constructors = {}
    imports = {}
    for decl in root.named_children:
        if decl.type != 'import_declaration':
            continue
        for spec in _walk(decl):
            if spec.type != 'import_spec':
                continue
            path = spec.child_by_field_name('path')
            name = _text(path)[1:-1]
            alias = _text(spec.child_by_field_name('name'))
            if name == 'github.com/spf13/cobra':
                imports[alias or 'cobra'] = (None, '')
            elif (path.start_point.row + 1, name) in import_paths:
                imports[alias or posixpath.basename(name)] = (import_paths[path.start_point.row + 1, name], alias)
    cobra = {alias for alias, value in imports.items() if value[0] is None}
    for decl in root.named_children:
        if decl.type != 'function_declaration':
            continue
        symbol = _text(decl.child_by_field_name('name'))
        constructors.setdefault(symbol, []).append(None)
        result = decl.child_by_field_name('result')
        if not result or _text(result) not in {'*' + alias + '.Command' for alias in cobra}:
            continue
        body = _single(decl.child_by_field_name('body'))
        if not body:
            continue
        statements = [s for s in body.named_children if s.type != 'comment']
        if not statements or statements[-1].type != 'return_statement':
            continue
        returned = _text(_single(_single(statements[-1])))
        if not returned.isidentifier():
            continue
        bound = defaultdict(int)
        for n in _walk(decl):
            if n.type in ('short_var_declaration', 'assignment_statement'):
                left = n.child_by_field_name('left')
                for target in left.named_children if left else []:
                    bound[_text(target)] += 1
            elif n.type in ('parameter_declaration','var_spec','const_spec'):
                for target in n.children_by_field_name('name'):
                    bound[_text(target)] += 1
        if bound[returned] != 1 or any(bound[a] for a in cobra):
            continue
        if any(n.type == 'return_statement' and _text(_single(_single(n))) != returned for n in _walk(body)):
            continue
        fields = {}
        calls = []
        for stmt in statements:
            if stmt.type == 'short_var_declaration' and _text(_single(stmt.child_by_field_name('left'))) == returned:
                unary = _single(stmt.child_by_field_name('right'))
                literal = unary.child_by_field_name('operand') if unary and unary.type == 'unary_expression' and unary.text.startswith(b'&') else None
                if literal and literal.type == 'composite_literal' and '*' + _text(literal.child_by_field_name('type')) == _text(result):
                    fields = _fields(literal)
            call = _single(stmt) if stmt.type == 'expression_statement' else None
            if not call or call.type != 'call_expression' or _text(call.child_by_field_name('function')) != returned + '.AddCommand':
                continue
            for child in call.child_by_field_name('arguments').named_children:
                if child.type != 'call_expression':
                    continue
                func = child.child_by_field_name('function')
                if func.type == 'identifier' and not bound[_text(func)]:
                    calls.append((posixpath.dirname(file), '', _text(func), stmt.start_point.row+1))
                elif func.type == 'selector_expression':
                    alias = _text(func.child_by_field_name('operand'))
                    if alias in imports and not bound[alias] and imports[alias][0] is not None:
                        folder, explicit = imports[alias]
                        calls.append((folder, '' if explicit else alias, _text(func.child_by_field_name('field')), stmt.start_point.row+1))
        if set(fields) == {'Use','Short'} and not any(bound[returned + '.' + key] for key in fields):
            token = fields['Use'][0].split()[0]
            if re.fullmatch(r'[\w][\w-]*', token):
                constructors[symbol][-1] = (file, token, fields, calls)
    return package, constructors


def connect(facts_by_file, directories, limit):
    definitions = defaultdict(list)
    for file, (package, constructors) in facts_by_file.items():
        folder = posixpath.dirname(file)
        for name, rows in constructors.items():
            definitions[folder, name].extend((package, row) for row in rows)
    result = []
    for _, constructors in facts_by_file.values():
        for rows in constructors.values():
            for row in filter(None, rows):
                file, parent, _, calls = row
                for folder, default_alias, name, line in calls:
                    members = directories.get(folder, [])
                    if not members or not all(f in facts_by_file for f in members):
                        continue
                    children = definitions[folder, name]
                    if len(children) != 1:
                        continue
                    package, child = children[0]
                    if not child or default_alias and default_alias != package:
                        continue
                    target, token, fields, _ = child
                    result.append({'kind':'cobra_subcommand','command':parent+' '+token,'description':fields['Short'][0],
                                   'file':file,'line':line,'target':target,'target_line':fields['Use'][1],
                                   'description_line':fields['Short'][1]})
                    if len(result) >= limit:
                        return result
    return result
