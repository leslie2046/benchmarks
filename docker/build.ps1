param([string]$Archive)
$ErrorActionPreference = 'Stop'
$composePath = Join-Path $PSScriptRoot 'compose.yaml'

& docker compose -f $composePath build
if ($LASTEXITCODE -ne 0) { throw 'Docker image build failed.' }
if ($Archive) {
    & docker compose -f $composePath pull db
    if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL image pull failed.' }
    & docker image save --output $Archive prismlab-api:local prismlab-web:local postgres:16
    if ($LASTEXITCODE -ne 0) { throw 'Docker image archive export failed.' }
}
