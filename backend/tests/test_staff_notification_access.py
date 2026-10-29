"""Notification read endpoints must never modify another staff member's inbox."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock


class HTTPError(Exception):
    def __init__(self, status_code, detail): self.status_code = status_code


class StaffNotificationAccessTests(unittest.TestCase):
    def setUp(self):
        tree=ast.parse((Path(__file__).parents[1]/'staff.py').read_text())
        nodes=[node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name in {'staff_read_notification','staff_read_all_notifications','staff_list_notifications'}]
        for node in nodes:node.decorator_list=[]
        self.client=MagicMock()
        self.env={'Depends':lambda value:None,'require_staff':object(),'service_client':lambda:self.client,'rows':lambda result:result.data,
                  'notification_api':lambda row:row,'NOTIFICATION_SELECT':'*','now_iso':lambda:'now','HTTPException':HTTPError}
        module=ast.Module(body=[ast.ImportFrom(module='__future__',names=[ast.alias(name='annotations')],level=0)]+nodes,type_ignores=[])
        exec(compile(ast.fix_missing_locations(module),'staff.py','exec'),self.env)
        self.context={'account':{'id':'staff-self'}}

    def test_read_one_filters_by_recipient_and_missing_record_returns_404(self):
        query=self.client.table.return_value.update.return_value
        query.eq.return_value.eq.return_value.select.return_value.execute.return_value=SimpleNamespace(data=[])
        with self.assertRaises(HTTPError) as caught:
            self.env['staff_read_notification']('another-staffs-notice',self.context)
        self.assertEqual(caught.exception.status_code,404)
        query.eq.assert_called_once_with('id','another-staffs-notice')
        query.eq.return_value.eq.assert_called_once_with('recipient_staff_account_id','staff-self')

    def test_mark_all_read_is_scoped_to_own_unread_records(self):
        self.env['staff_read_all_notifications'](self.context)
        query=self.client.table.return_value.update.return_value
        query.eq.assert_called_once_with('recipient_staff_account_id','staff-self')
        query.eq.return_value.eq.assert_called_once_with('is_read',False)

    def test_background_feed_filters_every_row_by_current_staff_recipient(self):
        query=self.client.table.return_value.select.return_value
        query.eq.return_value.order.return_value.limit.return_value.execute.return_value=SimpleNamespace(data=[{'id':'notice'}])
        result=self.env['staff_list_notifications'](self.context)
        query.eq.assert_called_once_with('recipient_staff_account_id','staff-self')
        self.assertEqual(result['data'],[{'id':'notice'}])


if __name__=='__main__':unittest.main()
