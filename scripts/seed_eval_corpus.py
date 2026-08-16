#!/usr/bin/env python
"""Put the evaluation corpus in the database and point the golden set at it.

    python scripts/seed_eval_corpus.py
    python scripts/eval_retrieval.py --set docs/rag/eval/golden.json

A golden set that only runs against one laptop's database is not a golden set:
the numbers cannot be reproduced, so they cannot be argued with. The corpus
lives in the repository as Markdown, this seeds it, and the content ids in
golden.json are rewritten to whatever the ingestion produced.

Runs the ingestion inline rather than through the API, so it needs no HTTP,
no session and no worker: the corpus is two files, and waiting on a queue to
find out whether they were indexed is a slower way to be told the same thing.
"""

import asyncio
import json
import sys
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.infrastructure.database.session import SessionFactory  # noqa: E402

# Imported for their side effect only: SQLAlchemy resolves foreign keys against
# whatever is registered, and a subject points at the icon and colour
# catalogues. Without these the mappers cannot be configured at all.
from app.modules.catalogs.infrastructure import models as _catalogs  # noqa: E402,F401
from app.modules.documents.infrastructure.models import (  # noqa: E402
    Document,
    DocumentContent,
    DocumentFormat,
)
from app.modules.rag.infrastructure.chunking.chunker import (  # noqa: E402
    chunk_markdown,
)
from app.modules.rag.infrastructure.embedding.cache import (  # noqa: E402
    build_cached_embedder,
)
from app.modules.rag.infrastructure.models import Chunk  # noqa: E402
from app.modules.subjects.infrastructure.models import Subject  # noqa: E402
from app.modules.users.infrastructure.models import User  # noqa: E402

CORPUS = Path("docs/rag/eval/corpus")
GOLDEN = Path("docs/rag/eval/golden.json")
EMAIL = "retrieval-eval@profplan.local"


async def _account(session) -> Subject:
    """The account and subject the corpus hangs off, created once.

    A real account rather than loose rows, because retrieval is scoped by
    ownership everywhere and an evaluation that bypasses the scoping would be
    measuring a query the application never runs.
    """
    user = await session.scalar(select(User).where(User.email == EMAIL))
    if user is None:
        user = User(name="Retrieval Evaluation", email=EMAIL, password_hash=None)
        session.add(user)
        await session.flush()

    subject = await session.scalar(
        select(Subject).where(
            Subject.user_id == user.uuid, Subject.name == "Evaluation"
        )
    )
    if subject is None:
        subject = Subject(user_id=user.uuid, name="Evaluation")
        session.add(subject)
        await session.flush()
    return subject


async def _seed() -> int:
    embedder = build_cached_embedder()
    content_ids: list[str] = []

    async with SessionFactory() as session:
        subject = await _account(session)
        fmt = await session.scalar(
            select(DocumentFormat).where(DocumentFormat.format == "md")
        )
        if fmt is None:
            fmt = DocumentFormat(format="md")
            session.add(fmt)
            await session.flush()

        for path in sorted(CORPUS.glob("*.md")):
            markdown = path.read_text()
            # Replaced rather than added to, so running this twice does not
            # double the corpus and halve every recall number.
            existing = await session.scalar(
                select(Document).where(
                    Document.subject_id == subject.uuid, Document.title == path.stem
                )
            )
            if existing is not None:
                await session.delete(existing)
                await session.flush()

            document = Document(
                subject_id=subject.uuid,
                document_format_id=fmt.uuid,
                title=path.stem,
                original_filename=path.name,
                document_path=f"eval://{uuid4()}",
            )
            session.add(document)
            await session.flush()
            content = DocumentContent(
                document_id=document.uuid, markdown=markdown, version=1
            )
            session.add(content)
            await session.flush()

            pieces = chunk_markdown(markdown)
            embeddings = await embedder.embed_texts(pieces)
            for index, (body, embedding) in enumerate(
                zip(pieces, embeddings, strict=False)
            ):
                session.add(
                    Chunk(
                        document_content_id=content.uuid,
                        chunk_index=index,
                        content=body,
                        embedding=embedding,
                    )
                )
            content_ids.append(str(content.uuid))
            print(f"{path.name}: {len(pieces)} chunks")

        await session.commit()

    golden = json.loads(GOLDEN.read_text())
    golden["content_ids"] = content_ids
    GOLDEN.write_text(json.dumps(golden, indent=2) + "\n")
    print(f"\n{GOLDEN} now points at {len(content_ids)} document contents")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_seed()))
