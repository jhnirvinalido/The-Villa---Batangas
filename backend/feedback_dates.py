"""Resolve actual review dates without substituting an historical import date."""
from datetime import date, datetime, timedelta, timezone

MANILA = timezone(timedelta(hours=8))


def exact_review_date(row):
    explicit = str(row.get('review_date') or '').strip()
    if explicit:
        try:return date.fromisoformat(explicit).isoformat()
        except ValueError:pass
    if row.get('source') == 'historical_dataset':
        # Older imported rows may already contain an exact date as their label.
        label = str(row.get('review_date_label') or '').strip()
        for pattern in ('%Y-%m-%d','%B %d, %Y','%d %B %Y'):
            try:return datetime.strptime(label,pattern).date().isoformat()
            except ValueError:pass
        return None
    created = str(row.get('created_at') or '').strip()
    if not created:return None
    try:
        timestamp=datetime.fromisoformat(created.replace('Z','+00:00'))
        if timestamp.tzinfo is None:timestamp=timestamp.replace(tzinfo=timezone.utc)
        return timestamp.astimezone(MANILA).date().isoformat()
    except ValueError:return None
