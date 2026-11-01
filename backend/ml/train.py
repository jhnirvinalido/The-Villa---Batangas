"""Train sentiment from explicit text annotations; never infer labels from stars."""
import argparse
import csv
import hashlib
import json
import random
import re
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path
from .naive_bayes import LABELS, TfidfNB
from .preprocessing import normalize
from feedback_policy import admin_feedback_projection

HEADERS={'Sentiment Label','Guest Feedback (Verbatim)'}
BASELINE_CONFIG={
    'analyzer':'word','word_ngram_range':(1,2),'char_ngram_range':(3,5),
    'alpha':1.0,'class_prior_adjustment':{'neutral':1.0},'neutral_oversample':1,
}

def _text_identity(text):
    return re.sub(r'\s+',' ',normalize(text)).strip()


def read_dataset(path):
    records=[];seen={}
    with Path(path).open(encoding='utf-8-sig',newline='') as handle:
        reader=csv.DictReader(handle)
        if not HEADERS.issubset(reader.fieldnames or []):raise ValueError('CSV requires explicit Sentiment Label and Guest Feedback (Verbatim) columns; star ratings are never sentiment labels.')
        for number,row in enumerate(reader,2):
            text=str(row['Guest Feedback (Verbatim)'] or '').strip()
            if not text:raise ValueError(f'Row {number} has no comment.')
            label=str(row['Sentiment Label'] or '').strip().lower()
            if label not in LABELS:raise ValueError(f'Row {number} requires a positive, neutral, or negative text annotation.')
            # Remove explicit known names/contact details, but keep original CSV unchanged.
            text=admin_feedback_projection({'comments':text,'guest_name':row.get('Guest Name'),'hide_identity':True})['comments']
            identity=_text_identity(text)
            if identity in seen:
                if seen[identity]!=label:raise ValueError(f'Conflicting labels on duplicate review at row {number}.')
                continue
            seen[identity]=label;records.append({
                'text':text,'label':label,
                'group':row.get('Guest Group') or row.get('Review ID') or row.get('Guest Name') or str(number),
                'review_id':row.get('Review ID') or str(number),
                'annotation_status':row.get('Annotation Status',''),
            })
    return records

def metrics(actual,predicted):
    matrix={label:{other:0 for other in LABELS} for label in LABELS}
    for truth,pred in zip(actual,predicted):matrix[truth][pred]+=1
    per_class={}
    for label in LABELS:
        tp=matrix[label][label];support=sum(matrix[label].values());predicted_count=sum(matrix[other][label] for other in LABELS)
        precision=tp/predicted_count if predicted_count else 0;recall=tp/support if support else 0
        per_class[label]={'precision':precision,'recall':recall,'f1':2*precision*recall/(precision+recall) if precision+recall else 0,'support':support}
    return {'accuracy':sum(a==b for a,b in zip(actual,predicted))/len(actual),'macro_f1':sum(per_class[label]['f1'] for label in LABELS)/len(LABELS),'per_class':per_class,'confusion_matrix':matrix}

def _group_indices(records):
    """Keep source groups and duplicate normalized text in the same partition."""
    parents=list(range(len(records)))

    def find(index):
        while parents[index]!=index:
            parents[index]=parents[parents[index]]
            index=parents[index]
        return index

    def union(first,second):
        first=find(first);second=find(second)
        if first!=second:parents[second]=first

    owners={}
    for index,row in enumerate(records):
        identity=_text_identity(row['text'])
        keys=(('group',str(row.get('group',index))),('text',identity))
        for key in keys:
            if key in owners:union(index,owners[key])
            else:owners[key]=index
    groups={}
    for index in range(len(records)):groups.setdefault(find(index),[]).append(index)
    return list(groups.values())


