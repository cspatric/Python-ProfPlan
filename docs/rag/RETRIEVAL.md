# Retrieval

Two searches run over the teacher's documents and their rankings are fused.

## Why two

A vector search answers "what is this about" and is reliably bad at tokens
that carry no meaning to average: a surname, an acronym, a year, a formula.
"van Helmont", "RuBisCO" and "1779" embed as noise near other noise. A lexical
search is the exact opposite: blind to a paraphrase, perfect on a rare word.
They fail in different places, which is the only good reason to run both.

The lexical half is a Postgres `tsvector` on `chunks.content`, a **generated
column**, so a chunk that exists is a chunk that is searchable and no code path
can forget to fill it. It backfilled 1.534 existing chunks at migration time
without reprocessing anything.

## Two decisions that made the difference

**OR with ranking, not AND.** `websearch_to_tsquery` joins terms with AND, so
"why are food chains short" only matches a passage containing every one of
those words, which no passage does. That is a lexical *filter*, and it is how a
feature ends up switched on and doing nothing. The query is built as the
question's lexemes joined by `|`, and `ts_rank_cd` does the separating: it
takes proximity into account, so a passage where the terms appear together
beats one where they are scattered. This is the single change that took the
lexical half from **0,35 to 0,75** recall@1.

**`english` on both sides.** The configuration matters less than the fact that
the index and the query use the *same* one: stemming is a mapping, and a
mapping applied to both sides matches itself whatever language the text is in.
What `english` adds over `simple` is stopword removal, without which "how",
"do" and "the" are indexed terms and a question made mostly of them ranks the
whole corpus equally.

## Reciprocal rank fusion, not a weighted sum

Cosine distance and `ts_rank_cd` are different quantities on different scales
with no meaningful conversion between them. Any weighting of the two is a magic
number that happens to work on the documents it was tuned on. RRF reads only
the *positions*, which is the one thing the two lists genuinely agree on:

    score = 1/(k + vector_rank) + 1/(k + lexical_rank)

with `k = 60` from the original paper. `k` flattens the curve so rank 1 does
not swamp everything: the first result is worth 1/61 and the tenth 1/70, close
enough that **agreement between the two lists beats a strong showing in one**,
which is the entire reason to run two searches.

Each half contributes a pool of 30 candidates before fusion, larger than the
limit on purpose: fusion can only promote what one of the lists returned.

A passage found only by the lexical half still gets a real cosine distance
computed for it, so a citation can say how close it was instead of showing a
blank where the number should be. And a question with no searchable word left
after stopwords falls back to the vector search alone rather than returning
nothing.

## Measured, not asserted

```bash
docker compose --profile dev exec api python scripts/seed_eval_corpus.py
docker compose --profile dev exec api python scripts/eval_retrieval.py \
    --set docs/rag/eval/golden.json
```

The corpus lives in `docs/rag/eval/corpus/` and the seed rewrites the content
ids in the golden set, so the numbers below can be reproduced rather than
believed. 20 questions: half conceptual, half turning on a name, a number or an
acronym. A set of only one kind proves whichever half of the search it was
written for. The corpus is 12 chunks of course notes plus **40 sections of
neighbouring topics sharing the same vocabulary**, because without decoys a
small corpus makes every retrieval look perfect.

Run on 2026-08-14:

| mode | recall@1 | recall@3 | recall@5 | MRR | ms |
| --- | --- | --- | --- | --- | --- |
| vector | 0,80 | 0,95 | 0,95 | 0,88 | 9 |
| lexical | 0,75 | 0,85 | 0,85 | 0,79 | 5 |
| **hybrid** | **0,85** | 0,95 | 0,95 | **0,89** | 7 |

**The honest reading.** The gain is one question at recall@1 and 0,01 of MRR.
It is real and it is small, and on this corpus it could not be large: the
vector search already finds 95% of the answers in the top three, so there is
almost no headroom. What the harness shows that the average hides is the shape
of the trade:

| question | vector | lexical | hybrid |
| --- | --- | --- | --- |
| where is carbon dioxide turned into sugar | 2 | 1 | **1** |
| why do we think mitochondria used to be bacteria | 1 | 3 | 1 |
| what stops water from breaking as it rises in a tree | 1 | 2 | 1 |
| how do plants turn light into chemical energy | 2 | not found | **3** |

The last row is a real regression: a purely conceptual question the lexical
half could not help with, pushed down one place by fusion. That is the cost of
RRF and it is worth paying at these numbers, but it is the thing to watch if
the corpus ever becomes mostly prose.

Hybrid is not slower. 7 ms against 9 ms is noise at this size, but it says the
second search is not a latency problem: both halves are indexed (HNSW and GIN)
and the pools are small.

## What is not here

**No cross-encoder reranker.** It is the obvious next step and it needs a model
server this stack does not have: reranking 30 candidates on the CPU that is
already sharing itself between embedding and the API would cost more latency
than the retrieval it improves. The place for it is after the pool and before
the cut, and the harness above is what will say whether it earns its keep.

**No query expansion.** Same reason to wait: it costs an LLM call per search,
and the number to beat is now written down.

## Turning it off

`RAG_HYBRID_SEARCH=false` falls back to the vector search alone, which is what
makes the comparison above possible without a branch. `RAG_CANDIDATE_POOL` and
`RAG_RRF_K` are the two knobs; neither is sensitive, and the harness is how to
find out if a change to them helps.
