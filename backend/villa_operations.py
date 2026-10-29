"""Connect open villa work to catalog and booking availability."""
from datetime import datetime
from fastapi import HTTPException

SOURCE = 'manual-maintenance-request'


def maintenance_details(row):
    for event in reversed(row.get('status_history') or []):
        if isinstance(event, dict) and isinstance(event.get('maintenance'), dict):
            return event['maintenance']
    return {}


def operation_summary(client):
    try:
        records = []
        offset = 0
        while True:
            batch = client.table('admin_tasks').select('id,status,status_history,approved_at,updated_at,due_date').eq('source', SOURCE).order('id').range(offset, offset + 499).execute().data or []
            records.extend(batch)
            if len(batch) < 500:
                break
            offset += len(batch)
    except Exception:
        raise HTTPException(status_code=503, detail='Villa operational availability could not be checked. Please retry.') from None
    result = {}
    for row in records:
        meta = maintenance_details(row)
        villa_id = meta.get('villaId')
        if not villa_id:
            continue
        summary = result.setdefault(villa_id, {'open': 0, 'blocking': 0, 'inspections': 0, 'forVerification': 0, 'hasHistory': True})
        if row['status'] not in {'Completed', 'Cancelled'}:
            summary['open'] += 1
            summary['blocking'] += bool(meta.get('blocksBooking'))
            if meta.get('blocksBooking'):
                # Each request reserves its scheduled calendar date. Multiple
                # requests can cover several dates without blocking every day.
                scheduled = str(row.get('due_date') or '')[:10]
                if scheduled:
                    summary.setdefault('blockingDates', []).append(scheduled)
                else:
                    summary['undatedBlocking'] = True
            summary['inspections'] += meta.get('kind') == 'Inspection'
            summary['forVerification'] += row['status'] == 'Pending Review'
        elif meta.get('blocksBooking') and len(str(meta.get('verificationNote') or '').strip()) >= 5:
            released = row.get('approved_at') or row.get('updated_at')
            if released and (not summary.get('_releasedAt') or datetime.fromisoformat(str(released).replace('Z', '+00:00')) > datetime.fromisoformat(str(summary['_releasedAt']).replace('Z', '+00:00'))):
                summary['_releasedAt'] = released
    return result


def apply_operational_status(catalog, client, summaries=None):
    summaries = operation_summary(client) if summaries is None else summaries
    for villa in catalog:
        summary = dict(summaries.get(villa['id'], {'open': 0, 'blocking': 0, 'inspections': 0, 'forVerification': 0, 'hasHistory': False}))
        released = summary.pop('_releasedAt', None)
        villa['manual_status'] = villa['status']
        villa['operations'] = summary
        if summary['blocking']:
            villa['status'] = 'Under Maintenance'
        elif released and villa['status'] == 'Under Maintenance':
            released_at = datetime.fromisoformat(str(released).replace('Z', '+00:00'))
            changed_at = datetime.fromisoformat(str(villa['updated_at']).replace('Z', '+00:00')) if villa.get('updated_at') else None
            if changed_at is None or released_at >= changed_at:
                villa['status'] = 'Available'
    return catalog
