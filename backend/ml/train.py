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
from feedback_policy import admin_feedback_projection

HEADERS={'Sentiment Label','Guest Feedback (Verbatim)'}

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
            identity=re.sub(r'\s+',' ',text.casefold()).strip()
            if identity in seen:
                if seen[identity]!=label:raise ValueError(f'Conflicting labels on duplicate review at row {number}.')
                continue
            seen[identity]=label;records.append({'text':text,'label':label,'group':row.get('Guest Group') or row.get('Review ID') or row.get('Guest Name') or str(number)})
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

def evaluate(records,seed=42,analyzer='word'):
    # Keep every phrase from the same guest/review in one fold.
    groups={}
    for i,row in enumerate(records):groups.setdefault(row['group'],[]).append(i)
    folds=min(3,min(sum(any(records[i]['label']==label for i in indices) for indices in groups.values()) for label in LABELS))
    if folds<2:raise ValueError('At least two independent review groups per class are required.')
    rng=random.Random(seed);items=list(groups.values());rng.shuffle(items)
    # Find a valid grouped split; never inspect model scores when selecting a split.
    partitions=None
    for _ in range(1000):
        rng.shuffle(items);candidate=[[] for _ in range(folds)]
        for j,indices in enumerate(items):candidate[j%folds].extend(indices)
        if all(set(records[i]['label'] for i in range(len(records)) if i not in set(test))==set(LABELS) for test in candidate):
            partitions=candidate;break
    if partitions is None:raise ValueError('Unable to construct grouped folds with all classes in training.')
    predictions=[None]*len(records);baseline=[None]*len(records);sizes=[]
    for test in partitions:
        training=[row for i,row in enumerate(records) if i not in set(test)]
        model=TfidfNB(analyzer).fit([row['text'] for row in training],[row['label'] for row in training])
        majority=Counter(row['label'] for row in training).most_common(1)[0][0]
        for i in test:predictions[i]=model.predict_one(records[i]['text'])['label'];baseline[i]=majority
        sizes.append({'train':len(training),'test':len(test),'test_groups':sorted(set(records[i]['group'] for i in test))})
    actual=[row['label'] for row in records]
    return {'method':f'{folds}-fold grouped out-of-fold evaluation','seed':seed,'analyzer':analyzer,'fold_sizes':sizes,'model':metrics(actual,predictions),'majority_baseline':metrics(actual,baseline)}

def train(source,destination):
    source=Path(source);destination=Path(destination);destination.mkdir(parents=True,exist_ok=True)
    records=read_dataset(source)
    report={'dataset_rows':len(records),'class_distribution':dict(Counter(row['label'] for row in records)),
      'label_source':'explicit phrase annotations; provisional AI annotations require independent human review',
      'evaluation':evaluate(records,42),'feature_comparison':{mode:evaluate(records,42,mode) for mode in ('word','char')},'split_sensitivity':[evaluate(records,seed) for seed in (7,19)],
      'limitations':['Pilot only; too few examples for a reliable general-purpose sentiment model.','Very few examples per class; minority-class estimates are highly unstable.','Cross-validation measures agreement with provisional text annotations, not independently verified sentiment.','Vocabulary is fit inside each fold; test comments never contribute to training features.','No synthetic rows, oversampling, or test-set tuning.','Names, review dates, and ratings are not inference features.','Clause extraction and vocabulary-based category matching require separate human evaluation.','Posterior scores are uncalibrated; unknown vocabulary can fall back to class priors.']}
    fingerprint=hashlib.sha256(source.read_bytes()).hexdigest()
    version='pilot-phrase-tfidf-nb-'+fingerprint[:12]
    model=TfidfNB('word').fit([row['text'] for row in records],[row['label'] for row in records])
    artifact={'version':version,'created_at':datetime.now(timezone.utc).isoformat(),'dataset_sha256':fingerprint,'training_rows':len(records),'training_unit':'phrases','training_reviews':len(set(row['group'] for row in records)),'class_distribution':report['class_distribution'],'label_source':report['label_source'],'pilot':True,'algorithm':'Multinomial Naive Bayes, alpha=1, empirical class priors, word unigram/bigram TF-IDF; grouped phrase evaluation','evaluation':report['evaluation'],'model':model.to_dict()}
    (destination/'sentiment_model.json').write_text(json.dumps(artifact,ensure_ascii=False,indent=2)+'\n')
    (destination/'evaluation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'reviews':len(records),'classes':report['class_distribution'],'cross_validation_accuracy':report['evaluation']['model']['accuracy'],'macro_f1':report['evaluation']['model']['macro_f1'],'baseline_accuracy':report['evaluation']['majority_baseline']['accuracy'],'artifact':str(destination/'sentiment_model.json')},indent=2))
    return report

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--data',type=Path,default=Path(__file__).parent/'datasets'/'sentiment_phrases.csv');parser.add_argument('--output',type=Path,default=Path(__file__).parent/'artifacts');args=parser.parse_args();train(args.data,args.output)
