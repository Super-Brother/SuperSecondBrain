#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

conda run -n secondbrain-chat pyinstaller \
  --clean \
  --noconfirm \
  packaging/pyinstaller/secondbrain-backend.spec
