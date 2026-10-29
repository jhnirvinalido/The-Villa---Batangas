"""Public checkout regressions with isolated storage and PayMongo doubles."""
import ast
import hashlib
import hmac
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from test_manual_checkout import HTTPError, load_functions


class PublicCheckoutTests(unittest.TestCase):
    def setUp(self):
        self.env = load_functions()
        tree = ast.parse((Path(__file__).parents[1] / 'booking.py').read_text())
        names = {'create_public_booking', '_sync_public_checkout_draft',
                 'cancel_public_booking', '_require_booking_token'}
        nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
        for node in nodes:
            node.decorator_list = []
        self.env.update(Header=lambda **_: None, hmac=hmac,
                        _token_hash=lambda token: hashlib.sha256(token.encode()).hexdigest(),
                        _safe_public_booking=lambda row: {k:v for k,v in row.items() if not k.endswith('_hash')})
        exec(compile(ast.fix_missing_locations(ast.Module(body=[ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')], level=0)] + nodes, type_ignores=[])), 'booking.py', 'exec'), self.env)
        self.client = MagicMock()
        self.client.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = SimpleNamespace(data=[])
        self.booking = {'id':'draft-id', 'booking_code':'V-1', 'user_id':None,
                        'amount_paid':0, 'total_amount':1000, 'payment_due_amount':500,
                        'booking_status':'Pending Payment', 'payment_method_code':'qrph',
                        'paymongo_checkout_session_id':'cs_1', 'hold_expires_at':'2099-01-01T00:00:00+00:00'}
        self.draft = {'booking_payload':self.booking}
        self.session = {'id':'cs_1','attributes':{}}
        self.payment = {'id':'pay_1','attributes':{'amount':50000,'currency':'PHP','status':'paid'}}
        self.env.update(_service=lambda:self.client,
                        _public_checkout_draft=lambda *_:self.draft,
                        _paymongo_request=MagicMock(return_value={'data':self.session}),
                        _send_booking_confirmation_email=MagicMock())

    def test_creation_stores_only_checkout_draft_and_no_email(self):
        self.env['_prepare_public_booking'] = MagicMock(return_value={'booking':self.booking,'booking_access_token':'secret'})
        result = self.env['create_public_booking'](object())
        self.assertEqual(result['booking_access_token'],'secret')
        self.assertEqual([c.args[0] for c in self.client.table.call_args_list],['public_booking_checkouts'])
        self.env['_prepare_public_booking'].assert_called_once()
        self.assertTrue(self.env['_prepare_public_booking'].call_args.kwargs['draft_only'])
        self.env['_send_booking_confirmation_email'].assert_not_called()

    def test_pending_failed_expired_do_not_create_booking(self):
        for state in ('pending','failed','expired'):
            self.env['_session_payment_state'] = lambda _, state=state: {'paid':False,'state':state,'message':state}
            result = self.env['_sync_public_checkout_draft'](self.client,self.draft)
            self.assertEqual(result['state'],state)
        self.client.rpc.assert_not_called()
        self.client.table.assert_not_called()
        self.env['_send_booking_confirmation_email'].assert_not_called()
        self.env['_assign_prearrival_staff'].assert_not_called()

    def test_verified_payment_promotes_atomically_and_sends_confirmation(self):
        self.env['_session_payment_state'] = lambda _: {'paid':True,'payment':self.payment}
        self.client.rpc.return_value.execute.return_value = SimpleNamespace(data={**self.booking,'amount_paid':500,'_checkout_finalized':True})
        result = self.env['_sync_public_checkout_draft'](self.client,self.draft)
        self.assertEqual(result['state'],'paid')
        name, params = self.client.rpc.call_args.args
        self.assertEqual(name,'finalize_public_booking_checkout')
        self.assertEqual(params['p_payment']['amount'],500)
        self.env['_send_booking_confirmation_email'].assert_called_once()
        self.assertNotIn('_checkout_finalized',result['booking'])
        self.env['_assign_prearrival_staff'].assert_called_once()
        assigned_booking, assigned_client = self.env['_assign_prearrival_staff'].call_args.args
        self.assertEqual(assigned_booking['amount_paid'], 500)
        self.assertIs(assigned_client, self.client)

    def test_wrong_currency_amount_session_never_promotes(self):
        self.env['_session_payment_state'] = lambda _: {'paid':True,'payment':self.payment}
        for field, bad in [('amount',1),('currency','USD')]:
            original = self.payment['attributes'][field]
            self.payment['attributes'][field] = bad
            with self.assertRaises(HTTPError):
                self.env['_sync_public_checkout_draft'](self.client,self.draft)
            self.payment['attributes'][field] = original
        self.session['id'] = 'wrong-session'
        with self.assertRaises(HTTPError):
            self.env['_sync_public_checkout_draft'](self.client,self.draft)
        self.client.rpc.assert_not_called()

    def test_cancelled_unpaid_checkout_never_writes_bookings(self):
        self.env['_require_booking_token'] = lambda *_:self.booking
        self.env['_session_payment_state'] = lambda _: {'paid':False,'state':'pending','message':'Pending'}
        result = self.env['cancel_public_booking']('draft-id','token')
        self.assertTrue(result['cancelled'])
        self.assertIsNone(result['booking'])
        self.assertEqual([c.args[0] for c in self.client.table.call_args_list],['public_booking_checkouts'])
        self.client.rpc.assert_not_called()

    def test_cancel_return_cannot_discard_verified_payment(self):
        self.env['_require_booking_token'] = lambda *_:self.booking
        self.env['_session_payment_state'] = lambda _: {'paid':True,'payment':self.payment}
        self.client.rpc.return_value.execute.return_value = SimpleNamespace(data={**self.booking,'amount_paid':500})
        with self.assertRaises(HTTPError):
            self.env['cancel_public_booking']('draft-id','token')
        self.client.table.return_value.update.assert_not_called()

    def test_draft_access_requires_matching_secure_token(self):
        token = 'a'*40
        self.booking['guest_access_token_hash'] = self.env['_token_hash'](token)
        lookup = self.client.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute
        lookup.return_value = SimpleNamespace(data=[])
        self.assertEqual(self.env['_require_booking_token']('draft-id',token),self.booking)
        with self.assertRaises(HTTPError):
            self.env['_require_booking_token']('draft-id','b'*40)


if __name__ == '__main__':
    unittest.main()
