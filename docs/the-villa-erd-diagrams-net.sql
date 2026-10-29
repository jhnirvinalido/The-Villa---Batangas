-- DIAGRAM IMPORT ONLY: application-derived schema projection, not a migration.
-- Inferred PK/FK declarations below visualize logical references; deployed constraints are unverified.
-- Confirmed DDL: public_booking_checkouts.id; staff_assignment_email_outbox PK, FKs and composite UNIQUE.
-- auth_users represents Supabase auth.users. Types are illustrative; selected attributes only.
-- villa_ids JSON represents array membership: M:N villas/bookings, not an enforced array FK.
-- No booking FK on checkout drafts: IDs are promoted to booking IDs.
-- feedback_invitation_outbox has RPC-managed booking linkage; its key columns are not available locally.
-- No invented FK for payment_transaction_id, provider payment_intent_id, or evidence_fingerprint.
-- Nullability and uniqueness are intentionally unspecified except the migration-confirmed outbox.

CREATE TABLE auth_users (
    id UUID,
    email TEXT,
    PRIMARY KEY (id)
);

CREATE TABLE profiles (
    id UUID,
    full_name TEXT,
    phone TEXT,
    PRIMARY KEY (id),
    FOREIGN KEY (id) REFERENCES auth_users (id)
);

CREATE TABLE staff_accounts (
    id UUID,
    auth_user_id UUID,
    employee_code TEXT,
    full_name TEXT,
    email TEXT,
    username TEXT,
    phone TEXT,
    role TEXT,
    department TEXT,
    account_status TEXT,
    PRIMARY KEY (id),
    FOREIGN KEY (auth_user_id) REFERENCES auth_users (id)
);

CREATE TABLE villa_catalog (
    id TEXT,
    title TEXT,
    price DECIMAL(12,2),
    capacity INTEGER,
    status TEXT,
    PRIMARY KEY (id)
);

CREATE TABLE bookings (
    id UUID,
    booking_code TEXT,
    user_id UUID,
    villa_id TEXT,
    villa_ids JSON,
    customer_name TEXT,
    customer_email TEXT,
    customer_phone TEXT,
    check_in_date DATE,
    check_out_date DATE,
    guest_count INTEGER,
    booking_status TEXT,
    payment_status TEXT,
    total_amount DECIMAL(12,2),
    amount_paid DECIMAL(12,2),
    balance_amount DECIMAL(12,2),
    checked_in_by_staff_id UUID,
    checked_out_by_staff_id UUID,
    PRIMARY KEY (id),
    FOREIGN KEY (user_id) REFERENCES auth_users (id),
    FOREIGN KEY (villa_id) REFERENCES villa_catalog (id),
    FOREIGN KEY (checked_in_by_staff_id) REFERENCES staff_accounts (id),
    FOREIGN KEY (checked_out_by_staff_id) REFERENCES staff_accounts (id)
);

CREATE TABLE booking_payments (
    id UUID,
    booking_id UUID,
    user_id UUID,
    amount DECIMAL(12,2),
    currency TEXT,
    status TEXT,
    paymongo_payment_id TEXT,
    PRIMARY KEY (id),
    FOREIGN KEY (booking_id) REFERENCES bookings (id),
    FOREIGN KEY (user_id) REFERENCES auth_users (id)
);

CREATE TABLE front_desk_payment_intents (
    booking_id UUID,
    cashier_staff_id UUID,
    payment_intent_id TEXT,
    expected_amount DECIMAL(12,2),
    status TEXT,
    FOREIGN KEY (booking_id) REFERENCES bookings (id),
    FOREIGN KEY (cashier_staff_id) REFERENCES staff_accounts (id)
);

CREATE TABLE front_desk_payments (
    id UUID,
    booking_id UUID,
    cashier_staff_id UUID,
    payment_intent_id TEXT,
    receipt_number TEXT,
    amount DECIMAL(12,2),
    status TEXT,
    PRIMARY KEY (id),
    FOREIGN KEY (booking_id) REFERENCES bookings (id),
    FOREIGN KEY (cashier_staff_id) REFERENCES staff_accounts (id)
);

CREATE TABLE front_desk_payment_items (
    id UUID,
    front_desk_payment_id UUID,
    description TEXT,
    amount DECIMAL(12,2),
    PRIMARY KEY (id),
    FOREIGN KEY (front_desk_payment_id) REFERENCES front_desk_payments (id)
);

CREATE TABLE booking_workflow_events (
    id UUID,
    booking_id UUID,
    actor_staff_id UUID,
    actor_user_id UUID,
    event_type TEXT,
    metadata JSON,
    created_at TIMESTAMP,
    PRIMARY KEY (id),
    FOREIGN KEY (booking_id) REFERENCES bookings (id),
    FOREIGN KEY (actor_staff_id) REFERENCES staff_accounts (id),
    FOREIGN KEY (actor_user_id) REFERENCES auth_users (id)
);

