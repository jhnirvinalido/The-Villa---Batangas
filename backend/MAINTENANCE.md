# Villa operations and on-call maintenance

Use **Admin → Villas & Pricing**. Edit a villa to **Set under maintenance**, **Report repair**, or **Request inspection**. The work form is bound to that villa. The same page contains work history, technician responses, repair/inspection findings and administrator verification. There is no separate maintenance sidebar entry.

Staff have **Villas & Pricing** in their own workspace. They can view public villa prices and operational status and report a repair or inspection. They cannot change pricing, choose arbitrary assignments, approve work, or reopen a villa.

## Availability and existing reservations

Each request records `villaId`, `kind` (`Repair` or `Inspection`) and `blocksBooking`. An open blocking request makes the effective catalog status **Under Maintenance**. The existing booking flow reads this same operational status. Nonblocking inspections leave booking availability to the reservation calendar. Existing reservations remain recorded; the villa editor offers a reservation review action when maintenance affects them.

A blocking request cannot be moved to another villa or cleared while open. The administrator must verify the work or cancel with a reason. Availability follows the reservation calendar once the final blocking request closes. A pre-existing manual catalog maintenance flag is preserved and must be explicitly released in the villa editor. Editing prices while a derived block is active preserves the underlying manual status, preventing an accidental permanent block.

If Villa 1 is marked under maintenance without an active blocking maintenance request, apply `migrations/20261030_villa1_availability_repair.sql` once. It restores that one catalog row to Available only when no open blocking request exists.

The effective status is derived from durable open task records, avoiding a separate task/catalog write that could partially succeed. Public catalog responses expose counts only. Operational availability failures stop booking availability checks instead of silently treating the villa as ready.

## On-call flow

1. Reporting an issue queues an availability request to an active Maintenance staff contact. Automatic selection considers current workload and does not assume a fixed shift or availability.
2. The background worker emails the assigned technician at their saved staff-account email address. SMTP acceptance is recorded separately from technician acceptance. Staff assignment and maintenance alerts also appear in the staff web notification center, with an in-app sound while the portal is open.
3. The technician opens a private response link without a staff login and accepts with an arrival time, declines, or proposes another time. An administrator can record phone/Messenger responses in the same request. Proposed times require admin approval before work starts.
4. After the reply window (High 15, Medium 30, Low 60 minutes), one reminder is queued. After the reminder window, an untried backup contact is selected. If no backup remains, admin follow-up is flagged. Confirmed overdue arrivals are flagged, never silently reassigned or started.
5. Work progresses **Pending → In Progress → Pending Review → Completed**. Repair/inspection findings and admin verification are required. Waiting-for-parts work cannot be submitted. Closed records are read-only.

## Configuration

Use a publicly reachable HTTPS frontend address for production. Configure `MAINTENANCE_FRONTEND_URL` in the backend environment, or use the existing `FRONTEND_URL`. For same-Wi-Fi tests, an HTTP LAN address is supported. The frontend's `VITE_API_URL` must also point to a backend reachable by that phone, with the backend bound appropriately. Restart the backend after changing its environment and rebuild/restart the frontend after changing Vite configuration.

Localhost response links are blocked from automatic sending. Requests remain queued with an admin notice; phone/Messenger replies can still be recorded by an administrator. This avoids sending technicians a link that opens their own phone instead of this application.

Configure SMTP in the backend to email maintenance availability requests and reminders to the assigned technician's saved staff-account email. Assignment emails use the durable staff assignment outbox. Set `MAINTENANCE_AUTOMATION_ENABLED=false` to stop the maintenance worker. Optional `MAINTENANCE_TOKEN_SECRET` overrides a server-side HMAC key derived from the existing service-role secret. Never put signing keys in frontend configuration. No automatic Messenger API integration or automatic phone calls are made; administrators can contact the technician by email from the maintenance record.

## API and persistence

- `GET/POST /admin/maintenance`, `PATCH /admin/maintenance/{id}` use existing admin authentication. PATCH requires the current `expectedUpdatedAt` revision.
- `GET /admin/maintenance/{id}/response-link` returns the current private technician link to admins.
- `GET/POST /maintenance-response/{id}` requires `X-Maintenance-Token`. GET is read-only; POST explicitly records one response for the current invitation. Tokens expire after 24 hours and become invalid when the invitation or technician changes.
- `GET/POST /staff/villa-operations` uses staff authentication. The report model rejects pricing, approval and assignment fields.

Requests use existing `admin_tasks` with `source=manual-maintenance-request`. Server-generated maintenance snapshots in `status_history` persist booking impact, availability state, response deadlines, notification leases and attempts. No schema migration or browser-local fallback is needed. Ordinary task edit/delete routes reject these records. Generic assignment emails are suppressed for on-call work so technicians receive the appropriate response invitation.

Task revision checks arbitrate admin saves, technician replies and worker delivery claims. Ambiguous SMTP results and expired delivery leases require admin follow-up instead of blind retries. Email Message-IDs are not assumed to guarantee provider idempotency. Task/catalog realtime signals refresh admin, staff and public availability views without exposing work details publicly.

## Verification

```sh
PYTHONPATH=backend backend/.venv/bin/python -m pytest backend/tests -q
node --test frontend/tests/*.test.mjs
cd frontend
npm run build
```

Browser checks use fixture APIs only; no live repair records, messages or emails are created.
