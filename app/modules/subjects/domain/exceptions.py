"""Subject domain exceptions."""


class SubjectNotFoundError(Exception):
    """Raised when a subject does not exist or is not owned by the user."""
