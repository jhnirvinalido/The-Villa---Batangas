# One-service Render Free deployment

The root Dockerfile builds React and runs FastAPI with the resulting static
files. Both use one HTTPS origin; Supabase remains the database/auth/storage
provider. Local development is unchanged when FRONTEND_DIST is unset.

See the [system architecture](./SYSTEM_ARCHITECTURE.md) and its
[architecture diagram](./the-villa-render-architecture.svg) for the application
and deployment-profile overview.

## Create the service

1. Push these changes to your GitHub repository. Never commit `.env` files.
2. In Render choose **New > Web Service**, connect the repository, and select
   the branch with these changes.
3. Leave Root Directory empty, choose **Docker**, use `./Dockerfile`, and
   choose the **Free** instance. Use `/health` as the health check path.
   No custom build/start command is needed. Alternatively create a Blueprint
   from the root `render.yaml`, which defines the same free service.
4. Add these environment variables using your existing backend configuration:
   `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`.
5. Set `FRONTEND_URL` and `BACKEND_PUBLIC_URL` to the assigned Render HTTPS
   origin, e.g. `https://the-villa-xxxx.onrender.com`, without a trailing slash.
   The feedback invitation's private form URL is built from `FRONTEND_URL`, so
   do not leave it as localhost. If the assigned URL was not available at
   service creation, update the setting and redeploy. Set
   `MAINTENANCE_FRONTEND_URL` to the same origin if used.
6. Configure HTTPS email delivery by setting
   `RESEND_API_KEY` and `RESEND_FROM` in Render. The sender must be verified in
   Resend; the sandbox sender only delivers to the account owner's address
   until a domain is verified. This provider sends booking/payment emails,
   feedback invitations, staff assignments, and maintenance on-call emails.
   Local development can continue to use the existing SMTP settings. Set a
   stable `FEEDBACK_TOKEN_SECRET` with at least 32 random bytes; do not rotate
   it while invitations are pending. Never commit these values or put them in
   frontend/Vite variables.
7. Copy the other integration settings you actually use into Render's environment:
   `PAYMONGO_SECRET_KEY`, `PAYMONGO_WEBHOOK_SECRET`, SMS provider settings, and
   any additional settings from your local backend environment. Keep all secret
   keys out of Vite variables, the repository, and screenshots.

The frontend API URL is built as same-origin. Do not set VITE_API_URL to localhost.
Keep one process/instance: this app runs background workers inside FastAPI.
`PUBLIC_BOOKING_ALLOW_PAST_DATES=true` is enabled for testing. It permits
past check-in dates on the public booking form while still enforcing valid
dates, availability, and the check-out-after-check-in rule. Set it to `false`
after testing to restore the future-date restriction; restart or redeploy the
backend after changing it. Local development defaults to the same test setting.
This setting does not change PayMongo mode or prevent paid reservations; use
PayMongo test credentials while testing.

## External services

- Supabase Auth: add the Render origin and the app's actual callback URLs to
  allowed redirects, and update Site URL if this becomes the primary site.
- Google OAuth, if enabled: add the Render origin to authorized JavaScript
  origins and configure the callback URI used by your existing Supabase flow.
- PayMongo: update checkout return URLs through FRONTEND_URL and set the webhook
  to `https://YOUR-SERVICE.onrender.com/bookings/paymongo/webhook`. Use the
  matching test/live webhook secret. Begin with test keys, verify booking status
  updates, then configure the approved merchant's live integration separately.

## Free-plan limitations that affect this project

- Render sleeps after 15 minutes without inbound traffic. Waking takes time;
  background email/assignment/cleanup workers stop while the service is asleep.
- Outbound SMTP ports 25, 465, and 587 are blocked on Free web services. The
  all application email flows use Resend's HTTPS API when
  `RESEND_API_KEY` and `RESEND_FROM` are configured. The sender must be verified
  in Resend (the sandbox only delivers to the account owner until a domain is
  verified). SMTP remains the local-development fallback; SMTP credentials
  alone do not enable email on Render Free. `SMTP_ALLOW_ON_RENDER=true` only
  bypasses the app guard; it does not unblock Render's network and must not be
  used on Free.
- Local files are ephemeral. Store persistent application data in Supabase.
- Free compute has limited memory. Verify runtime memory and deployment logs;
  this configuration is not evidence that the whole app fits its allocation.
- Supabase Free has its own quotas and inactivity-pausing policy.

## Check before evaluation

Open `/health`, `/`, `/book`, `/admin-login`, and a refreshed dashboard URL.
Confirm API requests go to the Render origin, never localhost. Test sign-in,
availability, a test booking/checkout, signed payment webhook handling, and
guest/admin/staff status updates. Check a missing API URL and asset remain 404.
Check the Render logs and Resend delivery dashboard, then complete a real
post-stay invitation test to a guest address you control. A green app health
check does not verify sender-domain, email delivery, database migration, or
inbox-link behavior.

## Checkout return troubleshooting

In the combined Render deployment, guest checkout return URLs use Render's
`RENDER_EXTERNAL_URL` so the guest returns to the same origin. Keep
`FRONTEND_URL` and `BACKEND_PUBLIC_URL` set to that same HTTPS origin for other
links. Browser tokens have an expiring local-storage fallback for returns in
another tab. Existing checkouts already created with the wrong return URL are
not rewritten; test a new checkout after deploying. Never put the guest token
in a query string or disable token verification to recover an old checkout.

The repository is prepared locally; creating the Render service and supplying
credentials in your own account are still required.
