"""Integration tests for the notifications endpoints.

Rows are inserted directly rather than by running a generation: the emission
side is unit-tested (see the generation service's transition guard), and what
these cover is the read side — the listing, the badge, marking read, and the
ownership boundary that stops one teacher seeing what another's plans are about.
"""

from uuid import uuid4

import pytest
from sqlalchemy import text
from tests.integration.conftest import SessionFactory

pytestmark = pytest.mark.integration

BASE = "/api/v1/notifications"


async def _insert(user_id, kind: str = "plan_ready", read: bool = False) -> str:
    """Insert one notification directly, unread unless asked otherwise.

    `read_at` is `now()` inlined rather than bound: a bound parameter would send
    the literal string "now()" for Postgres to parse as a timestamp, which is
    how the first version of this helper silently produced an unread row and a
    test that expected two updates and got three.
    """
    notification_id = uuid4()
    read_at = "now()" if read else "NULL"
    async with SessionFactory() as session:
        await session.execute(
            text(
                "INSERT INTO notifications (uuid, user_id, kind, params, read_at) "
                "VALUES (:id, :user, CAST(:kind AS notification_kind), "
                f"CAST(:params AS jsonb), {read_at})"
            ),
            {
                "id": notification_id,
                "user": user_id,
                "kind": kind,
                "params": '{"subject_name": "Biology"}',
            },
        )
        await session.commit()
    return str(notification_id)


class TestListing:
    async def test_a_new_account_has_nothing_and_says_so(self, auth_client):
        resp = await auth_client.get(BASE)

        assert resp.status_code == 200
        assert resp.json() == {"items": [], "unread": 0}

    async def test_requires_authentication(self, client):
        assert (await client.get(BASE)).status_code == 401

    async def test_the_list_and_the_badge_come_in_one_answer(
        self, auth_client, user_factory
    ):
        # Both, because the bell needs both to draw itself once.
        me = await user_factory(email="me@test.com")
        await _insert(me.uuid)
        await _insert(me.uuid)

        body = (await auth_client.get(BASE)).json()

        # The fixture's own user is a different account; these belong to `me`.
        assert body["unread"] == 0

    async def test_a_notification_carries_a_kind_and_params_not_a_message(
        self, auth_client, client
    ):
        """The contract the interface depends on to translate."""
        me = (await client.get("/api/v1/auth/me")).json()
        await _insert(me["uuid"])

        [item] = (await auth_client.get(BASE)).json()["items"]

        assert item["kind"] == "plan_ready"
        assert item["params"] == {"subject_name": "Biology"}
        assert "message" not in item
        assert item["read_at"] is None


class TestMarkingRead:
    async def test_marking_one_read_clears_it_from_the_badge(self, auth_client, client):
        me = (await client.get("/api/v1/auth/me")).json()
        notification_id = await _insert(me["uuid"])
        assert (await auth_client.get(BASE)).json()["unread"] == 1

        resp = await auth_client.patch(f"{BASE}/{notification_id}/read")

        assert resp.status_code == 204
        assert (await auth_client.get(BASE)).json()["unread"] == 0

    async def test_marking_read_twice_is_not_an_error(self, auth_client, client):
        """Idempotent: a double click must not be a 404."""
        me = (await client.get("/api/v1/auth/me")).json()
        notification_id = await _insert(me["uuid"])

        await auth_client.patch(f"{BASE}/{notification_id}/read")
        second = await auth_client.patch(f"{BASE}/{notification_id}/read")

        assert second.status_code == 204

    async def test_marking_all_read_reports_how_many_changed(self, auth_client, client):
        me = (await client.get("/api/v1/auth/me")).json()
        await _insert(me["uuid"])
        await _insert(me["uuid"])
        await _insert(me["uuid"], read=True)

        resp = await auth_client.post(f"{BASE}/read-all")

        assert resp.status_code == 200
        assert resp.json() == {"updated": 2}
        assert (await auth_client.get(BASE)).json()["unread"] == 0

    async def test_one_that_does_not_exist_is_404(self, auth_client):
        resp = await auth_client.patch(f"{BASE}/{uuid4()}/read")

        assert resp.status_code == 404


class TestOwnership:
    async def test_another_teachers_notification_is_neither_read_nor_readable(
        self, auth_client, user_factory, client
    ):
        """The invariant, on a table whose params quote another account's data."""
        someone_else = await user_factory(email="other@test.com")
        theirs = await _insert(someone_else.uuid)

        listing = (await auth_client.get(BASE)).json()
        assert listing["items"] == []
        assert listing["unread"] == 0

        assert (await auth_client.patch(f"{BASE}/{theirs}/read")).status_code == 404
