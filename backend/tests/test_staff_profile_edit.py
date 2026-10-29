import ast
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

class ProfileEditTests(unittest.TestCase):
    def setUp(self):
        tree=ast.parse((Path(__file__).parents[1]/'staff.py').read_text())
        node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='update_my_staff_profile')
        node.decorator_list=[]
        node.args.defaults=[]
        class HTTPError(Exception):
            def __init__(self,**kw): self.status_code=kw['status_code']
        self.error=HTTPError
        self.client=MagicMock()
        self.env={'service_client':lambda:self.client,'rows':lambda _: [{'id':'self'}], 'staff_api':lambda row:row,'STAFF_SELECT':'*','now_iso':lambda:'now','HTTPException':HTTPError}
        module=ast.Module(body=[ast.ImportFrom(module='__future__',names=[ast.alias(name='annotations')],level=0),node],type_ignores=[])
        exec(compile(ast.fix_missing_locations(module),'staff.py','exec'),self.env)
        self.data=SimpleNamespace(full_name=' Staff Name ',personal_email=' personal@example.com ',nickname=' Host ',avatar_url='',role='admin',id='another-account')
    def test_only_own_profile_and_allowed_fields_are_updated(self):
        self.env['update_my_staff_profile'](self.data,{'account':{'id':'self'}})
        self.client.table.return_value.update.return_value.eq.assert_called_once_with('id','self')
        updates=self.client.table.return_value.update.call_args.args[0]
        self.assertEqual(updates['nickname'],'Host')
        self.assertEqual(updates['full_name'],'Staff Name')
        self.assertNotIn('role',updates)
        self.assertNotIn('email',updates)
        self.assertNotIn('phone',updates)
        self.assertEqual(updates['personal_email'],'personal@example.com')
        self.assertIsNone(updates['avatar_url'])
    def test_invalid_picture_never_writes(self):
        self.data.avatar_url='invalid image'
        with self.assertRaises(self.error):self.env['update_my_staff_profile'](self.data,{'account':{'id':'self'}})
        self.client.table.assert_not_called()
    def test_blank_name_never_writes(self):
        self.data.full_name='   '
        with self.assertRaises(self.error):self.env['update_my_staff_profile'](self.data,{'account':{'id':'self'}})
        self.client.table.assert_not_called()
    def test_staff_can_save_personal_email_without_changing_login_email(self):
        self.data.personal_email='personal@example.com'
        self.env['update_my_staff_profile'](self.data,{'account':{'id':'self'}})
        updates=self.client.table.return_value.update.call_args.args[0]
        self.assertEqual(updates['personal_email'],'personal@example.com')
        self.assertNotIn('email',updates)
