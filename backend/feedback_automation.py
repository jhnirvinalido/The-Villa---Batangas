"""Persist sentiment analysis for feedback independently of page visits."""
import hashlib
from feedback_policy import analysis_input
from feedback_analysis import AnalysisFilters, records_for
from ml.inference import model_status, save_pilot_prediction
from ml.preprocessing import VERSION


def input_hash(row):
    return hashlib.sha256(analysis_input(row)['text'].encode()).hexdigest()


def needs_analysis(row, version):
    return (row.get('sentiment_model_version') != version
            or row.get('analysis_pipeline_version') != VERSION
            or row.get('sentiment_input_hash') != input_hash(row))


def process_feedback_analysis(client=None):
    if client is None:
        from admin import service_client
        client = service_client()
    metadata = model_status()
    if not metadata['available']:
        return
    records = records_for(client, AnalysisFilters())
    for row in records:
        if needs_analysis(row, metadata['version']):
            save_pilot_prediction(client, row)
