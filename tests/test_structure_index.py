import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import structure_index


class Structure(unittest.TestCase):
    def test_pinned_declarations_and_exact_imports_without_reading_private_or_untracked_files(self):
        with tempfile.TemporaryDirectory() as root:
            repo = Path(root)
            git = lambda *args: subprocess.check_output(['git','-C',root,*args]).decode().strip()
            git('init','-q')
            sources = {'src/pkg/__init__.py':'', 'src/pkg/db.py':'class Store:\n    async def read(self): pass\n',
                       'src/pkg/cli.py':'from .db import Store\nimport pkg.db\nimport missing\nfrom . import dynamic\n',
                       'docs.txt':'text', '.aws/private.py':'def secret(): pass', 'broken.py':'def ??',
                       'ambiguous.py':'import dup', 'dup.py':'', 'src/dup.py':''}
            for name,text in sources.items():
                path=repo/name
                path.parent.mkdir(parents=True,exist_ok=True)
                path.write_text(text)
            os.symlink('src/pkg/db.py',repo/'link.py')
            git('add','.')
            git('-c','user.name=Test','-c','user.email=test@example.invalid','commit','-qm','original')
            pin=git('rev-parse','HEAD')
            (repo/'src/pkg/db.py').write_text('def altered(): pass')
            index=structure_index.build(root,pin)
            rows={f['file']:f['declarations'] for f in index['files']}
            self.assertEqual(rows['src/pkg/db.py'],[{'kind':'class','name':'Store','line':1},
                                                   {'kind':'async_function','name':'Store.read','line':2}])
            self.assertEqual([(e['line'],e['target']) for e in index['imports'] if e['file']=='src/pkg/cli.py'],
                             [(1,'src/pkg/db.py'),(2,'src/pkg/db.py')])
            self.assertFalse({'link.py','broken.py','.aws/private.py'} & set(rows))
            self.assertEqual(index['coverage']['unresolved_imports'],3)
            self.assertEqual(index['coverage']['skipped_files'],1)
            self.assertEqual(index['coverage']['unsupported_files'],1)
            with patch.object(structure_index,'MAX_FILES',1):
                limited=structure_index.build(root,pin)
            self.assertTrue(limited['coverage']['truncated'])
            self.assertLessEqual(limited['coverage']['indexed_files'],1)
            by_dir={row['directory']:row for row in limited['coverage']['directories']}
            self.assertEqual(set(by_dir),{'.','src'})
            self.assertEqual(sum(row['candidate_files'] for row in by_dir.values()),limited['coverage']['candidate_files'])
            self.assertEqual(sum(row['indexed_files'] for row in by_dir.values()),limited['coverage']['indexed_files'])
            self.assertEqual(sum(row['skipped_files'] for row in by_dir.values()),limited['coverage']['skipped_files'])
            self.assertNotIn('directories',index['coverage'])

    def test_absolute_import_names_the_nearest_package_root_before_the_repository_root(self):
        with tempfile.TemporaryDirectory() as root:
            git = lambda *args: subprocess.check_output(['git','-C',root,*args]).decode().strip()
            git('init','-q')
            sources = {'scripts/jobs/run.py':'', 'sub/scripts/__init__.py':'', 'sub/scripts/jobs/__init__.py':'', 'sub/scripts/jobs/run.py':'',
                       'sub/scripts/jobs/main.py':'import scripts.jobs.run\nimport scripts.only\n', 'scripts/only.py':'',
                       'tool/main.py':'import scripts.jobs.run\n'}
            for name,text in sources.items():
                path=Path(root)/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text)
            git('add','.');git('-c','user.name=Test','-c','user.email=test@example.invalid','commit','-qm','x')
            index=structure_index.build(root,git('rev-parse','HEAD'))
            self.assertEqual(sorted((e['file'],e['target']) for e in index['imports']),
                             [('sub/scripts/jobs/main.py','scripts/only.py'),('sub/scripts/jobs/main.py','sub/scripts/jobs/run.py'),
                              ('tool/main.py','scripts/jobs/run.py')])

    def test_selected_file_uses_only_its_blob_and_resolves_unsampled_imports(self):
        import json
        import sys
        with tempfile.TemporaryDirectory() as root:
            repo=Path(root)
            git=lambda *args:subprocess.check_output(['git','-C',root,*args]).decode().strip()
            git('init','-q')
            (repo/'target.py').write_text('import peer\ndef run(): pass')
            (repo/'peer.py').write_text('class Peer: pass')
            (repo/'.aws').mkdir()
            (repo/'.aws/key.py').write_text('class Private: pass')
            (repo/'alias.py').write_bytes((repo/'.aws/key.py').read_bytes())
            (repo/'odd_alias.py').write_text('def private_alias(): pass')
            (repo/'note.md').write_text('note')
            (repo/'bad.py').write_text('def ?')
            os.symlink('target.py',repo/'link.py')
            git('add','.')
            odd_oid=git('rev-parse',':odd_alias.py')
            subprocess.run(['git','-C',root,'update-index','-z','--index-info'],check=True,
                           input=b'100644 '+odd_oid.encode()+b'\t.aws/invalid-\xff.py\0')
            git('-c','user.name=Test','-c','user.email=test@example.invalid','commit','-qm','original')
            pin=git('rev-parse','HEAD')
            with patch.object(structure_index,'_blobs',wraps=structure_index._blobs) as blobs:
                result=structure_index.build(root,pin,only_file='target.py')
                self.assertEqual([file for file,_ in blobs.call_args.args[2]],['target.py'])
            self.assertEqual(result['imports'],[{'file':'target.py','target':'peer.py','line':1}])
            self.assertEqual(result['declarations'],[{'name':'run','kind':'function','line':2}])
            for file,expected in [('note.md','unsupported'),('bad.py','unparsed'),('link.py','unavailable'),
                                  ('.aws/key.py','unavailable'),('alias.py','unavailable'),('odd_alias.py','unavailable'),('unknown.py','unavailable')]:
                self.assertEqual(structure_index.build(root,pin,only_file=file)['status'],expected)
            with patch.object(structure_index,'MAX_FILE_BYTES',2):
                self.assertEqual(structure_index.build(root,pin,only_file='target.py')['status'],'too_large')
            with self.assertRaises(ValueError):
                structure_index.build(root,pin,only_file='../target.py')
            folder=repo/'maps'/'demo'
            folder.mkdir(parents=True)
            (folder/'dev.json').write_text(json.dumps({'repo':root,'ref':'HEAD','commit':pin,'structure_index':{'commit':pin}}))
            cmd=[sys.executable,str(Path(structure_index.__file__).with_name('project.py')),'file-structure','demo','--','','dev']
            env={**os.environ,'WHERE_WERE_WE_ROOT':str(folder.parent)}
            self.assertEqual(json.loads(subprocess.check_output(cmd+[pin,'target.py'],env=env)),result)
            (folder/'main.json').write_text(json.dumps({'repo':root,'ref':pin,'commit':pin,'inventory':{'commit':pin}}))
            main_cmd=cmd[:-1]+['main']
            self.assertEqual(json.loads(subprocess.check_output(main_cmd+[pin,'target.py'],env=env)),result)
            git('-c','user.name=Test','-c','user.email=test@example.invalid','commit','--allow-empty','-qm','Advance dev')
            different_branch=subprocess.run(cmd+[pin,'target.py'],env=env,capture_output=True)
            self.assertNotEqual(different_branch.returncode,0)
            self.assertEqual(json.loads(subprocess.check_output(main_cmd+[pin,'target.py'],env=env)),result)
            stale=subprocess.run(cmd+['0'*40,'target.py'],env=env,capture_output=True)
            self.assertNotEqual(stale.returncode,0)
            self.assertIn(b'Code changed',stale.stderr)

    def test_cli_manifests_resolve_only_tracked_local_targets_at_pin(self):
        with tempfile.TemporaryDirectory() as root:
            repo=Path(root)
            git=lambda *args:subprocess.check_output(['git','-C',root,*args]).decode().strip()
            git('init','-q')
            sources={'package.json':'{"bin":{"launch":"./tool","linked":"link","missing":"dist/tool"}}',
                     'tool':'#!/usr/bin/env node', 'nested/package.json':'{"name":"@org/other","bin":"../tool"}',
                     'pyproject.toml':'[project.scripts]\nstart = "app:run"\nbad = "dup:run"\n',
                     'src/app.py':'def run(): pass','dup.py':'','src/dup.py':''}
            for file,content in sources.items():
                path=repo/file
                path.parent.mkdir(parents=True,exist_ok=True)
                path.write_text(content)
            os.symlink('tool',repo/'link')
            git('add','.')
            git('-c','user.name=Test','-c','user.email=test@example.invalid','commit','-qm','commands')
            pin=git('rev-parse','HEAD')
            (repo/'package.json').write_text('{}')
            result=structure_index.build(root,pin)
            by_command={r['command']:r for r in result['cli_entries']}
            self.assertEqual(set(by_command),{'launch','start'})
            self.assertEqual(by_command['launch'],dict(command='launch',kind='npm_bin',file='package.json',target='tool',line=1))
            self.assertEqual(by_command['start'],dict(command='start',kind='python_script',file='pyproject.toml',
                                                       target='src/app.py',symbol='run',line=2,target_line=1))
            self.assertEqual(result['coverage']['cli_manifests_read'],3)
            private=structure_index.build(root,pin,excluded=lambda file:file=='tool')
            self.assertEqual([r['command'] for r in private['cli_entries']],['start'])

    def test_project_description_uses_pinned_plain_text_and_excludes_private_aliases(self):
        with tempfile.TemporaryDirectory() as root:
            repo=Path(root)
            git=lambda *args:subprocess.check_output(['git','-C',root,*args]).decode().strip()
            git('init','-q')
            (repo/'README.md').write_text('# Example\n\n![Build](external)\n\nA public project introduction.\n')
            (repo/'package.json').write_text('{\n"description":"A packaged tool."\n}')
            (repo/'pyproject.toml').write_text('[project]\ndescription = "A Python tool."')
            (repo/'alias').write_bytes((repo/'package.json').read_bytes())
            git('add','.')
            git('-c','user.name=Test','-c','user.email=test@example.invalid','commit','-qm','descriptions')
            pin=git('rev-parse','HEAD')
            (repo/'README.md').write_text('Working tree text')
            def description(*excluded):
                return structure_index.build(root,pin,excluded=excluded.__contains__)['project_description']
            self.assertEqual(description(),dict(file='package.json',line=2,text='A packaged tool.'))
            self.assertEqual(description('alias'),dict(file='pyproject.toml',line=2,text='A Python tool.'))
            self.assertEqual(description('alias','pyproject.toml'),dict(file='README.md',line=5,text='A public project introduction.'))
            self.assertIsNone(description('alias','pyproject.toml','README.md'))
            (repo/'README.md').write_text('# Example\n\n## Installation\n\nInstall this tool.\n')
            git('add','README.md')
            git('-c','user.name=Test','-c','user.email=test@example.invalid','commit','-qm','instructions only')
            pin=git('rev-parse','HEAD')
            self.assertIsNone(description('alias','pyproject.toml'))

    def test_declarations_inside_statement_suites_keep_source_order(self):
        with tempfile.TemporaryDirectory() as root:
            repo=Path(root)
            git=lambda *a:subprocess.check_output(['git','-C',root,*a]).decode().strip()
            git('init','-q')
            (repo/'example.py').write_text("""def main():
    try:
        def first(): pass
    except Exception:
        def recovered(): pass
    else:
        def success(): pass
    finally:
        def last(): pass
    match 1:
        case 1:
            import peer
            def matched(): pass
""")
            (repo/'peer.py').touch()
            git('add','.')
            git('-c','user.name=Test','-c','user.email=test@example.invalid','commit','-qm','suites')
            result=structure_index.build(root,git('rev-parse','HEAD'),only_file='example.py')
            self.assertEqual([d['name'] for d in result['declarations']],
                             ['main','main.first','main.recovered','main.success','main.last','main.matched'])
            self.assertEqual(result['imports'],[{'file':'example.py','line':12,'target':'peer.py'}])

    def test_documented_features_only_quote_visible_complete_bullets_of_pinned_readme(self):
        with tempfile.TemporaryDirectory() as root:
            repo=Path(root)
            git=lambda *a:subprocess.check_output(['git','-C',root,*a]).decode().strip()
            git('init','-q')
            markdown="""# Demo
<!--
## Features
- Commented claim
-->
~~~
## Features
- Fenced claim
~~~
## 주요 기능
- 파일 목록을 표시합니다.
- Only works
  on Linux.
- See [site](https://example.org)
- Shows exact `status`
## Future
- Planned feature
"""
            (repo/'README.md').write_text(markdown)
            (repo/'alias').write_text(markdown)
            git('add','.')
            git('-c','user.name=Test','-c','user.email=test@example.invalid','commit','-qm','docs')
            pin=git('rev-parse','HEAD')
            (repo/'README.md').write_text('## Features\n- Untracked text')
            def features(**options):
                return structure_index.build(root,pin,**options)['documented_features']
            self.assertEqual(features(),[{'file':'README.md','line':11,'text':'파일 목록을 표시합니다.'},
                                         {'file':'README.md','line':15,'text':'Shows exact `status`'}])
            self.assertEqual(features(excluded=lambda f:f=='alias'),[])

    def test_go_declarations_and_only_unambiguous_same_module_imports(self):
        with tempfile.TemporaryDirectory() as root:
            repo=Path(root)
            git=lambda *a:subprocess.check_output(['git','-C',root,*a]).decode().strip()
            git('init','-q')
            sources={'go.mod':'module example.org/demo','cmd/main.go':"""package main
import (
    "example.org/demo/one"
    "example.org/demo/many"
    "example.org/demo/nested"
    "fmt"
)
type (Item struct{}; Alias = int)
func (i *Item) Run() {}
func main() {}
""",'one/file.go':'package one','one/file_test.go':'package one','many/a.go':'package many',
                     'many/b.go':'package many','nested/go.mod':'module example.org/other','nested/x.go':'package nested'}
            for file,text in sources.items():
                path=repo/file
                path.parent.mkdir(parents=True,exist_ok=True)
                path.write_text(text)
            git('add','.')
            git('-c','user.name=Test','-c','user.email=test@example.invalid','commit','-qm','go module')
            pin=git('rev-parse','HEAD')
            result=structure_index.build(root,pin,only_file='cmd/main.go')
            self.assertEqual([(d['kind'],d['name'],d['line']) for d in result['declarations']],
                             [('type','Item',8),('type','Alias',8),('method','Run',9),('function','main',10)])
            self.assertEqual(result['imports'],[{'file':'cmd/main.go','line':3,'target':'one/file.go'}])
            self.assertEqual(result['package_imports'],[{'file':'cmd/main.go','line':4,'package':'example.org/demo/many',
                                                        'directory':'many','member_count':2,'members':['many/a.go','many/b.go']}])
            self.assertEqual(result['coverage']['unresolved_imports'],2)
            full=structure_index.build(root,pin)
            self.assertEqual(full['package_imports'],result['package_imports'])
            hidden=structure_index.build(root,pin,only_file='cmd/main.go',excluded=lambda f:f=='many/b.go')
            self.assertEqual(hidden['package_imports'],[])
            self.assertEqual(hidden['imports'],result['imports'])
            private=structure_index.build(root,pin,only_file='cmd/main.go',excluded=lambda f:f=='one/file.go')
            self.assertEqual(private['imports'],[])
            for n in range(9):
                (repo/f'many/extra{n}.go').write_text('package many')
            git('add','many')
            git('-c','user.name=Test','-c','user.email=test@example.invalid','commit','-qm','more package files')
            updated=structure_index.build(root,git('rev-parse','HEAD'),only_file='cmd/main.go')
            package=updated['package_imports'][0]
            self.assertEqual(package['member_count'],11)
            self.assertEqual(len(package['members']),8)
            self.assertEqual(updated['imports'],result['imports'])

    def test_cobra_requires_returned_literal_and_direct_registered_constructor(self):
        with tempfile.TemporaryDirectory() as root:
            repo=Path(root)
            git=lambda *a:subprocess.check_output(['git','-C',root,*a]).decode().strip()
            git('init','-q')
            (repo/'go.mod').write_text('module example.org/cli')
            (repo/'main.go').write_text("""package main
import ("github.com/spf13/cobra"; child "example.org/cli/child")
func New() *cobra.Command {
 cmd := &cobra.Command{Use:"root",Short:"Root command"}
 cmd.AddCommand(child.New())
 if enabled {cmd.AddCommand(child.Ignored())}
 cmd.AddCommand(child.Dynamic())
 return cmd
}
""")
            (repo/'child').mkdir()
            (repo/'child/commands.go').write_text("""package child
import c "github.com/spf13/cobra"
func New() *c.Command {
 cmd := &c.Command{Use:"show [file]", Short:"Show the file", RunE:func(cmd *c.Command,args []string)error{return nil}}
 return cmd
}
func Dynamic() *c.Command {
 cmd := &c.Command{Use:"maybe", Short:makeHelp()}
 return cmd
}
func Ignored() *c.Command {
 cmd := &c.Command{Use:"hidden",Short:"Hidden"}
 return cmd
}
""")
            git('add','.')
            git('-c','user.name=Test','-c','user.email=test@example.invalid','commit','-qm','commands')
            pin=git('rev-parse','HEAD')
            rows=structure_index.build(root,pin)['cli_entries']
            self.assertEqual(rows,[dict(kind='cobra_subcommand',command='root show',description='Show the file',
                                        file='main.go',line=5,parent_line=4,target='child/commands.go',target_line=4,description_line=4,handler_line=4)])
            (repo/'child/other.go').write_text((repo/'child/commands.go').read_text())
            git('add','.')
            git('-c','user.name=Test','-c','user.email=test@example.invalid','commit','-qm','ambiguous constructor')
            self.assertEqual(structure_index.build(root,git('rev-parse','HEAD'))['cli_entries'],[])

    def test_directory_reads_only_descendants_and_resolves_root_imports(self):
        import json
        import sys
        with tempfile.TemporaryDirectory() as root:
            repo=Path(root)
            git=lambda *a:subprocess.check_output(['git','-C',root,*a]).decode().strip()
            git('init','-q')
            sources={'pkg/main.py':'import peer\ndef run(): pass','pkg/nested/work.py':'def inner(): pass',
                     'pkg/leak.py':'class Secret: pass','.aws/private.py':'class Secret: pass',
                     'pkg2/outside.py':'def outside(): pass','peer.py':'class Peer: pass'}
            for file,source in sources.items():
                path=repo/file
                path.parent.mkdir(parents=True,exist_ok=True)
                path.write_text(source)
            git('add','.')
            git('-c','user.name=Test','-c','user.email=test@example.invalid','commit','-qm','folder sample')
            pin=git('rev-parse','HEAD')
            with patch.object(structure_index,'_blobs',wraps=structure_index._blobs) as blobs:
                result=structure_index.build(root,pin,directory='pkg')
                self.assertEqual([p for call in blobs.call_args_list for p,_ in call.args[2]],['pkg/main.py','pkg/nested/work.py'])
            self.assertEqual(result['imports'],[{'file':'pkg/main.py','line':1,'target':'peer.py'}])
            self.assertEqual(result['coverage']['candidate_files'],2)
            with patch.object(structure_index,'MAX_DIRECTORY_FILES',1):
                limited=structure_index.build(root,pin,directory='pkg')
            self.assertTrue(limited['coverage']['truncated'])
            self.assertEqual(limited['coverage']['indexed_files'],1)
            with self.assertRaises(ValueError):
                structure_index.build(root,pin,directory='pkg/../pkg2')
            folder=repo/'maps/demo'
            folder.mkdir(parents=True)
            saved=json.dumps({'repo':root,'ref':'HEAD','commit':pin,'inventory':{'commit':pin}})
            (folder/'dev.json').write_text(saved)
            cmd=[sys.executable,str(Path(structure_index.__file__).with_name('project.py')),'directory-structure','demo','--','','dev']
            env={**os.environ,'WHERE_WERE_WE_ROOT':str(folder.parent)}
            response=json.loads(subprocess.check_output(cmd+[pin,'pkg'],env=env))
            self.assertEqual(response.pop('cache_progress'),{'pages':[1],'total_pages':1,'indexed_files':2,'selected_files':2,'unparsed_files':0,'first_missing_page':None})
            self.assertEqual(response,result)
            import project
            with patch('mapcore.ROOT',folder.parent),patch.object(structure_index,'build',side_effect=AssertionError('cache miss')):
                reopened=project.selected_structure('demo','','dev',pin,directory='pkg')
                self.assertEqual(reopened.pop('cache_progress')['pages'],[1])
                self.assertEqual(reopened,result)
            with patch('mapcore.ROOT',folder.parent),patch.object(structure_index,'MAX_DIRECTORY_FILES',1),patch.object(structure_index,'_blobs',wraps=structure_index._blobs) as blobs:
                second=project.selected_structure('demo','','dev',pin,directory='pkg',page=2)
                self.assertEqual(second['pagination']['page'],2)
                self.assertEqual(second['pagination']['selected_files'],1)
                self.assertEqual([p for call in blobs.call_args_list for p,_ in call.args[2]],
                                 [f['file'] for f in second['files']])
                with patch.object(structure_index,'build',side_effect=AssertionError('cache miss')):
                    self.assertEqual(project.selected_structure('demo','','dev',pin,directory='pkg',page=2),second)
                self.assertEqual(second['cache_progress']['pages'],[2])
                self.assertEqual(second['cache_progress']['first_missing_page'],1)
                first=project.selected_structure('demo','','dev',pin,directory='pkg')
                self.assertEqual(first['cache_progress']['pages'],[1,2])
                slot1,_=project._directory_cache('demo',{'path':root,'refs':{'dev':'HEAD'},'layout':{}},'','dev',pin,'pkg',1)
                project.atomic(slot1,{'key':'unrelated:17','result':{}})
                with patch.object(structure_index,'build',side_effect=AssertionError('cache miss')):
                    reopened=project.selected_structure('demo','','dev',pin,directory='pkg',page=2)
                self.assertEqual(reopened['cache_progress']['pages'],[2])
                self.assertEqual(reopened['cache_progress']['indexed_files'],1)
                self.assertEqual(reopened['cache_progress']['first_missing_page'],1)
            with patch('mapcore.ROOT',folder.parent):
                repo_config={'path':root,'refs':{'dev':'HEAD'}}
                slots=[project._directory_cache('demo',repo_config,'','dev',pin,'pkg',page)[0]
                       for page in range(1,18)]
                self.assertEqual(len(set(slots[:16])),16)
                self.assertEqual(slots[0],slots[16])
            import analysis_run
            policy=analysis_run._secret
            with patch('mapcore.ROOT',folder.parent),patch.object(analysis_run,'_secret',side_effect=lambda f:policy(f) or f=='pkg/main.py'):
                filtered=project.selected_structure('demo','','dev',pin,directory='pkg')
                self.assertEqual([f['file'] for f in filtered['files']],['pkg/nested/work.py'])
            with patch('mapcore.ROOT',folder.parent),patch.object(structure_index,'VERSION',structure_index.VERSION+1),patch.object(structure_index,'build',wraps=structure_index.build) as updated:
                project.selected_structure('demo','','dev',pin,directory='pkg')
                updated.assert_called_once()
            build=structure_index.build
            def advance_during_read(*args,**kwargs):
                result=build(*args,**kwargs)
                git('-c','user.name=Test','-c','user.email=test@example.invalid','commit','--allow-empty','-qm','advance')
                return result
            with patch('mapcore.ROOT',folder.parent),patch.object(structure_index,'build',side_effect=advance_during_read):
                with self.assertRaisesRegex(ValueError,'Code changed'):
                    project.selected_structure('demo','','dev',pin,directory='pkg/nested')
            stale=subprocess.run(cmd+['0'*40,'pkg'],env=env,capture_output=True)
            self.assertNotEqual(stale.returncode,0)
            self.assertEqual((folder/'dev.json').read_text(),saved)

    def test_next_routes_require_project_ownership_static_config_and_named_exports(self):
        with tempfile.TemporaryDirectory() as root:
            repo=Path(root)
            git=lambda *a:subprocess.check_output(['git','-C',root,*a]).decode().strip()
            git('init','-q')
            code="export async function GET() {}\nexport const POST = () => {};\nexport default function DELETE() {}"
            sources={'package.json':'{"dependencies":{"next":"^15.0"}}','next.config.ts':'export default {images:{}}',
                     'app/api/notes/route.ts':code,'src/app/api/shadow/route.ts':code,
                     'tests/fixtures/app/api/nested/route.ts':code,'app/fixtures/unused/route.ts':code,
                     'app/api/[id]/route.ts':code,'app/(group)/route.ts':code,'app/api/conflict/route.ts':code,
                     'app/api/conflict/page.tsx':'export default function View() { return null }'}
            for file,text in sources.items():
                path=repo/file
                path.parent.mkdir(parents=True,exist_ok=True)
                path.write_text(text)
            def commit():
                git('add','.')
                git('-c','user.name=Test','-c','user.email=test@example.invalid','commit','-qm','route files')
                return git('rev-parse','HEAD')
            pin=commit()
            def routes(pin,**opts):
                return structure_index.build(root,pin,**opts)['service_flow']['registered_routes']
            self.assertEqual([(r['method'],r['path'],r['server']['line']) for r in routes(pin)],
                             [('GET','/api/notes',1),('POST','/api/notes',2)])
            self.assertEqual(routes(pin,excluded=lambda f:f=='package.json'),[])
            (repo/'next.config.ts').write_text("export default {basePath:'/base'}")
            self.assertEqual(routes(commit()),[])
            (repo/'next.config.ts').unlink()
            (repo/'package.json').write_text('{}')
            self.assertEqual(routes(commit()),[])

    def test_directory_pages_partition_files_at_both_limits(self):
        entries=[(f'area/{i}.py',(b'oid',size)) for i,size in enumerate([6,5,3,0,12,2])]
        pages=[structure_index._directory_page(entries,page,2,10) for page in (1,2,3)]
        self.assertEqual([[p for p,_ in rows] for rows,_ in pages],
                         [['area/0.py'],['area/1.py','area/2.py'],['area/3.py','area/5.py']])
        self.assertEqual([meta['selected_bytes'] for _,meta in pages],[6,8,2])
        self.assertTrue(all(meta['oversized_files']==1 and meta['total_eligible_files']==5 for _,meta in pages))
        for invalid in (0,-1,4,True):
            with self.assertRaises(ValueError):structure_index._directory_page(entries,invalid,2,10)

    def test_coverage_limits_directory_rows_but_preserves_the_total(self):
        candidates=[f'area{i}/source.py' for i in range(31)]+['backend/first.py','backend/second.py']
        coverage=structure_index._directory_coverage(candidates,{'area0/source.py'})
        self.assertEqual(coverage['directory_count'],32)
        self.assertEqual(len(coverage['directories']),24)
        self.assertEqual(coverage['directories'][0],{'directory':'backend','candidate_files':2,'indexed_files':0,'skipped_files':2})
        self.assertFalse(any(row['directory']=='area0' for row in coverage['directories']))

    def test_pnpm_workspace_proves_membership_from_exact_manifest_and_glob_lines(self):
        with tempfile.TemporaryDirectory() as root:
            repo=Path(root)
            git=lambda *a:subprocess.check_output(['git','-C',root,*a]).decode().strip()
            git('init','-q')
            config="packages:\n  - 'packages/*'\n  - '!packages/omit'\n"
            sources={'pnpm-workspace.yaml':config,'packages/core/package.json':'{\n"name":"@app/core",\n"description":"Core library."}',
                     'packages/omit/package.json':'{"name":"omit"}','tests/packages/other/package.json':'{"name":"other"}',
                     'packages/alias/package.json':'{"name":"hidden"}','.aws/private.json':'{"name":"hidden"}'}
            for file,text in sources.items():
                path=repo/file
                path.parent.mkdir(parents=True,exist_ok=True)
                path.write_text(text)
            git('add','.')
            git('-c','user.name=Test','-c','user.email=test@example.invalid','commit','-qm','workspace')
            pin=git('rev-parse','HEAD')
            (repo/'pnpm-workspace.yaml').write_text('packages: []')
            data=structure_index.build(root,pin)
            self.assertEqual(data['coverage']['workspace_manifests_matched'],1)
            self.assertEqual(data['workspace_packages'],[dict(name='@app/core',directory='packages/core',
                file='packages/core/package.json',line=2,description='Core library.',description_line=3,
                workspace={'file':'pnpm-workspace.yaml','line':2})])
            self.assertEqual(structure_index._pnpm_patterns(b'packages:\n  - packages/*\n  - "!**/secret"'),[])
            self.assertEqual(structure_index._pnpm_patterns(b'packages:\n  - apps/*\npackages: []'),[])

    def test_workspace_dependencies_require_unique_members_and_explicit_same_name_protocol(self):
        with tempfile.TemporaryDirectory() as root:
            repo=Path(root)
            git=lambda *a:subprocess.check_output(['git','-C',root,*a]).decode().strip()
            git('init','-q')
            (repo/'pnpm-workspace.yaml').write_text('packages:\n  - packages/*')
            for name in ('one','two','three'):
                folder=repo/'packages'/name
                folder.mkdir(parents=True)
                (folder/'package.json').write_text('{"name":"'+name+'"}')
            (repo/'packages/one/package.json').write_text("""{
"name":"one",
"devDependencies":{"two":"workspace:^"},
"dependencies":{"three":"~1.0","unknown":"workspace:*","alias":"workspace:two@*"}
}""")
            def commit():
                git('add','.')
                git('-c','user.name=Test','-c','user.email=test@example.invalid','commit','-qm','links')
                return git('rev-parse','HEAD')
            first=structure_index.build(root,commit())['workspace_dependencies']
            self.assertEqual(first,[dict(source='one',target='two',kind='devDependencies',specifier='workspace:^',
                                         file='packages/one/package.json',line=3)])
            (repo/'packages/three/package.json').write_text('{"name":"two"}')
            self.assertEqual(structure_index.build(root,commit())['workspace_dependencies'],[])

    def test_package_json_workspace_array_and_private_yarn_packages_object(self):
        with tempfile.TemporaryDirectory() as root:
            repo=Path(root)
            git=lambda *a:subprocess.check_output(['git','-C',root,*a]).decode().strip()
            git('init','-q')
            (repo/'libs/tool').mkdir(parents=True)
            (repo/'libs/tool/package.json').write_text('{"name":"tool"}')
            def scan(config):
                (repo/'package.json').write_text(config)
                git('add','.')
                git('-c','user.name=Test','-c','user.email=test@example.invalid','commit','-qm','membership')
                return structure_index.build(root,git('rev-parse','HEAD'))['workspace_packages']
            for config in ['{"workspaces":[\n"libs/*"]}', '{"private":true,"workspaces":{"packages":[\n"libs/*"],"nohoist":["**/x"]}}']:
                self.assertEqual(scan(config),[dict(name='tool',directory='libs/tool',file='libs/tool/package.json',
                                                   line=1,workspace={'file':'package.json','line':2})])
            self.assertEqual(scan('{"workspaces":["libs/*"],"workspaces":[]}'),[])
            self.assertEqual(scan('{"workspaces":["libs/*","**/fixtures"]}'),[])
            (repo/'pnpm-workspace.yaml').write_text('packages: []')
            self.assertEqual(scan('{"workspaces":["libs/*"]}'),[])

    def test_bounded_selection_visits_sibling_code_and_keeps_auxiliary_evidence(self):
        paths=['aaa/examples/case'+str(i)+'.py' for i in range(30)]
        paths+=['services/a/worker'+str(i)+'.py' for i in range(30)]
        paths+=['services/z/entry.py','web/ui/index.py']
        entries=[(path,(b'blob',10)) for path in paths]
        sample=[p for p,_ in structure_index._bounded_order(entries)]
        self.assertEqual(sample,[p for p,_ in structure_index._bounded_order(entries[::-1])])
        self.assertEqual(set(sample),set(paths))
        self.assertEqual(len(sample),len(paths))
        self.assertIn('services/z/entry.py',sample[:7])
        self.assertIn('web/ui/index.py',sample[:7])
        self.assertTrue(any('/examples/' in path for path in sample[:8]))

    def test_standalone_commonjs_cli_connects_explicit_local_modules(self):
        with tempfile.TemporaryDirectory() as root:
            repo=Path(root)
            git=lambda *args:subprocess.check_output(['git','-C',root,*args]).decode().strip()
            git('init','-q')
            (repo/'cli.cjs').write_text("#!/usr/bin/env node\nconst worker=require('./worker.cjs');\nworker.run();")
            (repo/'worker.cjs').write_text('function run(){};module.exports={run};')
            (repo/'shadow.cjs').write_text("function other({require}){return require('./worker.cjs')} ")
            (repo/'missing.cjs').write_text("require('./absent.cjs');require('third-party');")
            git('add','.');git('-c','user.name=Test','-c','user.email=test@example.invalid','commit','-qm','Add CLI')
            index=structure_index.build(root,git('rev-parse','HEAD'))
            self.assertEqual(index['service_flow']['connections'],[])
            self.assertEqual(index['imports'],[{'file':'cli.cjs','line':2,'target':'worker.cjs'}])
            self.assertEqual(index['coverage']['unresolved_imports'],2)
            worker=next(row for row in index['files'] if row['file']=='worker.cjs')
            self.assertEqual(worker['declarations'],[{'name':'run','kind':'function','line':1}])

    def test_typescript_tsx_and_javascript_static_structure(self):
        with tempfile.TemporaryDirectory() as root:
            repo=Path(root)
            git=lambda *args:subprocess.check_output(['git','-C',root,*args]).decode().strip()
            git('init','-q')
            sources={
                'src/main.tsx':"""import {run} from './task';
export {shared} from './shared.js';
import {ambiguous} from './choice';
import external from 'external';
// import unused from './fake';
const text = "export function fake() {}";
export function View() { return <div/> }
export const persist = async () => run();
""",
                'src/task.ts':"export interface Item { name: string }\nexport async function run() {}\n",
                'src/choice.ts':'export type X = string;',
                'src/choice.js':'export function noop() {}',
                'src/shared.js':'export class Shared { save() {} }',
                'src/bad.ts':'const = ;',
            }
            for name,txt in sources.items():
                path=repo/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(txt)
            git('add','.');git('-c','user.name=Test','-c','user.email=test@example.invalid','commit','-qm','Pinned modules')
            pin=git('rev-parse','HEAD')
            index=structure_index.build(root,pin)
            if index['coverage']['unavailable_languages']:
                self.skipTest('Install the packaged JavaScript and TypeScript grammars to check parsing')
            files={f['file']:f for f in index['files']}
            self.assertEqual(files['src/main.tsx']['language'],'typescript')
            self.assertEqual([(x['kind'],x['name'],x['line']) for x in files['src/main.tsx']['declarations']],
                             [('function','View',7),('async_function','persist',8)])
            self.assertEqual(files['src/shared.js']['declarations'][-1]['name'],'Shared.save')
            self.assertEqual(files['src/task.ts']['declarations'][0]['kind'],'interface')
            self.assertEqual(index['imports'],[{'file':'src/main.tsx','line':1,'target':'src/task.ts'},
                                               {'file':'src/main.tsx','line':2,'target':'src/shared.js'}])
            self.assertEqual(index['coverage']['unresolved_imports'],2)
            # A file the grammar cannot fully read is kept from its recovered tree and named as partly read.
            self.assertEqual(index['coverage']['languages']['typescript'],{'candidate_files':4,'indexed_files':4})
            self.assertEqual(index['coverage']['partial_files'],['src/bad.ts'])
