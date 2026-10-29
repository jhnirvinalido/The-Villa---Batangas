import json
import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from feedback_analysis import AnalysisFilters, records_for
from ml.complaints import analyze_review, categories, report
from ml.naive_bayes import TfidfNB
from ml.preprocessing import normalize, phrases
from ml.recommendations import generate
from ml.train import read_dataset, evaluate
from pathlib import Path


class StubModel:
    def predict_one(self, text):
        # A controlled classifier tests aggregation independently of ML quality.
        negative = any(word in text for word in ('dirty','weak','slow')) and 'not dirty' not in text
        return {'label':'negative' if negative else 'positive','known_feature_occurrences':1}


class AnalysisTests(unittest.TestCase):
    def test_normalize_preserves_negation_and_original_tagalog(self):
        self.assertEqual(normalize('Hindi drrty ang poool'), 'hindi dirty ang pool')
        self.assertEqual(normalize('sobrang init sa room'), 'sobrang init sa room')
        self.assertEqual(normalize('slooow wifi'), 'slow wi-fi')

    def test_clauses_preserve_mixed_sentiment_and_category_is_not_sentiment_rule(self):
        row={'id':'1','comments':'dirty pool, weak aircon pero friendly staff.'}
        result=analyze_review(row, StubModel())
        self.assertEqual([r['sentiment'] for r in result], ['negative','negative','positive'])
        self.assertEqual(result[0]['categories'], ['Pool cleanliness'])
        self.assertIn('Staff service',categories('friendly staff'))
        self.assertEqual(len(phrases('not dirty pool but weak aircon')),2)

    def test_distinct_reviews_count_once_per_category_and_positive_not_complaint(self):
        rows=[{'id':'a','comments':'dirty pool. dirty pool. friendly staff.','overall_rating':5},
              {'id':'b','comments':'dirty pool. slow wifi.','overall_rating':1}]
        result=report(rows+rows[:1],StubModel())
        counts={r['category']:r['negative_review_count'] for r in result['summary']['top_complaints']}
        self.assertEqual(counts,{'Pool cleanliness':2,'Internet connectivity':1})
        self.assertEqual(result['summary']['average_star_rating'],3)
        self.assertEqual(result['summary']['total_reviews'],2)
        self.assertEqual(result['summary']['phrase_sentiments']['positive'],1)

    def test_evidence_does_not_contain_known_identity_or_private_note(self):
        result=report([{'id':'a','comments':'Maria Cruz says dirty pool. Contact maria@example.com.',
                       'guest_name':'Maria Cruz','guest_email':'maria@example.com','private_note':'private secret','overall_rating':2}],StubModel())
        output=json.dumps(result)
        for value in ('Maria','Cruz','maria@example.com','private secret'): self.assertNotIn(value,output)

    def test_tfidf_round_trip_and_vocabulary_fitted_only_on_training(self):
        model=TfidfNB().fit(['dirty pool','ordinary room','friendly staff'],['negative','neutral','positive'])
        self.assertNotIn('unseen',model.idf)
        self.assertEqual(TfidfNB.from_dict(model.to_dict()).predict_one('dirty pool'),model.predict_one('dirty pool'))
        self.assertEqual(model.predict_one('zzzzz')['known_feature_occurrences'],0)

    def test_grouped_evaluation_never_splits_a_review(self):
        records=read_dataset(Path(__file__).parents[1]/'ml/datasets/sentiment_phrases.csv')
        result=evaluate(records)
        seen=set()
        for fold in result['fold_sizes']:
            group=set(fold['test_groups']);self.assertFalse(group & seen);seen.update(group)
        self.assertEqual(len(seen),26)

    def test_month_filters_use_source_review_date_not_import_timestamp(self):
        client=MagicMock()
        client.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value=SimpleNamespace(data=[{'id':'a','source':'historical_dataset','review_date_label':'August 2026','created_at':'2026-10-21','overall_rating':5}])
        rows=records_for(client,AnalysisFilters(source='historical',start='2026-08-01',end='2026-08-01'))
        self.assertEqual(len(rows),1)
        self.assertEqual(records_for(client,AnalysisFilters(source='historical',start='2026-09-01')),[])

    def test_gemini_missing_configuration_never_calls_network(self):
        with patch.dict(os.environ,{'GEMINI_API_KEY':'','GEMINI_MODEL':''}),patch('ml.recommendations.requests.post') as send:
            with self.assertRaises(ValueError):generate({})
            send.assert_not_called()

    def test_gemini_evidence_counts_are_server_owned_and_categories_validated(self):
        summary=report([{'id':'a','comments':'dirty pool.','overall_rating':2}],StubModel())['summary']
        response=MagicMock(ok=True)
        response.json.return_value={'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':json.dumps({'actions':[{'category':'Pool cleanliness','action':'Inspect pool cleaning procedures.','rationale':'This category has reported negative evidence.'}]})}]}}]}
        with patch.dict(os.environ,{'GEMINI_API_KEY':'test-secret','GEMINI_MODEL':'test-model'}),patch('ml.recommendations.requests.post',return_value=response) as send:
            result=generate(summary)
            self.assertEqual(result['actions'][0]['negative_review_count'],1)
            body=send.call_args.kwargs['json']
            self.assertNotIn('test-secret',json.dumps(body))
            response.json.return_value['candidates'][0]['content']['parts'][0]['text']=json.dumps({'actions':[{'category':'Unsupported category','action':'Inspect equipment and service.','rationale':'This is not supported by the report.'}]})
            with self.assertRaises(ValueError):generate(summary)

    def test_unknown_phrases_abstain_and_do_not_count_as_complaints(self):
        model=MagicMock();model.predict_one.return_value={'label':'negative','known_feature_occurrences':0}
        summary=report([{'id':'a','comments':'pool zzzzxxyy.','overall_rating':1}],model)['summary']
        self.assertEqual(summary['top_complaints'],[])
        self.assertEqual(summary['phrase_sentiments'],{'unclassified':1})

    def test_provider_errors_are_actionable_without_echoing_provider_secrets(self):
        summary=report([{'id':'a','comments':'dirty pool.','overall_rating':2}],StubModel())['summary']
        for status,expected in [(401,'API key'),(403,'denied'),(404,'not found'),(429,'quota')]:
            response=MagicMock(ok=False,status_code=status)
            response.text='provider secret and credentials'
            with patch.dict(os.environ,{'GEMINI_API_KEY':'test-secret','GEMINI_MODEL':'test-model'}),patch('ml.recommendations.requests.post',return_value=response):
                with self.assertRaises(RuntimeError) as failure:generate(summary)
                self.assertIn(expected,str(failure.exception))
                self.assertNotIn('secret',str(failure.exception))