CREATE TABLE admin_tasks (
    id UUID,
    booking_id UUID,
    assigned_staff_id UUID,
    created_by_staff_id UUID,
    updated_by_staff_id UUID,
    approved_by_staff_id UUID,
    title TEXT,
    status TEXT,
    checklist JSON,
    attachments JSON,
    PRIMARY KEY (id),
    FOREIGN KEY (booking_id) REFERENCES bookings (id),
    FOREIGN KEY (assigned_staff_id) REFERENCES staff_accounts (id),
    FOREIGN KEY (created_by_staff_id) REFERENCES staff_accounts (id),
    FOREIGN KEY (updated_by_staff_id) REFERENCES staff_accounts (id),
    FOREIGN KEY (approved_by_staff_id) REFERENCES staff_accounts (id)
);

CREATE TABLE staff_messages (
    id UUID,
    staff_account_id UUID,
    sender_account_id UUID,
    task_id UUID,
    concern TEXT,
    body TEXT,
    sender_type TEXT,
    PRIMARY KEY (id),
    FOREIGN KEY (staff_account_id) REFERENCES staff_accounts (id),
    FOREIGN KEY (sender_account_id) REFERENCES staff_accounts (id),
    FOREIGN KEY (task_id) REFERENCES admin_tasks (id)
);

CREATE TABLE admin_notifications (
    id UUID,
    recipient_staff_account_id UUID,
    task_id UUID,
    message_id UUID,
    payment_transaction_id UUID,
    type TEXT,
    is_read BOOLEAN,
    PRIMARY KEY (id),
    FOREIGN KEY (recipient_staff_account_id) REFERENCES staff_accounts (id),
    FOREIGN KEY (task_id) REFERENCES admin_tasks (id),
    FOREIGN KEY (message_id) REFERENCES staff_messages (id)
);

CREATE TABLE admin_settings (
    id UUID,
    staff_account_id UUID,
    assignment_alerts BOOLEAN,
    payment_alerts BOOLEAN,
    PRIMARY KEY (id),
    FOREIGN KEY (staff_account_id) REFERENCES staff_accounts (id)
);

CREATE TABLE staff_settings (
    id UUID,
    staff_account_id UUID,
    push_notifications BOOLEAN,
    dark_mode BOOLEAN,
    PRIMARY KEY (id),
    FOREIGN KEY (staff_account_id) REFERENCES staff_accounts (id)
);

CREATE TABLE guest_feedback (
    id UUID,
    booking_id UUID,
    source TEXT,
    overall_rating INTEGER,
    comments TEXT,
    review_date DATE,
    sentiment_label TEXT,
    PRIMARY KEY (id),
    FOREIGN KEY (booking_id) REFERENCES bookings (id)
);

CREATE TABLE feedback_invitation_outbox (
    status TEXT
);

CREATE TABLE staff_assignment_email_outbox (
    id UUID,
    task_id UUID NOT NULL,
    recipient_staff_account_id UUID NOT NULL,
    status TEXT,
    attempts INTEGER,
    next_attempt_at TIMESTAMP,
    PRIMARY KEY (id),
    FOREIGN KEY (task_id) REFERENCES admin_tasks (id),
    FOREIGN KEY (recipient_staff_account_id) REFERENCES staff_accounts (id),
    UNIQUE (task_id, recipient_staff_account_id)
);

CREATE TABLE feedback_recommendation_reports (
    id UUID,
    created_by_staff_id UUID,
    approved_by_staff_id UUID,
    evidence_fingerprint TEXT,
    filters JSON,
    recommendation JSON,
    status TEXT,
    PRIMARY KEY (id),
    FOREIGN KEY (created_by_staff_id) REFERENCES staff_accounts (id),
    FOREIGN KEY (approved_by_staff_id) REFERENCES staff_accounts (id)
);

CREATE TABLE feedback_analysis_jobs (
    evidence_fingerprint TEXT,
    status TEXT,
    last_error TEXT
);

CREATE TABLE public_booking_checkouts (
    id UUID,
    booking_payload JSON,
    expires_at TIMESTAMP,
    created_at TIMESTAMP,
    PRIMARY KEY (id)
);

CREATE TABLE manual_booking_checkouts (
    id UUID,
    created_by_staff_id UUID,
    booking_payload JSON,
    expires_at TIMESTAMP,
    PRIMARY KEY (id),
    FOREIGN KEY (created_by_staff_id) REFERENCES staff_accounts (id)
);
