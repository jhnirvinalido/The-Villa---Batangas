# Google Cloud setup

Use a Google OAuth client whose application type is:

```text
Web application
```

The client ID must exactly match:

```text
902473082784-u3bfsivv3utk4q261auidc99hhelhlod.apps.googleusercontent.com
```

Add these Authorized JavaScript origins:

```text
http://localhost
http://localhost:5173
```

Optional for `127.0.0.1`:

```text
http://127.0.0.1
http://127.0.0.1:5173
```

Check the exact browser origin:

```javascript
window.location.origin
```

The exact result must be listed in Google Cloud.

In Supabase, enable Google under:

```text
Authentication
→ Sign In / Providers
→ Google
```

Use the client ID and client secret from the same OAuth Web application.
