"""Local, commit-bound Python declarations and statically resolvable module imports."""
import ast
import os
from pathlib import PurePosixPath
import re
import subprocess
import warnings

MAX_FILES = 2048
MAX_BYTES = 64 * 1024 * 1024
MAX_FILE_BYTES = 512 * 1024
MAX_DECLARATIONS = 20_000
MAX_IMPORTS = 20_000


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
        if file.endswith('.py'):
            candidates[file] = (oid, int(size))
        else:
            unsupported += 1

    candidates = {file: entry for file, entry in candidates.items() if entry[0] not in denied}

    def module_file(base, roots):
        matches = {file for root in roots for suffix in ('.py', '/__init__.py')
                   if (file := root + base + suffix) in candidates}
        return next(iter(matches)) if len(matches) == 1 else None

    files = []
    imports = []
    parsed = set()
    consumed = declarations = unresolved = 0
    selected = []
    truncated = False
    for file, entry in candidates.items():
        size = entry[1]
        if size > MAX_FILE_BYTES or consumed + size > MAX_BYTES or len(selected) >= MAX_FILES:
            truncated = True
            continue
        selected.append((file, entry))
        consumed += size
    for file, raw in _blobs(git, env, selected):
        try:
            with warnings.catch_warnings():
                warnings.simplefilter('ignore', SyntaxWarning)
                tree = ast.parse(raw)
        except (SyntaxError, ValueError, UnicodeError, RecursionError):
            continue
        parsed.add(file)
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
        files.append({'file': file, 'declarations': rows})
    resolved = [edge for edge in imports if edge['target'] in parsed]
    unresolved += len(imports) - len(resolved)
    coverage = {'candidate_files': len(candidates), 'indexed_files': len(files),
                'skipped_files': len(candidates) - len(files), 'unsupported_files': unsupported,
                'unresolved_imports': unresolved, 'truncated': truncated}
    return {'commit': commit, 'files': files, 'imports': resolved, 'coverage': coverage}
