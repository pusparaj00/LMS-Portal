from typing import Annotated

from fastapi import APIRouter, Depends

from app.auth import CurrentUser, require_role
from app.schemas import ChatRequest, ChatResponse

router = APIRouter()
Student = Annotated[CurrentUser, Depends(require_role("student"))]

CANNED_REPLY = "This is a canned reply from the stub LLM adapter."


@router.post("/chat", response_model=ChatResponse, tags=["chat"])
def chat(body: ChatRequest, user: Student):
    """Placeholder until the chat router exists: a fixed reply, never an unchecked model reply."""
    return ChatResponse(reply=CANNED_REPLY, route="general", sources=[])
