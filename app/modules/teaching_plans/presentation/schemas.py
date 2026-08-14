"""Request/response schemas for teaching plans."""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.generation.domain.item_kinds import ItemKind
from app.modules.generation.presentation.schemas import GenerationResponse
from app.modules.teaching_plans.domain.entities import PlanLevel
from app.shared.validation import OptionalText

# Bounds, named so the message can quote them and the frontend can mirror
# them. They are deliberately generous: the point is to reject nonsense that
# would waste an AI call, not to police how anyone teaches.
MIN_CLASS_DURATION, MAX_CLASS_DURATION = 5, 600
MIN_CLASSES_PER_WEEK, MAX_CLASSES_PER_WEEK = 1, 14
MAX_PLAN_DAYS = 1095  # three years
MAX_AI_INPUT = 4000
#: Per kind, not in total. Twenty exams in one plan is already absurd; the
#: ceiling exists so a typo cannot ask the planner for two thousand items.
MAX_ITEMS_OF_A_KIND = 50


class PlanCreate(BaseModel):
    """Payload to create a plan.

    ``input`` is the teacher's free-text request for the AI — creating a plan
    automatically runs the planner and fans out the item generation.
    """

    subject_id: UUID
    starts_at: date
    ends_at: date
    class_duration: int = Field(
        ge=MIN_CLASS_DURATION,
        le=MAX_CLASS_DURATION,
        description="Class length in minutes",
    )
    class_per_week: int = Field(ge=MIN_CLASSES_PER_WEEK, le=MAX_CLASSES_PER_WEEK)
    # What the plan should be, beyond its calendar. All optional, and all of
    # them reach the planner prompt (see generation/domain/plan_brief.py).
    level: PlanLevel | None = Field(
        default=None, description="how demanding the plan should be"
    )
    audience: OptionalText = Field(
        default=None, max_length=500, description="who the class is, e.g. '9th grade'"
    )
    objectives: OptionalText = Field(
        default=None, max_length=2000, description="what students must be able to do"
    )
    prior_knowledge: OptionalText = Field(
        default=None, max_length=2000, description="what the class already knows"
    )
    resources: OptionalText = Field(
        default=None, max_length=1000, description="lab, computers, none"
    )
    total_weight: float | None = Field(default=None, ge=0)
    academic_items_id: UUID | None = None
    input: OptionalText = Field(
        default=None,
        max_length=MAX_AI_INPUT,
        description="what the teacher wants the AI to plan/generate",
    )
    document_ids: list[UUID] = Field(
        default_factory=list,
        description="documents (of this subject) the AI should generate from",
    )
    # What the plan should be made of. All optional: leaving them out is what
    # the app did until now, and means "planner decides".
    activity_count: int | None = Field(
        default=None,
        ge=0,
        le=MAX_ITEMS_OF_A_KIND,
        description="how many activities the plan must contain",
    )
    exam_count: int | None = Field(
        default=None,
        ge=0,
        le=MAX_ITEMS_OF_A_KIND,
        description="how many exams the plan must contain",
    )
    assignment_count: int | None = Field(
        default=None,
        ge=0,
        le=MAX_ITEMS_OF_A_KIND,
        description="how many assignments the plan must contain",
    )
    item_kinds: list[ItemKind] = Field(
        default_factory=list,
        description="the only kinds of item the plan may contain; empty means any",
    )

    @model_validator(mode="after")
    def _check_composition(self) -> "PlanCreate":
        """A requested count must be of a kind the plan is allowed to contain.

        Asking for three exams while restricting the plan to lessons and
        readings is a contradiction, and the planner would have to break one of
        the two instructions silently. Better to say so here.
        """
        if not self.item_kinds:
            return self
        for count, kind in (
            (self.activity_count, ItemKind.ACTIVITY),
            (self.exam_count, ItemKind.EXAM),
            (self.assignment_count, ItemKind.ASSIGNMENT),
        ):
            if count and kind not in self.item_kinds:
                raise ValueError(
                    f"{count} items of kind '{kind.value}' were requested, but "
                    f"'{kind.value}' is not among the allowed item kinds"
                )
        return self

    def requested_counts(self) -> dict[ItemKind, int]:
        """The counts that were actually asked for, keyed by kind."""
        return {
            kind: count
            for kind, count in (
                (ItemKind.ACTIVITY, self.activity_count),
                (ItemKind.EXAM, self.exam_count),
                (ItemKind.ASSIGNMENT, self.assignment_count),
            )
            if count is not None
        }

    @model_validator(mode="after")
    def _check_dates(self) -> "PlanCreate":
        if self.ends_at < self.starts_at:
            raise ValueError("ends_at must not be before starts_at")
        # An unbounded period is not a plan: the planner would be asked to
        # cover it and would spend an AI call producing something useless.
        if (self.ends_at - self.starts_at).days > MAX_PLAN_DAYS:
            raise ValueError(f"the period must not be longer than {MAX_PLAN_DAYS} days")
        return self


class PlanUpdate(BaseModel):
    """Payload to update a plan (all fields optional)."""

    subject_id: UUID | None = None
    starts_at: date | None = None
    ends_at: date | None = None
    class_duration: int | None = Field(
        default=None, ge=MIN_CLASS_DURATION, le=MAX_CLASS_DURATION
    )
    class_per_week: int | None = Field(
        default=None, ge=MIN_CLASSES_PER_WEEK, le=MAX_CLASSES_PER_WEEK
    )
    level: PlanLevel | None = None
    audience: OptionalText = Field(default=None, max_length=500)
    objectives: OptionalText = Field(default=None, max_length=2000)
    prior_knowledge: OptionalText = Field(default=None, max_length=2000)
    resources: OptionalText = Field(default=None, max_length=1000)
    total_weight: float | None = Field(default=None, ge=0)
    academic_items_id: UUID | None = None


class PlanResponse(BaseModel):
    """Public representation of a plan."""

    model_config = ConfigDict(from_attributes=True)

    uuid: UUID
    user_id: UUID
    subject_id: UUID
    starts_at: date
    ends_at: date
    class_duration: int
    class_per_week: int
    level: PlanLevel | None
    audience: str | None
    objectives: str | None
    prior_knowledge: str | None
    resources: str | None
    total_weight: float | None
    academic_items_id: UUID | None
    created_at: datetime
    updated_at: datetime


class PlanCreatedResponse(PlanResponse):
    """A created plan plus the AI generation kicked off for it.

    ``generation`` is null when the AI could not plan (e.g. all providers
    down) — the plan itself is still created and the generation can be
    retriggered via POST /plans/{id}/generate.
    """

    generation: GenerationResponse | None = None
