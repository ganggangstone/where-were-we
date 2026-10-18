#!/usr/bin/env python3
"""Prepare a relocatable macOS Python/MCP runtime; never copy a developer venv.

Build on each target architecture separately. Downloads occur only at build time.
Python archives: https://github.com/astral-sh/python-build-standalone/releases/tag/20261013
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import plistlib
import re
import shlex
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
PYTHON_VERSION = '3.13.16'
PYTHON_RELEASE = '20261013'
ARCHIVES = {
    'aarch64-apple-darwin': '16a5332fb0dcb77f163fc8f8cbccd95be1644cc53e68e5d2a79f50afd6680a0e',
    'x86_64-apple-darwin': 'f507ae04eb7747cd97cb484e8c5d83936cbfc52d9b08a1f35c00b47c707b1ae1',
}
FULL_ARCHIVES = {
    'aarch64-apple-darwin': '3497822d8bf4884bc79258f62668f985654d03d40ec74da4ca9ae7a5667c4362',
    'x86_64-apple-darwin': '2a36086baac5e4584b59d4638df04a1c348244b276829125f1aa038ab97a1ce6',
}
# Explicit allowlist: no project maps, private documents, venvs, or other repo files.
BACKEND_FILES = ('mapcore.py', 'project.py', 'mcp_server.py', 'extract.py', 'ai_extract.py', 'briefing.py', 'connections.py', 'refresh.py',
                 'collect.py', 'group.py', 'steps.py', 'system.py', 'jobs.py')


def digest(path):
    with open(path, 'rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def fetch_archive(target, cache, full=False):
    suffix = 'pgo+lto-full.tar.zst' if full else 'install_only_stripped.tar.gz'
    expected = (FULL_ARCHIVES if full else ARCHIVES)[target]
    name = f'cpython-{PYTHON_VERSION}+{PYTHON_RELEASE}-{target}-{suffix}'
    archive = cache / name
    url = f'https://github.com/astral-sh/python-build-standalone/releases/download/{PYTHON_RELEASE}/{name}'
    return fetch_checked(url, archive, expected)


def fetch_checked(url, archive, expected):
    archive.parent.mkdir(parents=True, exist_ok=True)
    if archive.exists() and digest(archive) != expected:
        raise ValueError(f'Cached Python archive checksum mismatch: {archive}')
    if not archive.exists():
        partial = archive.with_suffix('.partial')
        try:
            with urllib.request.urlopen(url, timeout=120) as response, partial.open('wb') as output:
                shutil.copyfileobj(response, output)
            if digest(partial) != expected:
                raise ValueError('Downloaded Python archive checksum mismatch')
            partial.replace(archive)
        finally:
            partial.unlink(missing_ok=True)
    return archive


def unpack(archive, destination):
    # Python 3.12+ data filter rejects paths and links escaping the destination.
    with tarfile.open(archive, 'r:gz') as tar:
        tar.extractall(destination, filter='data')
    if not (destination / 'python/bin/python3').is_file():
        raise ValueError('Python archive does not contain python/bin/python3')


def clean_environment():
    return {key: value for key, value in os.environ.items()
            if not key.startswith(('PYTHON', 'PIP_')) and key != 'VIRTUAL_ENV'}


def release_environment():
    """Remap source paths in every Rust dependency, including panic strings."""
    env = dict(os.environ)
    encoded = env.get('CARGO_ENCODED_RUSTFLAGS')
    flags = encoded.split('\x1f') if encoded else shlex.split(env.get('RUSTFLAGS', ''))
    flags += [f'--remap-path-prefix={Path.home()}=/build/home',
              f'--remap-path-prefix={ROOT}=/build/where-were-we']
    env.pop('RUSTFLAGS', None)
    env['CARGO_ENCODED_RUSTFLAGS'] = '\x1f'.join(flags)
    return env


def seal_app(app):
    """Seal local bundles, preserving any already valid distribution signature."""
    verify = ['/usr/bin/codesign', '--verify', '--deep', '--strict', str(app)]
    if subprocess.run(verify, capture_output=True, text=True).returncode == 0:
        return
    details = subprocess.run(['/usr/bin/codesign', '-d', '--verbose=4', str(app)],
                             capture_output=True, text=True)
    if details.returncode == 0:
        if 'Signature=adhoc' not in details.stderr:
            raise ValueError('Invalid identity signature: rebuild with the original signing identity')
    elif 'code object is not signed at all' not in details.stderr:
        raise ValueError('Cannot inspect the app signature: ' + details.stderr.strip())
    # Linker-only ad-hoc signatures do not seal app resources and can stall launch.
    # This local signature is not Developer ID signing or notarization.
    subprocess.run(['/usr/bin/codesign', '--force', '--deep', '--sign', '-', str(app)], check=True)
    subprocess.run(verify, check=True)


def build_app(target, no_sign=False):
    command = ['cargo', 'tauri', 'build', '--target', target, '--bundles', 'app']
    if no_sign:
        command.append('--no-sign')
    # The Tauri beforeBuildCommand prepares the runtime; do not run it twice.
    subprocess.run(command, cwd=ROOT, env=release_environment(), check=True)
    seal_app(ROOT / "src-tauri/target" / target / "release/bundle/macos/where-were-we.app")


def cask_definition(version, hashes):
    if not re.fullmatch(r'(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)', version):
        raise ValueError('A stable major.minor.patch version is required')
    if not hashes or not set(hashes).issubset(ARCHIVES) or any(not re.fullmatch(r'[a-f0-9]{64}', h) for h in hashes.values()):
        raise ValueError('Provide SHA-256 hashes for actual macOS release archives')
    lines = ['cask "where-were-we" do']
    both = len(hashes) == 2
    if both:
        lines += ['  arch arm: "aarch64-apple-darwin", intel: "x86_64-apple-darwin"', '']
    lines.append(f'  version "{version}"')
    if both:
        lines += [f'  sha256 arm: "{hashes["aarch64-apple-darwin"]}",',
                  f'         intel: "{hashes["x86_64-apple-darwin"]}"']
        target = '#{arch}'
    else:
        target, checksum = next(iter(hashes.items()))
        lines.append(f'  sha256 "{checksum}"')
    lines += ['', f'  url "https://github.com/ganggangstone/where-were-we/releases/download/v#{{version}}/where-were-we_#{{version}}_{target}.zip"',
              '  name "where-were-we"', '  desc "Local code structure maps for humans and AI agents"',
              '  homepage "https://github.com/ganggangstone/where-were-we"', '']
    if not both:
        lines.append('  depends_on arch: :' + ('arm64' if target.startswith('aarch64') else 'x86_64'))
    lines += ['  depends_on formula: ["gh", "git"]', '  depends_on macos: :big_sur', '',
              '  app "where-were-we.app"', 'end', '']
    return '\n'.join(lines)


def release_preview(target):
    """Create a release ZIP and print a reviewable cask/notes; never publish."""
    config = json.loads((ROOT / 'src-tauri/tauri.conf.json').read_text())
    version = config['version']
    cask_definition(version, {target: '0' * 64})  # Validate before creating output paths.
    app = ROOT / 'src-tauri/target' / target / 'release/bundle/macos/where-were-we.app'
    with (app / 'Contents/Info.plist').open('rb') as stream:
        info = plistlib.load(stream)
    if info['CFBundleShortVersionString'] != version:
        raise ValueError('Build the current app version before preparing its release')
    resources = app / 'Contents/Resources/runtime'
    if json.loads((resources / 'runtime.json').read_text())['target'] != target:
        raise ValueError('The app and bundled Python architectures differ')
    actual = subprocess.check_output(['/usr/bin/lipo', '-archs', str(app / 'Contents/MacOS/where-were-we')], text=True).split()
    if actual != ['arm64' if target.startswith('aarch64') else 'x86_64']:
        raise ValueError('The app binary does not match the selected architecture')
    if list(app.rglob('__pycache__')):
        raise ValueError('Rebuild the app without Python bytecode caches')
    home = str(Path.home()).encode()
    if any(home in path.read_bytes() for path in app.rglob('*') if path.is_file()):
        raise ValueError('Build-machine home path found: build with --build before releasing')
    readme = (ROOT / 'README.md').read_text()
    notes = readme.split('<!-- release-notes:start -->', 1)[1].split('<!-- release-notes:end -->', 1)[0].strip()
    if '### 한국어' not in notes or '### English' not in notes:
        raise ValueError('Release notes must include Korean and English')
    output = ROOT / 'src-tauri/target/release-assets'
    output.mkdir(parents=True, exist_ok=True)
    archive = output / f'where-were-we_{version}_{target}.zip'
    seal_app(app)
    subprocess.run(['/usr/bin/ditto', '-c', '-k', '--keepParent', '--norsrc', str(app), str(archive)], check=True)
    checksum = digest(archive)
    return {'version': version, 'archive': str(archive), 'sha256': checksum,
            'cask': cask_definition(version, {target: checksum}), 'notes': notes}


def prepare(target, output):
    native = {'arm64': 'aarch64', 'x86_64': 'x86_64'}.get(platform.machine())
    if platform.system() != 'Darwin' or target != f'{native}-apple-darwin':
        raise ValueError('Build on a macOS machine matching --target; universal/cross builds are not supported')
    if output.exists() and not (output / 'runtime.json').is_file():
        raise ValueError(f'Refusing to replace an unmanaged directory: {output}')
    cache = ROOT / 'src-tauri/target/runtime-cache'
    archive = fetch_archive(target, cache)
    # install_only archives omit the dependency notices. Take those from the
    # matching full distribution, verifying its independently pinned digest.
    notices = fetch_archive(target, cache, full=True)
    # This PBS metadata references zlib-ng's notice, but its full archive omits
    # that text. Use the version in this PBS release's pythonbuild/downloads.json;
    # this does not assert that zlib-ng is included (macOS zlib is a system link).
    zlib_notice = fetch_checked('https://raw.githubusercontent.com/python/cpython-source-deps/zlib-ng-2.2.4/LICENSE.md',
                               cache / 'LICENSE.zlib-ng.txt',
                               '6c9f0d975b41afaa34d22f55bb8986ce69e5cb7ad327cb2b28820cd425edf5ee')
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.runtime-', dir=output.parent) as temporary:
        stage = Path(temporary)
        unpack(archive, stage)
        subprocess.run(['/usr/bin/tar', '-xf', str(notices), '-C', str(stage),
                        'python/PYTHON.json', 'python/licenses'], check=True)
        shutil.copyfile(zlib_notice, stage / 'python/licenses/LICENSE.zlib-ng.txt')
        python = stage / 'python/bin/python3'
        env = clean_environment()
        subprocess.run([str(python), '-I', '-m', 'pip', '--isolated', 'install',
                        '--disable-pip-version-check', '--no-compile', '--only-binary=:all:',
                        '--require-hashes', '-r', str(ROOT / 'requirements-runtime.lock')],
                       env=env, check=True)
        backend = stage / 'backend'
        backend.mkdir()
        for name in BACKEND_FILES:
            shutil.copyfile(ROOT / name, backend / name)
        shutil.copyfile(ROOT / 'LICENSE', stage / 'LICENSE.where-were-we')
        shutil.copyfile(ROOT / 'requirements-runtime.lock', stage / 'requirements-runtime.lock')
        # Keep distribution licenses, package metadata/licenses and SSL certificates.
        # Avoid bytecode containing the build machine's source paths.
        for directory in sorted(stage.rglob('__pycache__'), reverse=True):
            shutil.rmtree(directory)
        # Console scripts contain build-time absolute shebangs and are unused.
        # Keep one real interpreter: the bundler dereferences symlinks, which
        # would otherwise duplicate the Python executable under several names.
        actual_python = python.resolve()
        python.unlink()
        actual_python.rename(python)
        for entry in python.parent.iterdir():
            if entry != python:
                entry.unlink()
        manifest = {'target': target, 'python': PYTHON_VERSION, 'archive_sha256': ARCHIVES[target],
                    'notices_archive_sha256': FULL_ARCHIVES[target],
                    'requirements_sha256': digest(ROOT / 'requirements-runtime.lock')}
        (stage / 'runtime.json').write_text(json.dumps(manifest, indent=2) + '\n')
        subprocess.run([str(python), '-I', '-B', '-c',
                        'import ssl, subprocess; from mcp.server import MCPServer; '
                        'subprocess.run([__import__("sys").executable, "-I", "-B", "-c", "import mcp"], check=True)'],
                       env=env, check=True)
        # Only generated output with our marker can be replaced.
        if output.exists():
            shutil.rmtree(output)
        shutil.move(str(stage), str(output))
    print(f'Prepared {target}: {output}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', choices=ARCHIVES,
                        default=os.environ.get('TAURI_ENV_TARGET_TRIPLE') or
                        {'arm64': 'aarch64-apple-darwin', 'x86_64': 'x86_64-apple-darwin'}.get(platform.machine()))
    parser.add_argument('--build', action='store_true', help='Build the .app with build paths removed (requires cargo-tauri)')
    parser.add_argument('--no-sign', action='store_true', help='Skip identity signing; seal the local app with an ad-hoc signature')
    parser.add_argument('--release-preview', action='store_true', help='Package the built app and print cask/notes without publishing')
    args = parser.parse_args()
    if args.build:
        build_app(args.target, args.no_sign)
    elif not args.release_preview:
        prepare(args.target, ROOT / 'src-tauri/runtime')
    if args.release_preview:
        print(json.dumps(release_preview(args.target), ensure_ascii=False, indent=2))
