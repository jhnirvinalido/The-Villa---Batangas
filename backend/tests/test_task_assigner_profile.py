import ast
import unittest
from pathlib import Path

class TaskAssignerProfileTests(unittest.TestCase):
    def setUp(self):
        tree=ast.parse((Path(__file__).parents[1]/'admin.py').read_text())
        node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='task_api')
        module=ast.Module(body=[ast.ImportFrom(module='__future__',names=[ast.alias(name='annotations')],level=0),node],type_ignores=[])
        self.env={}
        exec(compile(ast.fix_missing_locations(module),'admin.py','exec'),self.env)
    def test_assigner_uses_current_saved_photo_name_and_nickname(self):
        creator={'full_name':'Villa Admin','nickname':'Host','avatar_url':'saved-photo','email':'private@example.com'}
        result=self.env['task_api']({'id':'task'},None,creator)
        self.assertEqual(result['assignedBy'],'Villa Admin')
        self.assertEqual(result['assignedByAvatarUrl'],'saved-photo')
        self.assertEqual(result['assignedByNickname'],'Host')
        self.assertNotIn('private@example.com',str(result))
    def test_missing_photo_allows_initials_fallback(self):
        result=self.env['task_api']({'id':'task'},None,{'full_name':'Villa Admin'})
        self.assertIsNone(result['assignedByAvatarUrl'])
        self.assertEqual(result['assignedBy'],'Villa Admin')

    def test_automatic_booking_preparation_is_attributed_to_system(self):
        result=self.env['task_api']({'id':'task','source':'automatic-booking-preparation'})
        self.assertEqual(result['assignedBy'],'System')
        self.assertIsNone(result['assignedByAvatarUrl'])
