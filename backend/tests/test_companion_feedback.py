"""Companion HTTP and capability tests. Database RPC execution is mocked."""
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
sys.path.insert(0, str(Path(__file__).parents[1]))
with patch.dict(os.environ, {'SUPABASE_URL':'https://feedback-test.invalid','SUPABASE_ANON_KEY':'test-anon-key','SUPABASE_SERVICE_ROLE_KEY':'test-service-key'}):
    import main
    import booking
    import companion_feedback as companions
from fastapi.testclient import TestClient

class CompanionFeedbackTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(main.app)
        self.booking_id = '11111111-1111-4111-8111-111111111111'
        self.url = f'/public-bookings/{self.booking_id}/feedback'
        self.token = 't' * 64
        self.db = MagicMock()
        self.record = {'id': self.booking_id, 'guest_count': 8}
        patch.object(booking, '_limit_feedback_request').start()
        patch.object(booking, '_service', return_value=self.db).start()
        self.verify = patch.object(booking, '_require_feedback_booking', return_value=self.record).start()
        self.addCleanup(patch.stopall)

    def tearDown(self):
        main.app.dependency_overrides.clear()
        self.client.close()

    def test_eight_guests_receive_seven_unique_stable_links(self):
        self.db.rpc.return_value.execute.return_value = SimpleNamespace(data=[{'slot': n, 'submitted': False, 'expires_at': '2026-11-30'} for n in range(1, 8)])
        response = self.client.post(self.url+'/companions', json={'token':self.token})
        self.assertEqual(response.status_code, 200)
        links = response.json()['invitations']
        self.assertEqual(len(links), 7)
        self.assertEqual(len({r['url'] for r in links}), 7)
        self.assertTrue(all('companion=1#token=' in r['url'] for r in links))
        again = self.client.post(self.url+'/companions', json={'token':self.token})
        self.assertEqual(again.json(), response.json())
        self.verify.assert_called_with(self.booking_id, self.token)
        args = self.db.rpc.call_args.args[1]
        self.assertEqual(len(args['p_tokens']), 7)
        self.assertNotIn(self.token, str(args))
        self.assertEqual(response.headers['cache-control'], 'no-store')

    def test_single_guest_has_no_companion_slots(self):
        self.record['guest_count'] = 1
        self.db.rpc.return_value.execute.return_value = SimpleNamespace(data=[])
        response = self.client.post(self.url+'/companions', json={'token':self.token})
        self.assertEqual(response.json(), {'invitations':[], 'capacity':0})
        self.assertEqual(self.db.rpc.call_args.args[1]['p_tokens'], [])

    def test_owner_token_required_to_issue_links(self):
        self.verify.side_effect = booking.HTTPException(401, 'Invalid owner link')
        response = self.client.post(self.url+'/companions', json={'token':self.token})
        self.assertEqual(response.status_code, 401)
        self.db.rpc.assert_not_called()

    def test_token_bound_to_booking_slot_and_owner_token(self):
        a = companions.companion_token(self.booking_id, 1, 'owner-a')
        for b in [companions.companion_token(self.booking_id, 2, 'owner-a'), companions.companion_token(self.booking_id, 1, 'owner-b'), companions.companion_token('another-booking', 1, 'owner-a')]:
            self.assertNotEqual(a, b)

    def test_companion_get_uses_rpc_and_only_hashes_token(self):
        self.db.rpc.return_value.execute.return_value = SimpleNamespace(data={'submitted':False,'booking':{'villa_name':'Villa 1'}})
        response = self.client.get(self.url+'/companion', headers={'X-Feedback-Token':self.token})
        self.assertEqual(response.status_code, 200)
        self.db.rpc.assert_called_once_with('access_companion_feedback', {'p_booking_id':self.booking_id,'p_token_hash':booking._token_hash(self.token),'p_feedback':None})
        self.verify.assert_not_called()
        self.assertEqual(response.headers['referrer-policy'], 'no-referrer')

    def test_invalid_or_expired_capability_fails_closed_without_leaking_sql(self):
        self.db.rpc.return_value.execute.side_effect = RuntimeError('SECRET internal database error')
        response = self.client.get(self.url+'/companion', headers={'X-Feedback-Token':self.token})
        self.assertEqual(response.status_code, 409)
        self.assertNotIn('SECRET', response.text)

    def test_missing_token_does_not_reach_database(self):
        response = self.client.get(self.url+'/companion')
        self.assertEqual(response.status_code, 401)
        self.db.rpc.assert_not_called()

    def test_submission_uses_separate_atomic_rpc_and_never_public_feedback_table(self):
        self.db.rpc.return_value.execute.return_value = SimpleNamespace(data={'submitted':True,'duplicate':False})
        with patch('live_updates.emit_table') as emit:
            response = self.client.post(self.url+'/companion', json={'token':self.token,'overall_rating':4,'comments':'The villa was comfortable and the pool was clean.'})
        self.assertEqual(response.status_code, 200)
        self.db.table.assert_not_called()
        self.assertEqual(self.db.rpc.call_args.args[0], 'access_companion_feedback')
        emit.assert_called_once_with('companion_feedback', {})

    def test_duplicate_is_successful_without_extra_live_event(self):
        self.db.rpc.return_value.execute.return_value = SimpleNamespace(data={'submitted':True,'duplicate':True})
        with patch('live_updates.emit_table') as emit:
            response = self.client.post(self.url+'/companion', json={'token':self.token,'overall_rating':4,'comments':'The villa was comfortable and the pool was clean.'})
        self.assertEqual(response.status_code, 200)
        emit.assert_not_called()

    def test_companion_validation_does_not_echo_secrets(self):
        response = self.client.post(self.url+'/companion', json={'token':self.token,'overall_rating':9,'comments':'short'})
        self.assertEqual(response.status_code, 422)
        self.assertNotIn(self.token, response.text)
        self.assertNotIn('"input"', response.text)
        self.db.rpc.assert_not_called()

    def test_companion_admin_endpoint_requires_authentication(self):
        response = self.client.get('/admin/guest-feedback/companions')
        self.assertEqual(response.status_code, 401)

    def test_admin_projection_excludes_invitation_private_note_and_contact_data(self):
        main.app.dependency_overrides[companions.require_admin] = lambda: {'account':{'id':'admin'}}
        db = MagicMock()
        db.table.return_value.select.return_value.order.return_value.limit.return_value.execute.return_value = SimpleNamespace(data=[{'id':'review-1','overall_rating':4,'comments':'Email me at guest@example.com about this stay.','created_at':'2026-10-28','invitation_id':'secret-id','private_note':'private secret'}])
        with patch('admin.service_client', return_value=db):
            response = self.client.get('/admin/guest-feedback/companions')
        self.assertEqual(response.status_code, 200)
        for secret in ['guest@example.com','secret-id','private secret','invitation_id','private_note']:
            self.assertNotIn(secret, response.text)
        self.assertEqual(response.json()['data'][0]['source'], 'companion')
