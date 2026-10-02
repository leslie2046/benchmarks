$ErrorActionPreference = 'Stop'
$composePath = Join-Path $PSScriptRoot 'compose.yaml'

& docker compose -f $composePath up --detach --no-build
if ($LASTEXITCODE -ne 0) { throw 'Docker container startup failed.' }
& docker compose -f $composePath ps
if ($LASTEXITCODE -ne 0) { throw 'Cannot inspect Docker containers.' }
Write-Output 'Container startup requested. Open http://localhost:8080 after the services are ready.'
