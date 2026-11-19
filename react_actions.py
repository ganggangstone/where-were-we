"""JSX events connected through a lexical handler and a verified imported fetch wrapper."""
from collections import Counter, defaultdict

FUNCTIONS = {'function_declaration','function_expression','arrow_function','method_definition','generator_function_declaration'}


def _walk(root, prune=()):
    stack = [root]
    while stack:
        node = stack.pop()
        yield node
        if node == root or node.type not in prune:
            stack.extend(reversed(node.named_children))


def _name(node):
    return node.text.decode() if node and node.type in ('identifier','property_identifier') else ''


def _callee(node):
    if node.type != 'call_expression':
        return ''
    fn = node.child_by_field_name('function')
    if fn.type == 'member_expression':
        base = _name(fn.child_by_field_name('object'))
        member = _name(fn.child_by_field_name('property'))
        return base+'.'+member if base and member else ''
    return _name(fn)


def _line(node):
    return node.start_point.row + 1


def _binding_counts(root):
    counts=Counter()
    for node in _walk(root):
        if node.type in ('variable_declarator','function_declaration','class_declaration','import_specifier'):
            name = node.child_by_field_name('alias') or node.child_by_field_name('name')
            if name:counts[_name(name)] += 1
        if node.type == 'arrow_function':
            param=node.child_by_field_name('parameter')
            if param:counts[_name(param)]+=1
        if node.type == 'formal_parameters':
            for child in _walk(node):
                if child.type in ('identifier','shorthand_property_identifier_pattern'):
                    counts[child.text.decode()] += 1
        if node.type=='assignment_expression':
            left=node.child_by_field_name('left')
            if left:
                for child in _walk(left):
                    if child.type=='identifier':counts[_name(child)]+=1
    return counts


def _exported_wrappers(root, lines):
    exports={}
    counts=_binding_counts(root)
    for exp in root.named_children:
        if exp.type!='export_statement':continue
        decl=exp.child_by_field_name('declaration')
        if not decl:continue
        functions=[]
        if decl.type=='function_declaration':
            functions.append((_name(decl.child_by_field_name('name')),decl))
        elif decl.type=='lexical_declaration' and decl.children[0].type=='const':
            for item in decl.named_children:
                obj=item.child_by_field_name('value')
                name=_name(item.child_by_field_name('name'))
                if not obj or not name:continue
                if obj.type in FUNCTIONS:
                    functions.append((name,obj))
                elif obj.type=='object' and all(p.type in ('pair','comment') for p in obj.named_children):
                    seen=Counter(_name(p.child_by_field_name('key')) for p in obj.named_children)
                    if '' in seen and any(p.type!='comment' and not _name(p.child_by_field_name('key')) for p in obj.named_children):continue
                    for prop in obj.named_children:
                        member=_name(prop.child_by_field_name('key'))
                        fn=prop.child_by_field_name('value')
                        if member and seen[member]==1 and fn and fn.type in FUNCTIONS:
                            functions.append((name+'.'+member,fn))
        for name,fn in functions:
            if counts[name.split('.')[0]] != 1:continue
            hits=[_line(n) for n in _walk(fn,FUNCTIONS) if _callee(n)=='fetch' and _line(n) in lines]
            if hits:exports[name]=(_line(fn),hits)
    return exports


