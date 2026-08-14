# Backup and restore

Two things in this system cannot be rebuilt: the **database** and the
**uploaded files**. Everything else, images, embeddings, indexes, search
results, is derived and can be regenerated from those two. So those two are
what gets backed up, and everything here is about them.

## What to run

```bash
./scripts/backup.sh /srv/backups      # take one
./scripts/restore.sh /srv/backups/20260814T043224Z   # put one back
```

`backup.sh` writes a timestamped directory holding:

| file | what it is |
| --- | --- |
| `postgres.dump` | `pg_dump -Fc`: compressed, restorable table by table |
| `minio/` | every object in the bucket, mirrored |
| `manifest.txt` | when it was taken, the Alembic revision, and the sizes |

The manifest exists for one reason: **a dump restored onto a database at a
different migration is corruption that looks like success**. Check
`alembic_revision` against the code you are restoring into before you start.

`restore.sh` stops the API and the worker first, because a task writing during
a restore races with it and leaves rows the dump never had. It then drops and
recreates the database, mirrors the bucket back with `--remove` (a restore has
to reproduce a moment, not merge into one), starts the services and counts what
came back. It refuses to call an empty database a success.

## Measured, not estimated

Run on 2026-08-14 against the development stack, on the machine this was built
on. The data was **deliberately destroyed first**: every chunk, every document
row and every object in the bucket was deleted, because a restore you cannot
watch undo something proves nothing.

| | |
| --- | --- |
| Database size | 24 MB (`postgres.dump`) |
| Objects | 78 files, 53 MB |
| Backup time | about 20 s |
| **Restore time** | **17 s**, service stopped to service answering |
| After the restore | `users=38 subjects=1711 plans=1225 documents=20 chunks=1534`, 78 objects, identical to before |
| Application after the restore | `/ready` ok, registering a user and creating a subject both work |

**These numbers are for 24 MB.** They are the shape of the thing, not a
promise about production. Re-measure when the data is an order of magnitude
bigger, and write the new number here: a recovery time nobody has measured is
a guess, and the moment you need it is the worst moment to find that out.

## What this does not cover yet

Said plainly, because a backup document that implies more than it does is
worse than none:

- **Nothing schedules this.** There is no cron entry, no timer, no operator.
  Someone has to run it, and until something runs it automatically the real
  recovery point is "the last time a human remembered".
- **Nothing takes it off the machine.** A backup on the same disk as the
  database survives a bad migration and a dropped table; it does not survive
  the disk, the machine or the region. Copy it somewhere else.
- **Nothing verifies old backups.** The restore above was run once, by hand.
  A backup nobody has restored is a hypothesis, and the way to keep it a fact
  is to run `restore.sh` against a throwaway stack on a schedule and update the
  table above.
- **No point-in-time recovery.** `pg_dump` restores the moment it was taken,
  so everything written between the backup and the failure is gone. WAL
  archiving is what closes that gap, and it is not set up.

## Recovery objectives

Stated so they can be argued with, which is the point of stating them:

| | target | today |
| --- | --- | --- |
| **RPO** (data you can afford to lose) | 24 hours | undefined: nothing is scheduled |
| **RTO** (time to be back) | 1 hour | 17 s measured at 24 MB |

The RTO is comfortable and the RPO is the honest problem. Scheduling the
backup and copying it off the machine are the two things that would close it,
in that order.
