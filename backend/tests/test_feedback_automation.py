import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from feedback_automation import needs_analysis, input_hash, process_feedback_analysis
from ml.preprocessing import VERSION


class FeedbackAutomationTests(unittest.TestCase):
    def setUp(self):
        self.db=MagicMock()
        self.db.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value=SimpleNamespace(data=[])
        self.record={'id':'review','comments':'The pool needs cleaning.','sentiment_model_version':'current','analysis_pipeline_version':VERSION}
        self.record['sentiment_input_hash']=input_hash(self.record)
        self.summary={'fingerprint':'fingerprint','top_complaints':[{'category':'Pool cleanliness'}]}
        self.analysis={'summary':self.summary,'model':{'version':'current'}}
        self.patches=[patch('feedback_automation.model_status',return_value={'available':True,'version':'current'}),
                      patch('feedback_automation.records_for',return_value=[self.record]),
                      patch('feedback_automation.build_report',return_value=self.analysis),
                      patch('feedback_automation.configured',return_value=True)]
        for item in self.patches:item.start()
        self.addCleanup(patch.stopall)

    def test_only_new_changed_or_outdated_reviews_need_analysis(self):
        self.assertFalse(needs_analysis(self.record,'current'))
        self.assertTrue(needs_analysis({**self.record,'comments':'Different feedback'},'current'))
        self.assertTrue(needs_analysis(self.record,'new-model'))
        self.assertTrue(needs_analysis({**self.record,'analysis_pipeline_version':'old'},'current'))

    def test_existing_matching_report_is_reused_without_gemini_call(self):
        self.db.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value=SimpleNamespace(data=[{'id':'existing'}])
        with patch('feedback_automation.generate') as generate,patch('feedback_automation.save_pilot_prediction') as save:
            process_feedback_analysis(self.db)
        generate.assert_not_called();save.assert_not_called();self.db.rpc.assert_not_called()

    def test_another_worker_claim_prevents_duplicate_generation(self):
        self.db.rpc.return_value.execute.return_value=SimpleNamespace(data=None)
        with patch('feedback_automation.generate') as generate:
            process_feedback_analysis(self.db)
        generate.assert_not_called()

    def test_success_uses_atomic_finish_and_system_audit(self):
        self.db.rpc.return_value.execute.return_value=SimpleNamespace(data='claim')
        draft={'actions':[{'category':'Pool cleanliness'}]}
        with patch('feedback_automation.generate',return_value=draft):process_feedback_analysis(self.db)
        name,payload=self.db.rpc.call_args.args
        self.assertEqual(name,'finish_feedback_analysis_job')
        self.assertEqual(payload['p_claim'],'claim')
        self.assertEqual(payload['p_recommendation'],draft)
        self.assertIsNone(payload['p_error'])
        self.assertNotIn('created_by_staff_id',payload)

    def test_provider_failure_records_retry_instead_of_fake_recommendations(self):
        self.db.rpc.return_value.execute.return_value=SimpleNamespace(data='claim')
        with patch('feedback_automation.generate',side_effect=RuntimeError('Gemini quota reached')):
            process_feedback_analysis(self.db)
        payload=self.db.rpc.call_args.args[1]
        self.assertIsNone(payload['p_recommendation'])
        self.assertEqual(payload['p_error'],'Gemini quota reached')

    def test_no_negative_evidence_never_calls_gemini(self):
        self.summary['top_complaints']=[]
        with patch('feedback_automation.generate') as generate:
            process_feedback_analysis(self.db)
        generate.assert_not_called();self.db.rpc.assert_not_called()
