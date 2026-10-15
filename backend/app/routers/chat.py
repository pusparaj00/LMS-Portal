"""Chat endpoint (F-50 to F-53, TR-D-08). Every message is routed, handled and logged."""
import json
from collections.abc import Iterator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import Connection, text

from app.auth import Conn, CurrentUser, require_role
from app.chat import handlers, history, routing
from app.config import get_settings
from app.db import get_chat_engine, get_redis
from app.llm.adapter import LLMAdapter
from app.routers.feedback import llm_adapter
from app.schemas import ChatRequest, ChatResponse, RouterInfo

router = APIRouter(tags=["chat"])
Student = Annotated[CurrentUser, Depends(require_role("student"))]


def chat_connection() -> Iterator[Connection]:
    """The read-only role: handlers can read mastery through it and cannot write anything."""
    if not get_settings().chat_database_url:
        raise HTTPException(503, "chat is not configured")
    with get_chat_engine().connect() as conn:
        yield conn


@router.post("/chat", response_model=ChatResponse)
def chat(
    body: ChatRequest,
    user: Student,
    conn: Conn,
    chat_conn: Annotated[Connection, Depends(chat_connection)],
    adapter: Annotated[LLMAdapter, Depends(llm_adapter)],
):
    settings = get_settings()
    r = get_redis()
    past = history.window(r, user.id, body.problem_id, settings.chat_history_turns)

    if body.route is not None:
        decision = routing.Decision(body.route, None, "student", "chosen by the student")
    else:
        decision = routing.classify(adapter, body.message, settings.router_min_confidence)
    provider = getattr(adapter.config, "provider", None)

    turn = handlers.Turn(
        conn=conn, chat_conn=chat_conn, user_id=user.id, problem_id=body.problem_id, message=body.message,
        adapter=adapter, settings=settings, history=past,
    )
    reply = handlers.handle(decision.route, turn)
    router_info = RouterInfo(
        how=decision.how, confidence=decision.confidence, reason=decision.reason,
        provider=getattr(adapter.config, "provider", provider),
    )

    cited = [s.model_dump(include={"chunk_id", "title", "section"}) for s in reply.sources]
    meta = {"router": router_info.model_dump(), "tools": reply.tools, "problem_id": body.problem_id}
    conn.execute(
        text(
            "INSERT INTO chat_messages (user_id, role, content, route, sources) VALUES (:u, 'user', :c, :r, :s)"
        ),
        {"u": user.id, "c": body.message, "r": decision.route, "s": json.dumps({"router": meta["router"]})},
    )
    message_id = conn.execute(
        text(
            "INSERT INTO chat_messages (user_id, role, content, route, sources)"
            " VALUES (:u, 'assistant', :c, :r, :s) RETURNING id"
        ),
        {
            "u": user.id, "c": reply.text, "r": decision.route,
            "s": json.dumps({**meta, "sources": cited}),
        },
    ).scalar_one()
    history.append(r, user.id, settings.chat_history_turns, body.message, reply.text)
    return ChatResponse(
        message_id=message_id, reply=reply.text, route=decision.route, router=router_info, tools=reply.tools,
        sources=reply.sources,
    )
