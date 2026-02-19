from __future__ import annotations

import asyncio
import json

from sse_starlette.sse import EventSourceResponse
from starlette.requests import Request


async def stream(request: Request):
    """SSE endpoint: yields BotState JSON every second."""
    bot_loop = request.app.state.bot_loop

    async def event_generator():
        while True:
            if await request.is_disconnected():
                break
            state = bot_loop.state
            yield {"data": state.model_dump_json()}
            await asyncio.sleep(1)

    return EventSourceResponse(event_generator())
