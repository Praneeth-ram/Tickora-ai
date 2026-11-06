"""Application error types and the single JSON error format used by the API.

Every error response has this shape:

    {
      "detail": "<message>",            # kept for existing clients
      "error": {
        "code": "<machine_readable_code>",
        "message": "<message>",
        "details": <optional structured data or null>
      }
    }
"""
import logging
from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.services.date_resolver import InvalidDateError
from backend.services.dynamic_query_service import QueryPlanError
from backend.services.llm_chat_service import ModelServiceError, PlanRejectedError
from backend.exceptions import AppError, NotFoundError, ServiceUnavailableError


logger = logging.getLogger(__name__)

_HTTP_CODES = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    422: "validation_failed",
    429: "rate_limited",
    503: "service_unavailable",
}


def error_body(code: str, message: str, details=None) -> dict:
    return {
        "detail": message,
        "error": {"code": code, "message": message, "details": details},
    }


async def _app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=error_body(exc.code, exc.message, jsonable_encoder(exc.details)),
    )


async def _http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    message = exc.detail if isinstance(exc.detail, str) else "Request failed."
    return JSONResponse(
        status_code=exc.status_code,
        content=error_body(_HTTP_CODES.get(exc.status_code, "http_error"), message),
        headers=exc.headers,
    )


async def _validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content=error_body(
            "validation_failed",
            "The request is invalid.",
            jsonable_encoder(exc.errors()),
        ),
    )


async def _query_error_handler(request: Request, exc: Exception) -> JSONResponse:
    # Raised when a question cannot be turned into a supported database query.
    return JSONResponse(
        status_code=400,
        content=error_body("bad_request", str(exc)),
    )


async def _plan_rejected_handler(request: Request, exc: PlanRejectedError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content=error_body("plan_rejected", str(exc)),
    )


async def _model_error_handler(request: Request, exc: ModelServiceError) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content=error_body("service_unavailable", str(exc)),
    )


async def _unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    # Log the full traceback server-side; never send it to the client.
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content=error_body("internal_error", "An unexpected error occurred."),
    )


def register_exception_handlers(app: FastAPI) -> None:
    # Starlette chooses the most specific class in the MRO, so subclasses
    # such as PlanRejectedError use their own handler.
    app.add_exception_handler(AppError, _app_error_handler)
    # Base Starlette class: also catches routing 404s and FastAPI HTTPException.
    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)
    app.add_exception_handler(RequestValidationError, _validation_error_handler)
    app.add_exception_handler(QueryPlanError, _query_error_handler)
    app.add_exception_handler(InvalidDateError, _query_error_handler)
    app.add_exception_handler(PlanRejectedError, _plan_rejected_handler)
    app.add_exception_handler(ModelServiceError, _model_error_handler)
    app.add_exception_handler(Exception, _unhandled_error_handler)
