# Taiga MCP Server

## Project Overview
- Implements a Starlette-based Model Context Protocol (MCP) server that exposes both Server-Sent Events (SSE) and Streamable HTTP transports for ChatGPT and other MCP compliant clients.
- Serves as a bridge between ChatGPT and the Taiga project management API, currently including an `echo` tool for transport validation with ongoing integration of Taiga-specific actions.
- Deployed as a container workload to Azure Container Apps and packaged for distribution through GitHub Container Registry (GHCR).

## Runtime Architecture
- `app.py` instantiates `FastMCP` with the Taiga MCP identity, mounts SSE at `/sse/` and Streamable HTTP at `/mcp/`, and disables trailing-slash redirects to preserve MCP session headers.
- A custom middleware rewrites bare `/mcp` requests to `/mcp/` and normalizes blank paths inside the sub-application to avoid 307 redirects that previously dropped MCP session headers.
- The FastMCP session manager is started via Starlette's lifespan hook to ensure streamable sessions stay active for long-running ChatGPT conversations.
- Health checks:
  - `GET /` → plain text "Taiga MCP up" for quick availability probes.
  - `GET /healthz` → minimal health endpoint for container orchestrators.

## Endpoints Summary
- `/` — Root status page.
- `/healthz` — Liveness probe used by Azure Container Apps.
- `/sse/` — Server-Sent Events transport; requires `Accept: text/event-stream` and returns the message posting endpoint in the first event payload.
- `/sse/sse/messages/` — POST target for SSE message submission (returned in SSE `endpoint` event).
- `/mcp/` — Streamable HTTP transport; clients **must** send `Accept: application/json, text/event-stream` to satisfy protocol negotiation.

## MCP Tools
- `echo(message)` — diagnostic helper that returns the provided message.
- `taiga.projects.list()` — lists projects visible to the service account.
- `taiga.epics.list(project_id)` — lists epics for a project, including id/ref/subject/status metadata.
- `taiga.stories.create(project_id, subject, description?, status?, tags?, assigned_to?)` — creates a Taiga user story; `status` accepts either an id or status name/slug.
- `taiga.epics.add_user_story(epic_id, user_story_id)` — links a user story to an epic.

## Action Proxy Surface
- Purpose: provide a lightweight HTTP bridge for Taiga automation while MCP write tools stay allowlisted.
- Auth: every request supplies `X-Api-Key`; the value must match the `ACTION_PROXY_API_KEY` environment variable (missing/invalid keys return 401, unconfigured key returns 503).
- Endpoints:
  - `GET /actions/list_projects?search=foo` → `{ "projects": [...] }` with optional case-insensitive name filter.
  - `GET /actions/get_project?project_id=123` → `{ "project": {...} }` returning the full Taiga project payload for the given id.
  - `GET /actions/get_project_by_slug?slug=acme-backlog` → `{ "project": {...} }` resolving the project via slug.
  - `GET /actions/list_epics?project_id=123&project_id=456` → `{ "epics": [...] }` including the originating `project_id` for each epic.
  - `GET /actions/statuses?project_id=123` → `{ "statuses": [...] }` to drive status pickers.
  - `POST /actions/create_story` → `{ "story": {...} }`; accepts the same payload as the MCP tool and resolves status slugs/names.
  - `POST /actions/update_story` → `{ "story": {...} }`; accepts `story_id` plus any combination of `project_id`, `subject`, `description`, `status`, `tags`, `assigned_to` (status strings resolve to ids automatically).
  - `POST /actions/delete_story` → `{ "deleted": {"story_id": ...} }`.
  - `POST /actions/add_story_to_epic` → `{ "link": {...} }` after linking a story to an epic.
  - `POST /actions/create_epic` / `update_epic` / `delete_epic` → manage epics (`project_id`, `subject`, optional `description`, `status`, `assigned_to`, `tags`, `color`).
  - `POST /actions/create_task` / `update_task` / `delete_task` → manage tasks (`project_id`, `subject`, optional `description`, `status`, `assigned_to`, `tags`, `user_story_id`).
  - `POST /actions/create_issue` / `update_issue` / `delete_issue` → manage issues (`project_id`, `subject`, optional `description`, `status`, `priority`, `severity`, `type`, `assigned_to`, `tags`).
