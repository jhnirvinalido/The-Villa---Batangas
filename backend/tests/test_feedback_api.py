"""HTTP contract tests. Dummy environment; all database/SMTP calls are mocked."""
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
sys.path.insert(0,str(Path(__file__).parents[1]))
try:
    with patch.dict(os.environ,{'SUPABASE_URL':'https://feedback-test.invalid','SUPABASE_ANON_KEY':'test-anon-key','SUPABASE_SERVICE_ROLE_KEY':'test-service-key'}):
        import main
        import booking
        import admin
    from fastapi.testclient import TestClient
    HAS_DEPS=True
except ImportError:
    HAS_DEPS=False

@unittest.skipUnless(HAS_DEPS,'Use backend/.venv/bin/python for HTTP tests')
class FeedbackAPITests(unittest.TestCase):
    def setUp(self):
        self.client=TestClient(main.app)
        self.db=MagicMock()
        self.booking_id='11111111-1111-4111-8111-111111111111'
        self.url=f'/public-bookings/{self.booking_id}/feedback'
        self.record={'id':self.booking_id,'customer_name':'Maria Cruz','customer_email':'maria@example.com','booking_code':'TV-123','villa_name':'Villa 1','check_in_date':'2026-10-19','check_out_date':'2026-10-20'}
        self.limiter=patch.object(booking,'_limit_feedback_request').start()
        self.addCleanup(patch.stopall)
    def tearDown(self):
        main.app.dependency_overrides.clear()
        self.client.close()
    def test_get_returns_minimal_metadata_and_no_store(self):
        self.db.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value=SimpleNamespace(data=[])
        with patch.object(booking,'_service',return_value=self.db),patch.object(booking,'_require_feedback_booking',return_value=self.record) as verify:
            response=self.client.get(self.url,headers={'X-Feedback-Token':'test-token'})
        self.assertEqual(response.status_code,200)
        self.assertEqual(set(response.json()['booking']),{'villa_name','check_in_date','check_out_date'})
        self.assertEqual(response.headers['cache-control'],'no-store')
        verify.assert_called_once_with(self.booking_id,'test-token')
    def test_public_rating_summary_exposes_only_aggregate_counts(self):
        self.db.rpc.return_value.execute.return_value=SimpleNamespace(data=[
            {'overall_rating':5,'comments':'Private guest comment','guest_name':'Guest'},
            {'overall_rating':4,'comments':'Another private comment','guest_name':'Other'},
            {'overall_rating':5},
            {'overall_rating':0},
        ])
        with patch.object(booking,'_service',return_value=self.db):
            response=self.client.get('/public-bookings/feedback/summary')
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json()['data'],{
            'count':3,
            'average':4.7,
            'distribution':{'1':0,'2':0,'3':0,'4':1,'5':2},
        })
        self.assertNotIn('Private guest comment',response.text)
        self.assertNotIn('Guest',response.text)
    def test_public_rating_summary_reports_storage_failure(self):
        self.db.rpc.return_value.execute.side_effect=RuntimeError('storage unavailable')
        with patch.object(booking,'_service',return_value=self.db):
            response=self.client.get('/public-bookings/feedback/summary')
        self.assertEqual(response.status_code,503)
        self.assertEqual(response.json()['detail'],'Guest ratings are temporarily unavailable.')
    def test_validation_errors_do_not_echo_token_or_comments(self):
        secret='sensitive-token-not-for-output-12345'
        response=self.client.post(self.url,json={'token':secret,'overall_rating':6,'comments':'a'})
        self.assertEqual(response.status_code,422)
        self.assertNotIn(secret,response.text)
        self.assertNotIn('"input"',response.text)
        self.limiter.assert_called_once()
    def test_valid_submission_and_duplicate_response(self):
        payload=dict(token='t'*40,overall_rating=5,cleanliness_rating=4,service_rating=5,villa_rating=4,value_rating=5,would_recommend=True,comments='The villa was clean and the staff were helpful.',hide_identity=True)
        self.db.rpc.return_value.execute.return_value=SimpleNamespace(data={'submitted':True,'duplicate':True})
        with patch.object(booking,'_service',return_value=self.db),patch.object(booking,'_require_feedback_booking',return_value=self.record):
            response=self.client.post(self.url,json=payload)
        self.assertEqual(response.status_code,200);self.assertTrue(response.json()['submitted'])
        self.assertTrue(self.db.rpc.call_args.args[1]['p_feedback']['hide_identity'])
    def test_minimal_dataset_aligned_submission_requires_only_overall_rating_and_comment(self):
        payload=dict(token='t'*40,overall_rating=4,comments='The villa was comfortable and the staff were helpful.')
        self.db.rpc.return_value.execute.return_value=SimpleNamespace(data={'submitted':True,'duplicate':True})
        with patch.object(booking,'_service',return_value=self.db),patch.object(booking,'_require_feedback_booking',return_value=self.record):
            response=self.client.post(self.url,json=payload)
        self.assertEqual(response.status_code,200)
        stored=self.db.rpc.call_args.args[1]['p_feedback']
        for field in ['cleanliness_rating','service_rating','villa_rating','value_rating','would_recommend']:
            self.assertIsNone(stored[field])
        self.assertEqual(stored['overall_rating'],4)

    def test_rate_limit_applies_before_invalid_payload_validation(self):
        self.limiter.side_effect=booking.HTTPException(status_code=429,detail='Please wait.')
        response=self.client.post(self.url,json={})
        self.assertEqual(response.status_code,429)
        self.assertEqual(response.headers['cache-control'],'no-store')
    def test_administrator_feedback_endpoint_hides_identity_and_declares_analysis_unavailable(self):
        main.app.dependency_overrides[admin.require_admin]=lambda:{'account':{'id':'admin-test'}}
        row={'id':'review-1','booking_id':self.booking_id,'booking_code':'TV-123','guest_name':'Maria Cruz','guest_email':'maria@example.com','hide_identity':True,'comments':'Maria Cruz enjoyed TV-123. The villa was clean and comfortable.','private_note':'private message','overall_rating':5,'analysis_status':'awaiting_integration'}
        self.db.rpc.return_value.execute.return_value=SimpleNamespace(data=[row])
        self.db.table.return_value.select.return_value.execute.return_value=SimpleNamespace(data=[])
        with patch.object(admin,'service_client',return_value=self.db),patch('ml.inference.model_status',return_value={'available':False,'pilot':True,'gemini_available':False}):
            response=self.client.get('/admin/guest-feedback')
        self.assertEqual(response.status_code,200)
        self.assertFalse(response.json()['analysis_available'])
        for secret in ['Maria','Cruz','maria@example.com','TV-123',self.booking_id,'private message']:
            self.assertNotIn(secret,response.text)
    def test_public_booking_payload_omits_all_feedback_and_access_secrets(self):
        result=booking._safe_public_booking({**self.record,'guest_access_token_hash':'secret','feedback_token_hash':'secret','feedback_token_expires_at':'future','feedback_token_revoked_at':None})
        self.assertFalse(any('token' in key for key in result))

    def test_analysis_and_recommendations_require_admin_authentication(self):
        for method,path,payload in [
            ('GET','/admin/guest-feedback/analysis',None),
            ('POST','/admin/guest-feedback/recommendations',{}),
            ('POST',f'/admin/guest-feedback/recommendations/{self.booking_id}/approve',None),
        ]:
            response=self.client.request(method,path,json=payload)
            self.assertEqual(response.status_code,401)

    def test_recommendation_approval_rejects_stale_evidence(self):
        main.app.dependency_overrides[admin.require_admin]=lambda:{'account':{'id':'admin-test'}}
        stored={'id':self.booking_id,'filters':{'source':'all'},'evidence_fingerprint':'old','status':'draft'}
        self.db.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value=SimpleNamespace(data=[stored])
        with patch.object(admin,'service_client',return_value=self.db),patch('feedback_analysis.build_report',return_value={'summary':{'fingerprint':'new'}}):
            response=self.client.post(f'/admin/guest-feedback/recommendations/{self.booking_id}/approve')
        self.assertEqual(response.status_code,409)
        self.db.table.return_value.update.assert_not_called()

    def test_recommendations_fail_before_external_call_when_storage_missing(self):
        main.app.dependency_overrides[admin.require_admin]=lambda:{'account':{'id':'admin-test'}}
        self.db.table.return_value.select.return_value.limit.return_value.execute.side_effect=RuntimeError('missing table')
        with patch.object(admin,'service_client',return_value=self.db),patch('ml.recommendations.generate') as generate:
            response=self.client.post('/admin/guest-feedback/recommendations',json={})
        self.assertEqual(response.status_code,503)
        generate.assert_not_called()

    def test_approval_records_admin_and_timestamp_without_executing_tasks(self):
        main.app.dependency_overrides[admin.require_admin]=lambda:{'account':{'id':'admin-test'}}
        stored={'id':self.booking_id,'filters':{'source':'all'},'evidence_fingerprint':'same','status':'draft'}
        self.db.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value=SimpleNamespace(data=[stored])
        self.db.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value=SimpleNamespace(data=[{**stored,'status':'approved'}])
        with patch.object(admin,'service_client',return_value=self.db),patch('feedback_analysis.build_report',return_value={'summary':{'fingerprint':'same'}}):
            response=self.client.post(f'/admin/guest-feedback/recommendations/{self.booking_id}/approve')
        self.assertEqual(response.status_code,200)
        update=self.db.table.return_value.update.call_args.args[0]
        self.assertEqual(update['approved_by_staff_id'],'admin-test')
        self.assertTrue(update['approved_at'])
        self.assertTrue(all(call.args[0]=='feedback_recommendation_reports' for call in self.db.table.call_args_list))

    def test_recommendation_generation_saves_draft_and_returns_it(self):
        main.app.dependency_overrides[admin.require_admin]=lambda:{'account':{'id':'admin-test'}}
        draft={'actions':[{'category':'Pool cleanliness','action':'Inspect the pool.'}],'model':'test-model'}
        analysis={'summary':{'fingerprint':'snapshot'},'model':{'version':'test-version'}}
        self.db.table.return_value.insert.return_value.execute.return_value=SimpleNamespace(data=[{'id':self.booking_id,'status':'draft','recommendation':draft}])
        with patch.object(admin,'service_client',return_value=self.db),patch('feedback_analysis.build_report',return_value=analysis),patch('ml.recommendations.generate',return_value=draft):
            response=self.client.post('/admin/guest-feedback/recommendations',json={'source':'all','villa':'','rating':None,'start':None,'end':None})
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json()['data']['recommendation'],draft)
        saved=self.db.table.return_value.insert.call_args.args[0]
        self.assertEqual(saved['created_by_staff_id'],'admin-test')
        self.assertEqual(saved['evidence_fingerprint'],'snapshot')

    def test_public_written_reviews_need_no_login_and_exclude_sensitive_fields(self):
        record={'id':'review','overall_rating':2,'comments':'Maria Cruz reported a problem with the pool.',
                'guest_name':'Maria Cruz','guest_email':'maria@example.com','private_note':'private secret',
                'booking_id':self.booking_id,'source':'historical_dataset','review_date_label':'August 2026'}
        with patch.object(booking,'_service',return_value=self.db),patch('feedback_analysis.records_for',return_value=[record]):
            response=self.client.get('/public-bookings/feedback/reviews')
        self.assertEqual(response.status_code,200)
        self.assertIn('no-store',response.headers['cache-control'])
        self.assertEqual(response.json()['data']['count'],1)
        self.assertEqual(response.json()['data']['reviews'][0]['rating'],2)
        for value in ['Maria','Cruz','maria@example.com','private secret',self.booking_id]:self.assertNotIn(value,response.text)
