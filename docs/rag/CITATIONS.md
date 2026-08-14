# Where an activity came from

This exists because of a specific failure. The AI wrote several confident
paragraphs about software architecture for a plan whose only uploaded document
was a machine learning book, and nothing in the application could say whether
that came from the book or from the model's own memory. On the page, grounded
text and invented text look exactly alike.

Now every generated activity records the passages it was written from, and the
page shows them.

## What is recorded

`academic_item_source`, one row per passage, per activity:

| column | why |
| --- | --- |
| `rank` | 1-based, the same number the prompt printed, so a "[2]" in the generated text points at the second citation |
| `excerpt` | **a copy** of the passage as it was sent to the model |
| `section` | the heading breadcrumb, e.g. `Chapter 2 > Gradient Descent` |
| `distance` | cosine distance at retrieval time |
| `document_id` | so a citation can name the file |
| `chunk_id` | a soft pointer, no foreign key |

**The passage is copied, not referenced.** Re-ingesting a document replaces
every one of its chunks, so a citation that were only a foreign key would break
exactly when somebody uploads a corrected file, which is the moment they most
want to know what the plan was based on. What is recorded is not what the
document says today: it is what was put in front of the model that day, which
is the only thing that can support or contradict what it then wrote.

**`chunk_id` has no foreign key on purpose.** It is a convenience, and a
re-ingestion landing between retrieval and the insert must never fail an
activity over a pointer. Uuids are not reused, so a dangling id is dangling
rather than pointing at somebody else's passage.

**Regenerating replaces the rows.** An activity rewritten from other passages
must not keep the old ones; they would attribute the new text to material that
had nothing to do with it.

## What the reader sees

`GET /api/v1/academic-items/{id}/sources` returns them in order, with the
document title and a similarity (`1 - distance`, so 1.0 is identical). The
activity page draws them beside the material, each with the section it came
from and the passage itself.

The similarity is shown as a word, not a number: 0.62 means nothing to a
teacher, and the only useful distinction is "this really is about that" against
"this was the nearest thing in your documents". A weak match presented without
that caveat is a citation flattering itself.

**The empty state is the point.** An activity with no sources says so: *"No
source document. The AI wrote this from its own knowledge, so check it against
your material before handing it out."* That is not an error message, it is the
answer, and it is the one the original failure needed.

Hand-made activities are excluded, they never claimed a source, so the panel
would be answering a question nobody asked.

## The limits, stated

- **Sources are per activity, not per sentence.** The panel says which
  passages fed the activity, not which sentence came from which. Sentence-level
  attribution needs the model to cite as it writes, and a model that is asked
  to cite will cite whether or not it used the source.
- **The planner's own retrieval is not recorded.** The roadmap is drafted from
  its own context; only the activities carry citations.
- **A source is not proof.** It is what the model was shown. It can still have
  written around it, which is what the similarity label is for.

## Verified on 2026-08-14

A document with three unmistakable sections (light reactions, the Calvin cycle,
student misconceptions) uploaded, indexed into 3 chunks, and a plan generated
from it. Each activity cited the section it was actually about:

| activity | closest citation | distance |
| --- | --- | --- |
| A Origem da Massa Vegetal | Common student misconceptions | 0.253 |
| Reações Luminosas e o Ciclo de Calvin | Photosynthesis: the light reactions | 0.292 |
| Introdução à Respiração Celular | The Calvin cycle | 0.369 |

The generated lesson on plant mass used van Helmont's willow, 74 kg gained
against 57 grams of soil lost, which appears nowhere but in the uploaded file.
Read on the page at `/subjects/{id}/plans/{id}/items/{id}`, not only in SQL.
