"""Privacy notice and consent (TR-S-05).

A student must have agreed to the current notice before any of their code, answers or messages is processed, and
withdrawing agreement stops that processing at once. The list of model providers in the notice is read from the live
configuration, so the notice cannot name a provider the system does not use, or leave one out.
"""
from typing import Annotated

from fastapi import Depends, HTTPException
from sqlalchemy import Connection, text

from app.auth import Conn, CurrentUser, require_role
from app.config import Settings, get_settings
from app.llm.adapter import GEMINI_KEYS, LOCAL, OPENAI_COMPATIBLE
from app.schemas import ConsentNotice, ConsentProvider, ConsentSection, ConsentStatus

CONSENT_VERSION = "2026-10-v1"  # change it whenever the notice changes; everyone is then asked again
REQUIRED_MESSAGE = (
    "You have not agreed to the privacy notice, or you withdrew your agreement. "
    "Open Privacy in the top bar to read it."
)
PROVIDER_NAME = {
    "gemini": "Google (Gemini)",
    "gemini_pro": "Google (Gemini)",
    "groq": "Groq",
    "openrouter": "OpenRouter, which passes requests on to the maker of the model",
    "mistral": "Mistral AI",
    "openai": "OpenAI",
    LOCAL: "A model run by your institution; requests stay inside it",
}


def configured_providers(settings: Settings) -> list[ConsentProvider]:
    """The providers that could receive a request, in the order they are tried, without repeats."""
    fallbacks = [e.partition(":")[0].strip() for e in settings.llm_fallback.split(",") if e.strip()]
    names = [settings.llm_provider, *fallbacks]
    found: list[ConsentProvider] = []
    for name in names:
        if name == LOCAL:
            usable = bool(settings.local_llm_base_url)
        elif name in GEMINI_KEYS:
            usable = bool(getattr(settings, GEMINI_KEYS[name][0]))
        elif name in OPENAI_COMPATIBLE:
            usable = bool(getattr(settings, OPENAI_COMPATIBLE[name][1]))
        else:
            usable = False  # the stub, or a name that is not a provider
        label = PROVIDER_NAME.get(name)
        if usable and label and label not in {p.name for p in found}:
            order = "first choice" if not found else "only if the one before fails"
            found.append(ConsentProvider(name=label, order=order))
    return found


def notice(settings: Settings) -> ConsentNotice:
    providers = configured_providers(settings)
    return ConsentNotice(
        version=CONSENT_VERSION,
        title="How this system uses your data",
        sections=[
            ConsentSection(heading="What is collected", paragraphs=[
                "The code you run or submit, and the results of running it.",
                "Your answers in the placement test and in practice questions.",
                "Your messages to the assistant.",
                "The mastery estimates calculated from all of the above, and a record of every change to them.",
            ]),
            ConsentSection(heading="Why", paragraphs=[
                "To check your work, estimate what you know, choose your next questions, and explain your mistakes "
                "using your course notes. Nothing is used for advertising or sold.",
            ]),
            ConsentSection(heading="Who receives it", paragraphs=[
                "When you ask for an explanation, a hint or the assistant, the relevant part of your code, the "
                "test results and your message are sent to a model provider so it can write a reply. We do not add "
                "your name or email address. Anything you type yourself is sent as you typed it, so do not put "
                "personal details in your code or messages." if providers else
                "No model provider is configured, so explanations use fixed templates and nothing is sent outside "
                "the system.",
                "Your instructor can see your mastery and progress for the course, and class-level summaries.",
            ]),
            ConsentSection(heading="How long it is kept", paragraphs=[
                "Your data is kept for as long as the course uses this system. Deleting it on request is not "
                "available yet: ask your instructor.",
            ]),
            ConsentSection(heading="Withdrawing", paragraphs=[
                "You can withdraw at any time from Privacy in the top bar. From then on your code, answers and "
                "messages are no longer processed and the assistant and exercises stop working for you. Data "
                "collected before you withdrew stays until it is deleted.",
            ]),
            ConsentSection(heading="Status of this notice", paragraphs=[
                "This notice is a draft. It has not yet been reviewed by the institution's data protection contact.",
            ]),
        ],
        providers=providers,
    )


def status(conn: Connection, user_id: int) -> ConsentStatus:
    row = conn.execute(
        text("SELECT version, accepted_at, withdrawn_at FROM consents WHERE user_id = :u ORDER BY id DESC LIMIT 1"),
        {"u": user_id},
    ).first()
    accepted = row is not None and row.version == CONSENT_VERSION and row.withdrawn_at is None
    return ConsentStatus(
        version=CONSENT_VERSION, accepted=accepted, accepted_at=row.accepted_at if accepted else None,
        withdrawn_at=row.withdrawn_at if row is not None and row.withdrawn_at is not None else None,
    )


def accept(conn: Connection, user_id: int, version: str) -> ConsentStatus:
    if version != CONSENT_VERSION:
        raise HTTPException(409, "the privacy notice has changed; please read it again")
    if not status(conn, user_id).accepted:
        conn.execute(
            text("INSERT INTO consents (user_id, version) VALUES (:u, :v)"), {"u": user_id, "v": CONSENT_VERSION}
        )
    return status(conn, user_id)


def withdraw(conn: Connection, user_id: int) -> ConsentStatus:
    conn.execute(
        text(
            "UPDATE consents SET withdrawn_at = now() WHERE id = (SELECT max(id) FROM consents WHERE user_id = :u)"
            " AND withdrawn_at IS NULL"
        ),
        {"u": user_id},
    )
    return status(conn, user_id)


def consented_student(
    user: Annotated[CurrentUser, Depends(require_role("student"))], conn: Conn
) -> CurrentUser:
    """A student who has agreed to the current notice; anything that processes their data requires this."""
    if not status(conn, user.id).accepted:
        raise HTTPException(403, REQUIRED_MESSAGE)
    return user


def current_notice() -> ConsentNotice:
    return notice(get_settings())
