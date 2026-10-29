"""Automatic feedback analysis and cached Gemini drafts, independent of page visits."""
import hashlib
import logging
from feedback_policy import analysis_input
from feedback_analysis import AnalysisFilters, records_for, build_report
from ml.inference import model_status, save_pilot_prediction
from ml.preprocessing import VERSION
from ml.recommendations import configured, generate

logger = logging.getLogger('thevilla.feedback.automation')


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
    if not metadata['available']: return
    records = records_for(client, AnalysisFilters())
    for row in records:
        if needs_analysis(row, metadata['version']):
            save_pilot_prediction(client, row)
    if not configured(): return
    analysis = build_report(client, AnalysisFilters())
    summary = analysis['summary']
    if not summary['top_complaints']: return
    fingerprint = summary['fingerprint']
    # Reuse manual or approved reports for unchanged evidence too.
    existing = client.table('feedback_recommendation_reports').select('id').eq('evidence_fingerprint',fingerprint).limit(1).execute().data or []
    if existing: return
    claim = client.rpc('claim_feedback_analysis_job', {'p_fingerprint':fingerprint}).execute().data
    if not claim: return
    try:
        draft = generate(summary)
    except (ValueError, RuntimeError) as error:
        client.rpc('finish_feedback_analysis_job', {
            'p_fingerprint':fingerprint,'p_claim':claim,'p_summary':None,
            'p_model_version':None,'p_recommendation':None,'p_error':str(error)[:400],
        }).execute()
        logger.warning('Automatic recommendation failed; a bounded retry is scheduled.')
        return
    client.rpc('finish_feedback_analysis_job', {
        'p_fingerprint':fingerprint,'p_claim':claim,'p_summary':summary,
        'p_model_version':analysis['model']['version'],'p_recommendation':draft,'p_error':None,
    }).execute()

    from live_updates import emit_table
    emit_table('feedback_recommendation_reports')
