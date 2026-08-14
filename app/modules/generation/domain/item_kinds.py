"""The kinds of academic item a plan can contain.

This is the fixed vocabulary shared by three places that used to disagree: the
planner prompt (which asked for "conteudo | atividade | prova | ..." and got
whatever the model felt like), the metadata stored on each item, and the
teacher's own choice of what the plan should be made of.

Keeping it in one enum is what makes the last of those possible. A teacher can
only pick from a list that exists, and "how many exams" only means something if
an exam is a defined thing rather than a word the model happened to write.

The values are Portuguese because the planner has always emitted them in
Portuguese and the stored metadata of existing plans uses them; changing the
strings would orphan every item already generated.
"""

from enum import StrEnum


class ItemKind(StrEnum):
    """What a planned item is."""

    CONTENT = "conteudo"
    READING = "leitura"
    EXERCISES = "exercicios"
    ACTIVITY = "atividade"
    LAB = "laboratorio"
    PROJECT = "projeto"
    SEMINAR = "seminario"
    ASSIGNMENT = "trabalho"
    QUIZ = "quiz"
    EXAM = "prova"
    BIBLIOGRAPHY = "bibliografia"


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

#: Words the model reaches for that mean one of ours. The planner writes in the
#: teacher's language, so an English or Spanish plan comes back with English or
#: Spanish kinds; without this they would all collapse to the fallback.
_ALIASES = {
    "content": ItemKind.CONTENT,
    "lesson": ItemKind.CONTENT,
    "aula": ItemKind.CONTENT,
    "teoria": ItemKind.CONTENT,
    "reading": ItemKind.READING,
    "lectura": ItemKind.READING,
    "exercise": ItemKind.EXERCISES,
    "exercises": ItemKind.EXERCISES,
    "exercicio": ItemKind.EXERCISES,
    "lista": ItemKind.EXERCISES,
    "activity": ItemKind.ACTIVITY,
    "actividad": ItemKind.ACTIVITY,
    "pratica": ItemKind.ACTIVITY,
    "lab": ItemKind.LAB,
    "laboratory": ItemKind.LAB,
    "laboratorio": ItemKind.LAB,
    "project": ItemKind.PROJECT,
    "proyecto": ItemKind.PROJECT,
    "seminar": ItemKind.SEMINAR,
    "apresentacao": ItemKind.SEMINAR,
    "presentation": ItemKind.SEMINAR,
    "assignment": ItemKind.ASSIGNMENT,
    "homework": ItemKind.ASSIGNMENT,
    "tarea": ItemKind.ASSIGNMENT,
    "test": ItemKind.QUIZ,
    "quiz": ItemKind.QUIZ,
    "exam": ItemKind.EXAM,
    "prueba": ItemKind.EXAM,
    "avaliacao": ItemKind.EXAM,
    "examination": ItemKind.EXAM,
    "bibliography": ItemKind.BIBLIOGRAPHY,
    "referencias": ItemKind.BIBLIOGRAPHY,
    "references": ItemKind.BIBLIOGRAPHY,
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
    # Substring last: "prova escrita" and "atividade pratica" are common.
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
