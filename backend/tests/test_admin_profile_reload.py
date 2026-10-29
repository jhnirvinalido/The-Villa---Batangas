"""Refresh uses persisted profile data rather than the minimal auth record."""
import ast
import unittest
from pathlib import Path
from unittest.mock import MagicMock


class ProfileReloadTests(unittest.TestCase):
    def setUp(self):
        tree = ast.parse((Path(__file__).parents[1] / 'admin.py').read_text())
        nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in {'bootstrap','staff_api','get_current_admin_profile','load_bootstrap_bookings'}]
        for node in nodes:
            node.decorator_list = []
            node.args.defaults = []
        self.saved = {'id':'admin-id','full_name':'Updated Name','avatar_url':'saved-photo','nickname':'Villa Host'}
        self.fetch = MagicMock(return_value=self.saved)
        class HttpProblem(Exception):
            def __init__(self, detail):
                self.detail = detail
        self.env = {'HTTPException':HttpProblem,'logger':MagicMock(),'service_client':MagicMock(),
            'safe_table_rows':lambda _client, table, *_args, **_kw: [self.saved] if table == 'staff_accounts' else [],
            'rows':lambda _:[], 'load_bookings_with_payments':lambda _:[],
            'load_payment_timing_events':lambda _:[], 'apply_payment_timing_preferences':lambda bookings, _:bookings,
            'fetch_staff':self.fetch}
        for key in ('STAFF_SELECT','TASK_SELECT','NOTIFICATION_SELECT','FRONT_DESK_PAYMENT_SELECT','WORKFLOW_EVENT_SELECT'):
            self.env[key] = '*'
        module = ast.Module(body=[ast.ImportFrom(module='__future__',names=[ast.alias(name='annotations')],level=0)] + nodes,type_ignores=[])
        exec(compile(ast.fix_missing_locations(module),'admin.py','exec'),self.env)
        self.context = {'account':{'id':'admin-id','full_name':'Old Name'},'session':{}}

    def test_refresh_keeps_saved_photo_and_name(self):
        profile = self.env['bootstrap'](self.context)['data']['profile']
        self.assertEqual(profile['avatarUrl'],'saved-photo')
        self.assertEqual(profile['fullName'],'Updated Name')
        self.assertEqual(profile['nickname'],'Villa Host')
        self.fetch.assert_not_called()

    def test_missing_staff_list_fetches_current_profile(self):
        self.env['safe_table_rows'] = lambda *_args, **_kw: []
        self.assertEqual(self.env['bootstrap'](self.context)['data']['profile']['avatarUrl'],'saved-photo')
        self.fetch.assert_called_once_with('admin-id')

    def test_removed_photo_stays_removed(self):
        self.saved['avatar_url'] = None
        self.assertIsNone(self.env['bootstrap'](self.context)['data']['profile']['avatarUrl'])

    def test_profile_endpoint_reads_saved_identity_without_dashboard_data(self):
        self.env['safe_table_rows'] = MagicMock(side_effect=RuntimeError('Dashboard unavailable'))
        result = self.env['get_current_admin_profile'](self.context)['data']
        self.assertEqual(result['nickname'],'Villa Host')
        self.assertEqual(result['avatarUrl'],'saved-photo')
        self.env['safe_table_rows'].assert_not_called()
        self.fetch.assert_called_once_with('admin-id')

    def test_booking_failure_is_scoped_to_booking_page_data(self):
        self.env['load_bookings_with_payments'] = MagicMock(
            side_effect=self.env['HTTPException']('Bookings unavailable')
        )
        result = self.env['load_bootstrap_bookings'](self.env['service_client']())
        self.assertEqual(result, {'data': [], 'error': 'Bookings unavailable'})

    def test_booking_bootstrap_keeps_successful_rows(self):
        self.env['load_bookings_with_payments'] = MagicMock(return_value=[{'id':'booking-1'}])
        result = self.env['load_bootstrap_bookings'](self.env['service_client']())
        self.assertEqual(result, {'data': [{'id':'booking-1'}], 'error': ''})

    def test_failed_optional_reads_are_distinguished_from_successful_empty_reads(self):
        self.env['safe_table_rows'] = lambda _client, table, *_args, **_kw: None if table in {'staff_accounts','admin_tasks','front_desk_payments'} else []
        data = self.env['bootstrap'](self.context)['data']
        self.assertIsNone(data['staff'])
        self.assertIsNone(data['profile'])
        self.assertIsNone(data['tasks'])
        self.assertIsNone(data['paymentTransactions'])
        self.assertEqual(data['notifications'], [])
        self.assertEqual(set(data['snapshotErrors']), {'staff','tasks','payments'})
        self.fetch.assert_not_called()
