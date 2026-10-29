"""Minimal public review projection; never publish the admin feedback payload."""
from collections import Counter
from feedback_dates import exact_review_date
from feedback_policy import admin_feedback_projection


def public_reviews(records):
    reviews=[];seen=set()
    for row in sorted(records,key=lambda item:item.get('source')=='historical_dataset'):
        identity=str(row.get('id') or '')
        if not identity or identity in seen:continue
        rating=row.get('overall_rating')
        if type(rating) is not int or rating not in range(1,6):continue
        seen.add(identity)
        # Always scrub contact/booking details from comments, regardless of name display.
        safe=admin_feedback_projection({**row,'hide_identity':True})
        name=str(row.get('guest_name') or '').strip()
        hidden=row.get('source')=='historical_dataset' or row.get('hide_identity') is not False
        author='Anonymous' if hidden or name.casefold() in ('','anonymous','anonymous guest') else name
        reviews.append({'id':identity,'rating':rating,'comment':safe['comments'],
                        'author':author,
                        'date':exact_review_date(row) or (row.get('review_date_label') if row.get('source')=='historical_dataset' else None)})
    counts=Counter(row['rating'] for row in reviews)
    return {'reviews':reviews,'count':len(reviews),
            'average':round(sum(row['rating'] for row in reviews)/len(reviews),1) if reviews else None,
            'distribution':{str(rating):counts[rating] for rating in range(1,6)}}
