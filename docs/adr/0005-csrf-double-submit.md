# 0005 — Double-submit CSRF cookie, living as long as the session

**Status:** Accepted · lifetime corrected 2026-08-13

## Context

Sessions are HttpOnly cookies, which is what keeps a token out of reach of any
script on the page. It also means the browser attaches them to requests the
user did not intend, which is the whole of CSRF.

## Decision

A second cookie, `csrf_token`, readable by scripts, holding a random value with
no authority of its own. The frontend mirrors it into an `X-CSRF-Token` header
on every unsafe request, and the middleware rejects any mismatch. A page on
another origin can make the browser send the session cookie, but cannot read
this one to produce the matching header.

Safe methods are exempt, and so are login and register, where no session exists
yet to ride along with.

## Consequences

- The frontend must mirror the cookie. It did not, at first, and every write
  failed with "Missing or invalid CSRF token" until it did.
- **The cookie has to outlive the access token.** It originally expired with
  it, after fifteen minutes, while the refresh cookie lasted thirty days. A
  browser that idled past fifteen minutes kept a session cookie and lost the
  CSRF one, so the middleware answered 403 to every write, **including the POST
  to `/auth/refresh` that would have fixed it**. The session became unusable
  with no way out but logging in again. The cookie now lives as long as the
  refresh token, which is correct because the value proves nothing by itself:
  it only has to be unreadable from another origin.
- The pair is only as good as the SameSite policy behind it, and both are
  needed.

## What would change this

- **Moving off cookies.** With a token in memory and no ambient credential,
  CSRF stops being a category and this goes away.
- **A framework-level session.** If sessions ever move to a signed server-side
  store with its own CSRF handling, this hand-rolled pair should be deleted
  rather than kept alongside it.
