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

Produce the roadmap for this plan.

Work it out in the `reasoning` field FIRST, before writing a single module: how
many classes the period actually holds, how many modules that fits and what each
one covers, and anything specific the teacher asked for that you must honour (a
date, a topic, an assessment). If reference material was provided, say what you
are taking from it. Then write modules that follow from that reasoning — if the
two disagree, the reasoning is what you got right.

Respond with a SINGLE valid JSON object and NOTHING else (no markdown, no code
fences, no commentary), matching exactly this shape:

{
  "reasoning": "your reasoning, as described above",
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

The `prompt` field is the one that matters most. Another AI receives it alone,
without this roadmap, without the plan parameters and without the teacher's
request — everything it needs must be inside the prompt itself. "Write about
mitosis" is useless. A usable prompt names the audience, the format, the length
and what the output must contain.

## Example

The example below shows the expected level of detail. It is written in English,
but you must answer in the teacher's language.

Plan parameters: Subject: Cell Biology. Period: 2026-03-02 to 2026-03-27.
2 classes/week, 50 min each.

Teacher's request: Introductory unit on the cell for high-school students, with
a hands-on activity and one written test at the end.

{
  "reasoning": "The period is 4 weeks at 2 classes/week, so about 8 classes of 50 min. That fits 2 modules of roughly 4 classes each — enough for the cell as a concept, then its parts. The teacher asked explicitly for a hands-on activity and a written test: the microscopy lab closes module 1, and the test closes module 2 so it can cover both. No reference documents were provided, so I plan from a standard introductory syllabus and keep the depth at high-school level.",
  "summary": "A four-week introduction to cell biology for high-school students, from cell theory to organelles, with a microscopy lab and a written test covering both modules.",
  "modules": [
    {
      "title": "The cell as the unit of life",
      "description": "Cell theory, prokaryotes vs eukaryotes, and observing real cells under a microscope.",
      "items": [
        {
          "title": "Cell theory and the discovery of the cell",
          "kind": "conteudo",
          "when": "semana 1",
          "prompt": "Write the class content for a 50-minute introductory lesson on cell theory, for high-school students with no prior biology. Cover the three postulates of cell theory, the historical path from Hooke and Leeuwenhoek to Schwann and Virchow, and why the microscope was the precondition for the theory. Use plain language, include one analogy for cell size (orders of magnitude vs everyday objects), and end with 3 review questions and their answers."
        },
        {
          "title": "Microscopy lab: observing onion epidermis cells",
          "kind": "atividade",
          "when": "semana 2",
          "prompt": "Write a hands-on lab activity for high-school students, to be run in one 50-minute class, in which they prepare and observe an onion epidermis slide under an optical microscope. Include: materials list (assume a basic school lab), numbered step-by-step preparation instructions, safety notes, what students should draw and label in their report, and 3 guiding questions connecting what they see to cell theory. Add a short teacher's note on the two mistakes students most often make."
        }
      ]
    },
    {
      "title": "Inside the cell",
      "description": "The main organelles, their functions, and closing assessment.",
      "items": [
        {
          "title": "Organelles and their functions",
          "kind": "conteudo",
          "when": "semana 3",
          "prompt": "Write the class content for two 50-minute lessons for high-school students on eukaryotic cell organelles: nucleus, mitochondria, ribosomes, endoplasmic reticulum, Golgi apparatus, lysosomes, and (for plant cells) chloroplasts and cell wall. For each, give its structure in 2-3 sentences, its function, and one consequence of it failing. Include a comparison table of animal vs plant cells and end with 5 review questions with answers."
        },
        {
          "title": "Written test: introduction to the cell",
          "kind": "prova",
          "when": "semana 4",
          "prompt": "Write a 50-minute written test for high-school students covering cell theory, prokaryotes vs eukaryotes, the microscopy lab on onion epidermis, and organelle functions. Structure: 6 multiple-choice questions (4 options each), 2 short-answer questions, and 1 question interpreting a described microscope image. Include the answer key and the point value of each question, totalling 10 points."
        }
      ]
    }
  ]
}
