"""Public checkout regressions with isolated storage and PayMongo doubles."""
import ast
import hashlib
import hmac
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
import uuid

from test_manual_checkout import HTTPError, load_functions


class PublicCheckoutTests(unittest.TestCase):
    def setUp(self):
        self.env = load_functions()
        tree = ast.parse((Path(__file__).parents[1] / 'booking.py').read_text())
        names = {'create_public_booking', '_sync_public_checkout_draft',
                 'cancel_public_booking', '_require_booking_token',
                 '_public_checkout_draft', 'process_public_checkout_reconciliation',
                 '_create_public_booking_checkout', '_payment_intent_state',
                 '_sync_public_payment_intent'}
        nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
        for node in nodes:
            node.decorator_list = []
        self.env.update(Header=lambda **_: None, hmac=hmac,
                        _token_hash=lambda token: hashlib.sha256(token.encode()).hexdigest(),
                        _safe_public_booking=lambda row: {k:v for k,v in row.items() if not k.endswith('_hash')},
                        timedelta=timedelta, logger=MagicMock())
        exec(compile(ast.fix_missing_locations(ast.Module(body=[ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')], level=0)] + nodes, type_ignores=[])), 'booking.py', 'exec'), self.env)
        self.client = MagicMock()
        self.client.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = SimpleNamespace(data=[])
        self.booking = {'id':'draft-id', 'booking_code':'V-1', 'user_id':None,
                        'amount_paid':0, 'total_amount':1000, 'payment_due_amount':500,
                        'booking_status':'Pending Payment', 'payment_method_code':'qrph',
                        'paymongo_checkout_session_id':'cs_1', 'hold_expires_at':'2099-01-01T00:00:00+00:00',
                        'villa_name':'Villa 1'}
        self.draft = {'booking_payload':self.booking}
        self.session = {'id':'cs_1','attributes':{}}
        self.payment = {'id':'pay_1','attributes':{'amount':50000,'currency':'PHP','status':'paid'}}
        self.env.update(_service=lambda:self.client,
                        _public_checkout_draft=lambda *_:self.draft,
                        _paymongo_request=MagicMock(return_value={'data':self.session}),
                        _send_booking_confirmation_email=MagicMock())
        self.env.update(
            PAYMONGO_PUBLIC_KEY='pk_test_public',
            PAYMONGO_PAYMENT_INTENTS_URL='https://api.paymongo.com/v1/payment_intents',
            PAYMONGO_CREATE_CHECKOUT_URL='https://api.paymongo.com/v2/checkout_sessions',
            PAYMONGO_METHOD_DETAILS={
                'gcash': {'label': 'GCash', 'flow_type': 'wallet_redirect'},
                'maya': {'label': 'Maya', 'flow_type': 'wallet_redirect'},
                'debit': {'label': 'Credit or Debit Card', 'flow_type': 'card'},
                'qrph': {'label': 'QR Ph', 'flow_type': 'qr'},
            },
            PAYMONGO_METHOD_MAP={
                'gcash': ['gcash'],
                'maya': ['paymaya'],
                'debit': ['card'],
                'qrph': ['qrph'],
            },
            Decimal=Decimal,
            datetime=datetime,
            timezone=timezone,
            uuid=uuid,
            _centavos=lambda value: int(Decimal(str(value)) * 100),
            _money=lambda value: Decimal(str(value or 0)).quantize(Decimal('.01')),
            _paymongo_mode=lambda: 'test',
            _public_checkout_urls=lambda _: ('https://villa.test/success', 'https://villa.test/cancel'),
        )

    def test_guest_gcash_checkout_uses_paymongo_hosted_checkout(self):
        self.env['PAYMONGO_PUBLIC_KEY'] = ''
        self.env['_paymongo_request'].return_value = {
            'data': {
                'id': 'cs_gcash_1',
                'attributes': {'checkout_url': 'https://paymongo.test/gcash'},
            }
        }
        result = self.env['_create_public_booking_checkout'](
            'draft-id',
            SimpleNamespace(payment_method='gcash', payment_scope='selected'),
            x_booking_token='guest-token',
            draft_booking=self.booking,
        )
        request = self.env['_paymongo_request'].call_args
        attributes = request.kwargs['payload']['data']['attributes']
        self.assertEqual(request.args[1], self.env['PAYMONGO_CREATE_CHECKOUT_URL'])
        self.assertEqual(attributes['payment_method_types'], ['gcash'])
        self.assertEqual(result['checkout_session_id'], 'cs_gcash_1')
        self.assertEqual(result['checkout_url'], 'https://paymongo.test/gcash')
        self.assertEqual(self.booking['paymongo_checkout_session_id'], 'cs_gcash_1')
        self.assertIsNone(self.booking['paymongo_payment_intent_id'])

    def test_guest_other_methods_use_selected_hosted_checkout_type(self):
        for method, expected_type in (
            ('maya', 'paymaya'),
            ('debit', 'card'),
            ('qrph', 'qrph'),
        ):
            with self.subTest(method=method):
                booking = {**self.booking}
                self.env['_paymongo_request'].reset_mock()
                self.env['_paymongo_request'].return_value = {
                    'data': {
                        'id': f'cs_{method}_1',
                        'attributes': {'checkout_url': f'https://paymongo.test/{method}'},
                    }
                }

                result = self.env['_create_public_booking_checkout'](
                    'draft-id',
                    SimpleNamespace(payment_method=method, payment_scope='selected'),
                    x_booking_token='guest-token',
                    draft_booking=booking,
                )

                attributes = self.env['_paymongo_request'].call_args.kwargs[
                    'payload'
                ]['data']['attributes']
                self.assertEqual(attributes['payment_method_types'], [expected_type])
                self.assertEqual(result['checkout_session_id'], f'cs_{method}_1')
                self.assertEqual(booking['paymongo_checkout_session_id'], f'cs_{method}_1')
                self.assertIsNone(booking.get('paymongo_payment_intent_id'))

    def test_paid_gcash_payment_intent_finalizes_public_checkout(self):
        self.booking.update(
            paymongo_payment_intent_id='pi_gcash_1',
            paymongo_reference_number='V-1-SELECTED-TEST',
            payment_method_code='gcash',
        )
        payment = {
            'id': 'pay_gcash_1',
            'attributes': {
                'amount': 50000,
                'currency': 'PHP',
                'status': 'paid',
                'source': {'type': 'gcash'},
            },
        }
        self.env['_paymongo_request'].return_value = {
            'data': {
                'id': 'pi_gcash_1',
                'attributes': {
                    'status': 'succeeded',
                    'metadata': {
                        'reference_number': 'V-1-SELECTED-TEST',
                        'booking_id': 'draft-id',
                        'booking_channel': 'public',
                        'payment_method': 'gcash',
                    },
                    'payments': [payment],
                },
            }
        }
        saved = {**self.booking, 'booking_status': 'Confirmed', '_checkout_finalized': True}
        self.env['_apply_payment'] = MagicMock(return_value=saved)
        result = self.env['_sync_public_checkout_draft'](
            self.client,
            {'booking_payload': self.booking},
        )
        self.assertEqual(result['state'], 'paid')
        self.env['_apply_payment'].assert_called_once()
        call = self.env['_apply_payment'].call_args
        self.assertTrue(call.kwargs['public_draft'])
        self.assertEqual(call.args[2]['attributes']['payment_intent']['id'], 'pi_gcash_1')
        self.assertIsNone(call.args[2]['id'])
        self.env['_send_booking_confirmation_email'].assert_called_once()

    def test_paid_gcash_intent_requires_matching_booking_and_amount(self):
        self.booking.update(
            paymongo_payment_intent_id='pi_gcash_1',
            paymongo_reference_number='V-1-SELECTED-TEST',
            payment_method_code='gcash',
        )
        intent = {
            'id': 'pi_gcash_1',
            'attributes': {
                'status': 'succeeded',
                'metadata': {
                    'booking_id': 'draft-id',
                    'booking_channel': 'public',
                    'payment_method': 'gcash',
                },
                'payments': [{
                    'id': 'pay_gcash_1',
                    'attributes': {
                        'amount': 50000,
                        'currency': 'PHP',
                        'status': 'paid',
                    },
                }],
            },
        }
        self.env['_paymongo_request'].return_value = {'data': intent}
        self.env['_apply_payment'] = MagicMock()

        with self.assertRaises(HTTPError):
            self.env['_sync_public_payment_intent'](
                self.client,
                {**self.booking, 'id': 'another-booking'},
                'pi_gcash_1',
            )

        intent['attributes']['payments'][0]['attributes']['amount'] = 49999
        with self.assertRaises(HTTPError):
            self.env['_sync_public_payment_intent'](
                self.client,
                self.booking,
                'pi_gcash_1',
            )

        self.env['_apply_payment'].assert_not_called()

    def test_reconciliation_checks_public_gcash_intent_without_checkout_session(self):
        candidate = {
            'id': 'draft-id',
            'booking_payload': {
                **self.booking,
                'paymongo_checkout_session_id': None,
                'paymongo_payment_intent_id': 'pi_gcash_1',
            },
            'paymongo_checkout_session_id': None,
            'next_check_at': '2026-10-30T00:00:00+00:00',
        }
        query = MagicMock()
        self.client.table.return_value = query
        query.select.return_value = query
        query.lte.return_value = query
        query.order.return_value = query
        query.limit.return_value = query
        query.update.return_value = query
        query.eq.return_value = query
        query.execute.side_effect = [
            SimpleNamespace(data=[candidate]),
            SimpleNamespace(data=[{'id': 'draft-id'}]),
        ]
        draft = {
            'booking_payload': {
                **candidate['booking_payload'],
            },
        }
        self.env['_public_checkout_draft'] = MagicMock(return_value=draft)
        self.env['_sync_public_checkout_draft'] = MagicMock(
            return_value={'state': 'pending'}
        )

        checked = self.env['process_public_checkout_reconciliation'](
            self.client
        )

        self.assertEqual(checked, 1)
        self.env['_sync_public_checkout_draft'].assert_called_once_with(
            self.client, draft
        )

    def test_creation_stores_only_checkout_draft_and_no_email(self):
        self.env['_prepare_public_booking'] = MagicMock(return_value={'booking':self.booking,'booking_access_token':'secret'})
        result = self.env['create_public_booking'](SimpleNamespace(email='guest@example.com'))
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

    def test_verified_payment_finalization_failure_does_not_request_another_payment(self):
        self.env['_session_payment_state'] = lambda _: {'paid': True, 'payment': self.payment}
        self.client.rpc.return_value.execute.side_effect = RuntimeError('database constraint')
        result = self.env['_sync_public_checkout_draft'](self.client, self.draft)
        self.assertEqual(result['state'], 'payment_received')
        self.assertIn('do not pay again', result['message'])
        self.assertEqual(result['booking'], self.booking)
        self.env['_send_booking_confirmation_email'].assert_not_called()

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

    def test_reconciliation_worker_rechecks_active_checkout_without_guest_return(self):
        candidate = {
            'id': 'draft-id',
            'booking_payload': self.booking,
            'paymongo_checkout_session_id': 'cs_1',
            'next_check_at': '2026-10-30T00:00:00+00:00',
        }
        query = MagicMock()
        self.client.table.return_value = query
        query.select.return_value = query
        query.not_.is_.return_value = query
        query.lte.return_value = query
        query.order.return_value = query
        query.limit.return_value = query
        query.update.return_value = query
        query.eq.return_value = query
        query.execute.side_effect = [
            SimpleNamespace(data=[candidate]),
            SimpleNamespace(data=[{'id': 'draft-id'}]),
        ]
        self.env['_public_checkout_draft'] = MagicMock(return_value=self.draft)
        self.env['_sync_public_checkout_draft'] = MagicMock()

        checked = self.env['process_public_checkout_reconciliation'](self.client)

        self.assertEqual(checked, 1)
        self.env['_sync_public_checkout_draft'].assert_called_once_with(
            self.client, self.draft
        )


if __name__ == '__main__':
    unittest.main()
