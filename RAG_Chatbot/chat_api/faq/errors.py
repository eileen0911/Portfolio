class FAQValidationError(ValueError):
    """Raised when an FAQ flow config is not safe to load."""


class FAQFlowError(ValueError):
    """Raised when an FAQ flow transition is invalid."""
