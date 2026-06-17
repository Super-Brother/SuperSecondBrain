#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

./scripts/build_desktop_backend.sh

cd desktop
npm install
npm run package