def _fold_partitions(records,seed=42,max_folds=3,min_training_groups=1):
    groups=_group_indices(records)
    group_support={label:sum(any(records[i]['label']==label for i in group) for group in groups)
                   for label in LABELS}
    folds=min(max_folds,min(group_support.values()))
    if folds<2:raise ValueError('At least two independent review groups per class are required.')
    rng=random.Random(seed);partitions=None
    for _ in range(1000):
        items=list(groups);rng.shuffle(items)
        candidate=[[] for _ in range(folds)]
        for index,group in enumerate(items):candidate[index%folds].extend(group)
        valid=True
        for test in candidate:
            test_set=set(test)
            training_groups=[group for group in groups if not set(group).issubset(test_set)]
            if any(not any(records[i]['label']==label for group in training_groups for i in group)
                   for label in LABELS):
                valid=False;break
            if any(sum(any(records[i]['label']==label for i in group) for group in training_groups)
                   < min_training_groups for label in LABELS):
                valid=False;break
        if valid:
            partitions=candidate;break
    if partitions is None:raise ValueError('Unable to construct grouped folds with all classes in training.')
    return partitions


def _make_model(config):
    return TfidfNB(
        config['analyzer'],
        word_ngram_range=tuple(config.get('word_ngram_range',(1,2))),
        char_ngram_range=tuple(config.get('char_ngram_range',(3,5))),
        alpha=config.get('alpha',1.0),
        class_prior_adjustment=config.get('class_prior_adjustment'),
        neutral_oversample=config.get('neutral_oversample',1),
    )


def _parameter_grid():
    features=[
        {'analyzer':'word','word_ngram_range':(1,1)},
        {'analyzer':'word','word_ngram_range':(1,2)},
        {'analyzer':'word','word_ngram_range':(1,3)},
        {'analyzer':'char','char_ngram_range':(3,5)},
        {'analyzer':'char','char_ngram_range':(2,5)},
    ]
    return [
        {**feature,'alpha':alpha,'class_prior_adjustment':{'neutral':prior},
         'neutral_oversample':oversample}
        for feature in features
        for alpha in (0.25,1.0,2.0)
        for prior in (1.0,1.5,2.5)
        for oversample in (1,2,3)
    ]


def _select_configuration(records,seed=42,configurations=None):
    configurations=configurations or _parameter_grid()
    partitions=_fold_partitions(records,seed)
    actual=[row['label'] for row in records]
    predictions=[ [None]*len(records) for _ in configurations]
    feature_groups={}
    for config_index,config in enumerate(configurations):
        key=(config['analyzer'],tuple(config.get('word_ngram_range',(1,2))),
             tuple(config.get('char_ngram_range',(3,5))))
        feature_groups.setdefault(key,[]).append((config_index,config))
    for test in partitions:
        test_set=set(test)
        training=[row for index,row in enumerate(records) if index not in test_set]
        for related_configs in feature_groups.values():
            model=_make_model(related_configs[0][1]).fit(
                [row['text'] for row in training],[row['label'] for row in training])
            for config_index,config in related_configs:
                model._set_parameters(config.get('alpha',1.0),
                                      config.get('class_prior_adjustment'),
                                      config.get('neutral_oversample',1))
                for index in test:
                    predictions[config_index][index]=model.predict_one(records[index]['text'])['label']
    best=None
    for config_index,config in enumerate(configurations):
        score=metrics(actual,predictions[config_index])
        rank=(score['macro_f1'],score['per_class']['neutral']['recall'],score['accuracy'])
        if best is None or rank>best[0]:
            best=(rank,config,score)
    return best[1],best[2]


