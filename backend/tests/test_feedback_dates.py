import unittest
from feedback_dates import exact_review_date
from public_feedback import public_reviews


class FeedbackDateTests(unittest.TestCase):
    def test_historical_month_does_not_become_import_date(self):
        row={'source':'historical_dataset','review_date_label':'August 2026','created_at':'2026-10-22T00:00:00Z'}
        self.assertIsNone(exact_review_date(row))
        self.assertEqual(exact_review_date({**row,'review_date':'2026-08-17'}),'2026-08-17')

    def test_verified_review_uses_philippine_submission_date(self):
        self.assertEqual(exact_review_date({'created_at':'2026-10-21T17:00:00Z'}),'2026-10-22')

    def test_known_full_historical_date_is_preserved(self):
        self.assertEqual(exact_review_date({'source':'historical_dataset','review_date_label':'August 17, 2026'}),'2026-08-17')

    def test_public_date_and_name_come_from_saved_review(self):
        record={'id':'review','overall_rating':5,'source':'historical_dataset','review_date_label':'August 2026',
                'review_date':'2026-08-17','guest_name':'Alex Reyes','hide_identity':False,'comments':'Very comfortable stay.'}
        result=public_reviews([record])['reviews'][0]
        self.assertEqual(result['date'],'2026-08-17')
        self.assertEqual(result['author'],'Anonymous')
        self.assertEqual(public_reviews([{**record,'hide_identity':True}])['reviews'][0]['author'],'Anonymous')
