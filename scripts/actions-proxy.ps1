param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateSet("list-projects", "list-epics", "list-statuses", "create-story", "add-story-to-epic")]
    [string]$Action,

    [string]$BaseUrl = $env:TAIGA_PROXY_BASE_URL,
    [string]$ApiKey = $env:ACTION_PROXY_API_KEY,

    [string]$Search,
    [int[]]$ProjectId,
    [int]$EpicId,
    [int]$UserStoryId,
    [string]$Subject,
    [string]$Description,
    [string]$Status,
    [string[]]$Tags,
    [int]$AssignedTo
)

function Throw-IfMissing {
    param(
        [Parameter(Mandatory = $true)][string]$Value,
        [Parameter(Mandatory = $true)][string]$Message
    )

    if (-not $Value) {
        throw $Message
    }
}

function Build-QueryString {
    param(
        [Parameter(Mandatory = $true)][hashtable]$Parameters
    )

    $pairs = @()
    foreach ($key in $Parameters.Keys) {
        $value = $Parameters[$key]
        if ($null -eq $value) {
            continue
        }

        if ($value -is [System.Collections.IEnumerable] -and -not ($value -is [string])) {
            foreach ($item in $value) {
                if ($null -eq $item) { continue }
                $pairs += "{0}={1}" -f [System.Uri]::EscapeDataString($key), [System.Uri]::EscapeDataString([string]$item)
            }
        }
        else {
            $pairs += "{0}={1}" -f [System.Uri]::EscapeDataString($key), [System.Uri]::EscapeDataString([string]$value)
        }
    }

    if ($pairs.Count -eq 0) {
        return ""
    }

    return "?" + ($pairs -join "&")
}

Throw-IfMissing -Value $BaseUrl -Message "Base URL is required. Set TAIGA_PROXY_BASE_URL or pass -BaseUrl."
Throw-IfMissing -Value $ApiKey -Message "API key is required. Set ACTION_PROXY_API_KEY or pass -ApiKey."

$BaseUrl = $BaseUrl.TrimEnd('/')
$Headers = @{ "X-Api-Key" = $ApiKey }

switch ($Action) {
    "list-projects" {
        $endpoint = "$BaseUrl/actions/list_projects"
        $queryParams = @{}
        if ($Search) { $queryParams["search"] = $Search }
        $endpoint += Build-QueryString -Parameters $queryParams
        $response = Invoke-RestMethod -Method Get -Uri $endpoint -Headers $Headers -ErrorAction Stop
    }
    "list-epics" {
        if (-not $ProjectId) { throw "-ProjectId is required for list-epics" }
        $endpoint = "$BaseUrl/actions/list_epics"
        $queryParams = @{ "project_id" = $ProjectId }
        $endpoint += Build-QueryString -Parameters $queryParams
        $response = Invoke-RestMethod -Method Get -Uri $endpoint -Headers $Headers -ErrorAction Stop
    }
    "list-statuses" {
        if (-not $ProjectId) { throw "-ProjectId is required for list-statuses" }
        $endpoint = "$BaseUrl/actions/statuses"
        $queryParams = @{ "project_id" = $ProjectId[0] }
        $endpoint += Build-QueryString -Parameters $queryParams
        $response = Invoke-RestMethod -Method Get -Uri $endpoint -Headers $Headers -ErrorAction Stop
    }
    "create-story" {
        if (-not $ProjectId) { throw "-ProjectId is required for create-story" }
        if (-not $Subject) { throw "-Subject is required for create-story" }
        $endpoint = "$BaseUrl/actions/create_story"
        $payload = @{ project_id = $ProjectId[0]; subject = $Subject }
        if ($Description) { $payload.description = $Description }
        if ($Status) { $payload.status = $Status }
        if ($Tags) { $payload.tags = $Tags }
        if ($PSBoundParameters.ContainsKey("AssignedTo")) { $payload.assigned_to = $AssignedTo }
        $json = $payload | ConvertTo-Json -Depth 5
        $response = Invoke-RestMethod -Method Post -Uri $endpoint -Headers $Headers -Body $json -ContentType "application/json" -ErrorAction Stop
    }
    "add-story-to-epic" {
        if (-not $EpicId) { throw "-EpicId is required for add-story-to-epic" }
        if (-not $UserStoryId) { throw "-UserStoryId is required for add-story-to-epic" }
        $endpoint = "$BaseUrl/actions/add_story_to_epic"
        $payload = @{ epic_id = $EpicId; user_story_id = $UserStoryId }
        $json = $payload | ConvertTo-Json -Depth 2
        $response = Invoke-RestMethod -Method Post -Uri $endpoint -Headers $Headers -Body $json -ContentType "application/json" -ErrorAction Stop
    }
}

$response | ConvertTo-Json -Depth 10
