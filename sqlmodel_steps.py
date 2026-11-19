"""Statically evidenced session operations on declared SQLModel table classes."""
import ast
from collections import Counter

from default_flow import _module


def _imports(body):
    imports={}
    names=Counter()
    for node in body:
        if isinstance(node,ast.ImportFrom):
            for alias in node.names:
                name=alias.asname or alias.name
                names[name]+=1
                if node.module and not node.level:imports[name]=(node.module,alias.name,node.lineno)
        elif isinstance(node,(ast.ClassDef,ast.FunctionDef,ast.AsyncFunctionDef)):
            names[node.name]+=1
        elif isinstance(node,(ast.Assign,ast.AnnAssign)):
            for target in node.targets if isinstance(node,ast.Assign) else [node.target]:
                if isinstance(target,ast.Name):names[target.id]+=1
    return {n:v for n,v in imports.items() if names[n]==1},names


def _method(node, name):
    return isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and node.func.attr==name


def _constructor(node, imports, origin):
    return isinstance(node,ast.Name) and imports.get(node.id,())[:2]==origin


def _select_model(expr,imports):
    while isinstance(expr,ast.Call) and isinstance(expr.func,ast.Attribute) and expr.func.attr in ('where','order_by','offset','limit'):
        expr=expr.func.value
    if isinstance(expr,ast.Call) and _constructor(expr.func,imports,('sqlmodel','select')) and len(expr.args)==1 and isinstance(expr.args[0],ast.Name):
        return expr.args[0].id
    return None


def _operations(body, sessions, imports, guards=()):
    rows=[]
    for pos,stmt in enumerate(body):
        if isinstance(stmt,ast.If):
            guard_line=stmt.test.lineno if stmt.test.end_lineno==stmt.test.lineno else None
            rows.extend(_operations(stmt.body,sessions,imports,(*guards,(guard_line,True))))
            rows.extend(_operations(stmt.orelse,sessions,imports,(*guards,(guard_line,False))))
        if not isinstance(stmt,ast.Assign) or len(stmt.targets)!=1 or not isinstance(stmt.targets[0],ast.Name):
            continue
        var=stmt.targets[0].id
        value=stmt.value
        following=body[pos+1:pos+3]
        if not following:continue
        next_stmt=following[0]
        next_val=getattr(next_stmt,'value',None)
        model=_select_model(value,imports)
        if model and isinstance(next_stmt,ast.Assign):
            execution=next_val
            if _method(execution,'all') or _method(execution,'one'):execution=execution.func.value
            if _method(execution,'exec') and isinstance(execution.func.value,ast.Name) and execution.func.value.id in sessions and len(execution.args)==1 and isinstance(execution.args[0],ast.Name) and execution.args[0].id==var:
                filters=[]
                chain=value
                while isinstance(chain,ast.Call) and isinstance(chain.func,ast.Attribute):
                    if chain.func.attr=='where':filters.extend(arg.lineno if arg.lineno==arg.end_lineno else None for arg in chain.args)
                    chain=chain.func.value
                rows.append(('read',model,sessions[execution.func.value.id],execution.lineno,[value.lineno],guards,filters))
        if _method(value,'model_validate') and isinstance(value.func.value,ast.Name) and len(following)==2:
            commit=getattr(following[1],'value',None)
            if not (isinstance(next_stmt,ast.Expr) and isinstance(following[1],ast.Expr)
                    and _method(next_val,'add') and _method(commit,'commit')
                    and isinstance(next_val.func.value,ast.Name) and isinstance(commit.func.value,ast.Name)
                    and next_val.func.value.id==commit.func.value.id and commit.func.value.id in sessions
                    and len(next_val.args)==1 and isinstance(next_val.args[0],ast.Name)
                    and next_val.args[0].id==var and not commit.args and not commit.keywords):
                continue
            rows.append(('write',value.func.value.id,sessions[commit.func.value.id],commit.lineno,[value.lineno,next_val.lineno],guards,[]))
    return rows


