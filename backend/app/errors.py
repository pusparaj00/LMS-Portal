from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import TimeoutError as PoolTimeout
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.logging import request_id_var
from app.sandbox import RETRY_AFTER_SECONDS, SandboxBusy, SandboxUnavailable
from app.schemas import ErrorBody, ErrorResponse


def error_response(status: int, code: str, message: str) -> JSONResponse:
    body = ErrorResponse(
        error=ErrorBody(code=code, message=message, request_id=request_id_var.get())
    )
    return JSONResponse(status_code=status, content=body.model_dump())


def sandbox_error(exc: SandboxUnavailable) -> HTTPException:
    """A full queue says so and asks the client to retry (the interface does, automatically); a down runner does not."""
    if isinstance(exc, SandboxBusy):
        return HTTPException(
            503, "The sandbox is busy right now. Please try again in a moment.",
            headers={"Retry-After": str(RETRY_AFTER_SECONDS)},
        )
    return HTTPException(503, "sandbox unavailable, try again shortly")


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        response = error_response(exc.status_code, "http_error", str(exc.detail))
        response.headers.update(exc.headers or {})
        return response

    @app.exception_handler(PoolTimeout)
    async def pool_busy(request: Request, exc: PoolTimeout) -> JSONResponse:
        """Every database connection is in use: say so and ask the client to retry, instead of a 500."""
        response = error_response(503, "busy", "The system is busy right now. Please try again in a moment.")
        response.headers["Retry-After"] = str(RETRY_AFTER_SECONDS)
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        return error_response(422, "validation_error", str(exc.errors()))
