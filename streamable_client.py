"""Utility script to exercise the Taiga MCP Streamable HTTP endpoint."""

from __future__ import annotations

import argparse
import asyncio
import os
from typing import Any

import mcp
from mcp.client.streamable_http import streamablehttp_client


async def call_echo(mcp_url: str, message: str) -> dict[str, Any]:
    async with streamablehttp_client(mcp_url) as (reader, writer, _):
        async with mcp.ClientSession(reader, writer) as session:
            await session.initialize()
            response = await session.call_tool("echo", {"message": message})
            return response.model_dump()


async def list_tools(mcp_url: str) -> dict[str, Any]:
    async with streamablehttp_client(mcp_url) as (reader, writer, _):
        async with mcp.ClientSession(reader, writer) as session:
            await session.initialize()
            response = await session.list_tools()
            return response.model_dump()


async def main() -> None:
    parser = argparse.ArgumentParser(description="Invoke the Taiga MCP echo tool over Streamable HTTP.")
    default_url = os.getenv("MCP_URL", "http://127.0.0.1:8000/mcp")
    parser.add_argument(
        "mcp_url",
        nargs="?",
        default=default_url,
        help="MCP Streamable HTTP endpoint to target.",
    )
    parser.add_argument("--message", default="test", help="Message to send to the echo tool.")
    parser.add_argument("--list-tools", action="store_true", help="List available tools instead of calling echo.")
    args = parser.parse_args()

    if args.list_tools:
        result = await list_tools(args.mcp_url)
    else:
        result = await call_echo(args.mcp_url, args.message)
    print(result)


if __name__ == "__main__":
    asyncio.run(main())
