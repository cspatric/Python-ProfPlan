"""Teaching plan domain exceptions."""


class PlanNotFoundError(Exception):
    """Raised when a plan does not exist or is not owned by the user."""


class InvalidSubjectError(Exception):
    """Raised when the referenced subject does not belong to the user."""
