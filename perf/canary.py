"""Canary: prove the plan pipeline hits the MOCK LLM before any load is run.

run.sh executes this (in the locust image, on the compose network) before an
E2E run. It creates ONE probe plan and checks the mock's hit counter moved.
Only if that proof holds does run.sh pass MOCK_VERIFIED=1 to locust — the flag
that unlocks POST /plans in the harness. Any doubt → non-zero exit → no run.

Exit codes: 0 = verified; anything else = abort the load test.
"""

import json
import sys

import requests

API_HOST = "http://api:8000"
MOCK_HOST = "http://mockllm:9999"
POOL_FILE = "/mnt/locust/results/.pool.json"
API = "/api/v1"


def fail(msg: str) -> None:
    print(f"CANARY FAIL: {msg}", file=sys.stderr)
    sys.exit(1)


def main() -> None:
    with open(POOL_FILE) as fh:
        cookies = json.load(fh)[0]
    headers = {"X-CSRF-Token": cookies.get("csrf_token", "")}

    before = requests.get(f"{MOCK_HOST}/stats", timeout=10).json()

    subjects = requests.get(
        f"{API_HOST}{API}/subjects?limit=1", cookies=cookies, timeout=30
    )
    if subjects.status_code != 200 or not subjects.json():
        fail(f"could not fetch a subject: {subjects.status_code}")
    subject_id = subjects.json()[0]["uuid"]

    resp = requests.post(
        f"{API_HOST}{API}/plans",
        cookies=cookies,
        headers=headers,
        json={
            "subject_id": subject_id,
            "starts_at": "2026-03-01",
            "ends_at": "2026-03-29",
            "class_duration": 50,
            "class_per_week": 2,
            "input": "Canary probe: plan a four-week introductory unit.",
        },
        timeout=60,
    )
    if resp.status_code != 201:
        fail(f"probe POST /plans returned {resp.status_code}: {resp.text[:200]}")
    generation = (resp.json() or {}).get("generation")
    if not generation:
        fail("plan created but generation is null — planner did not run")

    after = requests.get(f"{MOCK_HOST}/stats", timeout=10).json()
    if after["chat"] <= before["chat"]:
        fail(
            "the probe plan did NOT hit the mock LLM "
            f"(chat hits {before['chat']} -> {after['chat']}). "
            "LLM traffic is going somewhere else — ABORTING."
        )

    print(
        f"CANARY OK: probe plan hit the mock (chat {before['chat']} -> "
        f"{after['chat']}, embed {before['embed']} -> {after['embed']}), "
        f"generation {generation['uuid']} queued."
    )


if __name__ == "__main__":
    main()
