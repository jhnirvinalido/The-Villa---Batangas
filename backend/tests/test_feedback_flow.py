"""Real backend functions with mocked Supabase/SMTP; no network or live mail."""
import hashlib
import sys
import smtplib
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
sys.path.insert(0,str(Path(__file__).parents[1]))
from feedback_policy import eligible_stay, meaningful_comments, admin_feedback_projection, analysis_input

try:
    import booking
    import feedback_service as service
    from pydantic import ValidationError
    HAS_DEPS=True
except ImportError:
    HAS_DEPS=False

class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.record={'id':'11111111-1111-4111-8111-111111111111','booking_status':'Completed','stay_status':'Checked Out','payment_status':'Paid','total_amount':1000,'amount_paid':1000,'balance_amount':0}
    def test_only_completed_stays_with_settled_ledger_are_eligible(self):
        self.assertTrue(eligible_stay(self.record,1000))
        for update,settled in [({'booking_status':'Confirmed','stay_status':'Not Checked In'},1000),({'amount_paid':500,'balance_amount':500},500),({},500),({'booking_status':'Cancelled'},1000),({'payment_status':'Refunded'},1000),({'refunded_amount':100},1000)]:
            with self.subTest(update=update): self.assertFalse(eligible_stay({**self.record,**update},settled))
    def test_meaningful_written_feedback(self):
        self.assertEqual(meaningful_comments('  The rooms were clean and comfortable.  '),'The rooms were clean and comfortable.')
        for value in ['', 'good', 'a '*20, '123456789012345678901234']:
            with self.subTest(value=value),self.assertRaises(ValueError):meaningful_comments(value)
    def test_identity_hidden_projection_and_analysis_exclude_sensitive_fields(self):
        row={**self.record,'id':'review-id','guest_name':'Maria Cruz','guest_email':'maria@example.com','booking_code':'TV-1234','guest_phone':'09171234567','hide_identity':True,'comments':'I am Maria Cruz, maria@example.com, 09171234567, TV-1234. The rooms were pleasant.','private_note':'Please call me privately.','overall_rating':5,'cleanliness_rating':5,'service_rating':5,'villa_rating':5,'value_rating':4,'analysis_status':'awaiting_integration'}
        safe=admin_feedback_projection(row)
        for key in ['booking_id','booking_code','guest_email','guest_phone','private_note']:self.assertNotIn(key,safe)
        for value in ['Maria','Cruz','maria@example.com','09171234567','TV-1234']:self.assertNotIn(value,str(safe))
        ml=analysis_input(row)
        self.assertEqual(set(ml),{'feedback_id','text','ratings'})
        self.assertNotIn('Please call',str(ml))
        self.assertEqual(safe['analysis_status'],'awaiting_integration')
    def test_named_feedback_retains_name_and_reference_but_not_private_note(self):
        safe=admin_feedback_projection({'guest_name':'Maria Cruz','booking_code':'TV-1','guest_email':'private@example.com','private_note':'private'})
        self.assertEqual(safe['guest_name'],'Maria Cruz');self.assertEqual(safe['booking_code'],'TV-1')
        self.assertNotIn('guest_email',safe);self.assertNotIn('private_note',safe)