def facts(tree):
    imports,names=_imports(tree.body)
    bases={}
    tables={}
    providers={}
    aliases={}
    functions={}
    for node in tree.body:
        if isinstance(node,ast.ClassDef) and names[node.name]==1 and len(node.bases)==1 and isinstance(node.bases[0],ast.Name):
            base=node.bases[0]
            if _constructor(base,imports,('sqlmodel','SQLModel')) or base.id in bases:
                bases[node.name]=node.lineno
                if any(k.arg=='table' and isinstance(k.value,ast.Constant) and k.value.value is True for k in node.keywords):
                    tables[node.name]=node.lineno
        if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)):
            args=[*node.args.posonlyargs,*node.args.args,*node.args.kwonlyargs]
            shadowed={x.id for stmt in node.body for x in ast.walk(stmt) if isinstance(x,ast.Name) and isinstance(x.ctx,(ast.Store,ast.Del))}
            sessions={a.arg:a.annotation.id for a in args if isinstance(a.annotation,ast.Name) and a.arg not in shadowed}
            usable={n:v for n,v in imports.items() if n not in shadowed and n not in {a.arg for a in args}}
            if rows:=_operations(node.body,sessions,usable):
                for decorator in node.decorator_list:
                    functions[node.name,decorator.lineno]=[r for r in rows if r[1] in usable]
            if names[node.name]==1 and len(node.body)==1 and isinstance(node.body[0],ast.With):
                ctx=node.body[0]
                if len(ctx.items)==1 and len(ctx.body)==1:
                    item=ctx.items[0]
                    value=getattr(ctx.body[0],'value',None)
                    if (isinstance(item.context_expr,ast.Call) and _constructor(item.context_expr.func,usable,('sqlmodel','Session'))
                            and isinstance(item.optional_vars,ast.Name) and isinstance(value,ast.Yield)
                            and isinstance(value.value,ast.Name) and value.value.id==item.optional_vars.id):
                        providers[node.name]=ctx.lineno
        if isinstance(node,ast.Assign) and len(node.targets)==1 and isinstance(node.targets[0],ast.Name) and names[node.targets[0].id]==1:
            value=node.value
            if not isinstance(value,ast.Subscript) or not _constructor(value.value,imports,('typing','Annotated')):continue
            parts=value.slice.elts if isinstance(value.slice,ast.Tuple) else []
            if len(parts)!=2 or not _constructor(parts[0],imports,('sqlmodel','Session')):continue
            dep=parts[1]
            if (isinstance(dep,ast.Call) and _constructor(dep.func,imports,('fastapi','Depends')) and len(dep.args)==1
                    and isinstance(dep.args[0],ast.Name) and dep.args[0].id in providers):
                aliases[node.targets[0].id]=(node.lineno,providers[dep.args[0].id])
    return {'imports':imports,'tables':tables,'aliases':aliases,'functions':functions}


def attach(modules,routes):
    resolved={}
    def locate(file,name):
        src=modules[file]['imports'].get(name)
        if not src:return None,None,None
        if src[0] not in resolved:resolved[src[0]]=_module(modules,src[0])
        return resolved[src[0]],src[1],src[2]
    for route in routes:
        server=route['server']
        file=server['file']
        if file not in modules:continue
        for op,model,session,line,lines,guards,filters in modules[file]['functions'].get((server['function'],server['line']),[]):
            definition,table,model_import=locate(file,model)
            dep,alias,session_import=locate(file,session)
            if (not definition or table not in modules[definition]['tables'] or not dep or alias not in modules[dep]['aliases']):continue
            proof=[(file,n) for n in [*lines,model_import,session_import]]
            proof.append((definition,modules[definition]['tables'][table]))
            proof.extend((dep,n) for n in modules[dep]['aliases'][alias])
            route.setdefault('data_steps',[]).append({'operation':op,'model':table,'file':file,'line':line,
                'evidence':[{'file':f,'line':n} for f,n in proof],
                **({'guards':[{'file':file,'line':n,'when':truth} for n,truth in guards]} if guards and all(n for n,_ in guards) else {}),
                **({'filters':[{'file':file,'line':n} for n in filters]} if filters and all(filters) else {})})
