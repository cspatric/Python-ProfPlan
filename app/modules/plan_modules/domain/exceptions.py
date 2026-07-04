"""Plan-module domain exceptions."""


class ModuleNotFoundError(Exception):
    """Raised when a module does not exist or is not owned by the user."""


class InvalidPlanError(Exception):
    """Raised when the referenced plan does not belong to the user."""
