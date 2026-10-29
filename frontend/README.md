# The Villa — Google linked-account and console fix

This package fixes two code-controlled issues:

1. Chrome's warning that a FedCM nonce should be inside `params`.
2. HTTP 409 when a verified email/password account also has a Google
   identity linked by Supabase.

## Nonce warning

The Google button now sets:

```javascript
use_fedcm_for_button: false
```

This uses the normal Google Identity Services popup flow instead of the
FedCM button path. The secure Google/Supabase nonce pair is preserved.

## 409 Conflict

The previous backend allowed only the account's original creation method.
For example, an account created with email/password was blocked from using
Google even after Supabase linked the verified Google identity to the same
user.

The backend now reads Supabase's linked providers and permits any provider
actually attached to the user:

```text
email
google
phone
```

It still returns 409 when the requested login method is not linked.

## Google 403 remains a Google Cloud setting

This cannot be removed through application code:

```text
[GSI_LOGGER]: The given origin is not allowed for the given client ID.
```

Run in the browser console:

```javascript
window.location.origin
```

Copy the exact result into:

```text
Google Cloud Console
→ Google Auth Platform
→ Clients
→ Authorized JavaScript origins
```

For the configured local URL, add:

```text
http://localhost:5173
```

When using the IP address, add:

```text
http://127.0.0.1:5173
```

The client edited in Google Cloud must exactly match:

```text
902473082784-u3bfsivv3utk4q261auidc99hhelhlod.apps.googleusercontent.com
```

## Install

Replace:

```text
frontend/src/register.jsx
backend/main.py
```

The package also includes all complete synchronized frontend and backend
files from the latest build.

## Restart

Backend:

```bash
cd "/Applications/XAMPP/xamppfiles/htdocs/The villa/backend"
source .venv/bin/activate
python main.py
```

Frontend:

```bash
cd "/Applications/XAMPP/xamppfiles/htdocs/The villa/frontend"
npm run dev
```

Clear old browser state once:

```javascript
localStorage.removeItem("theVillaAuth");
sessionStorage.removeItem("theVillaAuth");
delete window.__theVillaGoogleIdentityStateV2;
location.href = "/register";
```