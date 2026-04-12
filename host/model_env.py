from __future__ import annotations

import os
import shlex
from pathlib import Path
from typing import MutableMapping

LEGACY_DEFAULT_BASE_URL = ""
LEGACY_DEFAULT_MODEL = ""
DEFAULT_MODEL_ENV_PATH = Path("~/.config/marathon/model.env").expanduser()
MANAGED_KEYS = (
    "MARATHON_BASE_URL",
    "MARATHON_API_KEY",
    "MARATHON_MODEL",
    "MARATHON_MODEL_SETTINGS_JSON",
)


def resolve_model_env_path() -> Path:
    raw = os.environ.get("MARATHON_MODEL_ENV_FILE", "").strip()
    return Path(raw).expanduser() if raw else DEFAULT_MODEL_ENV_PATH


def parse_model_env_file(path: Path | None = None) -> dict[str, str]:
    env_path = (path or resolve_model_env_path()).expanduser()
    if not env_path.exists():
        return {}

    values: dict[str, str] = {}
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, raw_value = line.split("=", 1)
        key = key.strip()
        if key not in MANAGED_KEYS:
            continue

        value = raw_value.strip()
        if not value:
            values[key] = ""
            continue
        try:
            parts = shlex.split(value, posix=True)
        except ValueError:
            parts = [value]
        values[key] = parts[0] if len(parts) == 1 else value
    return values


def load_model_env_defaults(
    environ: MutableMapping[str, str] | None = None,
    *,
    env_file: Path | None = None,
) -> dict[str, str]:
    target = environ if environ is not None else os.environ
    loaded: dict[str, str] = {}
    for key, value in parse_model_env_file(env_file).items():
        current = str(target.get(key, "")).strip()
        if current:
            continue
        target[key] = value
        loaded[key] = value
    return loaded


def default_model() -> str:
    return os.environ.get("MARATHON_MODEL", "").strip() or LEGACY_DEFAULT_MODEL


def default_base_url() -> str:
    return os.environ.get("MARATHON_BASE_URL", "").strip() or LEGACY_DEFAULT_BASE_URL
