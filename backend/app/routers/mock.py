from typing import Annotated

from fastapi import APIRouter, Depends

from app.auth import CurrentUser, require_role
from app.config import get_settings
from app.llm.adapter import build_adapter
from app.schemas import (
    ChatRequest,
    ChatResponse,
    )

router = APIRouter()
Student = Annotated[CurrentUser, Depends(require_role("student"))]


@router.post("/chat", response_model=ChatResponse, tags=["chat"])
def chat(body: ChatRequest, user: Student):
    adapter = build_adapter(get_settings())
    return ChatResponse(reply=adapter.complete("", body.message), route="general", sources=[])
