import logging
import time
import uuid

from fastapi import FastAPI, Request

from app.errors import install_error_handlers
from app.logging import configure_logging, request_id_var
from app.routers import (
    accounts,
    courses,
    diagnostic,
    health,
    mock,
    problems,
    students,
    submissions,
)

configure_logging()
log = logging.getLogger("app.request")

app = FastAPI(title="Adaptive AI-Powered LMS API", version="1.0.0")
install_error_handlers(app)


@app.middleware("http")
async def request_context(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
    token = request_id_var.set(request_id)
    started = time.perf_counter()
    try:
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        log.info(
            "request",
            extra={
                "fields": {
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "ms": round((time.perf_counter() - started) * 1000, 1),
                }
            },
        )
        return response
    finally:
        request_id_var.reset(token)


app.include_router(health.router, prefix="/api/v1")
for module in (accounts, courses, problems, submissions, diagnostic, students, mock):
    app.include_router(module.router, prefix="/api/v1")
