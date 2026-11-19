"""Match declared SDK operations under explicit settings defaults without executing either side."""
import ast
from collections import defaultdict
from pathlib import PurePosixPath
import re

from service_flow import METHODS, _js_string, _literal, _path


def _at(file, line):
    return {'file':file, 'line':line}


def python_facts(tree):
    imports = {}
    constructors = {}
    bindings = defaultdict(int)
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module and not node.level:
            for alias in node.names:
                name = alias.asname or alias.name
                imports[name] = (node.module, alias.name, node.lineno)
                bindings[name] += 1
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            for target in node.targets if isinstance(node, ast.Assign) else [node.target]:
                if isinstance(target, ast.Name):
                    bindings[target.id] += 1
        elif isinstance(node,(ast.ClassDef,ast.FunctionDef,ast.AsyncFunctionDef)):
            bindings[node.name] += 1
    imports = {k:v for k,v in imports.items() if bindings[k] == 1}
    defaults = {}
    settings = {}
    mounts = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and bindings[node.name] == 1 and len(node.bases) == 1:
            base = node.bases[0]
            if isinstance(base, ast.Name) and imports.get(base.id, ())[:2] == ('pydantic_settings', 'BaseSettings'):
                defaults[node.name] = {field.target.id:(field.value.value,field.lineno) for field in node.body
                    if isinstance(field,ast.AnnAssign) and isinstance(field.target,ast.Name)
                    and isinstance(field.value,ast.Constant) and _path(field.value.value)}
        if isinstance(node,ast.Assign) and len(node.targets)==1 and isinstance(node.targets[0],ast.Name):
            name=node.targets[0].id
            call=node.value
            if bindings[name]!=1 or not isinstance(call,ast.Call) or not isinstance(call.func,ast.Name):
                continue
            if call.func.id in defaults and not call.args and not call.keywords:
                settings[name]=(defaults[call.func.id],node.lineno)
            source=imports.get(call.func.id,())[:2]
            if source in (('fastapi','FastAPI'),('fastapi','APIRouter')):
                prefix=_literal(call,'prefix','')
                if prefix=='' or _path(prefix):
                    constructors[name]=(source[1],prefix)
        if not isinstance(node,ast.Expr) or not isinstance(node.value,ast.Call):
            continue
        call=node.value
        if not isinstance(call.func,ast.Attribute) or call.func.attr!='include_router' or not isinstance(call.func.value,ast.Name):
            continue
        owner=call.func.value.id
        if owner not in constructors or len(call.args)!=1 or any(k.arg is None for k in call.keywords):
            continue
        router=call.args[0]
        if isinstance(router,ast.Name) and router.id in imports:
            module,symbol,line=imports[router.id]
        elif isinstance(router,ast.Attribute) and isinstance(router.value,ast.Name) and router.value.id in imports:
            parent,child,line=imports[router.value.id]
            module,symbol=parent+'.'+child,router.attr
        else:
            continue
        if line>=node.lineno:
            continue
        prefix=_literal(call,'prefix','')
        if prefix is None:
            value=next((k.value for k in call.keywords if k.arg=='prefix'),None)
            if not isinstance(value,ast.Attribute) or not isinstance(value.value,ast.Name) or value.value.id not in imports:
                continue
            prefix=(*imports[value.value.id],value.attr)
        elif prefix and not _path(prefix):
            continue
        package = imports[router.value.id][0] if isinstance(router,ast.Attribute) else None
        mounts.append((owner,module,symbol,line,prefix,node.lineno,package))
    return {'constructors':constructors,'settings':settings,'mounts':mounts,'empty':not tree.body}


def _module(files, name):
    suffix = name.replace('.', '/')
    candidates=[f for f in files if ('/'+f).endswith(('/'+suffix+'.py','/'+suffix+'/__init__.py'))]
    return candidates[0] if len(candidates)==1 else None


def default_routes(files, routers):
    result=[]
    resolved={}
    def module(name):
        if name not in resolved:
            resolved[name]=_module(files,name)
        return resolved[name]
    visits = 0
    def walk(file,owner,prefix,evidence,condition,seen):
        nonlocal visits
        visits += 1
        if visits > 20000 or (file,owner) in seen or len(seen)>=8:return
        for route in routers.get((file,owner),[]):
            if condition:
                result.append({**route,'path':prefix+route['path'],'mounts':evidence,'basis':'declared_defaults'})
        for parent,mod,symbol,imp,value,line,package in files[file]['mounts']:
            if parent!=owner:continue
            if package:
                init=module(package)
                if not init or not init.endswith('/__init__.py') or not files[init]['empty']:continue
            target=module(mod)
            if not target or symbol not in files[target]['constructors']:continue
            proof=[*evidence,_at(file,imp),_at(file,line)]
            conditional=condition
            if isinstance(value,tuple):
                settings_mod,binding,settings_line,field=value
                declaration=module(settings_mod)
                if not declaration or binding not in files[declaration]['settings']:continue
                fields,init_line=files[declaration]['settings'][binding]
                if field not in fields:continue
                value,field_line=fields[field]
                proof.extend([_at(file,settings_line),_at(declaration,init_line),_at(declaration,field_line)])
                conditional=True
            owner_prefix=files[file]['constructors'][owner][1]
            walk(target,symbol,prefix+owner_prefix+value,proof,conditional,seen|{(file,owner)})
    for file,facts in files.items():
        for name,(kind,_) in facts['constructors'].items():
            if kind=='FastAPI':walk(file,name,'',[],False,set())
    return result if visits<=20000 else []


