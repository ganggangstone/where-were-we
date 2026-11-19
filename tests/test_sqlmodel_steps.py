import ast
import unittest

import sqlmodel_steps
import structure_index


class SQLModelSteps(unittest.TestCase):
    def test_read_write_require_matching_session_table_and_commit(self):
        models="from sqlmodel import SQLModel\nclass Record(SQLModel,table=True): pass"
        deps="""from fastapi import Depends
from sqlmodel import Session
from typing import Annotated
def db():
    with Session(engine) as session:
        yield session
SessionDep = Annotated[Session, Depends(db)]
"""
        source="""from app.models import Record
from app.deps import SessionDep
from sqlmodel import select
@router.get('/')
def list_records(db:SessionDep):
    statement=select(Record).limit(5)
    rows=db.exec(statement).all()
@router.post('/')
def store_record(db:SessionDep,payload):
    record=Record.model_validate(payload)
    db.add(record)
    db.commit()
"""
        def analyze(models=models,deps=deps,source=source):
            modules={k:sqlmodel_steps.facts(ast.parse(v)) for k,v in [('src/app/models.py',models),('src/app/deps.py',deps),('src/app/routes.py',source)]}
            routes=[{'server':{'file':'src/app/routes.py','line':n,'function':f}} for n,f in [(4,'list_records'),(8,'store_record')]]
            sqlmodel_steps.attach(modules,routes)
            return [s for r in routes for s in r.get('data_steps',[])]
        steps=analyze()
        self.assertEqual([(s['operation'],s['model'],s['line']) for s in steps],[('read','Record',7),('write','Record',12)])
        self.assertIn({'file':'src/app/deps.py','line':5},steps[0]['evidence'])
        self.assertFalse(analyze(models=models.replace('table=True','table=False')))
        self.assertFalse(analyze(deps=deps.replace('yield session','yield other')))
        self.assertEqual(len(analyze(source=source.replace('db.commit()','db.rollback()'))),1)
        self.assertFalse(analyze(source=source.replace('db:SessionDep','db:Fake')))
        self.assertEqual(len(analyze(source=source.replace('select(Record)','untrusted(Record)'))),1)

    def test_python_314_exception_list_keeps_line_numbers(self):
        code=b'try:\n    pass\nexcept ValueError, RuntimeError:\n    pass\n'
        self.assertEqual(structure_index._python_tree(code).body[0].handlers[0].lineno,3)
        with self.assertRaises(SyntaxError):
            structure_index._python_tree(b'try:\n    pass\nexcept ValueError, RuntimeError as e:\n    pass\n')
