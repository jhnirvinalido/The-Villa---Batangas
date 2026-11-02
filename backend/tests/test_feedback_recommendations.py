import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from feedback_recommendations import process_recommendation_job


def response(data):
    return SimpleNamespace(data=data)

def rpc_response(data):
    return SimpleNamespace(execute=lambda: response(data))


def job(attempt=1):
    return {
        'id': f'job-{attempt}',
        'claim_id': f'claim-{attempt}',
        'attempts': attempt,
        'max_attempts': 3,
        'evidence_fingerprint': 'evidence-hash',
        'created_by_staff_id': 'admin-id',
        'filters': {'source': 'all'},
        'evidence_summary': {'top_complaints': [{
            'category': 'Pool cleanliness',
            'negative_review_count': 1,
            'evidence': ['The pool was dirty'],
        }]},
        'model_version': 'pilot-model',
    }


class FeedbackRecommendationWorkerTests(unittest.TestCase):
    def setUp(self):
        self.client = MagicMock()
        self.client.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = response([])
        self.report = {'id': 'report-id', 'status': 'draft'}

    def test_two_worker_cycles_for_same_evidence_persist_only_one_report(self):
        self.client.rpc.side_effect = [
            rpc_response(job()),
            rpc_response({'created': True, 'report': self.report}),
            rpc_response(True),
            rpc_response(None),
        ]
        with patch('feedback_recommendations.generate', return_value={'actions': []}) as generate, \
             patch('live_updates.emit_table'):
            first = process_recommendation_job(self.client)
            second = process_recommendation_job(self.client)

        self.assertTrue(first)
        self.assertFalse(second)
        generate.assert_called_once()
        rpc_names = [call.args[0] for call in self.client.rpc.call_args_list]
        self.assertEqual(rpc_names.count('persist_feedback_recommendation_report'), 1)
        self.assertEqual(rpc_names.count('finish_feedback_recommendation_job'), 1)

    def test_existing_report_recovers_a_claim_without_regenerating_or_duplicate_insert(self):
        self.client.rpc.side_effect = [rpc_response(job()), rpc_response(True)]
        self.client.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = response(
            [{'id': 'existing-report'}])
        with patch('feedback_recommendations.generate') as generate:
            self.assertTrue(process_recommendation_job(self.client))

        generate.assert_not_called()
        finish = self.client.rpc.call_args_list[-1]
        self.assertEqual(finish.args[0], 'finish_feedback_recommendation_job')
        self.assertEqual(finish.args[1]['p_report_id'], 'existing-report')

    def test_transient_provider_failures_are_returned_to_bounded_retry_queue(self):
        rpc_responses = []
        for attempt in range(1, 4):
            rpc_responses.extend([rpc_response(job(attempt)), rpc_response(True)])
        rpc_responses.append(rpc_response(None))
        self.client.rpc.side_effect = rpc_responses
        with patch('feedback_recommendations.generate', side_effect=RuntimeError('Gemini temporarily unavailable')) as generate:
            self.assertTrue(process_recommendation_job(self.client))
            self.assertTrue(process_recommendation_job(self.client))
            self.assertTrue(process_recommendation_job(self.client))
            self.assertFalse(process_recommendation_job(self.client))

        self.assertEqual(generate.call_count, 3)
        finished = [
            call.args[1] for call in self.client.rpc.call_args_list
            if call.args[0] == 'finish_feedback_recommendation_job'
        ]
        self.assertEqual(len(finished), 3)
        self.assertTrue(all(item['p_retryable'] for item in finished))
        self.assertTrue(all(item['p_status'] == 'retry' for item in finished))

    def test_invalid_provider_output_is_not_retried(self):
        self.client.rpc.side_effect = [rpc_response(job()), rpc_response(True)]
        with patch('feedback_recommendations.generate', side_effect=ValueError('Invalid provider response')):
            self.assertTrue(process_recommendation_job(self.client))

        finish = self.client.rpc.call_args_list[-1].args[1]
        self.assertFalse(finish['p_retryable'])
