"""Rule-based category matching + Naive Bayes sentiment, never rating rules."""
import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from feedback_policy import analysis_input
from .preprocessing import VERSION, normalize, phrases

VOCABULARY = json.loads((Path(__file__).parent / 'categories.json').read_text())


def categories(text):
    normalized = normalize(text)
    result = [name for name, patterns in VOCABULARY['categories'].items()
              if any(re.search(pattern, normalized) for pattern in patterns)]
    # Pool cleanliness is more specific than general pool facilities.
    if 'Pool cleanliness' in result:
        result.remove('Pool heating and facilities')
    return result


def analyze_review(row, model=None):
    if model is None:
        from .inference import load_model
        _, model = load_model()
    safe = analysis_input(row)
    result = []
    for clause in phrases(safe['text']):
        prediction = model.predict_one(clause['normalized'])
        result.append({**clause, 'categories': categories(clause['normalized']),
                       'sentiment': prediction['label'] if prediction['known_feature_occurrences'] else None})
    return result


def report(records, model=None):
    if model is None:
        from .inference import load_model
        _, model = load_model()
    # One record counts once even if repeated in query results.
    records = list({str(row['id']): row for row in records}.values())
    counts = Counter(); evidence = defaultdict(list); analyses = {}; distribution = Counter()
    rating_distribution = {str(n): 0 for n in range(1, 6)}
    months = defaultdict(list); source_counts = Counter()
    for row in records:
        rating = row.get('overall_rating')
        if rating in range(1, 6):
            rating_distribution[str(rating)] += 1
            try:
                month = datetime.strptime(row['review_date_label'], '%B %Y').strftime('%Y-%m') if row.get('source') == 'historical_dataset' else str(row.get('created_at') or '')[:7]
                if re.fullmatch(r'\d{4}-\d{2}', month): months[month].append(rating)
            except (ValueError, KeyError, TypeError):
                pass
        source_counts[row.get('source') or 'verified_stay'] += 1
        clauses = analyze_review(row, model)
        analyses[str(row['id'])] = clauses
        distribution.update(item['sentiment'] or 'unclassified' for item in clauses)
        per_review = set()
        for item in clauses:
            if item['sentiment'] != 'negative': continue
            for category in item['categories']:
                per_review.add(category)
                if len(evidence[category]) < 3 and item['text'][:400] not in evidence[category]:
                    evidence[category].append(item['text'][:400])
        counts.update(per_review)
    total_ratings = sum(rating_distribution.values())
    summary = {'total_reviews': len(records), 'source_counts': dict(source_counts),
               'average_star_rating': round(sum(int(k)*v for k,v in rating_distribution.items())/total_ratings, 2) if total_ratings else None,
               'rating_distribution': rating_distribution, 'phrase_sentiments': dict(distribution),
               'rating_trends': [{'month': key, 'review_count': len(values), 'average': round(sum(values)/len(values), 2)} for key,values in sorted(months.items())],
               'top_complaints': [{'category': key, 'negative_review_count': count, 'evidence': evidence[key]} for key,count in sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))],
               'pipeline_version': VERSION + '/' + VOCABULARY['version'],
               'requires_human_review': True, 'coverage_note': 'Up to 2000 reviews per source; phrase extraction is limited to 80 clauses per review.'}
    fingerprint_input = {'summary': summary, 'reviews': sorted((str(r['id']), str(r.get('comments')), r.get('overall_rating')) for r in records)}
    summary['fingerprint'] = hashlib.sha256(json.dumps(fingerprint_input, sort_keys=True).encode()).hexdigest()
    return {'summary': summary, 'reviews': analyses}
