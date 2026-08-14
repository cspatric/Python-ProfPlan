"""Integration tests for the document upload's own field rules.

The title arrives as a multipart form field, not inside a request model, so it
does not inherit any of the schema rules the JSON endpoints get for free. These
tests pin the bounds that were added for it: without them a blank title or one
longer than the column reached the database.
"""

import pytest

pytestmark = pytest.mark.integration

BASE = "/api/v1/documents"
SUBJECTS = "/api/v1/subjects"

_FILE = ("notes.txt", b"a study note", "text/plain")


async def _subject_id(auth_client) -> str:
    created = await auth_client.post(SUBJECTS, json={"name": "Biology"})
    return created.json()["uuid"]


async def test_blank_title_is_rejected(auth_client):
    subject_id = await _subject_id(auth_client)

    resp = await auth_client.post(
        BASE,
        data={"subject_id": subject_id, "title": "   "},
        files={"file": _FILE},
    )

    # Trimmed before the length rule runs, so spaces fail like an empty string.
    assert resp.status_code == 422


async def test_title_longer_than_the_column_is_rejected(auth_client):
    subject_id = await _subject_id(auth_client)

    resp = await auth_client.post(
        BASE,
        data={"subject_id": subject_id, "title": "t" * 256},
        files={"file": _FILE},
    )

    assert resp.status_code == 422


async def test_title_is_trimmed_on_the_way_in(auth_client):
    subject_id = await _subject_id(auth_client)

    resp = await auth_client.post(
        BASE,
        data={"subject_id": subject_id, "title": "  Cell division  "},
        files={"file": _FILE},
    )

    assert resp.status_code == 202
    assert resp.json()["title"] == "Cell division"


async def test_the_response_carries_ingestion_progress(auth_client):
    """The page reads these to show progress and an estimate.

    They are flat fields filled straight from the row, so this test is really
    asking one thing: are they in the payload at all? A missing field here
    turns a minutes-long ingestion back into an indefinite spinner.
    """
    subject_id = await _subject_id(auth_client)

    resp = await auth_client.post(
        BASE,
        data={"subject_id": subject_id, "title": "Progress fields"},
        files={"file": _FILE},
    )

    assert resp.status_code == 202
    body = resp.json()
    for field in (
        "ingestion_chunks_total",
        "ingestion_chunks_done",
        "ingestion_started_at",
    ):
        assert field in body

    listed = await auth_client.get(f"{BASE}?subject_id={subject_id}")
    assert all("ingestion_chunks_total" in doc for doc in listed.json())
