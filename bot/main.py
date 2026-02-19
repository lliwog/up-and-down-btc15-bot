from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.responses import FileResponse

from bot.config import load_config
from bot.engine.bot_loop import BotLoop
from bot.web.routes import stream


@asynccontextmanager
async def lifespan(app: FastAPI):
    config_path = os.environ.get("BOT_CONFIG")
    config = load_config(config_path)
    bot = BotLoop(config)
    app.state.bot_loop = bot
    task = asyncio.create_task(bot.run_forever())
    yield
    bot.stop()
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


app = FastAPI(lifespan=lifespan)

# SSE endpoint
app.add_api_route("/api/stream", stream, methods=["GET"])

# Static files (dashboard)
_static_dir = os.path.join(os.path.dirname(__file__), "web", "static")
app.mount("/static", StaticFiles(directory=_static_dir), name="static")


@app.get("/")
async def index():
    return FileResponse(os.path.join(_static_dir, "index.html"))
