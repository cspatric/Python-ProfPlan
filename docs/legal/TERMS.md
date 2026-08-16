# Terms of use

Short because the product is small, and honest because the alternative is
worse.

## What this is

ProfPlan drafts teaching plans and activities from documents you upload. It is
software that uses language models, which means **it produces text that can be
wrong, and confidently so**.

## What you are responsible for

**Checking the material before you teach it.** Every generated activity shows
the passages it was written from, and an activity written from nothing says so.
That exists precisely so that checking is possible; it is not a substitute for
doing it.

**Having the right to upload what you upload.** A textbook you own a copy of is
not necessarily a textbook you may put into a system that sends passages of it
to a third-party model. That call is yours, and it depends on your material and
your institution.

**Your account.** Sharing it, or leaving it signed in on a shared computer, is
outside anything this can protect you from.

## What we are responsible for

Keeping your material to the purpose you gave it for, which is drafting your
plans. Not selling it, not training on it, not showing it to another account.
The isolation is enforced in the search itself: a query is never run without
the ownership scope, so one account's question cannot match another's document.

Telling you what breaks. The application's own record of what it did, including
what each generation cost and which model wrote it, is available to you.

## What we do not promise

Availability. This is a project, not a service with an operations team behind
it; the objective the code is built to (99% of a rolling month, plans drafted
in under two minutes) is written down in `docs/observability/SLO.md` as an
engineering target, and it is not a commitment to you.

That the AI is right. See above.

## Ending it

You can delete your account at any time, from the application or from
`POST /api/v1/users/me/delete`, and it is deleted rather than hidden. We can
close an account that is being used to break the law or to attack the service,
and if that happens you can still export your data first unless the account is
what is doing the attacking.

## The law that applies

Brazilian law, and the LGPD in particular. See
[PRIVACY.md](PRIVACY.md), which is the part of this that has real obligations
behind it.