def evaluate(records,seed=42,analyzer='word'):
    config={**BASELINE_CONFIG,'analyzer':analyzer}
    predictions=[None]*len(records);majority_predictions=[None]*len(records);sizes=[]
    partitions=_fold_partitions(records,seed)
    for test in partitions:
        test_set=set(test)
        training=[row for index,row in enumerate(records) if index not in test_set]
        model=_make_model(config).fit([row['text'] for row in training],
                                      [row['label'] for row in training])
        majority=Counter(row['label'] for row in training).most_common(1)[0][0]
        for index in test:
            predictions[index]=model.predict_one(records[index]['text'])['label']
            majority_predictions[index]=majority
        sizes.append({'train':len(training),'test':len(test),
                      'test_groups':sorted(set(records[index].get('group',str(index)) for index in test))})
    actual=[row['label'] for row in records]
    return {
        'method':f'{len(partitions)}-fold grouped out-of-fold evaluation',
        'seed':seed,'analyzer':analyzer,'configuration':config,'fold_sizes':sizes,
        'model':metrics(actual,predictions),
        'majority_baseline':metrics(actual,majority_predictions),
    }


def evaluate_nested(records,seed=42,configurations=None):
    """Estimate tuned performance using grouped outer folds and inner-only selection."""
    configurations=configurations or _parameter_grid()
    outer_partitions=_fold_partitions(records,seed,min_training_groups=2)
    actual=[row['label'] for row in records]
    baseline_predictions=[None]*len(records);tuned_predictions=[None]*len(records)
    majority_predictions=[None]*len(records)
    selected_by_fold=[];fold_sizes=[];neutral_diagnostics={}
    for fold_number,test in enumerate(outer_partitions):
        test_set=set(test)
        training=[row for index,row in enumerate(records) if index not in test_set]
        selected,_=_select_configuration(training,seed+fold_number+1,configurations)
        baseline=_make_model(BASELINE_CONFIG).fit(
            [row['text'] for row in training],[row['label'] for row in training])
        tuned=_make_model(selected).fit(
            [row['text'] for row in training],[row['label'] for row in training])
        majority=Counter(row['label'] for row in training).most_common(1)[0][0]
        for index in test:
            text=records[index]['text']
            baseline_prediction=baseline.predict_one(text)
            tuned_prediction=tuned.predict_one(text)
            baseline_predictions[index]=baseline_prediction['label']
            tuned_predictions[index]=tuned_prediction['label']
            majority_predictions[index]=majority
            if records[index]['label']=='neutral':
                neutral_diagnostics[index]={
                    'review_id':records[index].get('review_id'),
                    'group':records[index].get('group'),
                    'text':text,
                    'fold':fold_number+1,
                    'baseline_prediction':baseline_prediction['label'],
                    'baseline_scores':baseline_prediction['scores'],
                    'baseline_known_features':baseline_prediction['known_feature_occurrences'],
                    'tuned_prediction':tuned_prediction['label'],
                    'tuned_scores':tuned_prediction['scores'],
                    'tuned_known_features':tuned_prediction['known_feature_occurrences'],
                    'selected_configuration':selected,
                }
        selected_by_fold.append(selected)
        fold_sizes.append({'train':len(training),'test':len(test),
                           'test_groups':sorted(set(records[index].get('group',str(index))
                                                    for index in test))})
    deployment_config,inner_score=_select_configuration(records,seed+10000,configurations)
    neutral_indices=[index for index,row in enumerate(records) if row['label']=='neutral']
    neutral_predictions=[neutral_diagnostics[index] for index in neutral_indices]
    return {
        'method':f'{len(outer_partitions)}-fold nested grouped CV; '
                 'configuration selection uses inner grouped CV only',
        'seed':seed,'outer_fold_sizes':fold_sizes,
        'baseline':metrics(actual,baseline_predictions),
        'tuned':metrics(actual,tuned_predictions),
        'majority_baseline':metrics(actual,majority_predictions),
        'selected_configuration_by_outer_fold':selected_by_fold,
        'neutral_oof_diagnostics':[neutral_diagnostics[index]
                                   for index,row in enumerate(records)
                                   if row['label']=='neutral'],
        'neutral_oof_summary':{
            'support':len(neutral_indices),
            'review_groups':len({records[index].get('group',str(index))
                                 for index in neutral_indices}),
            'baseline_predictions':dict(Counter(item['baseline_prediction']
                                                 for item in neutral_predictions)),
            'tuned_predictions':dict(Counter(item['tuned_prediction']
                                              for item in neutral_predictions)),
        },
        'deployment_configuration_selected_on_full_data':deployment_config,
        'full_data_inner_cv_score_for_selection_only':inner_score,
        'search_configurations':len(configurations),
        'selection_metric':'macro_f1; ties use neutral recall, then accuracy',
    }

