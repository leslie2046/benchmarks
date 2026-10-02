#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [[ $# -ne 0 ]]; then
  echo "Usage: bash docker/start.sh" >&2
  exit 2
fi
docker compose -f "$script_dir/compose.yaml" up --detach --no-build
docker compose -f "$script_dir/compose.yaml" ps
echo "Container startup requested. Open http://localhost:8080 after the services are ready."
