import os
from contextlib import asynccontextmanager
from typing import Any, Sequence

from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Mount, Route

from mcp.server.fastmcp import FastMCP

from taiga_client import TaigaAPIError, get_taiga_client

mcp = FastMCP("Taiga MCP", sse_path="/", streamable_http_path="/")
# Prebuild sub-apps so we can wire their lifespans into the parent Starlette app.
sse_subapp = mcp.sse_app(mount_path="/sse")
streamable_http_subapp = mcp.streamable_http_app()
streamable_http_subapp.router.redirect_slashes = False


@streamable_http_subapp.middleware("http")
async def _normalize_blank_path(request, call_next):
    # Starlette mounts strip the trailing slash, leaving an empty path for "/mcp".
    # Ensure the downstream Streamable HTTP route sees the root path.
    if request.scope.get("path") == "":
        request.scope["path"] = "/"
        request.scope["raw_path"] = b"/"
    return await call_next(request)


@mcp.tool()
def echo(message: str) -> str:
    """Echo a message back to the caller."""
    return message


def _slice(record: dict[str, Any], keys: Sequence[str]) -> dict[str, Any]:
    return {key: record.get(key) for key in keys if key in record}


@mcp.tool(name="taiga.projects.list")
async def taiga_projects_list() -> list[dict[str, Any]]:
    """Return the available Taiga projects visible to the service account."""

    async with get_taiga_client() as client:
        projects = await client.list_projects()
    keep = ("id", "name", "slug", "description", "is_private")
    return [_slice(project, keep) for project in projects]


@mcp.tool(name="taiga.epics.list")
async def taiga_epics_list(project_id: int) -> list[dict[str, Any]]:
    """List epics for a Taiga project."""

    async with get_taiga_client() as client:
        epics = await client.list_epics(project_id)
    keep = (
        "id",
        "ref",
        "subject",
        "created_date",
        "modified_date",
        "status",
    )
    return [_slice(epic, keep) for epic in epics]


async def _resolve_status_id(client, project_id: int, status: int | str | None) -> int | None:
    if status is None:
        return None
    if isinstance(status, int):
        return status

    statuses = await client.list_user_story_statuses(project_id)
    for entry in statuses:
        if entry.get("name") == status or entry.get("slug") == status:
            return entry.get("id")
    raise TaigaAPIError(f"Status '{status}' not found for project {project_id}")


@mcp.tool(name="taiga.stories.create")
async def taiga_stories_create(
    project_id: int,
    subject: str,
    description: str | None = None,
    status: int | str | None = None,
    tags: list[str] | None = None,
    assigned_to: int | None = None,
) -> dict[str, Any]:
    """Create a user story in Taiga and return the created record."""

    async with get_taiga_client() as client:
        status_id = await _resolve_status_id(client, project_id, status)
        payload: dict[str, Any] = {
            "project": project_id,
            "subject": subject,
        }
        if description:
            payload["description"] = description
        if status_id is not None:
            payload["status"] = status_id
        if tags:
            payload["tags"] = tags
        if assigned_to is not None:
            payload["assigned_to"] = assigned_to

        story = await client.create_user_story(payload)

    keep = (
        "id",
        "ref",
        "subject",
        "project",
        "status",
        "description",
        "assigned_to",
        "tags",
        "created_date",
        "modified_date",
    )
    return _slice(story, keep)


@mcp.tool(name="taiga.epics.add_user_story")
async def taiga_epics_add_user_story(epic_id: int, user_story_id: int) -> dict[str, Any] | None:
    """Attach a user story to an epic."""

    async with get_taiga_client() as client:
        response = await client.link_epic_user_story(epic_id, user_story_id)
    return response


async def healthz(_):
    return PlainTextResponse("ok", status_code=200)


async def root(_):
    return PlainTextResponse("Taiga MCP up", status_code=200)

@asynccontextmanager
async def lifespan(_app):
    # The streamable HTTP transport requires its session manager task group to be running.
    async with mcp.session_manager.run():
        yield


# Mount the MCP streamable app under both /mcp and /mcp/ so proxies that normalize
# paths differently will still carry the session headers through without a redirect.
app = Starlette(
    routes=[
        Route("/", root),
        Route("/healthz", healthz),
        Mount("/sse", app=sse_subapp),
        Mount("/mcp", app=streamable_http_subapp),
    ],
    lifespan=lifespan,
)
app.router.redirect_slashes = False


@app.middleware("http")
async def _rewrite_mcp_path(request, call_next):
    if request.scope.get("path") == "/mcp":
        request.scope["path"] = "/mcp/"
        request.scope["raw_path"] = b"/mcp/"
    return await call_next(request)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="0.0.0.0", port=int(os.getenv("PORT", "8000")))