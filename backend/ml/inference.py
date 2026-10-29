"""Local pilot inference. Original feedback remains the source of truth."""
import json
import logging
import os
from functools import lru_cache
from pathlib import Path
from .naive_bayes import MultinomialNB, TfidfNB
from feedback_policy import analysis_input

logger=logging.getLogger('thevilla.feedback.ml')
MODEL_PATH=Path(__file__).parent/'artifacts'/'sentiment_model.json'

@lru_cache(maxsize=2)
def _load(path,mtime):
    artifact=json.loads(Path(path).read_text())
    return artifact,(TfidfNB if artifact['model'].get('kind')=='tfidf_nb' else MultinomialNB).from_dict(artifact['model'])

def load_model():
    path=Path(os.getenv('FEEDBACK_MODEL_PATH',str(MODEL_PATH)))
    return _load(str(path),path.stat().st_mtime_ns)

def model_status():
    try:
        artifact,_=load_model()
        evaluation=artifact['evaluation']
        return {'available':True,'pilot':True,'version':artifact['version'],'training_rows':artifact['training_rows'],'training_unit':artifact.get('training_unit','reviews'),'training_reviews':artifact.get('training_reviews',artifact['training_rows']),'class_distribution':artifact['class_distribution'],'label_source':artifact['label_source'],'cross_validation_accuracy':evaluation['model']['accuracy'],'macro_f1':evaluation['model']['macro_f1'],'baseline_accuracy':evaluation['majority_baseline']['accuracy'],'gemini_available':bool(os.getenv('GEMINI_API_KEY') and os.getenv('GEMINI_MODEL')),'requires_human_review':True}
    except Exception:
        return {'available':False,'pilot':True,'gemini_available':bool(os.getenv('GEMINI_API_KEY') and os.getenv('GEMINI_MODEL')),'requires_human_review':True}

def predict_feedback(row):
    artifact,model=load_model()
    text=analysis_input(row)['text']
    result=model.predict_one(text)
    return {**result,'model_version':artifact['version'],'pilot':True,'requires_human_review':True}

def save_pilot_prediction(client,row):
    """Persist experimental output separately from ratings and original comments."""
    try:
        result=predict_feedback(row)
        from datetime import datetime,timezone
        from .complaints import analyze_review
        from .preprocessing import VERSION
        clauses=analyze_review(row)
        from feedback_automation import input_hash
        response=client.table('guest_feedback').update({'sentiment_input_hash':input_hash(row),'phrase_analysis':clauses,'analysis_pipeline_version':VERSION,'sentiment_label':result['label'] if result['known_feature_occurrences'] else None,'sentiment_model_version':result['model_version'],'sentiment_scores':result['scores'] if result['known_feature_occurrences'] else None,'sentiment_analyzed_at':datetime.now(timezone.utc).isoformat(),'analysis_status':'pilot_review_required' if result['known_feature_occurrences'] else 'insufficient_vocabulary'}).eq('id',row['id']).execute()
        if response.data:
            from live_updates import emit_table
            emit_table("guest_feedback", {"id": row["id"]})
        return bool(response.data)
    except Exception:
        logger.warning('Pilot feedback analysis unavailable; original submission remains saved.')
        return False
