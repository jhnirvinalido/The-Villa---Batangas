# Interface update — 2 November 2026

The supplied screenshots were treated as usability feedback. Existing booking, payment, and role-based access rules remain the source of truth.

## Applied feedback

| Feedback | Implemented behavior |
| --- | --- |
| Completed assignments are hard to find | My assignments includes active, review, and completed work. Status filters narrow the list; History remains an archive with explicit details actions. The navigation count reflects the whole assignment list. |
| Working hours need a place in the workflow | Staff and Maintenance have Work hours navigation with clock-in/out, dated records, review status, and administrator notes. The calendar links to recorded hours for the selected day. Admin has Work hours review. Planned assignments and recorded hours are labeled separately. |
| Bulk completion looks like another assigned step | Mark all complete sits in the checklist header. Its indeterminate state reflects partial completion. Assigned steps remain in their own list. |
| Starting work should be intentional | Checklist inputs stay disabled until the staff member selects Start task. Existing scheduling and review restrictions still apply. |
| Too much unused header space and a disappearing notification button | A compact sticky page header holds the title, notifications where supported, and refresh controls. |
| The payment balance has no explanation | Admin and Front Desk booking registers show booking total (TCP), amount paid, and balance due. Details repeat all three values. Airbnb payments retain their external-payment labels. |
| Card-only browsing and incomplete list controls | Assignment lists default to tables with an optional card view. Search, status, priority, date, sort, and pagination can be combined. Admin booking registers have sortable columns and pagination. Mobile front-desk filters expand on demand. |
| Some tables require clicking rows and others require buttons | Task history, staff assignments, admin assignments, booking history, and booking registers use explicit View details actions. Row styling does not imply a hidden click action. |
| Branding is too close to viewport edges | Public header padding scales with viewport width, with a 20 px minimum. |
| Sidebar controls and capitalization are inconsistent | All four workspaces share one brand/toggle component. Desktop navigation collapses to icons; the logo reopens it. Mobile starts with an icon rail and expands over the page, with a backdrop and Escape to close. Staff navigation uses distinct icons and role labels use consistent capitalization. |

## Visual direction

The login uses an existing property photograph beside a restrained, unboxed form. Public pages keep their multipage navigation, photo carousel, and warm neutral backgrounds. The portals share brown navigation, quiet paper surfaces, readable table density, consistent action buttons, visible focus states, and a compact header. Decorative statistic-card blobs and the glass login treatment were removed.

## Deployment dependency

Work-hours screens use the existing authenticated time-record APIs. The database must include `backend/migrations/20261102_staff_time_records.sql`. UI validation uses an isolated browser with mocked records and mutations; it does not apply a database migration or alter real staff, guest, booking, or payment data.

## Verification

- Frontend production build passes. Vite retains its existing large-chunk advisory.
- All 88 frontend unit tests pass, including completed assignment visibility, checklist start requirements, payment filtering, sorting, and pagination.
- Nine time-record route tests cover staff ownership, server timestamps, duplicate clock-in, clock-out, approval, correction notes, and stale reviews.
- Focused lint passes for the shared components and updated login, task, list, work-hours, calendar, and front-desk components. The large Admin and Staff dashboard modules retain pre-existing lint findings outside this change.
- All 27 browser workflow assertions pass with no JavaScript runtime exceptions. All 27 responsive layout and toggle checks pass at 1,440, 390, and 320 px across login and all four portals, with no horizontal page overflow. Checks use isolated sample records. They cover navigation, task lists, card/table switching, checklist start and bulk state, calendar-to-hours navigation, clock-in/out, booking amounts, pagination, mobile filters, and sticky headers.