- Error model: JSON `{ "error": "..." }` payloads with 4xx for validation/Taiga errors and 500 for unexpected failures (also logged server-side).
- Helper scripts (require `ACTION_PROXY_API_KEY` and `TAIGA_PROXY_BASE_URL` pointing at `https://<fqdn>`):
  - `.\.chat-venv\Scripts\python.exe scripts/actions_proxy_client.py --pretty list-projects` — cross-platform CLI with subcommands for all endpoints.
  - `\.\.chat-venv\Scripts\python.exe scripts/actions_proxy_client.py get-project --project-id 1746402` — fetches the detailed project payload for the default AresNet workspace.
  - `\.\.chat-venv\Scripts\python.exe scripts/actions_proxy_client.py get-project-by-slug --slug johnwblack-aresnet` — resolves the default AresNet project slug.
  - `\.\.chat-venv\Scripts\python.exe scripts/actions_proxy_client.py create-story --project-id 1746402 --subject "Story"` (and matching `update-story`, `delete-story`, `create-epic`, `update-epic`, `delete-epic`, `create-task`, `update-task`, `delete-task`, `create-issue`, `update-issue`, `delete-issue`) mirror the HTTP endpoints; swap the project id if you target another Taiga workspace.
  - `powershell.exe -File scripts/actions-proxy.ps1 list-projects` — Windows-friendly wrapper with parameter validation.
- Raw curl samples:
  - `curl.exe -H "X-Api-Key: $env:ACTION_PROXY_API_KEY" "$env:TAIGA_PROXY_BASE_URL/actions/list_projects?search=beta"`
  - `curl.exe -H "X-Api-Key: $env:ACTION_PROXY_API_KEY" -H "Content-Type: application/json" -d "{\"project_id\":1746402,\"subject\":\"Story\"}" "$env:TAIGA_PROXY_BASE_URL/actions/create_story"`

## Local Development Workflow
- **Prerequisites**
  - Python 3.11 (project uses a `.chat-venv` virtual environment by default).
  - Docker Desktop for container builds.
  - Azure CLI for deployment automation.
  - GHCR authentication (`docker login ghcr.io`).
- **Install dependencies**
  - `python -m venv .chat-venv`
  - `.\.chat-venv\Scripts\python.exe -m pip install -r requirements.txt`
- **Run the server locally**
  - `.\.chat-venv\Scripts\uvicorn.exe app:app --host 127.0.0.1 --port 8010`
  - Streamable probe: `.\.chat-venv\Scripts\python.exe streamable_client.py http://127.0.0.1:8010/mcp --message "hello local"`
- **SSE manual test**
  - `curl.exe -sN -H "Accept: text/event-stream" http://127.0.0.1:8010/sse/`

## Container Build & Publish
- Build tagged images:
  - `docker build -t ghcr.io/johnwblack/taiga-mcp:v0.0.23 -t ghcr.io/johnwblack/taiga-mcp:latest .`
- Push to GHCR:
  - `docker push ghcr.io/johnwblack/taiga-mcp:v0.0.23`
  - `docker push ghcr.io/johnwblack/taiga-mcp:latest`

## Azure Container Apps Deployment
- Resource group: `rg-offset3`
- Container app: `taiga-mcp`
- Managed environment: `cae-offset3`
- Deployment command (after successful image push):
  - `az containerapp update -g rg-offset3 -n taiga-mcp --image ghcr.io/johnwblack/taiga-mcp:v0.0.23`
- CLI prerequisites on Windows (prevents permission errors):
  - ` $env:AZURE_EXTENSION_DIR = Join-Path $HOME '.az-extensions'`
  - ` $env:AZURE_CONFIG_DIR = Join-Path $HOME '.az-cli'`

## Secret Management for Taiga Credentials
- Secrets are stored in Azure Container Apps and surfaced as environment variables for the MCP process.
- Commands used:
  - `az containerapp secret set --resource-group rg-offset3 --name taiga-mcp --secrets taiga-username="info@offset3.com" taiga-password="<PASSWORD>"`
  - `az containerapp update --resource-group rg-offset3 --name taiga-mcp --set-env-vars TAIGA_USERNAME=secretref:taiga-username TAIGA_PASSWORD=secretref:taiga-password`
- Action proxy key can be managed via `az containerapp secret set --resource-group rg-offset3 --name taiga-mcp --secrets action-proxy-api-key="<RANDOM_TOKEN>"` and `az containerapp update --resource-group rg-offset3 --name taiga-mcp --set-env-vars ACTION_PROXY_API_KEY=secretref:action-proxy-api-key`.
- Environment variables available inside the container:
  - `TAIGA_BASE_URL` — base URL for Taiga API (secret reference `taiga-base-url`).
  - `TAIGA_USERNAME` — service account username.
  - `TAIGA_PASSWORD` — service account password.
  - `ACTION_PROXY_API_KEY` — shared secret used by the `/actions/*` endpoints.
  - Legacy variables `TAIGA_USERNAME_SECRET` / `TAIGA_PASSWORD_SECRET` remain for backward compatibility.
- Rotate passwords regularly and repeat the secret update commands to propagate changes.

## Verification Checklist
- Streamable HTTP smoke test:
  - `.\.chat-venv\Scripts\python.exe streamable_client.py https://taiga-mcp.politeground-c43f6662.eastus.azurecontainerapps.io/mcp --message "ping from retest"`
