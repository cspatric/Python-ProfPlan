"""What a notification is about."""

from enum import StrEnum


class NotificationKind(StrEnum):
    """The event a notification reports.

    A kind, not a sentence. The interface is offered in three languages and the
    text is rendered by whoever displays it, from this code plus the row's
    ``params`` — the same reason an API error carries a ``code``. A sentence
    written here would be frozen in whatever language the worker happened to be
    configured with, which is a language nobody chose.
    """

    #: A plan finished generating, with every activity written.
    PLAN_READY = "plan_ready"
    #: A plan finished, but some of its activities failed. The plan is usable.
    PLAN_PARTIAL = "plan_partial"
    #: The plan could not be drafted at all.
    PLAN_FAILED = "plan_failed"
    #: A document finished indexing and is now available to the AI.
    DOCUMENT_INDEXED = "document_indexed"
    #: A document could not be read after exhausting retries.
    DOCUMENT_FAILED = "document_failed"


#: The entity a notification points at, so a client can link to it. Plain
#: strings rather than a second enum: this mirrors the audit trail's `entity`
#: column and is polymorphic for the same reason.
ENTITY_PLAN = "plan"
ENTITY_DOCUMENT = "document"
