from fastapi import APIRouter

from app.config import get_settings
from app.llm.adapter import build_adapter
from app.schemas import (
    ChatRequest,
    ChatResponse,
    DiagnosticAnswerRequest,
    DiagnosticAnswerResponse,
    DiagnosticStartResponse,
    LoginRequest,
    Problem,
    ProblemCreate,
    ProblemList,
    RegisterRequest,
    SubmissionCreate,
    SubmissionResult,
    TokenResponse,
)

router = APIRouter()


@router.post("/auth/register", response_model=TokenResponse, status_code=201, tags=["auth"])
def register(body: RegisterRequest):
    return TokenResponse.mock()


@router.post("/auth/login", response_model=TokenResponse, tags=["auth"])
def login(body: LoginRequest):
    return TokenResponse.mock()


@router.get("/problems", response_model=ProblemList, tags=["problems"])
def list_problems(course_id: int):
    return ProblemList.mock()


@router.post("/problems", response_model=Problem, status_code=201, tags=["problems"])
def create_problem(body: ProblemCreate):
    return Problem.mock()


@router.post("/submissions", response_model=SubmissionResult, tags=["submissions"])
def create_submission(body: SubmissionCreate):
    return SubmissionResult.mock()


@router.post("/diagnostic/start", response_model=DiagnosticStartResponse, tags=["diagnostic"])
def diagnostic_start():
    return DiagnosticStartResponse.mock()


@router.post("/diagnostic/answer", response_model=DiagnosticAnswerResponse, tags=["diagnostic"])
def diagnostic_answer(body: DiagnosticAnswerRequest):
    return DiagnosticAnswerResponse.mock()


@router.post("/chat", response_model=ChatResponse, tags=["chat"])
def chat(body: ChatRequest):
    adapter = build_adapter(get_settings())
    return ChatResponse(reply=adapter.complete("", body.message), route="general", sources=[])
