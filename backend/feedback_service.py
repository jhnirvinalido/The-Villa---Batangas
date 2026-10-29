"""Persistent post-stay invitation worker; reuses booking.py SMTP and Supabase clients."""
import hashlib
import hmac
import logging
import os
import secrets
import smtplib
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email_validator import validate_email, EmailNotValidError
from html import escape
from urllib.parse import urlencode

from feedback_policy import eligible_stay

logger = logging.getLogger('thevilla.feedback')

def token_for(booking_id, nonce):
    import booking
    secret = os.getenv('FEEDBACK_TOKEN_SECRET','').strip() or booking.SUPABASE_SERVICE_ROLE_KEY
    if not secret:
        raise RuntimeError('Feedback signing secret is not configured.')
    return hmac.new(secret.encode(),f'feedback-v1:{booking_id}:{nonce}'.encode(),hashlib.sha256).hexdigest()

def settled_total(client, booking_id):
    total = 0
    from decimal import Decimal
    for table,column in [('booking_payments','amount'),('front_desk_payments','room_balance_amount')]:
        try:
            result = client.table(table).select(f'{column},status').eq('booking_id',str(booking_id)).execute()
        except Exception as error:
            # Full online payments remain verifiable when the optional front-desk
            # migration is absent. Never treat connection/permission errors as no payment.
            if table == 'front_desk_payments' and any(marker in str(error).lower() for marker in ('42p01','pgrst205','does not exist','could not find the table')):
                continue
            raise
        for row in result.data or []:
            state = str(row.get('status') or '').lower()
            if state in {'refunded','partially_refunded','partially refunded','reversed'}:
                return Decimal('-1')
            if state in {'paid','succeeded','success','completed','complete'}:
                total += Decimal(str(row.get(column) or 0))
    return total

def booking_eligible(client, record):
    return eligible_stay(record,settled_total(client,record['id']))

def queue_feedback_invitation(record, client=None):
    """Best effort only; the worker reconciles missed checkout/payment hooks."""
    try:
        import booking
        client = client or booking._service()
        if not booking_eligible(client,record):
            return False
        validate_email(str(record.get('customer_email') or ''),check_deliverability=False)
        nonce = secrets.token_urlsafe(32)
        token = token_for(str(record['id']),nonce)
        client.rpc('queue_guest_feedback_invitation',{'p_booking_id':str(record['id']),'p_nonce':nonce,'p_token_hash':hashlib.sha256(token.encode()).hexdigest()}).execute()
        return True
    except Exception:
        # Do not log the email address, raw feedback, token, or SMTP error response.
        logger.warning('Feedback invitation was not queued; reconciliation will retry.')
        return False