def train(source,destination):
    source=Path(source);destination=Path(destination);destination.mkdir(parents=True,exist_ok=True)
    records=read_dataset(source)
    fingerprint=hashlib.sha256(source.read_bytes()).hexdigest()
    statuses=Counter(row['annotation_status'] for row in records if row['annotation_status'])
    approved_statuses={'human_approved','human-approved','adjudicated','adjudicated_approved'}
    label_source=('human-approved labels explicitly marked in annotation status'
                  if statuses and all(status.strip().lower() in approved_statuses for status in statuses)
                  else 'labels supplied in dataset; approval status must be independently verified')
    report={'dataset_file':source.name,'dataset_sha256':fingerprint,
      'dataset_rows':len(records),'review_groups':len(_group_indices(records)),
      'class_distribution':dict(Counter(row['label'] for row in records)),
      'empirical_class_priors':{label:sum(row['label']==label for row in records)/len(records)
                                for label in LABELS},
      'annotation_status_counts':dict(statuses),'label_source':label_source,
      'evaluation':evaluate(records,42),'nested_evaluation':evaluate_nested(records,42),
      'feature_comparison':{mode:evaluate(records,42,mode) for mode in ('word','char')},
      'limitations':['Pilot only; too few examples for a reliable general-purpose sentiment model.',
        'Nested grouped CV estimates model-selection performance against the supplied labels; it is not an independent external test or production-accuracy guarantee.',
        'Vocabulary and IDF are fit inside each training fold; review groups and duplicate normalized texts never cross partitions.',
        'Neutral oversampling is applied only to training-fold feature counts; no synthetic or evaluation examples are generated.',
        'Names, review dates, and ratings are not inference features.',
        'Clause extraction and vocabulary-based category matching require separate human evaluation.',
        'Posterior scores are uncalibrated; unknown vocabulary can fall back to class priors.']}
    version='pilot-phrase-tfidf-nb-'+fingerprint[:12]
    config=report['nested_evaluation']['deployment_configuration_selected_on_full_data']
    model=_make_model(config).fit([row['text'] for row in records],[row['label'] for row in records])
    artifact={'version':version,'created_at':datetime.now(timezone.utc).isoformat(),'dataset_sha256':fingerprint,
      'training_rows':len(records),'training_unit':'phrases','training_reviews':len(set(row['group'] for row in records)),
      'class_distribution':report['class_distribution'],'label_source':report['label_source'],'pilot':True,
      'algorithm':'Multinomial Naive Bayes over fold-fitted word or character TF-IDF; grouped nested validation',
      'selected_configuration':config,'evaluation':report['nested_evaluation'],'model':model.to_dict()}
    (destination/'sentiment_model.json').write_text(json.dumps(artifact,ensure_ascii=False,indent=2)+'\n')
    (destination/'evaluation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'reviews':len(records),'classes':report['class_distribution'],
      'nested_baseline_accuracy':report['nested_evaluation']['baseline']['accuracy'],
      'nested_tuned_accuracy':report['nested_evaluation']['tuned']['accuracy'],
      'nested_tuned_macro_f1':report['nested_evaluation']['tuned']['macro_f1'],
      'selected_configuration':config,'artifact':str(destination/'sentiment_model.json')},indent=2))
    return report

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--data',type=Path,default=Path(__file__).parent/'datasets'/'sentiment_phrases.csv');parser.add_argument('--output',type=Path,default=Path(__file__).parent/'artifacts');args=parser.parse_args();train(args.data,args.output)
