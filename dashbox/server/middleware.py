from __future__ import annotations

import re
from typing import Any


media_segment_path_re = re.compile(r"^/media/[^/]+/\d+/\d+$")


class HeadRequestMiddleware:
    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") != "http" or scope.get("method") != "HEAD":
            await self.app(scope, receive, send)
            return
        if path_handles_head_without_get(str(scope.get("path") or "")):
            await self.app(scope, receive, send)
            return

        get_scope = dict(scope)
        get_scope["method"] = "GET"

        async def head_send(message: dict[str, Any]) -> None:
            if message.get("type") == "http.response.body":
                message = dict(message)
                message["body"] = b""
            await send(message)

        await self.app(get_scope, receive, head_send)


def path_handles_head_without_get(path: str) -> bool:
    return path == "/image" or media_segment_path_re.match(path) is not None
