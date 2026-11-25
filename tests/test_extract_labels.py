"""Screen action labels keep a readable sentence when an expression sits inside the text."""
import ast
import html
from pathlib import Path
import re
import unittest

def jsx_text():
    # extract.py runs as a script with arguments; only the label function and its pattern are loaded.
    ns={'re':re,'html':html}
    for node in ast.parse((Path(__file__).resolve().parents[1]/'extract.py').read_text()).body:
        if isinstance(node,ast.Assign) and getattr(node.targets[0],'id','')=='JSX_TEXT_RE' or isinstance(node,ast.FunctionDef) and node.name=='jsx_text':
            exec(compile(ast.Module([node],[]),'extract.py','exec'),ns)
    return ns['jsx_text']

class Labels(unittest.TestCase):
    def test_expression_inside_text_reads_as_a_gap_and_edge_expressions_are_dropped(self):
        f=jsx_text()
        self.assertEqual(f('Box · {count} items saved'),'Box · … items saved')
        self.assertEqual(f('{icon} Save'),'Save');self.assertEqual(f('Save {icon}'),'Save')
        self.assertEqual(f('<span>{x}</span> Delete'),'Delete');self.assertEqual(f('{value}'),'')
        self.assertEqual(f('{a} {b} Open'),'Open')

    def test_saved_names_follow_the_screen_rule_for_code_like_text(self):
        import json,shutil,subprocess,sys
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
        import analysis_label,mapcore
        cases={':':False,"on ? 'Stop' : 'Start'":False,'() => go()':False,'a && b':False,'x || y':False,"label: 'x'":False,'':False,'·':False,
               '저장':True,'Save draft':True,'Box · … items saved':True,'3':True,"Don't save":True,'Why?':True}
        self.assertEqual({t:mapcore.ui_text(t) for t in cases},cases)
        node=shutil.which('node')
        if node:  # the screen rule itself, read from ui/index.html
            line=next(l for l in (Path(__file__).resolve().parents[1]/'ui/index.html').read_text().splitlines() if l.startswith('const uiText ='))
            got=subprocess.run([node,'-e',line+'\nconsole.log(JSON.stringify(Object.fromEntries('+json.dumps(list(cases))+'.map(t=>[t,uiText(t)]))))'],capture_output=True,text=True,check=True).stdout
            self.assertEqual(json.loads(got),cases)
        labels,dropped=analysis_label.check({'units':[{'ref':0,'name':"on ? 'A' : 'B'"},{'ref':1,'name':'Orders'}],
                                             'groups':[{'name':'() => go()','units':[0]}],'requests':[{'ref':0,'name':'a && b'}]},{0:'u0',1:'u1'},{'evidence':{},'requests':{0:'q'}})
        self.assertEqual((labels['units'],labels['groups'],labels['requests'],dropped),({'u1':{'name':'Orders','what':''}},[],{},3))

if __name__=='__main__':unittest.main()
