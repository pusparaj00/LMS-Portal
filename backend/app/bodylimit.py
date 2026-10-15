"""Maximum request size (TR-S-04). Pure ASGI so it also stops bodies that arrive without a Content-Length."""
import json
import re

MAX_BODY_BYTES = 600_000  # a 50,000 character submission is well under this even in UTF-8
NOTES_PATH = re.compile(r"^/api/v1/courses/\d+/documents/?$")
MAX_NOTES_BODY_BYTES = 6_000_000  # a PDF of up to 4 MB, sent as base64 inside JSON (F-03)


class PayloadTooLarge(Exception):
    pass


class BodySizeLimit:
    def __init__(self, app, max_bytes: int = MAX_BODY_BYTES) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        # Only the notes upload may be large (a PDF); everything else keeps the tight limit.
        notes = scope["method"] == "POST" and NOTES_PATH.match(scope["path"])
        limit = max(self.max_bytes, MAX_NOTES_BODY_BYTES) if notes else self.max_bytes
        declared = dict(scope["headers"]).get(b"content-length")
        if declared is not None and declared.isdigit() and int(declared) > limit:
            await self._reject(send, limit)
            return

        received = 0
        exceeded = False
        answered = False

        async def limited_receive():
            nonlocal received, exceeded
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    exceeded = True
                    raise PayloadTooLarge
            return message

        async def tracking_send(message):
            # The framework turns the cut-off read into its own error answer; replace that with the 413.
            nonlocal answered
            if exceeded:
                if message["type"] == "http.response.start" and not answered:
                    answered = True
                    await self._reject(send, limit)
                return
            await send(message)

        try:
            await self.app(scope, limited_receive, tracking_send)
        except PayloadTooLarge:
            if not answered:
                await self._reject(send, limit)

    async def _reject(self, send, limit):
        body = json.dumps(
            {"error": {"code": "payload_too_large", "message": f"The request is larger than {limit} bytes.",
                       "request_id": "-"}}
        ).encode()
        await send({"type": "http.response.start", "status": 413,
                    "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
        await send({"type": "http.response.body", "body": body})
