"""Compare original-data and expanded-data models on identical grouped test folds."""
import argparse
import json
from pathlib import Path
from .train import read_dataset, evaluate, metrics
from .naive_bayes import TfidfNB, LABELS


def compare(original, expanded):
    original = read_dataset(original)
    records = read_dataset(expanded)
    original_groups = {r['group'] for r in original}
    evaluation = evaluate(records, 42)
    old_predictions = [None] * len(records)
    new_predictions = [None] * len(records)
    for fold in evaluation['fold_sizes']:
        held_out = set(fold['test_groups'])
        old_training = [r for r in original if r['group'] not in held_out]
        new_training = [r for r in records if r['group'] not in held_out]
        if set(r['label'] for r in old_training) != set(LABELS):
            raise ValueError('Original-data fold lacks a class; cannot make a fair comparison.')
        old = TfidfNB('word').fit([r['text'] for r in old_training], [r['label'] for r in old_training])
        new = TfidfNB('word').fit([r['text'] for r in new_training], [r['label'] for r in new_training])
        for i, row in enumerate(records):
            if row['group'] in held_out:
                old_predictions[i] = old.predict_one(row['text'])['label']
                new_predictions[i] = new.predict_one(row['text'])['label']
    result = {'status': 'experimental_ai_labels_not_independent_human_validation',
              'method': 'Same 3 grouped folds, word TF-IDF Naive Bayes; original-data baseline excludes every held-out original review group.',
              'original_phrases': len(original), 'combined_phrases': len(records),
              'combined_review_groups': len({r['group'] for r in records}),
              'original_review_groups': len(original_groups), 'results': {}}
    for name, selected in [('all', list(range(len(records)))),
                           ('original_reviews', [i for i, r in enumerate(records) if r['group'] in original_groups]),
                           ('new_reviews', [i for i, r in enumerate(records) if r['group'] not in original_groups])]:
        actual = [records[i]['label'] for i in selected]
        result['results'][name] = {'phrases': len(selected),
             'original_data_model': metrics(actual, [old_predictions[i] for i in selected]),
             'candidate': metrics(actual, [new_predictions[i] for i in selected])}
    return result

if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--original',type=Path,required=True)
    parser.add_argument('--expanded',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    report=compare(args.original,args.expanded)
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({name:{k:{metric:round(value[metric],4) for metric in ('accuracy','macro_f1')} for k,value in scores.items() if isinstance(value,dict)} for name,scores in report['results'].items()},indent=2))
