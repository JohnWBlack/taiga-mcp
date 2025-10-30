"""Utility helpers for interacting with the Taiga REST API."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Mapping

import httpx

__all__ = [
    "TaigaAPIError",
    "get_taiga_client",
]


class TaigaAPIError(RuntimeError):
    """Raised when the Taiga API responds with an error."""


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise TaigaAPIError(f"Environment variable {name} must be configured")
    return value


class TaigaClient:
    """Thin async wrapper around Taiga's REST API."""

    def __init__(self) -> None:
        base_url = _require_env("TAIGA_BASE_URL")
        # Normalise base URL to avoid eventual double slashes.
        base_url = base_url.rstrip("/")

        username = _require_env("TAIGA_USERNAME")
        password = _require_env("TAIGA_PASSWORD")

        self._client = httpx.AsyncClient(
            base_url=base_url,
            auth=(username, password),
            timeout=30.0,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        json: Mapping[str, Any] | None = None,
    ) -> Any:
        response = await self._client.request(method, path, params=params, json=json)
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:  # pragma: no cover - error details for humans
            detail = exc.response.text
            raise TaigaAPIError(
                f"Taiga API request failed with status {exc.response.status_code}: {detail}"
            ) from exc
        if response.content:
            return response.json()
        return None

    async def list_projects(self) -> list[dict[str, Any]]:
        data = await self._request("GET", "/projects")
        return list(data)

    async def list_epics(self, project_id: int) -> list[dict[str, Any]]:
        params = {"project": project_id}
        data = await self._request("GET", "/epics", params=params)
        return list(data)

    async def list_user_story_statuses(self, project_id: int) -> list[dict[str, Any]]:
        params = {"project": project_id}
        data = await self._request("GET", "/userstory-statuses", params=params)
        return list(data)

    async def create_user_story(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        data = await self._request("POST", "/userstories", json=payload)
        return dict(data)

    async def link_epic_user_story(self, epic_id: int, user_story_id: int) -> dict[str, Any] | None:
        payload = {"user_story": user_story_id}
        data = await self._request(
            "POST",
            f"/epics/{epic_id}/related_userstories",
            json=payload,
        )
        return dict(data) if data else None


@asynccontextmanager
async def get_taiga_client() -> AsyncIterator[TaigaClient]:
    client = TaigaClient()
    try:
        yield client
    finally:
        await client.close()
