"""Exercise the real route's early guards without importing external API clients."""
import ast
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
import sys
sys.path.insert(0,str(Path(__file__).parents[1]))
from task_workflow import staff_checklist_update

class HTTPError(Exception):
    def __init__(self,status_code,detail):
        self.status_code=status_code
        super().__init__(detail)

class StaffUpdateGuards(unittest.TestCase):
    def setUp(self):
        source=ast.parse((Path(__file__).parents[1]/'staff.py').read_text())
        route=next(node for node in source.body if isinstance(node,ast.FunctionDef) and node.name=='staff_update_task')
        route.decorator_list=[]
        module=ast.Module(body=[ast.ImportFrom(module='__future__',names=[ast.alias(name='annotations')],level=0),route],type_ignores=[])
        self.client=MagicMock()
        self.current={'assigned_staff_id':'staff-1','status':'In Progress','updated_at':'revision-2','progress':0,'checklist':[{'id':'one','label':'Inspect room','done':False}]}
        env={'Depends':lambda _:None,'require_staff':None,'HTTPException':HTTPError,'fetch_task':lambda _:self.current,'service_client':lambda:self.client,'staff_checklist_update':staff_checklist_update}
        exec(compile(ast.fix_missing_locations(module),'staff.py','exec'),env)
        self.route=env['staff_update_task']
    def request(self,**patch):
        data=SimpleNamespace(expected_updated_at=None,checklist=None,progress=None,notes=None,status=None,**{})
        for key,value in patch.items():setattr(data,key,value)
        return self.route('task-1',data,{'account':{'id':'staff-1'}})
    def test_stale_client_cannot_overwrite_newer_assignment(self):
        with self.assertRaises(HTTPError) as caught:self.request(expected_updated_at='revision-1')
        self.assertEqual(caught.exception.status_code,409)
        self.client.table.assert_not_called()
    def test_reviewed_and_completed_assignments_are_locked(self):
        for status in ['Pending Review','Completed','Cancelled']:
            self.current['status']=status
            with self.subTest(status=status),self.assertRaises(HTTPError) as caught:self.request(notes='Changed')
            self.assertEqual(caught.exception.status_code,409)
        self.client.table.assert_not_called()
    def test_staff_cannot_assign_arbitrary_progress(self):
        with self.assertRaises(HTTPError) as caught:self.request(progress=100)
        self.assertEqual(caught.exception.status_code,422)
        self.client.table.assert_not_called()
    def test_staff_cannot_remove_an_incomplete_step(self):
        with self.assertRaises(HTTPError) as caught:self.request(checklist=[])
        self.assertEqual(caught.exception.status_code,409)
        self.client.table.assert_not_called()
