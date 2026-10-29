"""Read the supplied historical dataset for authenticated admin display only."""
import csv
import hashlib
from datetime import date
from pathlib import Path

from feedback_policy import admin_feedback_projection
from .naive_bayes import rating_label

DATASET_PATH = Path(__file__).parents[1] / 'Guest_Feedback_No_Airbnb_Tenure.csv'


def historical_reviews(path=DATASET_PATH):
    records = []
    with Path(path).open(encoding='utf-8-sig', newline='') as handle:
        reader = csv.DictReader(handle)
        required = {'Star Rating', 'Guest Feedback (Verbatim)'}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError('Historical dataset requires rating and comment columns.')
        for row in reader:
            raw_date=str(row.get('Exact Review Date') or '').strip()
            exact_date=date.fromisoformat(raw_date).isoformat() if raw_date else None
            rating = int(row['Star Rating'])
            rating_label(row['Star Rating'])
            comment = str(row['Guest Feedback (Verbatim)'] or '').strip()
            if not comment:
                raise ValueError('Historical dataset contains an empty comment.')
            projected = admin_feedback_projection({
                'comments': comment, 'guest_name': row.get('Guest Name'),
                'hide_identity': True,
            })
            records.append({
                'id': 'historical-' + hashlib.sha256(f"{rating}:{row.get('Review Date', '')}:{' '.join(comment.casefold().split())}".encode()).hexdigest()[:20],
                'source': 'historical_dataset', 'hide_identity': True,
                'guest_name': 'Anonymous guest', 'overall_rating': rating,
                'comments': projected['comments'],
                'review_date': exact_date,
                'review_date_label': row.get('Review Date') or 'Date unavailable',
                'text_sentiment_label': row.get('Sentiment Label') or None,
                'annotation_status': row.get('Annotation Status') or None,
            })
    return records
