# One-service Render Free deployment

The root Dockerfile builds React and runs FastAPI with the resulting static
files. Both use one HTTPS origin; Supabase remains the database/auth/storage
provider. Local development is unchanged when FRONTEND_DIST is unset.

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
   Set `MAINTENANCE_FRONTEND_URL` to the same origin if used. If you only learn
   the URL after creation, update the settings and redeploy before testing.
6. Copy the integration settings you actually use into Render's environment:
   `PAYMONGO_SECRET_KEY`, `PAYMONGO_WEBHOOK_SECRET`, SMS provider settings, and
   any additional settings from your local backend environment. Keep all secret
   keys out of Vite variables, the repository, and screenshots.

The frontend API URL is built as same-origin. Do not set VITE_API_URL to localhost.
Keep one process/instance: this app runs background workers inside FastAPI.

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
  existing Gmail SMTP implementation will not send booking confirmations,
  feedback invitations, or staff notifications from this deployment. This needs
  an HTTPS email API or hosting that supports SMTP; do not assume setting SMTP
  credentials fixes it. Guest booking confirmations now support Resend: set
  `RESEND_API_KEY` and `RESEND_FROM` (a verified sender, e.g.
  `The Villa <bookings@YOUR-VERIFIED-DOMAIN>`). Resend's sandbox sender can only
  deliver to the account owner's address until a domain is verified. Staff and
  feedback flows that use SMTP directly are not migrated by this setting.
  SMTP attempts are skipped on Render unless `SMTP_ALLOW_ON_RENDER=true`;
  enable that override only after moving to a plan that allows SMTP.
- Local files are ephemeral. Store persistent application data in Supabase.
- Free compute has limited memory. Verify runtime memory and deployment logs;
  this configuration is not evidence that the whole app fits its allocation.
- Supabase Free has its own quotas and inactivity-pausing policy.

## Check before evaluation

Open `/health`, `/`, `/book`, `/admin-login`, and a refreshed dashboard URL.
Confirm API requests go to the Render origin, never localhost. Test sign-in,
availability, a test booking/checkout, signed payment webhook handling, and
guest/admin/staff status updates. Check a missing API URL and asset remain 404.
Email-dependent flows require resolving the SMTP limitation above.

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
