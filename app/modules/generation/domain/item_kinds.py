"""The kinds of academic item a plan can contain.

This is the fixed vocabulary shared by three places that used to disagree: the
planner prompt (which asked for "conteudo | atividade | prova | ..." and got
whatever the model felt like), the metadata stored on each item, and the
teacher's own choice of what the plan should be made of.

Keeping it in one enum is what makes the last of those possible. A teacher can
only pick from a list that exists, and "how many exams" only means something if
an exam is a defined thing rather than a word the model happened to write.

The values are English, like everything else in this codebase. They used to be
Portuguese, because that is what the planner emitted and what the stored
metadata of existing plans held — see the migration that rewrote both. Nothing
is orphaned by the change: reading a kind goes through `normalize_kind`, and the
old Portuguese words are in the alias table below, which is where words the
model writes belong.
"""

from enum import StrEnum


class ItemKind(StrEnum):
    """What a planned item is."""

    CONTENT = "content"
    READING = "reading"
    EXERCISES = "exercises"
    ACTIVITY = "activity"
    LAB = "lab"
    PROJECT = "project"
    SEMINAR = "seminar"
    ASSIGNMENT = "assignment"
    QUIZ = "quiz"
    EXAM = "exam"
    BIBLIOGRAPHY = "bibliography"


#: Kinds that produce a mark. Everything else is material to teach or read, and
#: the UI tells the two apart by this set alone.
GRADED_KINDS = frozenset(
    {
        ItemKind.PROJECT,
        ItemKind.SEMINAR,
        ItemKind.ASSIGNMENT,
        ItemKind.QUIZ,
        ItemKind.EXAM,
    }
)

#: Words the model reaches for that mean one of ours.
#:
#: This table is *input data*, not code in another language, and the difference
#: is worth stating because it looks the same in a grep. The planner writes in
#: the teacher's language, so a Portuguese plan comes back with Portuguese kinds
#: and a Spanish one with Spanish; without this they would all collapse to the
#: fallback. The Portuguese entries also cover every row written before the
#: values here were English, so a plan generated then still reads correctly.
_ALIASES = {
    # Portuguese
    "conteudo": ItemKind.CONTENT,
    "aula": ItemKind.CONTENT,
    "teoria": ItemKind.CONTENT,
    "leitura": ItemKind.READING,
    "exercicios": ItemKind.EXERCISES,
    "exercicio": ItemKind.EXERCISES,
    "lista": ItemKind.EXERCISES,
    "atividade": ItemKind.ACTIVITY,
    "pratica": ItemKind.ACTIVITY,
    "laboratorio": ItemKind.LAB,
    "projeto": ItemKind.PROJECT,
    "seminario": ItemKind.SEMINAR,
    "apresentacao": ItemKind.SEMINAR,
    "trabalho": ItemKind.ASSIGNMENT,
    "prova": ItemKind.EXAM,
    "avaliacao": ItemKind.EXAM,
    "bibliografia": ItemKind.BIBLIOGRAPHY,
    "referencias": ItemKind.BIBLIOGRAPHY,
    # Spanish
    "contenido": ItemKind.CONTENT,
    "lectura": ItemKind.READING,
    "ejercicios": ItemKind.EXERCISES,
    "actividad": ItemKind.ACTIVITY,
    "proyecto": ItemKind.PROJECT,
    "tarea": ItemKind.ASSIGNMENT,
    "prueba": ItemKind.EXAM,
    "examen": ItemKind.EXAM,
    # "seminario" and "bibliografia" are spelled the same in both languages and
    # are already above; a second entry would only be a duplicate key.
    # English words the model uses that are not the enum value itself
    "lesson": ItemKind.CONTENT,
    "exercise": ItemKind.EXERCISES,
    "laboratory": ItemKind.LAB,
    "presentation": ItemKind.SEMINAR,
    "homework": ItemKind.ASSIGNMENT,
    "test": ItemKind.QUIZ,
    "examination": ItemKind.EXAM,
}


def normalize_kind(raw: str | None) -> ItemKind:
    """Map whatever the planner wrote onto a kind we know.

    An unrecognised word becomes an activity rather than an error: the item
    itself is fine, and refusing a whole roadmap over one label would throw
    away a good plan and an AI call with it.
    """
    if not raw:
        return ItemKind.ACTIVITY

    text = raw.strip().lower()
    for kind in ItemKind:
        if kind.value == text:
            return kind
    if text in _ALIASES:
        return _ALIASES[text]
    # Substring last: "prova escrita" and "written exam" are both common.
    for word, kind in _ALIASES.items():
        if word in text:
            return kind
    for kind in ItemKind:
        if kind.value in text:
            return kind
    return ItemKind.ACTIVITY


def is_graded(kind: ItemKind) -> bool:
    """Whether this kind of item carries a mark."""
    return kind in GRADED_KINDS
