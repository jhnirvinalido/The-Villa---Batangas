"""Development checks, explicitly not independent human validation."""
import csv
import json
from collections import Counter
from pathlib import Path
from .complaints import categories
from .preprocessing import normalize

ROOT = Path(__file__).parent


def evaluate():
    with (ROOT/'datasets/noisy_text_tests.csv').open() as handle:
        fixtures = list(csv.DictReader(handle))
    noisy = [{'original': row['Original'], 'normalization_correct': normalize(row['Original'])==row['Expected Normalized'],
              'categories_correct': set(categories(row['Original']))==set(filter(None,row['Expected Categories'].split(';')))} for row in fixtures]
    with (ROOT/'datasets/sentiment_phrases.csv').open() as handle:
        phrases = list(csv.DictReader(handle))
    tp=fp=fn=0; expected_counts=Counter(); detected_counts=Counter(); seen_expected=set(); seen_detected=set()
    for row in phrases:
        expected=set(filter(None,row['Categories'].split(';')));detected=set(categories(row['Guest Feedback (Verbatim)']))
        tp+=len(expected & detected);fp+=len(detected-expected);fn+=len(expected-detected)
        if row['Sentiment Label']=='negative':
            seen_expected.update((row['Review ID'],key) for key in expected)
            seen_detected.update((row['Review ID'],key) for key in detected)
    expected_counts.update(key for _,key in seen_expected);detected_counts.update(key for _,key in seen_detected)
    precision=tp/(tp+fp) if tp+fp else 0;recall=tp/(tp+fn) if tp+fn else 0
    return {'status':'development_only_provisional_annotations_not_independent_test',
            'noisy_fixtures':{'count':len(noisy),'normalization_correct':sum(r['normalization_correct'] for r in noisy),'category_correct':sum(r['categories_correct'] for r in noisy),'results':noisy},
            'category_matching':{'precision':precision,'recall':recall,'micro_f1':2*precision*recall/(precision+recall) if precision+recall else 0,'phrase_count':len(phrases)},
            'distinct_review_category_count_check_with_reference_sentiment':[
                {'category':key,'reference_count':expected_counts[key],'detected_count':detected_counts[key],'absolute_error':abs(expected_counts[key]-detected_counts[key])}
                for key in sorted(set(expected_counts)|set(detected_counts))],
            'limitations':['Synthetic noisy fixtures are implementation smoke checks, not a measure of real-world Taglish generalization.',
                           'Category annotations are provisional and selected spans are not exhaustive full-review complaint ground truth.',
                           'Category count check uses reference sentiment to isolate vocabulary errors; it is not end-to-end deployed complaint accuracy.',
                           'Obtain independently human-reviewed holdout phrases and full reviews before final evaluation.',
                           'Evaluate Gemini separately for relevance, actionability, evidence support, and unsupported claims.']}


if __name__=='__main__':
    result=evaluate()
    (ROOT/'artifacts/pipeline_evaluation.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({key:value for key,value in result.items() if key not in {'noisy_fixtures','distinct_review_category_count_check_with_reference_sentiment'}},indent=2))
