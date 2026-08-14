# Email

Two things go out by email, and both are the only way back into an account:
the password reset link and the address verification link. Everything else in
the product survives a mail outage; these do not.

## How it is put together

`app/infrastructure/email/sender.py` has one port and two adapters. The console
adapter writes the whole body to the log and is what runs with
`EMAIL_ENABLED=false`; the SMTP adapter talks to a server. Nothing about *what*
is sent lives there, that is `auth/domain/emails.py`.

Sending happens inside a Celery task, never inside a request. A slow mail
server cannot make registration slow, and a mail server that is down cannot
make it fail: the account is created and signed in either way, and the link can
be asked for again. When the task exhausts its retries the message lands in the
dead letter queue, see
[RUNBOOK-dead-letter.md](../observability/RUNBOOK-dead-letter.md), though
`emails.send` is deliberately not replayable there because the body holds a
reset token that is never stored.

## Development: Mailpit

The dev stack ships Mailpit. It accepts everything on port 1025 and delivers
nothing; the messages are readable at <http://localhost:8025>.

```
EMAIL_ENABLED=true
SMTP_HOST=mailpit
SMTP_PORT=1025
SMTP_USE_TLS=false
```

That is the default, and it is the right default: developing against a real
provider means burning quota and, eventually, sending a test message to a real
person.

## Real delivery: Gmail with an app password

For a personal project this is the shortest honest path: free, 500 messages a
day, no domain required.

1. The Google account needs **2-Step Verification** on. Without it the app
   password page does not exist.
2. Go to <https://myaccount.google.com/apppasswords>, create one named
   "ProfPlan", and copy the 16 characters. Google shows them with spaces for
   readability; **the spaces are not part of it**.
3. Configure:

```
EMAIL_ENABLED=true
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USE_TLS=true
SMTP_USERNAME=you@gmail.com
SMTP_PASSWORD=the-16-characters-with-no-spaces
EMAIL_FROM_ADDRESS=you@gmail.com
EMAIL_FROM_NAME=ProfPlan
```

`EMAIL_FROM_ADDRESS` has to be the same account as `SMTP_USERNAME`, or an alias
Gmail already knows about. Gmail rewrites a sender it does not recognise, and
then the reply address is not the one the message claims.

Port 587 with STARTTLS, not 465: the adapter speaks STARTTLS on a plain socket,
which is what `SMTP_USE_TLS` switches on. Implicit TLS on 465 is a different
connection and is not implemented.

Then prove it, before anybody needs it:

```bash
docker compose --profile dev exec api python scripts/send_test_email.py you@gmail.com
```

It prints the configuration it is about to use and either the message id or the
exception. Almost every first failure is one of three things: the app password
pasted with its spaces, a `From` that is not the authenticated account, or a
network that blocks 587.

## When it grows past a personal project

Gmail is a mailbox, not a sending service. The move is to a provider that signs
with DKIM for a domain you own, Brevo or Resend or SES, which is the same
change: four environment variables. The application does not know the
difference, which is the reason it was built against plain SMTP.

The one thing that changes with a domain is that the reset links have to point
at it too, `FRONTEND_BASE_URL`.

## In production, the password is a secret

`SMTP_PASSWORD` comes from SSM like every other one, see [SECRETS.md](SECRETS.md).
It is not in the startup audit's required list, because an empty value means
"no authentication" for a local relay rather than a weak credential, but it
belongs in Parameter Store all the same.
