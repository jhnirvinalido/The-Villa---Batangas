"""HTTPS transport for guest mail on hosts that block SMTP."""
import base64
import os
from email.utils import getaddresses

import requests


class EmailProviderError(RuntimeError):
    def __init__(self, status_code):
        self.status_code = status_code
        super().__init__(f"Email provider did not accept the message (HTTP {status_code}).")


def send_resend(message, *, on_sending=None, on_accepted=None):
    sender = os.getenv("RESEND_FROM", "").strip()
    if not sender:
        raise RuntimeError("RESEND_FROM must be a sender verified by Resend.")
    payload = {
        "from": sender,
        "to": [address for _, address in getaddresses(message.get_all("To", []))],
        "subject": str(message.get("Subject", "")),
    }
    for kind in ("plain", "html"):
        part = message.get_body(preferencelist=(kind,))
        if part:
            payload["text" if kind == "plain" else "html"] = part.get_content()
    attachments = []
    for part in message.walk():
        if part.is_multipart() or not part.get_filename():
            continue
        attachment = {
            "filename": part.get_filename(),
            "content": base64.b64encode(part.get_payload(decode=True) or b"").decode(),
            "content_type": part.get_content_type(),
        }
        if part.get("Content-ID"):
            attachment["content_id"] = str(part["Content-ID"]).strip("<>")
        attachments.append(attachment)
    if attachments:
        payload["attachments"] = attachments
    if on_sending:
        on_sending()
    response = requests.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {os.environ['RESEND_API_KEY']}"},
        json=payload,
        timeout=(3, 5),
    )
    # Do not put provider response bodies (which may contain addresses) in logs.
    try:
        accepted = response.ok and bool(response.json().get("id"))
    except (TypeError, ValueError):
        accepted = False
    if not accepted:
        raise EmailProviderError(response.status_code)
    if on_accepted:
        on_accepted({})
    return {}
