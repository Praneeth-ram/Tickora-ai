class ModelServiceError(RuntimeError):
    """Raised when a question cannot be answered from the query plan."""


class ModelUnavailableError(ModelServiceError):
    """The model server cannot be reached or timed out."""


class PlanRejectedError(ModelServiceError):
    """The model server responded, but could not turn the question into a supported plan."""
