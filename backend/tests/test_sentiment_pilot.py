import json
import math
import sys
import tempfile
import unittest
from unittest.mock import MagicMock,patch
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]))
from ml.naive_bayes import MultinomialNB,TfidfNB,features,rating_label
from ml.train import read_dataset,evaluate,evaluate_nested,_fold_partitions
from ml.inference import predict_feedback,model_status

class PilotModelTests(unittest.TestCase):
    def test_rating_derived_labels(self):
        self.assertEqual([rating_label(i) for i in range(1,6)],['negative','negative','neutral','positive','positive'])
        for value in [0,6,3.5,True]:
            with self.assertRaises(ValueError):rating_label(value)
    def test_multinomial_nb_learns_counts_and_scores_sum_to_one(self):
        model=MultinomialNB().fit(['dirty dirty pool','ordinary average stay','friendly friendly staff'],['negative','neutral','positive'])
        self.assertEqual(model.predict_one('dirty pool')['label'],'negative')
        self.assertEqual(model.predict_one('friendly staff')['label'],'positive')
        self.assertAlmostEqual(sum(model.predict_one('pool')['scores'].values()),1)
        restored=MultinomialNB.from_dict(json.loads(json.dumps(model.to_dict())))
        self.assertEqual(restored.predict_one('friendly staff'),model.predict_one('friendly staff'))
    def test_unseen_text_uses_priors_without_nan_or_fake_confidence(self):
        model=MultinomialNB().fit(['bad','fine','good','great'],['negative','neutral','positive','positive'])
        prediction=model.predict_one('unseen vocabulary')
        self.assertEqual(prediction['known_feature_occurrences'],0)
        self.assertTrue(all(math.isfinite(score) for score in prediction['scores'].values()))
        self.assertAlmostEqual(prediction['scores']['positive'],.5)
    def test_negation_and_taglish_are_retained(self):
        result=features('Hindi malinis ang pool, not clean!')
        self.assertIn('hindi malinis',result);self.assertIn('not clean',result)
    def test_oversampling_and_prior_adjustment_support_neutral_class(self):
        model=TfidfNB('char', class_prior_adjustment={'negative':1.0,'neutral':1.5,'positive':1.0}, neutral_oversample=3)
        model.fit(['okay place for 8 guests','clean and quiet villa','good staff and pool','dirty bathroom and bad smell','we stayed in villa 1','room was clean'], ['neutral','positive','positive','negative','neutral','positive'])
        self.assertTrue(model.predict_one('the villa was okay and a bit average')['label'] in {'neutral','positive','negative'})
        self.assertEqual(model.class_prior_adjustment['neutral'],1.5)
    def test_tfidf_configuration_survives_serialization(self):
        model=TfidfNB('char',char_ngram_range=(2,4),alpha=.5,
                      class_prior_adjustment={'neutral':2},neutral_oversample=2)
        model.fit(['dirty room','plain room','nice room'],['negative','neutral','positive'])
        restored=TfidfNB.from_dict(json.loads(json.dumps(model.to_dict())))
        self.assertEqual(restored.predict_one('plain room'),model.predict_one('plain room'))
        self.assertEqual(restored.char_ngram_range,(2,4))
        self.assertEqual(restored.alpha,.5)
    def test_grouped_nested_evaluation_keeps_duplicate_texts_together(self):
        records=[]
        for label,marker in [('negative','dirty'),('neutral','ordinary'),('positive','clean')]:
            for index in range(3):
                records.append({'text':f'{marker} example {index}','label':label,
                                'group':f'{label}-{index}'})
        records.append({'text':'dirty example 0','label':'negative','group':'duplicate-group'})
        partitions=_fold_partitions(records,seed=19)
        duplicate_folds={fold for fold,indices in enumerate(partitions)
                         if any(records[index]['text']=='dirty example 0' for index in indices)}
        self.assertEqual(len(duplicate_folds),1)
        candidates=[
            {'analyzer':'word','word_ngram_range':(1,1),'alpha':1,
             'class_prior_adjustment':{'neutral':1},'neutral_oversample':1},
            {'analyzer':'char','char_ngram_range':(3,5),'alpha':1,
             'class_prior_adjustment':{'neutral':1.5},'neutral_oversample':2},
        ]
        result=evaluate_nested(records,seed=19,configurations=candidates)
        self.assertEqual(len(result['outer_fold_sizes']),3)
        self.assertEqual(result['search_configurations'],2)
        self.assertEqual(len(result['neutral_oof_diagnostics']),3)
        self.assertEqual(sum(result['tuned']['per_class'][label]['support']
                             for label in ('negative','neutral','positive')),len(records))
    def test_actual_dataset_has_26_real_unique_reviews_and_evaluation_support(self):
        records=read_dataset(Path(__file__).parents[1]/'Guest_Feedback_No_Airbnb_Tenure.csv')
        self.assertEqual(len(records),26)
        evaluation=evaluate(records)
        self.assertEqual(sum(item['support'] for item in evaluation['model']['per_class'].values()),26)
        self.assertEqual(evaluation['model']['per_class']['negative']['support'],7)
        self.assertAlmostEqual(evaluation['majority_baseline']['accuracy'],17/26)
    def test_prediction_uses_comment_only_never_rating_or_private_note(self):
        first=predict_feedback({'id':'test','comments':'The rooms were clean and comfortable.','overall_rating':1,'private_note':'dirty terrible awful'})
        second=predict_feedback({'id':'test','comments':'The rooms were clean and comfortable.','overall_rating':5,'private_note':'great wonderful'})
        self.assertEqual(first,second);self.assertTrue(first['requires_human_review'])
        self.assertEqual(model_status()['training_reviews'],26)
        self.assertEqual(model_status()['training_unit'],'phrases')
    def test_conflicting_duplicate_rows_are_not_split_into_training_and_test(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'reviews.csv'
            path.write_text('Sentiment Label,Guest Feedback (Verbatim)\nnegative,The stay was poor.\npositive,The stay was poor.\n')
            with self.assertRaises(ValueError):read_dataset(path)

    def test_explicit_text_label_overrides_stars_and_missing_label_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'reviews.csv'
            path.write_text('Star Rating,Sentiment Label,Guest Feedback (Verbatim)\n5,negative,The service was terrible.\n')
            self.assertEqual(read_dataset(path)[0]['label'],'negative')
            path.write_text('Star Rating,Guest Feedback (Verbatim)\n5,The service was terrible.\n')
            with self.assertRaises(ValueError):read_dataset(path)

    def test_model_absence_reports_unavailable_instead_of_fake_results(self):
        with patch.dict('os.environ',{'FEEDBACK_MODEL_PATH':'/missing/sentiment-model.json'}):
            self.assertFalse(model_status()['available'])
    def test_model_status_reads_nested_grouped_evaluation(self):
        artifact={'version':'test','training_rows':9,'training_reviews':9,
                  'class_distribution':{'negative':3,'neutral':3,'positive':3},
                  'label_source':'test labels',
                  'evaluation':{'tuned':{'accuracy':.7,'macro_f1':.6},
                                'baseline':{'accuracy':.5},
                                'majority_baseline':{'accuracy':.3}}}
        with patch('ml.inference.load_model',return_value=(artifact,None)):
            status=model_status()
        self.assertTrue(status['available'])
        self.assertEqual(status['cross_validation_accuracy'],.7)
        self.assertEqual(status['baseline_accuracy'],.5)
    def test_candidate_model_inference_smoke_for_approved_examples(self):
        candidate=Path(__file__).parents[1]/'ml'/'candidates'/'20261031_human_approved_232'/'sentiment_model.json'
        with patch.dict('os.environ',{'FEEDBACK_MODEL_PATH':str(candidate)}):
            negative=predict_feedback({'id':'negative','comments':'Napaka init sa 2nd floor, para kang nasa oven.'})
            positive=predict_feedback({'id':'positive','comments':'ganda din ng area at super linis at ang bango!'})
            neutral=predict_feedback({'id':'neutral','comments':'Villa 1'})
            ambiguous=predict_feedback({'id':'ambiguous','comments':'The Villa - Batangas was okay.'})
            empty=predict_feedback({'id':'empty','comments':''})
        self.assertEqual([negative['label'],positive['label'],neutral['label']],
                         ['negative','positive','neutral'])
        self.assertEqual(ambiguous['label'],'neutral')
        self.assertTrue(all(result['model_version'].startswith('pilot-phrase-tfidf-nb-')
                            for result in (negative,positive,neutral,ambiguous,empty)))
        self.assertEqual(empty['known_feature_occurrences'],0)
        self.assertIsNone(empty['label'])
    def test_storage_failure_does_not_claim_analysis_succeeded(self):
        from ml.inference import save_pilot_prediction
        client=MagicMock();client.table.return_value.update.return_value.eq.return_value.execute.side_effect=RuntimeError('Schema unavailable')
        self.assertFalse(save_pilot_prediction(client,{'id':'review','comments':'Clean and pleasant stay.'}))
    def test_unseen_vocabulary_is_saved_as_abstention_not_a_sentiment(self):
        from ml.inference import save_pilot_prediction
        client=MagicMock();client.table.return_value.update.return_value.eq.return_value.execute.return_value.data=[{'id':'review'}]
        self.assertTrue(save_pilot_prediction(client,{'id':'review','comments':'zzzxxyyqq'}))
        values=client.table.return_value.update.call_args.args[0]
        self.assertEqual(values['analysis_status'],'insufficient_vocabulary')
        self.assertIsNone(values['sentiment_label'])