def sdk_facts(root,file):
    if not root.named_children or not root.named_children[0].text.startswith(b'// This file is auto-generated by @hey-api/openapi-ts'):
        return None
    operations=[]
    imports={}
    clients={}
    factory_declaration=None
    factory_export=None
    stack=list(root.named_children)
    while stack:
        node=stack.pop()
        if node.type=='import_statement':
            source=node.child_by_field_name('source')
            if source:
                for child in node.named_children:
                    for names in child.named_children:
                        for item in names.named_children:
                            if item.type=='import_specifier' and len(item.named_children)==1:
                                imports[item.text.decode()]=(source.text[1:-1].decode(),node.start_point.row+1)
        if node.type=='export_statement':
            source=node.child_by_field_name('source')
            clause=next((child for child in node.named_children if child.type=='export_clause'),None)
            if source and clause and any(child.type=='export_specifier' and child.text==b'createClient' for child in clause.named_children):
                factory_export=(source.text[1:-1].decode(),node.start_point.row+1)
        if node.type=='variable_declarator':
            name=node.child_by_field_name('name')
            value=node.child_by_field_name('value')
            if name and name.text==b'createClient' and value and value.type=='arrow_function' and node.parent.parent.type=='export_statement':
                factory_declaration=node.start_point.row+1
            if name and value and value.type=='call_expression' and value.child_by_field_name('function').text==b'createClient':
                exported=node.parent.parent
                if exported and exported.type=='export_statement':
                    clients[name.text.decode()]=node.start_point.row+1
        if node.type=='call_expression':
            fn=node.child_by_field_name('function')
            if fn and fn.type=='member_expression':
                method=fn.child_by_field_name('property').text.decode().upper()
                receiver=fn.child_by_field_name('object').text.decode()
                match=re.fullmatch(r'\(\s*options\??\.client\s*\?\?\s*([\w$]+)\s*\)',receiver)
                args=node.child_by_field_name('arguments').named_children
                if method in METHODS and match and len(args)==1 and args[0].type=='object':
                    urls=[prop for prop in args[0].named_children if prop.type=='pair'
                          and prop.child_by_field_name('key').text==b'url']
                    if len(urls)==1:
                        path=_js_string(urls[0].child_by_field_name('value'))
                        if _path(path):operations.append((method,path,match[1],node.start_point.row+1,urls[0].start_point.row+1))
        stack.extend(reversed(node.named_children))
    return {'imports':imports,'clients':clients,'operations':operations,'factory_declaration':factory_declaration,'factory_export':factory_export}


def sdk_requests(files):
    def resolve(file, spec):
        if not spec.startswith('./'):return None
        stem=str(PurePosixPath(file).parent / spec)
        hits=[f for f in (stem+'.ts',stem+'.js',stem+'/index.ts',stem+'/index.js') if f in files]
        return hits[0] if len(hits)==1 else None
    result=[]
    for file,facts in files.items():
        for method,path,name,line,url_line in facts['operations']:
            imported=facts['imports'].get(name)
            if not imported or not imported[0].startswith('./'):continue
            target=resolve(file,imported[0])
            if not target:continue
            binding=files[target]['clients'].get(name)
            factory=files[target]['imports'].get('createClient')
            if not binding or not factory:continue
            factory_file=resolve(target,factory[0])
            if not factory_file:continue
            definitions=[]
            exported=files[factory_file]['factory_export']
            if exported:
                definitions.append(_at(factory_file,exported[1]))
                factory_file=resolve(factory_file,exported[0])
            if not factory_file or not files[factory_file]['factory_declaration']:continue
            definitions.append(_at(factory_file,files[factory_file]['factory_declaration']))
            result.append({'method':method,'path':path,'client':_at(file,line),'basis':'declared_defaults',
                           'evidence':[_at(file,url_line),_at(file,imported[1]),_at(target,binding),_at(target,factory[1]),*definitions]})
    return result