def _message(record, token, message_id):
    import booking
    link = f'{booking.FRONTEND_URL}/feedback?{urlencode({"booking":str(record["id"])})}#token={token}'
    name = str(record.get('customer_name') or 'Guest')
    reference = str(record.get('booking_code') or 'Your stay')
    villa = str(record.get('villa_name') or 'The Villa')
    checkout = booking._format_email_date(record.get('check_out_date'))
    expires = record.get('feedback_token_expires_at')
    expiry_note = (f'Your private feedback link is available until {booking._format_email_date(expires)}.'
                   if expires else 'Your private feedback link expires 30 days after this invitation was created.')
    logo_url, logo_bytes = booking._booking_email_logo()
    msg = EmailMessage()
    msg['Subject'] = 'Thank You for Staying at The Villa — Share Your Experience'
    msg['From'] = f'{booking.SMTP_FROM_NAME} <{booking.SMTP_FROM}>' if booking.SMTP_FROM_NAME else booking.SMTP_FROM
    msg['To'] = str(record['customer_email'])
    msg['Message-ID'] = message_id
    msg.set_content(
        f'THE VILLA | Booking & Management System\n\n'
        f'STAY COMPLETED\nThank you for staying with us\n\n'
        f'Hello {name},\n\nYour checkout has been completed. Thank you for choosing The Villa. '
        'We hope you had a comfortable and memorable stay.\n\n'
        f'Booking reference: {reference}\nVilla: {villa}\nScheduled checkout: {checkout}\n\n'
        'How was your experience? Please take a moment to rate your stay and let us know '
        'what we did well and where we can improve. After submitting, you can invite the other guests in your booking to share their own feedback with our team.\n\n'
        f'SHARE YOUR FEEDBACK\n{link}\n\n{expiry_note} '
        'You may choose to appear as Anonymous guest when submitting your feedback.\n\n'
        'We look forward to welcoming you again.\n\nWarm regards,\nThe Villa Management Team\n\n'
        'This is an automated message from The Villa Booking & Management System.'
    )
    logo = (
        f'<td width="72" valign="middle" style="width:72px;vertical-align:middle;">'
        f'<img src="{escape(logo_url, quote=True)}" alt="The Villa logo" width="54" height="54" '
        'style="display:block;width:54px;height:54px;border:0;outline:none;border-radius:10px;" /></td>'
        if logo_url else ''
    )
    html = f'''<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"></head>
<body style="margin:0;padding:0;background-color:#f3f1ee;color:#302a25;font-family:Arial,Helvetica,sans-serif;">
<div style="display:none;font-size:1px;line-height:1px;color:#f3f1ee;max-height:0;max-width:0;opacity:0;overflow:hidden;mso-hide:all;">Your stay is complete. Share your experience with The Villa.</div>
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background-color:#f3f1ee;">
<tr><td align="center" style="padding:32px 12px;">
<table role="presentation" width="600" cellspacing="0" cellpadding="0" border="0" style="width:100%;max-width:600px;background-color:#ffffff;border:1px solid #e7e2dc;border-radius:14px;overflow:hidden;">
<tr><td style="padding:25px 28px;border-bottom:1px solid #eee9e3;">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0"><tr>{logo}
<td valign="middle" style="vertical-align:middle;"><div style="font-family:Georgia,'Times New Roman',serif;font-size:25px;font-weight:bold;letter-spacing:0.2px;line-height:30px;color:#553323;">The Villa</div><div style="font-size:10px;line-height:18px;letter-spacing:1px;color:#8a8077;">BOOKING &amp; MANAGEMENT SYSTEM</div></td>
</tr></table></td></tr>
<tr><td style="padding:30px 28px 12px;">
<span style="display:inline-block;padding:6px 10px;border:1px solid #dbe8df;border-radius:5px;background-color:#f0f7f2;color:#477457;font-size:10px;font-weight:bold;letter-spacing:1px;">STAY COMPLETED</span>
<h1 style="margin:18px 0 20px;font-size:25px;line-height:34px;font-weight:700;letter-spacing:-0.5px;color:#302a25;">Thank you for staying with us.</h1>
<p style="margin:0 0 12px;font-size:14px;line-height:24px;">Hello {escape(name)},</p>
<p style="margin:0 0 22px;font-size:14px;line-height:24px;color:#756b62;">Your checkout has been completed. Thank you for choosing The Villa. We hope you had a comfortable and memorable stay.</p>
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background-color:#faf8f5;border:1px solid #ece6df;border-radius:9px;">
<tr><td colspan="2" style="padding:17px 18px 10px;font-size:10px;font-weight:bold;letter-spacing:1px;color:#8a7768;">YOUR STAY SUMMARY</td></tr>
<tr><td style="padding:7px 18px;font-size:12px;line-height:20px;color:#82776d;">Booking reference</td><td align="right" style="padding:7px 18px;font-size:12px;line-height:20px;font-weight:bold;color:#44352b;word-break:break-word;">{escape(reference)}</td></tr>
<tr><td style="padding:7px 18px;font-size:12px;line-height:20px;color:#82776d;">Villa</td><td align="right" style="padding:7px 18px;font-size:12px;line-height:20px;color:#44352b;word-break:break-word;">{escape(villa)}</td></tr>
<tr><td style="padding:7px 18px 17px;font-size:12px;line-height:20px;color:#82776d;">Scheduled checkout</td><td align="right" style="padding:7px 18px 17px;font-size:12px;line-height:20px;color:#44352b;">{escape(checkout)}</td></tr>
</table>
<h2 style="margin:27px 0 8px;font-size:17px;line-height:24px;color:#302a25;">How was your experience?</h2>
<p style="margin:0 0 22px;font-size:14px;line-height:24px;color:#756b62;">Your feedback helps us recognize what we do well and improve the details that matter to our guests. We would appreciate a moment of your time to rate your stay. After submitting, you can invite your companions to share their own feedback with our team.</p>
<table role="presentation" cellspacing="0" cellpadding="0" border="0"><tr><td bgcolor="#704832" style="background-color:#704832;border-radius:7px;mso-padding-alt:14px 24px;"><a href="{escape(link, quote=True)}" style="display:inline-block;padding:14px 24px;border:1px solid #704832;border-radius:7px;font-size:12px;font-weight:bold;letter-spacing:0.6px;text-decoration:none;color:#ffffff;">SHARE YOUR FEEDBACK</a></td></tr></table>
<p style="margin:15px 0 0;font-size:11px;line-height:19px;color:#968a7e;">{escape(expiry_note)} You can choose to appear as Anonymous guest.</p>
<p style="margin:26px 0 18px;font-size:13px;line-height:23px;color:#756b62;">We look forward to welcoming you again.<br><br>Warm regards,<br><strong style="color:#554131;">The Villa Management Team</strong></p>
</td></tr>
<tr><td style="padding:20px 28px;background-color:#faf9f7;border-top:1px solid #eee9e3;">
<p style="margin:0 0 9px;font-size:10px;line-height:18px;color:#968a7e;">This is an automated message from The Villa Booking &amp; Management System. This private feedback link is intended for the guest associated with this reservation.</p>
<p style="margin:0;font-size:10px;line-height:18px;color:#968a7e;">If the button does not open, <a href="{escape(link, quote=True)}" style="color:#85543b;text-decoration:underline;">open your feedback form here</a>.</p>
</td></tr></table>
<p style="margin:18px 0 0;font-size:10px;line-height:18px;color:#a3988d;">THE VILLA &nbsp;·&nbsp; GUEST SERVICES</p>
</td></tr></table></body></html>'''
    msg.add_alternative(html, subtype='html')
    if logo_bytes:
        msg.get_payload()[-1].add_related(logo_bytes, maintype='image', subtype='png', cid='<thevilla-booking-logo>', filename='favicon.png', disposition='inline')
    return msg

