from typing import Annotated

from fastapi import APIRouter, Depends

from app.auth import CurrentUser, require_role
from app.config import get_settings
from app.llm.adapter import build_adapter
from app.schemas import (
    ChatRequest,
    ChatResponse,
    DiagnosticAnswerRequest,
    DiagnosticAnswerResponse,
    DiagnosticStartResponse,
)

router = APIRouter()
Student = Annotated[CurrentUser, Depends(require_role("student"))]


@router.post("/diagnostic/start", response_model=DiagnosticStartResponse, tags=["diagnostic"])
def diagnostic_start(user: Student):
    return DiagnosticStartResponse.mock()


@router.post("/diagnostic/answer", response_model=DiagnosticAnswerResponse, tags=["diagnostic"])
def diagnostic_answer(body: DiagnosticAnswerRequest, user: Student):
    return DiagnosticAnswerResponse.mock()


@router.post("/chat", response_model=ChatResponse, tags=["chat"])
def chat(body: ChatRequest, user: Student):
    adapter = build_adapter(get_settings())
    return ChatResponse(reply=adapter.complete("", body.message), route="general", sources=[])
