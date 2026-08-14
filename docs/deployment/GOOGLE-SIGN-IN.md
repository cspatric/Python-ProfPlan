# Sign in with Google

Off by default. With no client id configured the two endpoints are not
registered at all and `GET /api/v1/auth/providers` answers `{"google": false}`,
which is how the sign-in page knows not to draw the button. A button that
posts to an endpoint that does not exist is worse than no button.

## Turning it on

1. Google Cloud console, **APIs & Services, Credentials**, create an OAuth
   client of type **Web application**.
2. Register the callback as an authorised redirect URI. It is compared
   character for character, so `http://localhost:5173/api/v1/auth/oauth/google/callback`
   and the same URL with a trailing slash are different URIs.
3. Put the values in the environment:

```bash
GOOGLE_OAUTH_CLIENT_ID=....apps.googleusercontent.com
GOOGLE_OAUTH_CLIENT_SECRET=...
GOOGLE_OAUTH_REDIRECT_URI=http://localhost:5173/api/v1/auth/oauth/google/callback
OAUTH_SUCCESS_REDIRECT=http://localhost:5173/subjects
OAUTH_FAILURE_REDIRECT=http://localhost:5173/login
```

In production the secret comes from SSM like every other one, see
[SECRETS.md](SECRETS.md); Terraform already creates the two parameters empty
(`infra/secrets.tf`).

## The flow

```
browser            API                     Google
   │  GET /auth/oauth/google
   │ ─────────────────►                     state -> Redis, 10 min, single use
   │  307 to accounts.google.com
   │ ────────────────────────────────────►  the person signs in and consents
   │  GET /auth/oauth/google/callback?code=…&state=…
   │ ─────────────────►                     state consumed with DELETE
   │                    POST /token ─────►  server to server, with the secret
   │                    ◄───────────── id_token
   │  307 to the app, with the session cookies
   ◄─────────────────
```

The authorization code flow for a confidential client: no token ever passes
through the browser, and the client secret never leaves the API process.

## What actually protects it

**The `state` is server side and single use.** A value that is only echoed back
proves nothing. This one has to be found in Redis, and it is consumed with
`DELETE`, whose return value says whether it was there. Two callbacks racing on
the same state cannot both win.

**The ID token's claims are checked; its signature is not.** The token did not
come from the browser, it came back on the API's own TLS connection to
`oauth2.googleapis.com`, authenticated with the client secret. The channel is
the proof. What still has to be checked is what the token *claims*, because a
genuine token issued for a different application is worth nothing here, so
`aud`, `iss` and `exp` are all verified. If the exchange ever stops being
server to server, the signature check stops being optional.

**An unverified address cannot claim an existing account.** This is the one
that matters. Three cases arrive at the callback:

| what came back | what happens |
| --- | --- |
| the Google `sub` is already linked | that user is signed in |
| nobody has the `sub` or the address | a new account, with no password |
| nobody has the `sub`, but an account owns the address | linked **only if Google says the address is verified**, otherwise refused |

Without that last refusal, anyone able to get an identity provider to assert an
address, which an unverified address is by definition not proof of, would be
handed the account that owns it here. The refusal ends on the sign-in page with
`?oauth=failed`, and the person signs in with their password instead.

The key is the `sub`, not the email: an address can change hands, a subject
cannot.

## Accounts with no password

An account created this way has `password_hash NULL`, not a random hash nobody
can match. Storing a placeholder would make "does this account have a password"
unanswerable and would let a password reset appear to work on an account that
never had one. Two consequences, both covered by tests:

- the login endpoint treats a null hash as a failed sign-in, before it ever
  reaches the verifier;
- migration `902bc620092e` widens the column, and its downgrade deletes the
  passwordless accounts rather than inventing hashes for them.

## Verified on 2026-08-14

Against the running stack, with placeholder credentials that were removed
afterwards:

| | |
| --- | --- |
| `GET /auth/providers` off / on | `{"google": false}` / `{"google": true}` |
| start endpoint with the feature off | 404, and no button on the page |
| start endpoint with it on | 307 to `accounts.google.com`, state in Redis |
| following the link in a browser | reached Google, which refused the placeholder client id |
| callback with `error=access_denied` | 307 to `/login?oauth=failed`, no cookies |
| callback with a state nobody issued | 307 to `/login?oauth=failed`, no cookies, no user created |
| a full round trip with a real Google account | **not run**: needs real credentials |

The exchange with Google is replaced in the tests, so everything except
Google's own consent screen is covered by
`tests/integration/test_google_oauth_flow.py` and
`app/modules/auth/tests/test_google_oauth.py`.