def process_feedback_outbox():
    import booking
    client = booking._service()
    # A bounded reconciliation sweep also covers interrupted hooks and payments
    # settled after checkout. Existing outbox rows make this idempotent.
    records = client.rpc('guest_feedback_invitation_candidates',{}).execute().data or []
    for record in records:
        queue_feedback_invitation(record,client)
    for _ in range(10):
        claim = client.rpc('claim_guest_feedback_invitation',{}).execute().data
        if not claim:
            break
        record = claim['booking']
        status = 'retry'
        reason = None
        sending = False
        try:
            if not client.rpc('feedback_booking_eligible',{'p_booking_id':str(record['id'])}).execute().data:
                client.rpc('finish_guest_feedback_invitation',{'p_booking_id':str(record['id']),'p_claim':claim['claim_id'],'p_status':'suppressed','p_error':'no_longer_eligible'}).execute()
                continue
            validate_email(str(record.get('customer_email') or ''),check_deliverability=False)
            token = token_for(str(record['id']),claim['token_nonce'])
            if not hmac.compare_digest(hashlib.sha256(token.encode()).hexdigest(),str(record.get('feedback_token_hash') or '')):
                status = 'uncertain'
                raise RuntimeError('Token key changed.')
            if not booking._smtp_configured():
                raise RuntimeError('SMTP is not configured.')
            message = _message(record,token,claim['message_id'])
            with smtplib.SMTP(booking.SMTP_HOST,booking.SMTP_PORT,timeout=20) as smtp:
                smtp.ehlo(); smtp.starttls(); smtp.ehlo()
                smtp.login(booking.SMTP_USER,booking.SMTP_PASSWORD)
                sending = True
                refused = smtp.send_message(message)
                if refused:
                    raise smtplib.SMTPRecipientsRefused(refused)
                status = 'accepted'
        except (smtplib.SMTPRecipientsRefused,smtplib.SMTPDataError):
            status,reason = 'retry','smtp_rejected'
        except EmailNotValidError:
            status,reason = 'suppressed','invalid_email'
        except Exception:
            if sending:
                status = 'uncertain'
            reason = 'delivery_uncertain' if status=='uncertain' else 'smtp_unavailable'
        # If completion fails after SMTP acceptance, do NOT resend. The lease
        # becomes uncertain and requires reconciliation by an operator.
        client.rpc('finish_guest_feedback_invitation',{'p_booking_id':str(record['id']),'p_claim':claim['claim_id'],'p_status':status,'p_error':reason}).execute()