@unittest.skipUnless(HAS_DEPS,'Run with backend/.venv/bin/python for API/SMTP tests')
class BackendFlowTests(unittest.TestCase):
    def setUp(self):
        self.id='11111111-1111-4111-8111-111111111111'
        self.record={'id':self.id,'customer_email':'guest@example.com','customer_name':'Guest','booking_code':'TV-1','villa_name':'Villa 1','booking_status':'Completed','stay_status':'Checked Out','payment_status':'Paid','total_amount':1000,'amount_paid':1000,'balance_amount':0}
        self.client=MagicMock()
    def token_booking(self):
        return {**self.record,'feedback_token_hash':hashlib.sha256(b'secure-token-value-for-test-123456').hexdigest(),'feedback_token_expires_at':(datetime.now(timezone.utc)+timedelta(days=1)).isoformat()}
    def test_full_payment_before_checkout_does_not_queue(self):
        record={**self.record,'booking_status':'Confirmed','stay_status':'Not Checked In'}
        with patch.object(service,'settled_total',return_value=1000):
            self.assertFalse(service.queue_feedback_invitation(record,self.client))
        self.client.rpc.assert_not_called()
    def test_checkout_and_late_payment_both_use_idempotent_queue_rpc(self):
        with patch.object(service,'settled_total',return_value=1000),patch.object(booking,'SUPABASE_SERVICE_ROLE_KEY','test-secret'):
            self.assertTrue(service.queue_feedback_invitation(self.record,self.client))
            self.assertTrue(service.queue_feedback_invitation(self.record,self.client))
        for call in self.client.rpc.call_args_list:
            self.assertEqual(call.args[0],'queue_guest_feedback_invitation')
            self.assertEqual(call.args[1]['p_booking_id'],self.id)
    def test_payment_evidence_combines_deposit_and_room_balance_not_service_charges(self):
        def table(name):
            query=MagicMock()
            query.select.return_value.eq.return_value.execute.return_value=SimpleNamespace(data=[{'amount':500,'status':'paid'}] if name=='booking_payments' else [{'room_balance_amount':500,'amount':900,'status':'Paid'}])
            return query
        self.client.table.side_effect=table
        self.assertEqual(service.settled_total(self.client,self.id),1000)
        self.assertTrue(service.booking_eligible(self.client,self.record))
    def test_missing_optional_front_desk_table_does_not_invent_room_payments(self):
        def table(name):
            query=MagicMock()
            if name=='front_desk_payments':
                query.select.return_value.eq.return_value.execute.side_effect=RuntimeError('PGRST205 could not find the table')
            else:
                query.select.return_value.eq.return_value.execute.return_value=SimpleNamespace(data=[{'amount':500,'status':'paid'}])
            return query
        self.client.table.side_effect=table
        self.assertEqual(service.settled_total(self.client,self.id),500)
        self.assertFalse(service.booking_eligible(self.client,self.record))

    def test_booking_confirmation_has_no_feedback_link(self):
        with patch.object(booking,'_smtp_configured',return_value=True),patch.object(booking,'_booking_email_logo',return_value=('',None)),patch.object(booking.smtplib,'SMTP') as smtp:
            self.assertTrue(booking._send_booking_confirmation_email(self.record))
            message=smtp.return_value.__enter__.return_value.send_message.call_args.args[0]
            self.assertNotIn('/feedback',message.as_string())
            self.assertNotIn('Share Your Experience',str(message['Subject']))
    def test_get_and_post_validator_reject_invalid_expired_revoked_and_unpaid(self):
        record=self.token_booking()
        self.client.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value=SimpleNamespace(data=[record])
        with patch.object(booking,'_service',return_value=self.client),patch.object(service,'booking_eligible',return_value=True):
            self.assertEqual(booking._require_feedback_booking(self.id,'secure-token-value-for-test-123456')['id'],self.id)
            for changes,token in [({},'invalid-token-with-enough-length'),({'feedback_token_expires_at':'2000-01-01T00:00:00+00:00'},'secure-token-value-for-test-123456'),({'feedback_token_revoked_at':'2026-10-20'},'secure-token-value-for-test-123456')]:
                self.client.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value=SimpleNamespace(data=[{**record,**changes}])
                with self.assertRaises(booking.HTTPException):booking._require_feedback_booking(self.id,token)
        with patch.object(booking,'_service',return_value=self.client),patch.object(service,'booking_eligible',return_value=False),self.assertRaises(booking.HTTPException):
            booking._require_feedback_booking(self.id,'secure-token-value-for-test-123456')
    def test_submission_validates_ratings_comments_and_hide_identity(self):
        values=dict(token='a'*40,overall_rating=5,cleanliness_rating=4,service_rating=5,villa_rating=4,value_rating=4,would_recommend=True,comments='The rooms were clean and the staff were helpful.',hide_identity=True,private_note='Private')
        request=booking.GuestFeedbackRequest(**values)
        self.assertTrue(request.hide_identity)
        for updates in [{'comments':''},{'comments':'good'},{'overall_rating':0},{'overall_rating':6}]:
            with self.subTest(updates=updates),self.assertRaises(ValidationError):booking.GuestFeedbackRequest(**{**values,**updates})
        self.client.rpc.return_value.execute.return_value=SimpleNamespace(data={'submitted':True,'duplicate':True})
        with patch.object(booking,'_service',return_value=self.client),patch.object(booking,'_require_feedback_booking',return_value=self.record):
            result=booking.submit_guest_feedback(self.id,request,MagicMock())
        self.assertTrue(result['submitted'])
        params=self.client.rpc.call_args.args[1]
        self.assertNotIn('token',params['p_feedback']);self.assertTrue(params['p_feedback']['hide_identity'])
    def run_worker(self, smtp_error=None, eligible=True):
        record=self.token_booking();nonce='stable-random-nonce'
        with patch.object(booking,'SUPABASE_SERVICE_ROLE_KEY','test-secret'):
            record['feedback_token_hash']=hashlib.sha256(service.token_for(self.id,nonce).encode()).hexdigest()
        claim={'booking':record,'token_nonce':nonce,'message_id':'<stable@thevilla.local>','claim_id':'lease-1'}
        claims=iter([claim,None])
        def rpc(name,params):
            data=next(claims) if name=='claim_guest_feedback_invitation' else [] if name=='guest_feedback_invitation_candidates' else eligible if name=='feedback_booking_eligible' else True
            return SimpleNamespace(execute=lambda:SimpleNamespace(data=data))
        self.client.rpc.side_effect=rpc
        with patch.object(booking,'_service',return_value=self.client),patch.object(booking,'SUPABASE_SERVICE_ROLE_KEY','test-secret'),patch.object(booking,'_smtp_configured',return_value=True),patch.object(booking,'_booking_email_logo',return_value=('',None)),patch.object(service.smtplib,'SMTP') as smtp:
            smtp.return_value.__enter__.return_value.send_message.return_value={}
            if smtp_error:smtp.return_value.__enter__.return_value.send_message.side_effect=smtp_error
            service.process_feedback_outbox()
            calls=smtp.return_value.__enter__.return_value.send_message.call_args_list
        finishes=[call.args[1] for call in self.client.rpc.call_args_list if call.args[0]=='finish_guest_feedback_invitation']
        return finishes[-1]['p_status'],calls
    def test_smtp_acceptance_recorded_with_stable_fragment_link(self):
        state,calls=self.run_worker();self.assertEqual(state,'accepted')
        self.assertIn('#token=',calls[0].args[0].get_body(preferencelist=('plain',)).get_content())
    def test_definite_smtp_rejection_is_retryable_without_undoing_checkout(self):
        state,_=self.run_worker(smtplib.SMTPDataError(451,b'temporary failure'))
        self.assertEqual(state,'retry');self.assertEqual(self.record['booking_status'],'Completed')
    def test_uncertain_smtp_failure_is_not_blindly_resent(self):
        state,_=self.run_worker(smtplib.SMTPServerDisconnected('connection lost'))
        self.assertEqual(state,'uncertain')
    def test_refund_between_queue_and_send_suppresses_email(self):
        state,calls=self.run_worker(eligible=False)
        self.assertEqual(state,'suppressed');self.assertEqual(calls,[])
    def test_checkout_succeeds_when_feedback_outbox_is_unavailable(self):
        import admin
        checked_in={**self.record,'booking_status':'Checked In','stay_status':'Checked In'}
        with patch.object(admin,'fetch_booking',return_value=checked_in),patch.object(admin,'enforce_booking_lifecycle_date'),patch.object(admin,'pending_front_desk_intents',return_value=[]),patch.object(admin,'update_booking_lifecycle',return_value=self.record),patch.object(admin,'sync_booking_tasks_after_lifecycle'),patch.object(admin,'create_checkout_turnover_task',return_value=None),patch.object(admin,'record_booking_event'),patch.object(admin,'attach_payment_timing',side_effect=lambda record:record),patch.object(booking,'_service',side_effect=RuntimeError('Outbox unavailable')):
            result=admin.checkout_booking(self.id,SimpleNamespace(notes=None),{'account':{'id':'admin-1','full_name':'Administrator'}})
        self.assertEqual(result['data']['booking_status'],'Completed')
        self.assertEqual(result['message'],'Guest checkout completed.')

    def test_retry_token_is_stable_and_booking_bound(self):
        with patch.object(booking,'SUPABASE_SERVICE_ROLE_KEY','test-secret'):
            self.assertEqual(service.token_for(self.id,'nonce'),service.token_for(self.id,'nonce'))
            self.assertNotEqual(service.token_for(self.id,'nonce'),service.token_for('other','nonce'))
