# Public website UX benchmark

Reviewed: 2 November 2026. Scope: public navigation, accommodation discovery, booking access, and footer information. This is a qualitative comparison of available official pages, not a performance or conversion study.

## References

| Official website | Observed pattern | Application to The Villa |
| --- | --- | --- |
| [The Farm at San Benito / Marriott](https://www.marriott.com/en-us/hotels/mnlfs-the-farm-at-san-benito-autograph-collection/overview/) | Separate links for Overview, Accommodations, Premium Accommodations, Experiences, and Gallery; prominent availability controls and map access. | Give guests separate destinations and keep booking accessible in the shared header. |
| [Las Palmas Villas & Casitas Siargao](https://laspalmassiargao.com/) | Accommodation summaries link to room details; Book Now is visible; the lower page presents location and separate inquiry and reservation contacts. | Provide villa detail URLs and a footer with clear exploration, planning, and location groups. Use only existing property information. |

The former Farm website's `/villas/` URL redirected to Marriott during this review. Nayomi's official domains could not be retrieved, so no benchmark findings are attributed to them.

## Before and after

| Criterion | Previous implementation | Updated implementation |
| --- | --- | --- |
| Main navigation | Buttons scroll through one long page. | Home, Villas, About, Location, FAQs, and Reviews use browser links and independent routes. |
| Villa discovery | Details open in a fixed dialog; mobile browsing shows one villa at a time. | Each villa has a shareable detail URL; the catalog uses a two-column desktop grid and a complete vertical mobile list. |
| Browsing space | Content constrained to 1,160 px, with detail content scrolling inside a modal. | Public content can expand to 1,320 px; detail content uses normal page scrolling. |
| First visit | Timed entrance overlay before browsing. | Homepage content is immediately available. |
| Footer | Brand, a small row of scroll buttons, and a booking button. | Responsive Explore, Plan your stay, and Find us columns, booking link, directions, reservation terms, and copyright. |
| Booking access | Booking buttons on the landing page and in villa dialogs. | Booking remains accessible from every public page; villa links carry the villa ID and capacity into the existing booking flow. |
| Policies | A section near the bottom of the landing page. | Dedicated `/policies` route linked from the shared footer and mobile menu. |
| Old links | Landing section anchors. | Existing `/#villas`, `/#about`, `/#location`, `/#faqs`, `/#guest-feedback`, and `/#policies` links redirect to their new pages. |
| Production deep links | Server recognizes only the original browser routes. | Hosting recognizes new public routes and villa detail URLs while preserving API and missing-asset 404 responses. |

## Content boundaries

Removed the “Batangas Private Staycation” brand subtitle from public, booking, and feedback screens. The actual San Jose, Batangas location remains available for guests planning their trip. Existing villa catalog updates, reviews, payment behavior, and staff access remain integrated. The shared footer appears on public browsing pages. The booking form uses a focused layout without the site footer.

No phone numbers, email addresses, social accounts, privacy statements, rates, or business policies were invented for the redesign. A contact or privacy page should be added only with approved property information.

## Verification

- Production frontend build: passed (`npm --prefix frontend run build`).
- Hosting regression tests: all four passed, covering public deep links, existing staff routes, API priority, and missing-asset 404s.
- Browser checks: eight public destinations at 1,440, 390, and 320 px (24 page checks), plus three trailing-slash/tablet checks at 992, 390, and 320 px. No horizontal overflow or JavaScript runtime exceptions were observed.
- Confirmed villa detail navigation, browser Back, selected-villa and guest-count booking parameters, mobile navigation closure, FAQ expansion, and the legacy reviews anchor redirect.
- Inspected desktop villa and mobile footer screenshots locally.

Build snapshot: CSS 922.63 kB (147.00 kB gzip), JavaScript 1,060.22 kB (315.48 kB gzip). Vite still reports a JavaScript chunk above 500 kB. These are build artifact sizes, not measured loading times; no Lighthouse, Core Web Vitals, or conversion improvements are claimed. Booking handoff was verified without submitting a reservation or payment.
