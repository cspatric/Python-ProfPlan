#!/usr/bin/env python
"""Measure the retrieval instead of arguing about it.

    python scripts/eval_retrieval.py --set docs/rag/eval/golden.json

Runs every question in a golden set through each retrieval mode and reports
recall@k and MRR side by side:

    mode      recall@1  recall@3  recall@5   MRR
    vector      0.62      0.85      0.92     0.74
    lexical     0.54      0.77      0.85     0.66
    hybrid      0.77      0.92      1.00     0.85

Why this exists: "hybrid search is better" is a claim, and a claim about
retrieval is the kind that feels obviously true and is often wrong on a
particular corpus. This is the only thing that can tell the difference, and it
is also what makes the next change safe to make.

**Recall, not precision.** What matters for this product is whether the passage
that answers the question was put in front of the model at all; a couple of
irrelevant passages alongside it cost tokens, a missing one costs a wrong
answer.

The golden set is expected passages by **substring**, not by chunk id: ids
change with every re-ingestion, and a set that has to be rebuilt whenever a
document is reprocessed is a set nobody will maintain.
"""

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.infrastructure.database.session import SessionFactory  # noqa: E402
from app.modules.rag.application.search_service import SearchService  # noqa: E402
from app.modules.rag.infrastructure.embedding.cache import (  # noqa: E402
    build_cached_embedder,
)
from app.modules.rag.infrastructure.repository import ChunkRepository  # noqa: E402

MODES = ("vector", "lexical", "hybrid")
CUTOFFS = (1, 3, 5)


def _hit(content: str, expected: str) -> bool:
    """Whether a retrieved passage is the one the question expected."""
    return expected.lower() in content.lower()


async def _run_one(session, embedding, question: dict, content_ids, mode: str, limit):
    chunks = ChunkRepository(session)

    if mode == "vector":
        rows = await chunks.search_similar(
            embedding, limit=limit, content_ids=content_ids
        )
        return [chunk.content for chunk, _ in rows]

    if mode == "lexical":
        rows = await chunks.search_lexical(
            question["question"], limit=limit, content_ids=content_ids
        )
        return [chunk.content for chunk, _ in rows]

    results = await SearchService(chunks).search(
        query_embedding=embedding,
        limit=limit,
        content_ids=content_ids,
        query_text=question["question"],
    )
    return [r.content for r in results]


async def _evaluate(path: Path) -> int:
    golden = json.loads(path.read_text())
    content_ids = [UUID(i) for i in golden["content_ids"]]
    questions = golden["questions"]
    limit = max(CUTOFFS)

    embedder = build_cached_embedder()
    # Embedded once, before anything is timed. Otherwise the first mode pays
    # for every embedding and the ms column compares the embedder rather than
    # the search, which is the number this is here to give.
    embeddings = {
        q["question"]: await embedder.embed_text(q["question"]) for q in questions
    }
    scores: dict[str, dict[str, float]] = {}
    #: question -> mode -> position of the expected passage (None = not found)
    found_at: dict[str, dict[str, int | None]] = {q["question"]: {} for q in questions}

    async with SessionFactory() as session:
        for mode in MODES:
            hits = {k: 0 for k in CUTOFFS}
            reciprocal = 0.0
            started = time.perf_counter()
            for question in questions:
                contents = await _run_one(
                    session,
                    embeddings[question["question"]],
                    question,
                    content_ids,
                    mode,
                    limit,
                )
                positions = [
                    i + 1
                    for i, content in enumerate(contents)
                    if _hit(content, question["expect"])
                ]
                first = positions[0] if positions else None
                found_at[question["question"]][mode] = first
                if first:
                    reciprocal += 1 / first
                    for k in CUTOFFS:
                        if first <= k:
                            hits[k] += 1
            total = len(questions)
            scores[mode] = {
                **{f"recall@{k}": hits[k] / total for k in CUTOFFS},
                "MRR": reciprocal / total,
                # Per question, over the search only: the embeddings were
                # computed before the clock started.
                "ms": (time.perf_counter() - started) * 1000 / total,
            }

    print(f"{len(questions)} questions, {len(content_ids)} document contents\n")
    header = f"{'mode':10}" + "".join(f"{f'recall@{k}':>10}" for k in CUTOFFS)
    print(header + f"{'MRR':>8}{'ms':>8}")
    for mode, row in scores.items():
        line = f"{mode:10}" + "".join(f"{row[f'recall@{k}']:>10.2f}" for k in CUTOFFS)
        print(line + f"{row['MRR']:>8.2f}{row['ms']:>8.0f}")

    best = max(scores, key=lambda m: scores[m]["MRR"])
    print(f"\nbest by MRR: {best}")

    # Where the modes disagree, which is the only part worth reading twice: an
    # average hides a question that got worse behind one that got better.
    disagreements = [
        (question, ranks)
        for question, ranks in found_at.items()
        if len(set(ranks.values())) > 1
    ]
    if disagreements:
        print(
            f"\n{len(disagreements)} questions where the modes disagree "
            "(position of the expected passage, - = not found):\n"
        )
        print(f"{'':52}" + "".join(f"{m:>10}" for m in MODES))
        for question, ranks in disagreements:
            cells = "".join(
                f"{(str(ranks[m]) if ranks[m] else '-'):>10}" for m in MODES
            )
            print(f"{question[:50]:52}{cells}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--set", dest="path", required=True, help="golden set JSON")
    args = parser.parse_args()
    return asyncio.run(_evaluate(Path(args.path)))


if __name__ == "__main__":
    sys.exit(main())
