"""The structured roadmap the planner agent must return.

The planner does NOT write prose — it returns a machine-readable plan of what
to generate. Each item carries the exact sub-prompt that a worker will later
send to the LLM, so the fan-out is fully driven by the planner's output.
"""

from pydantic import BaseModel, Field


class PlannedItem(BaseModel):
    """One academic item the plan should contain (a subtask to generate)."""

    title: str = Field(min_length=1, max_length=255)
    kind: str = Field(
        min_length=1,
        max_length=64,
        description="e.g. prova, atividade, conteudo, bibliografia",
    )
    when: str | None = Field(
        default=None, description="target date/week, e.g. 'dia 20' or 'semana 3'"
    )
    prompt: str = Field(
        min_length=1, description="the exact request to send to the LLM for this item"
    )


class PlannedModule(BaseModel):
    """A unit/module of the plan grouping several items."""

    title: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    items: list[PlannedItem] = Field(min_length=1)


class Roadmap(BaseModel):
    """The full plan the planner agent produced."""

    summary: str = Field(min_length=1, max_length=2000)
    modules: list[PlannedModule] = Field(min_length=1)

    def item_count(self) -> int:
        return sum(len(m.items) for m in self.modules)
