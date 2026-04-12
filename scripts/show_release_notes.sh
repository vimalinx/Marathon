#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION="${1:-v0.1.0}"

case "${VERSION}" in
  v0.1.0)
    NOTES_PATH="${ROOT_DIR}/docs/plans/2026-04-06-v0.1.0-release-notes.md"
    ;;
  *)
    echo "no release notes mapped for version: ${VERSION}" >&2
    exit 1
    ;;
esac

if [[ ! -f "${NOTES_PATH}" ]]; then
  echo "release notes file not found: ${NOTES_PATH}" >&2
  exit 1
fi

cat "${NOTES_PATH}"
