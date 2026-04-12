#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

ALLOW_DIRTY=0
SKIP_PYTEST=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --allow-dirty)
      ALLOW_DIRTY=1
      shift
      ;;
    --skip-pytest)
      SKIP_PYTEST=1
      shift
      ;;
    *)
      echo "unknown option: $1" >&2
      echo "usage: $0 [--allow-dirty] [--skip-pytest]" >&2
      exit 2
      ;;
  esac
done

echo "[release-check] repo: ${ROOT_DIR}"

required_files=(
  README.md
  LICENSE
  CONTRIBUTING.md
  SECURITY.md
  CODE_OF_CONDUCT.md
  CHANGELOG.md
  RELEASING.md
  .github/workflows/test.yml
)

for path in "${required_files[@]}"; do
  if [[ ! -f "${path}" ]]; then
    echo "[release-check] missing required file: ${path}" >&2
    exit 1
  fi
done

if [[ "${ALLOW_DIRTY}" != "1" ]]; then
  if [[ -n "$(git status --short)" ]]; then
    echo "[release-check] git worktree is dirty; commit or stash changes first" >&2
    git status --short >&2
    exit 1
  fi
else
  echo "[release-check] dirty worktree allowed"
fi

if rg -n "49\\.235\\.88\\.239|http://49\\.235" container host scripts README.md >/dev/null 2>&1; then
  echo "[release-check] found hardcoded provider endpoint; remove it before release" >&2
  rg -n "49\\.235\\.88\\.239|http://49\\.235" container host scripts README.md >&2 || true
  exit 1
fi

if [[ "${SKIP_PYTEST}" != "1" ]]; then
  echo "[release-check] running full pytest suite"
  python3 -m pytest -q
else
  echo "[release-check] skipping pytest"
fi

echo "[release-check] release readiness checks passed"
