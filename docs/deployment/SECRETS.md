# Secrets

A `.env` file is fine on a laptop and wrong on a server. It puts the database
password, both JWT signing keys and three paid API keys in one plaintext file,
with no rotation, no audit, and nothing stopping a placeholder from reaching
production.

Two things follow from that: **where the values come from is configurable**,
and **some values are refused outright**.

## Where they come from

`SECRETS_PROVIDER` decides. The loader runs before settings are built and puts
what it fetched into the environment, so nothing downstream knows the
difference.

| provider | what it reads | used for |
| --- | --- | --- |
| `env` (default) | `.env`, or whatever the orchestrator injected | local development |
| `aws-ssm` | every SecureString under `SECRETS_PATH` in Parameter Store | production |

An unknown value fails loudly rather than falling back. A typo in
`SECRETS_PROVIDER` quietly reverting to the file is how a production box ends
up running on whatever happened to be on disk.

**Parameter Store rather than Secrets Manager.** These are a handful of strings
that rotate rarely. SecureString parameters are encrypted with KMS just the
same, Parameter Store is free at this size, and Secrets Manager bills per
secret per month. The Terraform in `infra/` provisions the parameters and the
IAM policy that lets exactly one role read exactly that path.

The parameter name after the prefix **is** the environment variable, so
`/profplan/production/JWT_ACCESS_SECRET` becomes `JWT_ACCESS_SECRET` and adding
a secret needs no code change.

## What is refused

Outside development the app will not start if any of these is true:

| rule | why |
| --- | --- |
| a required secret is empty | nothing to sign or authenticate with |
| it matches a placeholder (`change-me`, `your-...`, `changeme`, ...) | it is the value shipped in the example file |
| it is under 32 characters | a signing key that short is a signing key in name only |
| both JWT secrets are the same | a stolen access token can then be replayed as a refresh token, which is the one thing having two of them prevents |
| `DEBUG` is on | stack traces and configuration to strangers |

Required: `SECRET_KEY`, `JWT_ACCESS_SECRET`, `JWT_REFRESH_SECRET`,
`POSTGRES_PASSWORD`, `MINIO_ROOT_PASSWORD`. Not every secret in the file: these
are the ones where a weak value is an unauthenticated stranger rather than a
broken feature.

**All problems are reported at once.** One per boot would cost a deploy per
secret.

Development, test and testing are exempt. Nobody should have to generate
32-character secrets to run a test suite, and a check that makes local work
annoying is a check that gets disabled.

### This is not hypothetical

Run against this repository's own `.env` today:

```
in development: passes, as it should

if this went up as production:
  x SECRET_KEY is still a placeholder
  x POSTGRES_PASSWORD is still a placeholder
  x MINIO_ROOT_PASSWORD is still a placeholder
  x DEBUG is on
```

## Generating them

```bash
python scripts/new_secret.py --all
```

Prints one strong value per required secret, ready to paste into Parameter
Store or an `.env`. It exists because a placeholder survives in a config file
for exactly as long as replacing it is more effort than leaving it.

## Rotating them

1. Write the new value into Parameter Store (or via Terraform, though see the
   warning below).
2. Restart the API and the workers. Secrets are read at boot, so nothing picks
   up a rotation while running.
3. **Rotating a JWT secret signs out everybody**, because every issued token
   stops verifying. Rotating both at once does it twice. That is the intended
   behaviour after a leak and a nasty surprise otherwise.

## What this does not do

- **Nothing rotates on a schedule.** Rotation is a manual act, and until
  something automates it the real answer to "when was this last rotated" is
  "never".
- **The Terraform holds the values in state.** Parameters created by Terraform
  put their plaintext in the state file, so the state must be treated as a
  secret itself, or the values written by hand and only *referenced* by the
  code. The `infra/` module marks them `ignore_changes` for that reason.
- **The `.env` is still plaintext locally.** That is a deliberate line: the
  laptop is not the threat model, and encrypting it there buys nothing while
  costing everyone a decryption step.
- **Nothing scans history.** `.env` was gitignored from the start, so no secret
  ever reached a commit here, but nothing enforces it. A pre-commit hook with
  gitleaks would.
