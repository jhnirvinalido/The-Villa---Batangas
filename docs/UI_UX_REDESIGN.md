# Interface update — 2 November 2026

The supplied screenshots were treated as usability feedback. Existing booking, payment, and role-based access rules remain the source of truth.

## Applied feedback

| Feedback | Implemented behavior |
| --- | --- |
| Completed assignments are hard to find | My assignments includes active, review, and completed work. Status filters narrow the list; History remains an archive with explicit details actions. The navigation count reflects the whole assignment list. |
| Remove work-hours interfaces | Staff and Admin work-hours pages, navigation entries, and the calendar link are removed. Historical time records and their backend APIs are preserved. |
| Notifications are clipped on small screens | The notification panel renders outside clipping ancestors and stays within the viewport, with a scrollable feed on short or narrow screens. |
| Villa filters show invalid/combined values | Booking, staff-monitoring, and history filters offer only Villa 1, Villa 2, and Villa 3. Combined villa names match each selected villa individually. |
| Extra charges need a clear reason | Additional charges require a short title/reason and positive amount; descriptions continue through settlement and appear on payment details/receipts. |
| Portals need to work across screen sizes | Dashboard content, controls, tables, headers, and settlement layouts shrink or scroll within their viewport instead of forcing page-wide overflow. |
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

## Preserved time-record data

The time-record tables, migration, and authenticated APIs remain available for historical data and future use, but the staff/admin interfaces are no longer exposed. Removing the screens does not delete existing records.

## Verification

- Frontend production build passes. Vite retains its existing large-chunk advisory.
- All 98 frontend unit tests pass, including the new exact-match behavior for combined villa names.
- Nine time-record route tests cover staff ownership, server timestamps, duplicate clock-in, clock-out, approval, correction notes, and stale reviews.
- Focused lint passes for the front-desk villa filter model, dashboard, and tests. Broader linting of legacy dashboard modules still reports existing issues.
- The notification, villa-filter, charge-description, work-hours removal, and responsive-layout changes were production-build validated; no browser visual test was run for this update.
