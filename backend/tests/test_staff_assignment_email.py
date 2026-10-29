import smtplib
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from staff_assignment_email import build_assignment_message, deliver_assignment_email, process_assignment_emails


class StaffAssignmentEmailTests(unittest.TestCase):
    def setUp(self):
        self.client = MagicMock()
        self.staff = {"id":"staff-1","full_name":"Staff Member","email":"login@example.com","personal_email":"staff@example.com", "role":"staff", "is_active":True,"account_status":"Active"}
        self.task = {"id":"task-1", "assigned_staff_id":"staff-1", "title":"Prepare Villa 1", "status":"Pending", "villa_name":"Villa 1", "due_date":"2026-10-26", "due_time":"14:00", "booking_code":"TV-123", "guest_phone":"private-phone","guest_email":"guest-secret@example.com","notes":"private-notes"}
        self.job = {"id":"job-1","lease_token":"lease-1","task_id":"task-1","recipient_staff_account_id":"staff-1"}
        self.config = SimpleNamespace(FRONTEND_URL="https://villa.example", SMTP_FROM="noreply@example.com", SMTP_FROM_NAME="The Villa", SMTP_HOST="smtp.example", SMTP_PORT=587, SMTP_USER="user", SMTP_PASSWORD="secret", _smtp_configured=lambda:True)
        def table(name):
            query = MagicMock()
            query.select.return_value.eq.return_value.limit.return_value.execute.return_value = SimpleNamespace(data=[self.staff] if name=="staff_accounts" else [self.task])
            return query
        self.client.table.side_effect = table
        self.client.rpc.return_value.execute.return_value = SimpleNamespace(data=True)
        self.patch = patch('staff_assignment_email.smtplib.SMTP')
        self.smtp_class = self.patch.start(); self.addCleanup(self.patch.stop)
        self.smtp = self.smtp_class.return_value.__enter__.return_value
        self.smtp.send_message.return_value = {}

    def status(self): return self.client.rpc.call_args.args[1]['p_status']
    def deliver(self): return deliver_assignment_email(self.client,self.job,self.config)

    def test_success_sends_current_assignment_and_records_acceptance_with_lease(self):
        self.assertEqual(self.deliver(),'accepted')
        self.smtp.starttls.assert_called_once()
        self.smtp.login.assert_called_once_with('user','secret')
        self.smtp.send_message.assert_called_once()
        message = self.smtp.send_message.call_args.args[0]
        plain = message.get_body(preferencelist=('plain',)).get_content()
        self.assertIn('https://villa.example/staff?task=task-1',plain)
        self.assertIn('14:00',plain)
        self.assertEqual(self.status(),'accepted')
        self.assertEqual(self.client.rpc.call_args.args[1]['p_lease'],'lease-1')
        for private in ('private-phone','guest-secret','private-notes','secret-key'):
            self.assertNotIn(private,message.as_string())

    def test_disabled_reassigned_cancelled_or_completed_tasks_do_not_email(self):
        cases=[('staff','is_active',False),('staff','role','admin'),('staff','account_status','Disabled'),
               ('task','assigned_staff_id','other'),('task','status','Cancelled'),('task','status','Completed')]
        for owner,key,value in cases:
            row = self.staff if owner=='staff' else self.task
            previous=row[key];row[key]=value
            self.assertEqual(self.deliver(),'suppressed')
            self.assertEqual(self.status(),'suppressed')
            row[key]=previous
        self.smtp.send_message.assert_not_called()

    def test_oncall_maintenance_uses_its_own_response_invitation(self):
        self.task.update(source='manual-maintenance-request', status_history=[{'maintenance': {'onCall': {'state': 'Awaiting response'}}}])
        self.assertEqual(self.deliver(), 'suppressed')
        self.smtp_class.assert_not_called()

    def test_invalid_email_is_rejected_before_smtp(self):
        self.staff['personal_email']='invalid'
        self.assertEqual(self.deliver(),'failed')
        self.smtp_class.assert_not_called()

    def test_connection_failure_retries_without_exposing_smtp_error(self):
        self.smtp_class.side_effect=OSError('private recipient / credentials')
        self.assertEqual(self.deliver(),'retry')
        self.assertEqual(self.status(),'retry')
        self.assertNotIn('private recipient',str(self.client.rpc.call_args))

    def test_ambiguous_timeout_after_send_is_not_automatically_retried(self):
        self.smtp.send_message.side_effect=TimeoutError('unknown submission outcome')
        self.assertEqual(self.deliver(),'uncertain')
        self.assertEqual(self.status(),'uncertain')

    def test_recipient_refusal_is_terminal(self):
        self.smtp.send_message.side_effect=smtplib.SMTPRecipientsRefused({'staff@example.com':(550,b'no user')})
        self.assertEqual(self.deliver(),'failed')
        self.assertEqual(self.status(),'failed')

    def test_explicit_data_rejection_is_retryable(self):
        self.smtp.send_message.side_effect=smtplib.SMTPDataError(451,b'temporary')
        self.assertEqual(self.deliver(),'retry')
        self.assertEqual(self.status(),'retry')

    def test_acceptance_is_recorded_before_quit_and_quit_error_does_not_resend(self):
        self.smtp_class.return_value.__exit__.side_effect=OSError('QUIT failed')
        with self.assertLogs('thevilla.staff_assignment_email',level='WARNING'):
            self.assertEqual(self.deliver(),'accepted')
        self.assertEqual(self.status(),'accepted')
        self.smtp.send_message.assert_called_once()

    def test_missing_smtp_does_not_claim_or_consume_retry_attempts(self):
        self.config._smtp_configured=lambda:False
        self.assertEqual(process_assignment_emails(self.client,self.config),[])
        self.client.rpc.assert_not_called()
        self.smtp_class.assert_not_called()

    def test_html_is_escaped_and_message_id_is_stable(self):
        self.task['title']='<script>alert(1)</script>'
        msg=build_assignment_message(self.staff,self.task,self.config.FRONTEND_URL,self.config.SMTP_FROM,self.config.SMTP_FROM_NAME,self.job['id'])
        html=msg.get_body(preferencelist=('html',)).get_content()
        self.assertIn('&lt;script&gt;',html)
        self.assertNotIn('<script>',html)
        self.assertEqual(msg['Message-ID'],'<villa-assignment-job-1@example.com>')


if __name__=='__main__':unittest.main()

class PersonalEmailNotificationTests(unittest.TestCase):
    def test_assignment_is_addressed_to_personal_email(self):
        message=build_assignment_message({'full_name':'Staff','email':'login@example.com','personal_email':'personal@example.com'}, {'id':'task-1'}, 'https://villa.example','sender@example.com','The Villa','job-1')
        self.assertEqual(message['To'],'personal@example.com')
