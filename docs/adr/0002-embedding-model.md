# 0002 — bge-m3 for embeddings, slow and multilingual

**Status:** Accepted · 2026-08-14

## Context

Every uploaded document is chunked and embedded before it can feed a plan. On
this hardware, with no GPU, embedding is by far the slowest step in the system:
it is minutes of work per document, against seconds for everything else.

Three models were measured on the same machine, on chunks of about 1200
characters, with nothing else running:

| model | seconds per chunk | dimensions | 154 chunks | a 2000-chunk book |
| --- | --- | --- | --- | --- |
| **bge-m3** | 1.47 | 1024 | 3.8 min | **49 min** |
| nomic-embed-text | 0.86 | 768 | 2.2 min | 29 min |
| all-minilm | 0.06 | 384 | 0.1 min | 1.9 min |

all-minilm is **24 times faster**. That is not a rounding difference, it is the
difference between a teacher waiting and a teacher not noticing.

## Decision

Keep **bge-m3**, and accept being the slowest of the three.

The material this product ingests is in Portuguese. bge-m3 is trained
multilingual; the two faster models are trained for English and degrade on
everything else. The cost of the slow model is paid **once per document, at
upload**. The cost of the fast one would be paid on **every plan generated from
that document afterwards**, as worse retrieval, and it would be invisible: a
plan built on the wrong three chunks still looks like a plan.

Speed was bought elsewhere instead, where it costs nothing: embedding runs in
batches so a long document actually finishes, identical text is served from a
Redis cache, and the page shows real progress so the wait is legible rather
than mysterious.

## Consequences

- A large book is roughly an hour of indexing. That is a known number now, it
  is on screen while it happens, and it is paid once.
- The vector size is fixed by a migration (`chunks.embedding` is
  `vector(1024)`). **Switching models is a schema change, not a settings
  change**: the column has to be resized and every stored vector recomputed,
  because vectors from different models cannot be compared. The ingestion
  refuses a mismatch on the first batch rather than discovering it on the
  insert after paying for every chunk.
- The measurement lives next to the setting in `app/core/config.py`, so the
  next person to wonder does not have to re-measure.

## What would change this

- **A GPU.** The ranking above is a CPU ranking; with a GPU the whole question
  disappears and bge-m3 stops being slow.
- **The content stops being multilingual.** If this were English-only, the
  faster models become the obvious choice and this record is wrong.
- **Someone measures retrieval quality.** The claim that the faster models
  retrieve worse on Portuguese is drawn from how they were trained, not from a
  measurement on this corpus. A retrieval benchmark on real teacher material
  would settle it properly, and is the honest next step if the indexing time
  ever becomes the thing people complain about.
