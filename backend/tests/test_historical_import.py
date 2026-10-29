import tempfile
import unittest
from pathlib import Path
from ml.historical_reviews import historical_reviews


class HistoricalImportTests(unittest.TestCase):
    def test_keys_survive_row_reordering_and_no_booking_is_fabricated(self):
        header = 'Guest Name,Star Rating,Review Date,Guest Feedback (Verbatim)\n'
        first = 'Alex,5,August 2026,We enjoyed our relaxing stay here\n'
        second = 'Sam,2,July 2026,The service needs much more improvement\n'
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'reviews.csv'
            path.write_text(header + first + second)
            original = historical_reviews(path)
            path.write_text(header + second + first)
            reordered = historical_reviews(path)
        self.assertEqual(original[0]['id'], reordered[1]['id'])
        self.assertTrue(all(row['hide_identity'] for row in original))
        self.assertTrue(all('booking_id' not in row for row in original))
        self.assertIsNone(original[1]['text_sentiment_label'])

    def test_invalid_rating_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'reviews.csv'
            path.write_text('Star Rating,Guest Feedback (Verbatim)\n6,Invalid rating review\n')
            with self.assertRaises(ValueError):
                historical_reviews(path)

    def test_reimport_keeps_csv_anonymous_and_preserves_known_exact_date(self):
        from unittest.mock import MagicMock, patch
        from types import SimpleNamespace
        from ml.import_historical import import_reviews
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'reviews.csv'
            path.write_text('Guest Name,Star Rating,Review Date,Guest Feedback (Verbatim)\nAlex,5,August 2026,A lovely and comfortable stay\n')
            key=historical_reviews(path)[0]['id']
            client=MagicMock()
            client.table.return_value.select.return_value.eq.return_value.execute.return_value=SimpleNamespace(data=[{
                'historical_import_key':key,'guest_name':'Alex Reyes','hide_identity':False,'review_date':'2026-08-17'}])
            with patch('admin.service_client',return_value=client):import_reviews(path)
            saved=client.table.return_value.upsert.call_args.args[0][0]
            self.assertEqual(saved['guest_name'],'Anonymous guest')
            self.assertTrue(saved['hide_identity'])
            self.assertEqual(saved['review_date'],'2026-08-17')
