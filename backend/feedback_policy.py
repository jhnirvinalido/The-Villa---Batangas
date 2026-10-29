"""Pure validation and privacy rules for the existing guest-feedback workflow."""
import re
from decimal import Decimal, InvalidOperation

CLOSED = {'completed', 'checked out', 'checked-out', 'checked_out'}
INVALID = {'cancelled', 'canceled', 'refunded', 'partially refunded', 'partially_refunded', 'invalid', 'invalidated', 'void', 'voided'}

def money(value):
    try:
        result = Decimal(str(value or 0))
        return result if result.is_finite() else Decimal('0')
    except (ValueError, InvalidOperation):
        return Decimal('0')

def eligible_stay(booking, settled_amount):
    states = {str(booking.get(key) or '').strip().lower() for key in ('booking_status','stay_status','payment_status')}
    return bool(states & CLOSED) and not bool(states & INVALID) and money(booking.get('total_amount')) > 0 and money(booking.get('balance_amount')) <= Decimal('0.01') and money(booking.get('amount_paid')) + Decimal('0.01') >= money(booking.get('total_amount')) and money(settled_amount) + Decimal('0.01') >= money(booking.get('total_amount')) and money(booking.get('refunded_amount')) == 0

def meaningful_comments(value):
    text = str(value or '').strip()
    if len(text) < 20 or len(text) > 3000 or len(re.findall(r'[^\W\d_]+',text,flags=re.UNICODE)) < 4 or len(set(text.casefold()) - set(' \t\r\n.!?')) < 5:
        raise ValueError('Please write at least 20 characters and four words describing your stay.')
    return text

def admin_feedback_projection(row):
    # Whitelist fields: no private note, token, booking association, or phone leaks.
    allowed = ('review_date','source','review_date_label','text_sentiment_label','annotation_status','id','villa_name','overall_rating','cleanliness_rating','service_rating','villa_rating','value_rating','would_recommend','created_at','analysis_status','sentiment_label','sentiment_model_version','sentiment_analyzed_at')
    result = {key:row.get(key) for key in allowed}
    hidden = row.get('source') == 'historical_dataset' or bool(row.get('hide_identity'))
    comments = str(row.get('comments') or '')
    if hidden:
        for key in ('guest_name','guest_email','guest_phone','booking_code','booking_id'):
            value = str(row.get(key) or '').strip()
            if value:
                comments = re.sub(re.escape(value),'[identity hidden]',comments,flags=re.IGNORECASE)
        for part in str(row.get('guest_name') or '').split():
            if len(part) > 1:
                comments = re.sub(r'\b'+re.escape(part)+r'\b','[name hidden]',comments,flags=re.IGNORECASE)
        comments = re.sub(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}', '[email hidden]',comments)
        comments = re.sub(r'(?<!\w)(?:\+?\d[\d ()-]{7,}\d)(?!\w)', '[number hidden]',comments)
    result.update(hide_identity=hidden, guest_name='Anonymous guest' if hidden else row.get('guest_name'), comments=comments)
    if not hidden:
        result['booking_code'] = row.get('booking_code')
    return result

def analysis_input(row):
    """Privacy-safe classifier input. Never include identity, tokens, or private notes."""
    safe = admin_feedback_projection({**row,'hide_identity':True})
    return {'feedback_id':row['id'], 'text':safe['comments'], 'ratings':{key:row.get(key) for key in ('overall_rating','cleanliness_rating','service_rating','villa_rating','value_rating')}}
