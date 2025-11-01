"""Minimal web app to exercise the Taiga MCP server via the Streamable HTTP transport."""

from __future__ import annotations

import logging
import os
from typing import Any

import mcp
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from mcp.client.streamable_http import streamablehttp_client
from pydantic import BaseModel

APP_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES = Jinja2Templates(directory=os.path.join(APP_DIR, "templates"))

MCP_URL = os.environ.get("MCP_URL", "http://127.0.0.1:8000/mcp")
MCP_HEADERS: dict[str, str] | None = None

logger = logging.getLogger(__name__)

app = FastAPI(title="Taiga MCP Chat Probe")
app.mount("/static", StaticFiles(directory=os.path.join(APP_DIR, "static")), name="static")


class ChatRequest(BaseModel):
    prompt: str


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return TEMPLATES.TemplateResponse("index.html", {"request": request, "mcp_url": MCP_URL})


async def _call_echo(message: str) -> dict[str, Any]:
    """Call the echo tool on the MCP server and return raw result."""
    if not MCP_URL:
        raise RuntimeError("MCP_URL environment variable not configured")

    async with streamablehttp_client(MCP_URL, headers=MCP_HEADERS) as (reader, writer, _):
        async with mcp.ClientSession(reader, writer) as session:
            await session.initialize()
            response = await session.call_tool("echo", {"message": message})
            return response.model_dump()


@app.post("/api/chat")
async def chat(body: ChatRequest) -> JSONResponse:
    try:
        echo_response = await _call_echo(body.prompt)
    except Exception as exc:  # broad catch to surface MCP errors to UI
        logger.exception("MCP call failed for prompt %s", body.prompt)
        raise HTTPException(status_code=502, detail=f"MCP call failed: {exc}") from exc

    # TODO: integrate OpenAI response selection. For now just return MCP tool output.
    return JSONResponse({"echo": echo_response})