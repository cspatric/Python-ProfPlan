"""Ollama-shaped mock LLM for load testing — answers in ~1ms, costs nothing.

Stands in for Ollama on the compose network (the load-test override points
``OLLAMA_BASE_URL`` here and blanks every paid provider key), so the FULL plan
pipeline — POST /plans → planner → Postgres → Celery fan-out → worker → item
content — runs for real with the LLM step replaced by canned output. This
measures the system, never a model: no tokens billed, no local model pinning
the CPU.

Endpoints (only what the app actually calls):
- ``POST /api/chat``  → planner prompts get a valid Roadmap JSON (sized to pass
  ``check_roadmap`` cleanly so the judge tier is never triggered); judge prompts
  get an approving verdict (belt-and-braces); everything else gets markdown.
- ``POST /api/embed`` → fixed 1024-dim vectors (bge-m3's dimension).
- ``GET  /stats``     → hit counters; the harness uses this as a CANARY: if a
  probe POST /plans does not increment ``chat``, the LLM traffic is going
  somewhere real and the load test aborts before spending anything.
"""

import json
import threading

from fastapi import FastAPI, Request

app = FastAPI()
_lock = threading.Lock()
_hits = {"chat": 0, "embed": 0}

# 4 items for an 8-class period (bounds: 2..12), summary >= 40 chars,
# prompts >= 80 chars, unique titles -> check_roadmap returns no issues.
_PROMPT_PAD = (
    " Cover the core concepts, include worked examples, and align the "
    "difficulty with an introductory undergraduate class."
)
_ROADMAP = json.dumps(
    {
        "reasoning": (
            "The period holds about eight classes, so the plan is split into "
            "two balanced modules of two items each, alternating content and "
            "assessment so every concept is introduced and then verified."
        ),
        "summary": (
            "Two-module plan alternating lecture content with assessments "
            "across the whole period."
        ),
        "modules": [
            {
                "title": "Module 1 - Foundations",
                "description": "Core concepts and first practice.",
                "items": [
                    {
                        "title": "Lecture notes: foundations",
                        "kind": "conteudo",
                        "when": "semana 1",
                        "prompt": "Write lecture notes on the foundations."
                        + _PROMPT_PAD,
                    },
                    {
                        "title": "Practice set: foundations",
                        "kind": "atividade",
                        "when": "semana 2",
                        "prompt": "Create a practice set on the foundations."
                        + _PROMPT_PAD,
                    },
                ],
            },
            {
                "title": "Module 2 - Applications",
                "description": "Applying the concepts and final assessment.",
                "items": [
                    {
                        "title": "Lecture notes: applications",
                        "kind": "conteudo",
                        "when": "semana 3",
                        "prompt": "Write lecture notes on applications." + _PROMPT_PAD,
                    },
                    {
                        "title": "Final assessment",
                        "kind": "prova",
                        "when": "semana 4",
                        "prompt": "Create the final assessment for the plan."
                        + _PROMPT_PAD,
                    },
                ],
            },
        ],
    }
)
_VERDICT = json.dumps({"approved": True, "issues": []})
_ITEM_MD = (
    "# Generated item (mock)\n\nThis content was produced by the load-test "
    "mock LLM in about a millisecond. It exists so the Celery pipeline has a "
    "realistic payload to persist.\n"
)


@app.post("/api/chat")
async def chat(request: Request) -> dict:
    with _lock:
        _hits["chat"] += 1
    body = await request.json()
    system = next(
        (
            m.get("content", "")
            for m in body.get("messages", [])
            if m.get("role") == "system"
        ),
        "",
    )
    if "curriculum planning assistant" in system:
        content = _ROADMAP
    elif "judge" in system.lower() or "review" in system.lower():
        content = _VERDICT
    else:
        content = _ITEM_MD
    return {"message": {"role": "assistant", "content": content}}


@app.post("/api/embed")
async def embed(request: Request) -> dict:
    with _lock:
        _hits["embed"] += 1
    body = await request.json()
    inputs = body.get("input", [])
    if isinstance(inputs, str):
        inputs = [inputs]
    return {"embeddings": [[0.001] * 1024 for _ in inputs]}


@app.get("/stats")
def stats() -> dict:
    with _lock:
        return dict(_hits)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
