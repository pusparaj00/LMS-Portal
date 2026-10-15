"""Maximum request size (TR-S-04). Pure ASGI so it also stops bodies that arrive without a Content-Length."""
import json

MAX_BODY_BYTES = 600_000  # a 50,000 character submission is well under this even in UTF-8


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
        declared = dict(scope["headers"]).get(b"content-length")
        if declared is not None and declared.isdigit() and int(declared) > self.max_bytes:
            await self._reject(send)
            return

        received = 0
        exceeded = False
        answered = False

        async def limited_receive():
            nonlocal received, exceeded
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    exceeded = True
                    raise PayloadTooLarge
            return message

        async def tracking_send(message):
            # The framework turns the cut-off read into its own error answer; replace that with the 413.
            nonlocal answered
            if exceeded:
                if message["type"] == "http.response.start" and not answered:
                    answered = True
                    await self._reject(send)
                return
            await send(message)

        try:
            await self.app(scope, limited_receive, tracking_send)
        except PayloadTooLarge:
            if not answered:
                await self._reject(send)

    async def _reject(self, send):
        body = json.dumps(
            {"error": {"code": "payload_too_large", "message": f"The request is larger than {self.max_bytes} bytes.",
                       "request_id": "-"}}
        ).encode()
        await send({"type": "http.response.start", "status": 413,
                    "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
        await send({"type": "http.response.body", "body": body})
