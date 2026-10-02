#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [[ $# -gt 0 && ( $# -ne 2 || "$1" != "--archive" ) ]]; then
  echo "Usage: bash docker/build.sh [--archive /path/to/prismlab-images.tar]" >&2
  exit 2
fi
docker compose -f "$script_dir/compose.yaml" build
if [[ $# -eq 2 ]]; then
  docker image save --output "$2" prismlab-api:local prismlab-web:local
fi
