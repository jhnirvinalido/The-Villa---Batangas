"""Exercise the real route's early guards without importing external API clients."""
import ast
import unittest
from pathlib import Path
from types import SimpleNamespace
import secrets
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
        self.current={'assigned_staff_id':'staff-1','status':'In Progress','updated_at':'revision-2','progress':0,'title':'Inspect room','checklist':[{'id':'one','label':'Inspect room','done':False}]}
        self.query=MagicMock()
        self.query.update.return_value=self.query
        self.query.eq.return_value=self.query
        self.query.select.return_value=self.query
        self.client.table.return_value=self.query
        self.query.execute.return_value=SimpleNamespace(data=[])
        env={
            'Depends':lambda _:None,'require_staff':None,'HTTPException':HTTPError,
            'fetch_task':lambda _:self.current,'service_client':lambda:self.client,
            'staff_checklist_update':staff_checklist_update,'rows':lambda response:response.data,
            'secrets':secrets,'now_iso':lambda:'2026-10-22T10:00:00+08:00',
            'TASK_SELECT':'id,status,progress,checklist',
            'notify_admins':MagicMock(),'record_booking_event':MagicMock(),
            'task_api':lambda row,account:{**row},
        }
        exec(compile(ast.fix_missing_locations(module),'staff.py','exec'),env)
        self.route=env['staff_update_task']
        self.env=env
    def request(self,**patch):
        data=SimpleNamespace(expected_updated_at=None,checklist=None,progress=None,notes=None,status=None,**{})
        for key,value in patch.items():setattr(data,key,value)
        return self.route('task-1',data,{'account':{'id':'staff-1','full_name':'Staff Member'}})
    def test_stale_client_cannot_overwrite_newer_assignment(self):
        with self.assertRaises(HTTPError) as caught:self.request(expected_updated_at='revision-1')
        self.assertEqual(caught.exception.status_code,409)
        self.client.table.assert_not_called()
    def test_reviewed_and_completed_assignments_are_locked(self):
        self.current['source']='manual-maintenance-request'
        for status in ['Pending Review','Completed','Cancelled']:
            self.current['status']=status
            with self.subTest(status=status),self.assertRaises(HTTPError) as caught:self.request(notes='Changed')
            self.assertEqual(caught.exception.status_code,409)
        self.client.table.assert_not_called()
        self.current.pop('source')
    def test_staff_cannot_assign_arbitrary_progress(self):
        with self.assertRaises(HTTPError) as caught:self.request(progress=100)
        self.assertEqual(caught.exception.status_code,422)
        self.client.table.assert_not_called()
    def test_staff_cannot_remove_an_incomplete_step(self):
        with self.assertRaises(HTTPError) as caught:self.request(checklist=[])
        self.assertEqual(caught.exception.status_code,409)
        self.client.table.assert_not_called()

    def test_staff_cannot_complete_until_every_checklist_step_is_done(self):
        with self.assertRaises(HTTPError) as caught:self.request(status='Completed')
        self.assertEqual(caught.exception.status_code,409)
        self.assertIn('Complete every checklist item',str(caught.exception))
        self.client.table.assert_not_called()

    def test_staff_completes_regular_assignment_without_admin_approval(self):
        self.current['checklist'][0]['done']=True
        self.query.execute.return_value=SimpleNamespace(data=[{
            **self.current,'status':'Completed','progress':100,
        }])
        result=self.request(status='Completed')
        saved=self.query.update.call_args.args[0]
        self.assertEqual(result['data']['status'],'Completed')
        self.assertEqual(saved['status'],'Completed')
        self.assertEqual(saved['progress'],100)
        self.assertEqual(saved['submitted_at'],None)
        self.assertEqual(self.env['notify_admins'].call_args.args[0],'Assignment Completed')

    def test_maintenance_work_still_requires_admin_verification(self):
        self.current['source']='manual-maintenance-request'
        self.current['checklist'][0]['done']=True
        with self.assertRaises(HTTPError) as caught:self.request(status='Completed')
        self.assertEqual(caught.exception.status_code,409)
        self.client.table.assert_not_called()
