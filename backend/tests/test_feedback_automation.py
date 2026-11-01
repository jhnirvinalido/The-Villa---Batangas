import unittest
from unittest.mock import MagicMock, patch
from feedback_automation import needs_analysis, input_hash, process_feedback_analysis
from ml.preprocessing import VERSION


class FeedbackAutomationTests(unittest.TestCase):
    def setUp(self):
        self.db=MagicMock()
        self.record={'id':'review','comments':'The pool needs cleaning.','sentiment_model_version':'current','analysis_pipeline_version':VERSION}
        self.record['sentiment_input_hash']=input_hash(self.record)
        self.patches=[patch('feedback_automation.model_status',return_value={'available':True,'version':'current'}),
                      patch('feedback_automation.records_for',return_value=[self.record])]
        for item in self.patches:item.start()
        self.addCleanup(patch.stopall)

    def test_only_new_changed_or_outdated_reviews_need_analysis(self):
        self.assertFalse(needs_analysis(self.record,'current'))
        self.assertTrue(needs_analysis({**self.record,'comments':'Different feedback'},'current'))
        self.assertTrue(needs_analysis(self.record,'new-model'))
        self.assertTrue(needs_analysis({**self.record,'analysis_pipeline_version':'old'},'current'))

    def test_matching_analysis_is_not_recomputed(self):
        with patch('feedback_automation.save_pilot_prediction') as save:
            process_feedback_analysis(self.db)
        save.assert_not_called()

    def test_changed_feedback_is_reanalyzed_without_generating_recommendations(self):
        changed_record={**self.record,'comments':'The room was dirty.'}
        with patch('feedback_automation.records_for',return_value=[changed_record]), \
             patch('feedback_automation.save_pilot_prediction') as save:
            process_feedback_analysis(self.db)
        save.assert_called_once_with(self.db,changed_record)
        self.db.rpc.assert_not_called()
        self.db.table.assert_not_called()

    def test_matching_feedback_does_not_call_gemini_or_database_recommendation_jobs(self):
        with patch('feedback_automation.save_pilot_prediction') as save, \
             patch('ml.recommendations.generate') as generate:
            process_feedback_analysis(self.db)
        save.assert_not_called()
        generate.assert_not_called()
        self.db.rpc.assert_not_called()
        self.db.table.assert_not_called()
