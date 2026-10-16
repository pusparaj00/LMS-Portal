"""LTI 1.3 endpoints (TR-A-09, F-70). The first two are visited by the browser during a launch from the LMS; the third
swaps the launch's one-time code for an ordinary session in this app."""
import html
from urllib.parse import parse_qsl

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from starlette.concurrency import run_in_threadpool

from app import audit, lti, ratelimit
from app.auth import create_token
from app.config import get_settings
from app.db import get_engine, get_redis
from app.schemas import LtiCode, LtiSession

router = APIRouter(prefix="/lti", tags=["lti"])


def _page(status: int, message: str) -> HTMLResponse:
    body = (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'><title>Adaptive LMS</title>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'></head>"
        "<body style='font-family:system-ui,sans-serif;max-width:36rem;margin:3rem auto;padding:0 1rem'>"
        f"<h1>The tool could not be opened</h1><p>{html.escape(message)}</p></body></html>"
    )
    return HTMLResponse(body, status_code=status)


def _base_url() -> str:
    base = get_settings().tool_base_url.rstrip("/")
    if not base:
        raise HTTPException(404, "LTI is not configured")
    return base


def _refused(exc: lti.LaunchRefused, ip: str, stage: str) -> HTMLResponse:
    audit.record("lti.launch_refused", ip=ip, status=403,
                 detail={"stage": stage, "reason": exc.reason, "detail": exc.detail[:200]})
    return _page(403, exc.message)


async def _params(request: Request) -> dict[str, str]:
    params = dict(request.query_params)
    if request.method == "POST":
        params.update(parse_qsl((await request.body()).decode("utf-8", "replace")))
    return params


@router.get("/login", response_class=HTMLResponse)
async def login_get(request: Request) -> Response:
    """OIDC login initiation from the platform, sent as a redirect."""
    return await _login(request)


@router.post("/login", response_class=HTMLResponse)
async def login_post(request: Request) -> Response:
    """OIDC login initiation from the platform, sent as a form post."""
    return await _login(request)


async def _login(request: Request) -> Response:
    base = _base_url()
    ip = ratelimit.client_ip(request)
    ratelimit.check("lti", ip)
    params = await _params(request)

    def start():
        with get_engine().connect() as conn:
            return lti.start_login(conn, get_redis(), params, base)

    try:
        url, state = await run_in_threadpool(start)
    except lti.LaunchRefused as exc:
        return _refused(exc, ip, "login")
    response = RedirectResponse(url, status_code=302)
    secure = base.startswith("https://")
    # In a new window the launch is first-party; over HTTPS the cookie must also survive the platform's cross-site POST.
    response.set_cookie(
        lti.state_cookie_name(state), state, max_age=lti.STATE_TTL_SECONDS, httponly=True, secure=secure,
        samesite="none" if secure else "lax", path="/api/v1/lti",
    )
    return response


@router.post("/launch", response_class=HTMLResponse)
async def launch(request: Request) -> Response:
    """The signed launch from the platform: checked, then mapped to an account and a course."""
    base = _base_url()
    ip = ratelimit.client_ip(request)
    ratelimit.check("lti", ip)
    form = await _params(request)

    def run():
        r = get_redis()
        with get_engine().begin() as conn:
            checked = lti.validate(conn, r, form, dict(request.cookies), base)
            user_id, course_id = lti.provision(conn, checked)
            audit.record("lti.launch", user_id=user_id, ip=ip, status=303, conn=conn,
                         detail={"platform_id": checked.platform.id, "course_id": course_id, "role": checked.role})
        return lti.issue_code(r, user_id, checked.role, course_id)

    try:
        code = await run_in_threadpool(run)
    except lti.LaunchRefused as exc:
        return _refused(exc, ip, "launch")
    response = RedirectResponse(f"{base}/#/lti/{code}", status_code=303)
    if form.get("state"):
        response.delete_cookie(lti.state_cookie_name(form["state"]), path="/api/v1/lti")
    return response


@router.post("/session", response_model=LtiSession)
def session(body: LtiCode, request: Request):
    """Swap a launch's one-time code (valid for a minute, usable once) for a session token."""
    ratelimit.check("lti", ratelimit.client_ip(request))
    found = lti.redeem_code(get_redis(), body.code)
    if found is None:
        raise HTTPException(404, "this launch link has expired or was already used; open the tool again from the LMS")
    return LtiSession(
        access_token=create_token(found["user_id"], found["role"]), token_type="bearer", role=found["role"],
        course_id=found["course_id"],
    )
