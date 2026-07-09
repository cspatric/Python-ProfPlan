# Planner prompt

<!--
This file is the FIRST prompt sent to the AI when a plan is created.
Edit it freely — the code loads it at call time and replaces the tokens:
  [[PLAN_INFO]]      -> plan parameters (period, classes/week, duration)
  [[TEACHER_INPUT]]  -> the teacher's free-text request
  [[CONTEXT_BLOCK]]  -> RAG excerpts from the teacher's documents (may be empty)
Everything below the divider is sent verbatim (tokens replaced).
-->

---

Plan parameters:
[[PLAN_INFO]]

Teacher's request:
[[TEACHER_INPUT]]
[[CONTEXT_BLOCK]]

Produce the roadmap for this plan. Respond with a SINGLE valid JSON object and
NOTHING else (no markdown, no code fences, no commentary), matching exactly
this shape:

{
  "summary": "one short paragraph describing the plan",
  "modules": [
    {
      "title": "module/unit title",
      "description": "what this module covers",
      "items": [
        {
          "title": "item title",
          "kind": "conteudo | atividade | prova | bibliografia | ...",
          "when": "optional target, e.g. 'semana 2' or 'dia 20' or null",
          "prompt": "a self-contained instruction telling another AI exactly what to generate for this item"
        }
      ]
    }
  ]
}

Every item's `prompt` must be specific enough that another AI can generate that
item without seeing this roadmap.