def _label(opening, event):
    """Read a literal label on the control or on its explicit form submit button."""
    def props(node):
        data={}
        for child in node.named_children:
            if child.type=='jsx_expression':return None
            if child.type!='jsx_attribute':continue
            parts=child.named_children
            key=_name(parts[0])
            if key in data:return None
            value=parts[1] if len(parts)==2 and parts[1].type=='string' else None
            data[key]=(value.text[1:-1].decode() if value else None,child)
        return data

    attrs=props(opening)
    if attrs is None or any(k in attrs for k in ('aria-labelledby','hidden','disabled','aria-hidden')):return None
    tag=_name(opening.child_by_field_name('name'))
    if 'aria-label' in attrs:
        label,site=attrs['aria-label']
    elif tag=='button' and opening.type=='jsx_opening_element':
        body=opening.parent.named_children[1:-1]
        if len(body)!=1 or body[0].type!='jsx_text':return None
        site=body[0]
        label=site.text.decode()
    elif tag=='form' and event=='onSubmit' and opening.type=='jsx_opening_element':
        submit=[]
        for child in opening.parent.named_children[1:-1]:
            if child.type=='jsx_text':continue
            if child.type not in ('jsx_element','jsx_self_closing_element'):return None
            control=child.named_children[0] if child.type=='jsx_element' else child
            kind=_name(control.child_by_field_name('name'))
            if not kind.islower():return None
            if kind not in ('button','input'):
                for nested in _walk(child):
                    if nested==control or nested.type not in ('jsx_self_closing_element','jsx_opening_element'):continue
                    nested_tag=_name(nested.child_by_field_name('name'))
                    if not nested_tag.islower() or nested_tag in ('button','input','form'):return None
                continue
            options=props(control)
            if options is None:return None
            typ=options.get('type',(None,None))[0]
            if kind=='button' and typ not in ('button','reset','submit'):return None
            if 'type' in options and typ is None:return None
            if typ=='submit':
                if kind!='button' or any(k in options for k in ('form','formAction','onClick')):return None
                submit.append(control)
        return _label(submit[0],'') if len(submit)==1 else None
    else:return None
    if not label or '&' in label or '\n' in label or not 0<len(label.strip())<=200:return None
    return label.strip(),_line(site)


def facts(root, requests):
    lines={r['client']['line'] for r in requests}
    exports=_exported_wrappers(root,lines) if lines else {}
    if b'on' not in root.text or b'<' not in root.text:
        return exports,[]
    imports={}
    for stmt in root.named_children:
        if stmt.type!='import_statement':continue
        for item in _walk(stmt):
            if item.type=='import_specifier':
                symbol=_name(item.child_by_field_name('name'))
                local=_name(item.child_by_field_name('alias')) or symbol
                imports[local]=(symbol,_line(stmt))
    if not imports:return exports,[]
    counts=_binding_counts(root)
    handlers={}
    attrs=[]
    for node in _walk(root):
        if node.type=='function_declaration':
            name=_name(node.child_by_field_name('name'))
            if counts[name]==1:handlers[name]=node
        if node.type=='jsx_attribute':attrs.append(node)
    events=[]
    for attr in attrs:
        children=attr.named_children
        if len(children)!=2 or children[1].type!='jsx_expression' or len(children[1].named_children)!=1:continue
        event=_name(children[0])
        tag=_name(attr.parent.child_by_field_name('name'))
        if not tag or not tag.islower() or not event.startswith('on') or not event[2:3].isupper():continue
        later=[n for n in attr.parent.named_children if n.start_byte>attr.start_byte]
        if any(n.type=='jsx_expression' or n.type=='jsx_attribute' and n.named_children and _name(n.named_children[0])==event for n in later):continue
        fn=children[1].named_children[0]
        if fn.type=='arrow_function':
            fn=fn.child_by_field_name('body')
            name=_callee(fn)
        else:name=_name(fn)
        handler=handlers.get(name)
        if not handler or handler.parent.type!='statement_block':continue
        scope=handler.parent
        if not scope.start_byte<=attr.start_byte<scope.end_byte:continue
        label=_label(attr.parent,event)
        for call in _walk(handler,FUNCTIONS):
            callee=_callee(call)
            local,_,member=callee.partition('.')
            if local not in imports or counts[local]!=1:continue
            symbol,imp=imports[local]
            events.append((symbol+('.'+member if member else ''),imp,{'event':event,'element':tag,'line':_line(attr),
                'handler':name,'handler_line':_line(handler),'call_line':_line(call),'import_line':imp,
                **({'label':label[0],'label_line':label[1]} if label else {})}))
    return exports,events


def attach(modules, edges, requests):
    routed=defaultdict(list)
    for request in requests:routed[request['client']['file'],request['client']['line']].append(request)
    targets={(e['file'],e['line']):e['target'] for e in edges}
    for file,(_,events) in modules.items():
        for symbol,imp,event in events:
            target=targets.get((file,imp))
            if target not in modules:continue
            wrapper=modules[target][0].get(symbol)
            if not wrapper:continue
            definition,lines=wrapper
            for line in lines:
                matches=routed[target,line]
                if len(matches)==1:
                    action={**event,'file':file,'client_definition':{'file':target,'line':definition}}
                    if 'label_line' in action:action['label_source']={'file':file,'line':action.pop('label_line')}
                    if action not in matches[0].setdefault('actions',[]):matches[0]['actions'].append(action)
