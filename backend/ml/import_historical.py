"""Import the original review CSV into guest_feedback using backend credentials."""
import argparse
from pathlib import Path
from .historical_reviews import DATASET_PATH, historical_reviews


def import_reviews(path):
    # Validate every CSV row before writing; never print database credentials.
    records = historical_reviews(path)
    from admin import service_client
    client = service_client()
    existing = client.table('guest_feedback').select('historical_import_key,guest_name,hide_identity,review_date').eq('source','historical_dataset').execute().data or []
    identities = {item['historical_import_key']:item for item in existing}
    payload = [{
        'source': 'historical_dataset', 'historical_import_key': row['id'],
        'review_date_label': row['review_date_label'],
        'review_date':row['review_date'] or identities.get(row['id'],{}).get('review_date'),
        'rating_derived_label': None,
        'text_sentiment_label': row['text_sentiment_label'],
        'annotation_status': row['annotation_status'],
        'guest_name':'Anonymous guest',
        'hide_identity':True,
        'overall_rating': row['overall_rating'], 'comments': row['comments'],
        'analysis_status': 'historical_training_data',
    } for row in records]
    if payload:
        client.table('guest_feedback').upsert(
            payload, on_conflict='historical_import_key', ignore_duplicates=False,
        ).execute()
    print(f'Import complete: {len(payload)} source reviews processed; existing import keys updated.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--data', type=Path, default=DATASET_PATH)
    args = parser.parse_args()
    if not args.data.is_file():
        parser.error(f'CSV file not found: {args.data}')
    import_reviews(args.data)
