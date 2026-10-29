# Google Sign-In setup

## Google Cloud

Open:

Google Cloud Console
→ Google Auth Platform
→ Clients

Select the Web application client with this exact ID:

902473082784-u3bfsivv3utk4q261auidc99hhelhlod.apps.googleusercontent.com

Add these Authorized JavaScript origins:

http://localhost
http://localhost:5173

Add these only when intentionally using 127.0.0.1 in the browser:

http://127.0.0.1
http://127.0.0.1:5173

Do not add /register or /dashboard.

Run this in the browser console:

window.location.origin

The exact result must be present in Google Cloud.

## Supabase

Authentication
→ Sign In / Providers
→ Google

Enable Google and use the client ID and client secret from the same OAuth
Web application.

## frontend/.env

VITE_API_URL=http://127.0.0.1:8000
VITE_GOOGLE_CLIENT_ID=902473082784-u3bfsivv3utk4q261auidc99hhelhlod.apps.googleusercontent.com

## Clear old Google state once

localStorage.removeItem("theVillaAuth");
sessionStorage.removeItem("theVillaAuth");
delete window.__theVillaGoogleIdentityStateV2;
location.href = "/register";

## Restart

Backend:
cd "/Applications/XAMPP/xamppfiles/htdocs/The villa/backend"
source .venv/bin/activate
python main.py

Frontend:
cd "/Applications/XAMPP/xamppfiles/htdocs/The villa/frontend"
npm run dev

Open exactly:
http://localhost:5173
