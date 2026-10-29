# The Villa ERD

Open `the-villa-erd.svg` for the black-and-white diagram. `the-villa-erd.mmd` is the editable Mermaid source.

This is an application-derived ERD, not a verified export of the deployed database. The repository does not contain the complete base schema. Only the two outbox foreign keys and its composite uniqueness are explicitly confirmed by the included DDL. Other links are supported by backend queries and write payloads; their database constraints and exact nullability require a schema export. Selected attributes are shown, not every column. Types in the Mermaid source describe application values, not verified PostgreSQL column types.

## Reading the diagram

Each panel is a view of the same database; repeated table names refer to the same table. Dashed lines are application relationships. Solid lines are migration-confirmed foreign keys. Endpoint labels state how many rows may participate. `REF` means an application reference; it does not assert an enforced FK. `ID` means the identifier used by the application; `PK` is reserved for keys confirmed by included DDL.

## Important cases

- Public bookings have `user_id = null`. Account references target the Supabase Auth identity; do not assume bookings must have a profile row.
- `profiles.id` and `staff_accounts.auth_user_id` use the Auth identity. Administrators and staff share `staff_accounts`; role is an attribute.
- `bookings.villa_id` stores the primary/legacy villa. Public multi-villa booking uses `villa_ids`. The full villa association is many-to-many through array membership. There is no `booking_villas` table in the inspected code, so none is invented here.
- Feedback from historical imports has no booking. The submission flow intends one verified review per booking; the backing RPC and unique constraint are absent from the repository, so database enforcement is unverified.
- Checkout draft IDs become booking IDs after promotion. Drafts are staging records, not child bookings; no FK to bookings is asserted.
- Front-desk payments have their own item table; online payments are separate rows in `booking_payments`.
- Payment intent IDs are provider identifiers. The diagram does not assume that `front_desk_payments.payment_intent_id` is a FK to an internal UUID.
- Analysis jobs and recommendation reports match evidence via `evidence_fingerprint`. This is not proof of a direct FK or a one-to-one relationship. Reports store aggregate evidence rather than individual feedback foreign keys.
- Task villa references can be embedded in metadata/JSON. No normalized task-to-villa FK is asserted.

## Sources

- `backend/admin.py`: select lists; task, message, notification, settlement, draft, and recommendation writes.
- `backend/booking.py`: authenticated/public booking, multi-villa membership, payment records, feedback submission.
- `backend/main.py`: profile and Auth identity handling.
- `backend/staff.py`: staff settings.
- `backend/villa_catalog.py`: villa identifiers and attributes.
- `backend/feedback_service.py` and `backend/ml/import_historical.py`: invitation lifecycle and historical feedback.
- `backend/migrations/20261022_public_checkout_drafts.sql`: draft PK and atomic promotion.
- `backend/migrations/20261025_staff_assignment_emails.sql`: enforced outbox references and uniqueness.

To certify physical cardinality, nullability, and all PK/FK constraints, compare this ERD with a current Supabase schema-only export.