- SSE availability test:
  - `curl.exe -sN -H "Accept: text/event-stream" https://taiga-mcp.politeground-c43f6662.eastus.azurecontainerapps.io/sse/ --max-time 5`
- Azure logs review:
  - `az containerapp logs show -g rg-offset3 -n taiga-mcp --tail 50`
- ChatGPT connector validation:
  - Configure ChatGPT with the MCP endpoint `https://taiga-mcp.politeground-c43f6662.eastus.azurecontainerapps.io/mcp` and confirm that the `echo` tool responds.
  - Verify Taiga API routes once exposed by running list and write operations through ChatGPT.

## Troubleshooting Notes
- `Not Acceptable: Client must accept text/event-stream` — Ensure clients send `Accept: application/json, text/event-stream` when calling `/mcp/`.
- `Session terminated` errors usually indicate a redirect; verify the request hits `/mcp/` (with trailing slash) and that proxies are not rewriting headers.
- Azure CLI `WinError 5` permission issues are resolved by setting `AZURE_EXTENSION_DIR` and `AZURE_CONFIG_DIR` to user-writable locations.
- After updating secrets, Azure Container Apps restarts the revision; allow 1–2 minutes before retesting endpoints.

## Testing
- Install dev dependencies: `python -m pip install -r requirements.txt pytest` (from the `.chat-venv` environment).
- Run the Python unit suite: `pytest` (covers `/actions/*` auth, validation, and Taiga error handling via fakes).
- Smoke test the helper CLI locally: `.\.chat-venv\Scripts\python.exe scripts/actions_proxy_client.py --help`.
- PowerShell validation: `powershell.exe -File scripts/actions-proxy.ps1 list-projects -BaseUrl http://127.0.0.1:8010 -ApiKey local-test` when the server is running with a dummy key.

## Request Payload Reference

### Stories
- Create (`POST /actions/create_story`): `{ "project_id": int, "subject": str, "description"?: str, "status"?: int|str, "tags"?: [str], "assigned_to"?: int }`
- Update (`POST /actions/update_story`): `{ "story_id": int, "project_id"?: int, "subject"?: str, "description"?: str, "status"?: int|str, "tags"?: [str], "assigned_to"?: int }`
- Delete (`POST /actions/delete_story`): `{ "story_id": int }`

### Epics
- Create (`POST /actions/create_epic`): `{ "project_id": int, "subject": str, "description"?: str, "status"?: int, "assigned_to"?: int, "tags"?: [str], "color"?: str }`
- Update (`POST /actions/update_epic`): `{ "epic_id": int, "subject"?: str, "description"?: str, "status"?: int, "assigned_to"?: int, "tags"?: [str], "color"?: str }`
- Delete (`POST /actions/delete_epic`): `{ "epic_id": int }`

### Tasks
- Create (`POST /actions/create_task`): `{ "project_id": int, "subject": str, "description"?: str, "status"?: int, "assigned_to"?: int, "tags"?: [str], "user_story_id"?: int }`
- Update (`POST /actions/update_task`): `{ "task_id": int, "subject"?: str, "description"?: str, "status"?: int, "assigned_to"?: int, "tags"?: [str], "user_story_id"?: int }`
- Delete (`POST /actions/delete_task`): `{ "task_id": int }`

### Issues
- Create (`POST /actions/create_issue`): `{ "project_id": int, "subject": str, "description"?: str, "status"?: int, "priority"?: int, "severity"?: int, "type"?: int, "assigned_to"?: int, "tags"?: [str] }`
- Update (`POST /actions/update_issue`): `{ "issue_id": int, "subject"?: str, "description"?: str, "status"?: int, "priority"?: int, "severity"?: int, "type"?: int, "assigned_to"?: int, "tags"?: [str] }`
- Delete (`POST /actions/delete_issue`): `{ "issue_id": int }`

## Azure AI Fallback (Future Option)
- Idea: expose Taiga access through an Azure OpenAI Assistants tool while the ChatGPT MCP allowlist is pending.
- Components: Azure Functions (or Container App) hosting the same FastMCP logic, Azure OpenAI Assistant registered with HTTPS tool endpoints, and service principal credentials stored in Key Vault.
- Status: deferred; revisit if the OpenAI allowlist remains blocked after proxy rollout. Keep scripts modular so the same helper payloads feed both the MCP proxy and any future Azure AI adapter.

## Project History (October 2025 Highlights)
- Refactored Starlette routing to eliminate automatic slash redirects that stripped MCP session headers on Azure.
- Added middleware to normalize Streamable HTTP paths and ensure compatibility with Azure ingress rewrite behavior.
- Built and published container versions `v0.0.4` through `v0.0.10`, with `v0.0.10` deployed as revision `taiga-mcp--0000016`.
- Validated SSE and Streamable HTTP transports using local clients, `curl`, and the ChatGPT MCP connector.
- Stored Taiga service account credentials securely in Azure Container Apps secrets to enable future write access to Taiga.
