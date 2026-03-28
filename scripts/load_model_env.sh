#!/usr/bin/env bash

MODEL_ENV_FILE="${MARATHON_MODEL_ENV_FILE:-$HOME/.config/marathon/model.env}"
MARATHON_ENV_KEYS=(
  MARATHON_BASE_URL
  MARATHON_API_KEY
  MARATHON_MODEL
  MARATHON_MODEL_SETTINGS_JSON
)

marathon_preserve_env_var() {
  local name="$1"
  local present_var="__MARATHON_ENV_PRESENT_${name}"
  local value_var="__MARATHON_ENV_VALUE_${name}"
  if [[ -v "${name}" ]]; then
    printf -v "${present_var}" '%s' 1
    printf -v "${value_var}" '%s' "${!name}"
  else
    printf -v "${present_var}" '%s' 0
    printf -v "${value_var}" '%s' ''
  fi
}

marathon_restore_env_var() {
  local name="$1"
  local present_var="__MARATHON_ENV_PRESENT_${name}"
  local value_var="__MARATHON_ENV_VALUE_${name}"
  if [[ "${!present_var:-0}" == "1" ]]; then
    export "${name}=${!value_var}"
  fi
  unset "${present_var}" "${value_var}"
}

for marathon_env_key in "${MARATHON_ENV_KEYS[@]}"; do
  marathon_preserve_env_var "${marathon_env_key}"
done

if [[ -f "${MODEL_ENV_FILE}" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "${MODEL_ENV_FILE}"
  set +a
fi

for marathon_env_key in "${MARATHON_ENV_KEYS[@]}"; do
  marathon_restore_env_var "${marathon_env_key}"
done

unset marathon_env_key
unset -f marathon_preserve_env_var
unset -f marathon_restore_env_var
