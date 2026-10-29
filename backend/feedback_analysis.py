"""Admin-only orchestration for feedback summaries and recommendation drafts."""
from datetime import date
from typing import Literal
from pydantic import BaseModel, Field
from ml.complaints import report
from ml.inference import model_status


class AnalysisFilters(BaseModel):
    source: Literal['all', 'verified', 'historical'] = 'all'
    villa: str = Field(default='', max_length=160)
    rating: int | None = Field(default=None, ge=1, le=5)
    start: date | None = None
    end: date | None = None


def records_for(client, filters):
    if filters.start and filters.end and filters.start > filters.end:
        raise ValueError('Start date must be before the end date.')
    records = []
    if filters.source != 'historical':
        records.extend(client.rpc('list_verified_guest_feedback', {}).execute().data or [])
    if filters.source != 'verified':
        records.extend(client.table('guest_feedback').select('*').eq('source','historical_dataset').order('created_at', desc=True).limit(2000).execute().data or [])
    result = []
    from datetime import datetime
    for row in records:
        if filters.villa and row.get('villa_name') != filters.villa: continue
        if filters.rating and row.get('overall_rating') != filters.rating: continue
        if filters.start or filters.end:
            try:
                # Historical source only records month/year: compare by month,
                # rather than claiming a precise day of submission.
                period = datetime.strptime(row['review_date_label'],'%B %Y').strftime('%Y-%m') if row.get('source') == 'historical_dataset' else str(row.get('created_at') or '')[:7]
                if len(period) != 7: continue
                if filters.start and period < filters.start.isoformat()[:7]: continue
                if filters.end and period > filters.end.isoformat()[:7]: continue
            except (ValueError,KeyError,TypeError): continue
        result.append(row)
    return result


def build_report(client, filters):
    metadata = model_status()
    if not metadata['available']: raise ValueError('The sentiment model is unavailable. Train or restore it first.')
    result = report(records_for(client, filters))
    # Include model version in evidence signature to invalidate stale drafts.
    import hashlib
    result['summary']['fingerprint'] = hashlib.sha256((result['summary']['fingerprint']+metadata['version']).encode()).hexdigest()
    return {**result, 'model': metadata, 'filters': filters.model_dump(mode='json')}
