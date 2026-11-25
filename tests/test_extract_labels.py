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

if __name__=='__main__':unittest.main()
