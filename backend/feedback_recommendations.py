"""Durable, deduplicated Gemini recommendation draft worker."""
import logging

from ml.recommendations import generate

logger = logging.getLogger("thevilla.feedback.recommendations")


def _data(response):
    value = getattr(response, "data", None)
    if isinstance(value, list):
        return value[0] if value else None
    return value


def process_recommendation_job(client=None):
    """Claim and process at most one report job; database RPCs own concurrency."""
    if client is None:
        from admin import service_client
        client = service_client()

    job = _data(client.rpc("claim_feedback_recommendation_job", {}).execute())
    if not job:
        return False

    job_id = job["id"]
    claim_id = job["claim_id"]
    report_id = None
    try:
        existing = (
            client.table("feedback_recommendation_reports")
            .select("id")
            .eq("evidence_fingerprint", job["evidence_fingerprint"])
            .limit(1)
            .execute()
        )
        existing_rows = getattr(existing, "data", None) or []
        if existing_rows:
            report_id = existing_rows[0]["id"]
        else:
            recommendation = generate(job["evidence_summary"])
            persisted = _data(client.rpc(
                "persist_feedback_recommendation_report",
                {"p_report": {
                    "created_by_staff_id": job["created_by_staff_id"],
                    "filters": job["filters"],
                    "evidence_fingerprint": job["evidence_fingerprint"],
                    "evidence_summary": job["evidence_summary"],
                    "model_version": job["model_version"],
                    "recommendation": recommendation,
                    "status": "draft",
                }},
            ).execute())
            if not persisted or not persisted.get("report"):
                raise RuntimeError("Recommendation report persistence returned no report.")
            report_id = persisted["report"]["id"]

        finished = _data(client.rpc(
            "finish_feedback_recommendation_job",
            {
                "p_job_id": job_id,
                "p_claim_id": claim_id,
                "p_status": "completed",
                "p_report_id": report_id,
                "p_error": None,
                "p_retryable": False,
            },
        ).execute())
        if finished is not True:
            logger.warning("Recommendation job completion was not recorded for job %s.", job_id)
        else:
            from live_updates import emit_table
            emit_table("feedback_recommendation_reports", {"id": report_id})
        return True
    except Exception as error:
        retryable = not isinstance(error, ValueError)
        if isinstance(error, RuntimeError):
            error_message = str(error)
        elif isinstance(error, ValueError):
            error_message = "Gemini returned invalid recommendation output. No draft was saved."
        else:
            error_message = "Recommendation processing failed. Check backend logs."
        logger.warning(
            "Recommendation job %s failed; retryable=%s; error_type=%s.",
            job_id, retryable, type(error).__name__,
        )
        finished = _data(client.rpc(
            "finish_feedback_recommendation_job",
            {
                "p_job_id": job_id,
                "p_claim_id": claim_id,
                "p_status": "retry" if retryable else "failed",
                "p_report_id": report_id,
                "p_error": error_message[:400],
                "p_retryable": retryable,
            },
        ).execute())
        if finished is not True:
            raise RuntimeError(
                f"Recommendation job {job_id} failed and its retry state could not be recorded."
            ) from error
        return True
