# backend/exceptions.py
"""Application error classes. This module must not import other project modules."""
from fastapi import status

class AppError(Exception):
    """Base class for errors raised deliberately by application code."""

    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    code: str = "internal_error"

    def __init__(self, message: str, *, details=None):
        super().__init__(message)
        self.message = message
        self.details = details

class BadRequestError(AppError):
    status_code = status.HTTP_400_BAD_REQUEST
    code = "bad_request"

class UnauthorizedError(AppError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "unauthorized"

class ForbiddenError(AppError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "forbidden"

class NotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "not_found"

class ValidationFailedError(AppError):
    status_code = 422
    code = "validation_failed"

class ServiceUnavailableError(AppError):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    code = "service_unavailable"