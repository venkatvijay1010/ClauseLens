"""ASGI-level request limits applied before FastAPI parses multipart uploads."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any


class RequestBodyTooLargeError(Exception):
    """Raised while streaming an HTTP request that exceeds the configured body budget."""


Receive = Callable[[], Awaitable[dict[str, Any]]]
Send = Callable[[dict[str, Any]], Awaitable[None]]
ASGIApp = Callable[[dict[str, Any], Receive, Send], Awaitable[None]]


class RequestBodyLimitMiddleware:
    """Reject oversized HTTP request bodies before multipart parsing can spool them.

    A `Content-Length` check handles ordinary uploads immediately. The wrapped `receive`
    function also enforces the limit for chunked requests without that header.
    """

    def __init__(self, app: ASGIApp, max_body_bytes: int):
        self.app = app
        self.max_body_bytes = max_body_bytes

    async def __call__(self, scope: dict[str, Any], receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        content_length = _content_length(scope)
        if content_length is not None and content_length > self.max_body_bytes:
            await _send_limit_response(send, self.max_body_bytes)
            return

        received_bytes = 0
        response_started = False

        async def limited_receive() -> dict[str, Any]:
            nonlocal received_bytes
            message = await receive()
            if message["type"] == "http.request":
                received_bytes += len(message.get("body", b""))
                if received_bytes > self.max_body_bytes:
                    raise RequestBodyTooLargeError
            return message

        async def tracked_send(message: dict[str, Any]) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracked_send)
        except RequestBodyTooLargeError:
            if not response_started:
                await _send_limit_response(send, self.max_body_bytes)


def _content_length(scope: dict[str, Any]) -> int | None:
    for name, value in scope.get("headers", []):
        if name.lower() != b"content-length":
            continue
        try:
            return int(value)
        except ValueError:
            return None
    return None


async def _send_limit_response(send: Send, max_body_bytes: int) -> None:
    payload = json.dumps(
        {"detail": f"Request body exceeds the {max_body_bytes:,}-byte safety limit."}
    ).encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": 413,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(payload)).encode("ascii")),
            ],
        }
    )
    await send({"type": "http.response.body", "body": payload})
