"""Integration tests for the plans CRUD flow."""

import pytest

pytestmark = pytest.mark.integration

BASE = "/api/v1/plans"


def _payload(subject_id: str) -> dict:
    return {
        "subject_id": subject_id,
        "starts_at": "2026-08-01",
        "ends_at": "2026-12-15",
        "class_duration": 50,
        "class_per_week": 2,
        "total_weight": 100,
    }


async def test_full_crud(auth_client, subject_id):
    created = await auth_client.post(BASE, json=_payload(subject_id))
    assert created.status_code == 201
    pid = created.json()["uuid"]

    assert (await auth_client.get(BASE)).status_code == 200
    assert (await auth_client.get(f"{BASE}/{pid}")).status_code == 200

    updated = await auth_client.patch(f"{BASE}/{pid}", json={"class_per_week": 3})
    assert updated.status_code == 200
    assert updated.json()["class_per_week"] == 3

    assert (await auth_client.delete(f"{BASE}/{pid}")).status_code == 204


async def test_create_with_unowned_subject_is_rejected(auth_client):
    from uuid import uuid4

    resp = await auth_client.post(BASE, json=_payload(str(uuid4())))
    assert resp.status_code == 422


async def test_create_with_inverted_dates_is_rejected(auth_client, subject_id):
    payload = _payload(subject_id)
    payload["starts_at"], payload["ends_at"] = payload["ends_at"], payload["starts_at"]
    resp = await auth_client.post(BASE, json=payload)
    assert resp.status_code == 422


# ----------------------------------------------------- planning inputs
_DETAILS = {
    "level": "advanced",
    "audience": "second-year undergraduates",
    "objectives": "derive and apply the quadratic formula",
    "prior_knowledge": "first-degree equations",
    "resources": "projector, no lab",
}


async def test_planning_inputs_round_trip(auth_client, subject_id):
    """They are only useful if they survive the trip to Postgres and back."""
    created = await auth_client.post(BASE, json=_payload(subject_id) | _DETAILS)

    assert created.status_code == 201
    body = created.json()
    for field, value in _DETAILS.items():
        assert body[field] == value

    fetched = await auth_client.get(f"{BASE}/{body['uuid']}")
    assert {k: fetched.json()[k] for k in _DETAILS} == _DETAILS


async def test_planning_inputs_are_optional(auth_client, subject_id):
    """A plan with only a calendar keeps working exactly as before."""
    created = await auth_client.post(BASE, json=_payload(subject_id))

    assert created.status_code == 201
    assert all(created.json()[field] is None for field in _DETAILS)


async def test_planning_inputs_can_be_edited(auth_client, subject_id):
    pid = (await auth_client.post(BASE, json=_payload(subject_id))).json()["uuid"]

    updated = await auth_client.patch(
        f"{BASE}/{pid}", json={"level": "introductory", "audience": "9th grade"}
    )

    assert updated.status_code == 200
    assert updated.json()["level"] == "introductory"
    assert updated.json()["audience"] == "9th grade"


async def test_an_unknown_level_is_rejected(auth_client, subject_id):
    resp = await auth_client.post(
        BASE, json=_payload(subject_id) | {"level": "impossible"}
    )

    assert resp.status_code == 422


# ------------------------------------------------------- field validation
async def test_class_duration_out_of_range_is_rejected(auth_client, subject_id):
    """gt=0 alone accepted a 999999-minute class."""
    too_long = await auth_client.post(
        BASE, json=_payload(subject_id) | {"class_duration": 999_999}
    )
    too_short = await auth_client.post(
        BASE, json=_payload(subject_id) | {"class_duration": 1}
    )

    assert too_long.status_code == 422
    assert too_short.status_code == 422


async def test_classes_per_week_out_of_range_is_rejected(auth_client, subject_id):
    resp = await auth_client.post(
        BASE, json=_payload(subject_id) | {"class_per_week": 500}
    )

    assert resp.status_code == 422


async def test_an_absurdly_long_period_is_rejected(auth_client, subject_id):
    """A plan the planner could never cover is not worth an AI call."""
    resp = await auth_client.post(
        BASE,
        json=_payload(subject_id)
        | {"starts_at": "2026-01-01", "ends_at": "2200-01-01"},
    )

    assert resp.status_code == 422


async def test_the_ai_instruction_is_bounded(auth_client, subject_id):
    """It goes straight into the prompt, so it cannot be unbounded."""
    resp = await auth_client.post(
        BASE, json=_payload(subject_id) | {"input": "x" * 5000}
    )

    assert resp.status_code == 422


async def test_blank_planning_fields_are_stored_as_null(auth_client, subject_id):
    """An empty string reaches the prompt as a fact about the class."""
    resp = await auth_client.post(
        BASE,
        json=_payload(subject_id) | {"audience": "   ", "objectives": ""},
    )

    assert resp.status_code == 201
    assert resp.json()["audience"] is None
    assert resp.json()["objectives"] is None


async def test_planning_fields_are_trimmed(auth_client, subject_id):
    resp = await auth_client.post(
        BASE, json=_payload(subject_id) | {"audience": "  9th grade  "}
    )

    assert resp.json()["audience"] == "9th grade"


async def test_requested_counts_must_be_of_an_allowed_kind(auth_client, subject_id):
    """Asking for exams while banning exams is a contradiction, not a plan."""
    resp = await auth_client.post(
        BASE,
        json={
            "subject_id": subject_id,
            "starts_at": "2026-09-01",
            "ends_at": "2026-10-01",
            "class_duration": 50,
            "class_per_week": 2,
            "exam_count": 2,
            "item_kinds": ["conteudo", "leitura"],
        },
    )

    assert resp.status_code == 422
    assert "prova" in resp.text


async def test_composition_within_the_allowed_kinds_is_accepted(
    auth_client, subject_id
):
    resp = await auth_client.post(
        BASE,
        json={
            "subject_id": subject_id,
            "starts_at": "2026-09-01",
            "ends_at": "2026-10-01",
            "class_duration": 50,
            "class_per_week": 2,
            "activity_count": 4,
            "exam_count": 1,
            "assignment_count": 1,
            "item_kinds": ["conteudo", "atividade", "prova", "trabalho"],
        },
    )

    assert resp.status_code == 201


async def test_an_unknown_item_kind_is_rejected(auth_client, subject_id):
    resp = await auth_client.post(
        BASE,
        json={
            "subject_id": subject_id,
            "starts_at": "2026-09-01",
            "ends_at": "2026-10-01",
            "class_duration": 50,
            "class_per_week": 2,
            "item_kinds": ["dissertacao-de-mestrado"],
        },
    )

    assert resp.status_code == 422


async def test_a_count_beyond_the_ceiling_is_rejected(auth_client, subject_id):
    resp = await auth_client.post(
        BASE,
        json={
            "subject_id": subject_id,
            "starts_at": "2026-09-01",
            "ends_at": "2026-10-01",
            "class_duration": 50,
            "class_per_week": 2,
            "activity_count": 500,
        },
    )

    assert resp.status_code == 422
