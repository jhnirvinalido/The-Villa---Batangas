# Azure deployment preparation

This project can be hosted as two Azure resources:

- **Frontend:** Azure Static Web Apps Free, built from `frontend/`.
- **Backend:** Azure App Service on Linux, deployed from `backend/`.

The backend uses Supabase for its database, authentication, and storage. This
plan does not migrate Supabase to Azure. Azure resources are not created by
these instructions. The App Service Basic B1 plan is paid; verify the current
price and your Azure for Students credit before creating it.

## Before deploying

1. Put the project in a GitHub repository. Azure's GitHub deployment flow needs
   access to that repository.
2. Make sure the Azure for Students subscription is active.
3. Keep the Supabase project and its credentials available. Do not commit keys
   or put backend secrets in frontend build settings.

## Deploy the backend

1. In the Azure portal, create a **Web App** with:
   - Publish: **Code**
   - Runtime stack: **Python 3.14** (or the newest Python runtime available)
   - Operating system: **Linux**
   - Region: **Southeast Asia**, if available and suitable for your Supabase
     region
   - App Service plan: **Basic B1** for an always-on, single-instance starting
     point
2. In the web app's **Configuration > General settings**, set the startup
   command to:

   ```sh
   python -m uvicorn main:app --host 0.0.0.0 --port 8000
   ```

   Set the deployment source to the repository's `backend/` directory so
   `requirements.txt` and `main.py` are at the app root. Enable build automation
   so Azure installs `backend/requirements.txt`.
3. In **Configuration > Application settings**, add the backend settings below.
   Set `FRONTEND_URL` and `MAINTENANCE_FRONTEND_URL` to the final Static Web Apps
   origin, without a trailing slash. Set `BACKEND_PUBLIC_URL` to the App Service
   origin, also without a trailing slash.
4. Save the settings and restart the web app. Verify that
   `https://<app-name>.azurewebsites.net/health` responds successfully and
   `/docs` loads.
5. Keep the App Service at **one instance**. The app starts background workers
   inside its web process; scaling to multiple instances would start duplicate
   workers unless the worker architecture is changed first.

### Backend application settings

Required for the app to start and connect to Supabase:

| Setting | Value |
| --- | --- |
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_ANON_KEY` | Supabase anon/public key |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase service-role key; store only as a backend secret |
| `FRONTEND_URL` | Static Web Apps origin |
| `MAINTENANCE_FRONTEND_URL` | Static Web Apps origin |
| `BACKEND_PUBLIC_URL` | App Service origin |

Set integration settings only for features you use. For example, payment
processing uses `PAYMONGO_PUBLIC_KEY`, `PAYMONGO_SECRET_KEY`, and
`PAYMONGO_WEBHOOK_SECRET`; email uses `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`,
`SMTP_PASSWORD`, and `SMTP_FROM`. SMS and AI feedback features also require
their provider credentials. Keep all provider secrets in App Service
application settings, never in the frontend.

The background worker feature flags default to enabled. Leave them enabled for
the current behavior. If you intentionally disable one, use the corresponding
`*_ENABLED` setting documented in `backend/main.py`.

## Deploy the frontend

1. Create an **Azure Static Web App** and connect the GitHub repository.
2. Set the build configuration to:
   - App location: `frontend`
   - API location: leave empty
   - Output location: `dist`
   - Build command: `npm run build`
3. Add `VITE_API_URL` as a GitHub Actions repository variable containing the
   backend origin, for example `https://<app-name>.azurewebsites.net`.
   Pass that variable to the generated Static Web Apps build job as
   `VITE_API_URL: ${{ vars.VITE_API_URL }}`. This is a public frontend URL, not
   a secret. The frontend embeds Vite variables at build time, so redeploy after
   changing it.
4. The file `frontend/public/staticwebapp.config.json` supplies SPA route
   fallback and the Google sign-in related response headers. Azure copies it
   into the built site.
5. Copy the resulting `https://<site-name>.azurestaticapps.net` origin into the
   backend's `FRONTEND_URL` and `MAINTENANCE_FRONTEND_URL`, then restart the
   backend.

## Update external authentication and payment settings

- In Supabase Auth URL configuration, add the deployed frontend origin and the
  app's sign-in callback URL to the allowed redirect URLs.
- In Google Cloud OAuth settings, add the deployed frontend origin as an
  authorized JavaScript origin.
- If PayMongo is enabled, configure its webhook to the relevant deployed
  backend webhook endpoint.

## Cost and uptime

The frontend's Static Web Apps Free plan includes a generated Azure hostname.
The backend's B1 plan is billed while it runs; the earlier Southeast Asia
estimate was about **US$13/month**, or about **US$158 for 12 months**, before
other Azure charges. Prices and student-credit terms can change, so check the
Azure calculator and subscription balance before deployment. The US$100 credit
does not guarantee a full year of B1 hosting, and Azure may disable resources
when the credit expires if the subscription is not converted to pay-as-you-go.
