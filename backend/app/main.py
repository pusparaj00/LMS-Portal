import logging
import time
import uuid

from fastapi import FastAPI, Request
from starlette.concurrency import run_in_threadpool

from app import audit
from app.bodylimit import BodySizeLimit
from app.config import get_settings
from app.errors import error_response, install_error_handlers
from app.logging import REQUEST_ID, configure_logging, request_id_var
from app.ratelimit import client_ip
from app.routers import (
    accounts,
    admin,
    announcements,
    assignments,
    chat,
    consent,
    content,
    courses,
    dashboards,
    diagnostic,
    documents,
    erasure,
    export,
    feedback,
    grading,
    health,
    insight,
    instructor,
    lti,
    me,
    notifications,
    people,
    planner,
    problems,
    quizzes,
    student_work,
    students,
    submissions,
    work,
)

configure_logging()
get_settings()  # read and checked now, so weak production secrets stop the process at start (TR-O-04)
log = logging.getLogger("app.request")

app = FastAPI(title="Adaptive AI-Powered LMS API", version="1.0.0")
app.add_middleware(BodySizeLimit)
install_error_handlers(app)


@app.middleware("http")
async def request_context(request: Request, call_next):
    offered = request.headers.get("X-Request-ID", "")
    request_id = offered if REQUEST_ID.fullmatch(offered) else uuid.uuid4().hex
    token = request_id_var.set(request_id)
    started = time.perf_counter()
    try:
        try:
            response = await call_next(request)
        except Exception:
            # Handled here, not by Starlette, so the request ID is still known and the JSON shape holds.
            log.exception("unhandled error", extra={"fields": {"path": request.url.path}})
            response = error_response(
                500, "internal_error", "Something went wrong on the server. Try again shortly."
            )
        response.headers["X-Request-ID"] = request_id
        user_id = getattr(request.state, "user_id", None)
        ip = client_ip(request)
        await run_in_threadpool(audit.for_response, request.url.path, request.method, response.status_code, user_id, ip)
        log.info(
            "request",
            extra={
                "fields": {
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "ms": round((time.perf_counter() - started) * 1000, 1),
                    "user_id": user_id,
                    "ip": ip,
                }
            },
        )
        return response
    finally:
        request_id_var.reset(token)


app.include_router(health.router, prefix="/api/v1")
for module in (
    accounts, courses, documents, problems, submissions, feedback, diagnostic, students, chat, instructor, export,
    consent, erasure, lti, assignments, announcements, me, admin, student_work, dashboards, content, quizzes, work,
    notifications, planner, people, grading, insight,
):
    app.include_router(module.router, prefix="/api/v1")
app.include_router(work.queue_router, prefix="/api/v1")
