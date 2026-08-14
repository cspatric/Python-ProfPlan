# Runbook: the dead letter queue

**What fired:** `DeadLetterQueueGrowing` or `DeadLetterQueueBacklog`.

**What it means:** tasks ran out of retries and were given up on. Nothing else
in the stack sees this. To the queue those tasks are finished, and to the API
they never existed, so without this list a failure leaves only a log line that
rotates.

Every entry is somebody: a document that is not searchable, a plan that never
filled in, a password reset that never arrived.

## 1. Look

```bash
docker compose exec worker python scripts/dead_letter.py list
```

Reads without consuming, so it is safe at any time. Each entry carries the task,
its arguments, how many retries it burned and the error.

## 2. Decide what kind of failure it is

| the error says | what it is | what to do |
| --- | --- | --- |
| `NoSuchKey`, `S3 operation failed` | the file is gone from object storage | the document cannot be recovered; delete it and ask for a re-upload |
| `ReadTimeout` on `/api/embed` | Ollama was down or overloaded | fix Ollama, then replay |
| `AllProvidersFailed` | every LLM provider refused | check keys and `profplan_llm_requests_total` by provider, then replay |
| `no text layer` / `readable text` | the file has nothing to index | not a failure to retry; the teacher has to run it through OCR |
| SMTP anything | the mail server | emails are **not** replayable, see below |

## 3. Replay what deserves it

```bash
docker compose exec worker python scripts/dead_letter.py replay --task documents.ingest
```

Replaying takes everything out of the list first, so nothing is requeued twice.
Anything filtered out by `--task`, and anything not replayable, is put straight
back: draining is not discarding.

**Fix the cause first.** Replaying into the same outage puts the same entries
back at the bottom of the same list, with one more retry burned.

**Emails cannot be replayed.** Only the address and the subject are kept; the
body is not, because a dead letter list is no place to store a password reset
token. Someone has to ask the person to request the reset again.

## 4. If it is a backlog

`DeadLetterQueueBacklog` (over 50) means nobody is draining this. The list is
capped at 1000, so past that the **oldest failures are lost for good**. Work out
what is producing them before the cap starts eating the evidence.

## What this is not

It is not a retry mechanism. Celery already retried three times with backoff
before an entry got here, so anything on this list has already failed four
times. If entries keep coming back after a replay, the answer is upstream.
