#!/usr/bin/env bash
set -euo pipefail

# Refresh a Codex model catalog from a configured provider.
# Usage: codex-refresh-models.sh PROFILE [--url URL] [--token TOKEN] [--output FILE]

usage() {
  cat <<'EOF'
Usage: codex-refresh-models.sh PROFILE [options]

Refresh ~/.codex/<PROFILE>.models.json from a Codex provider model endpoint.

Options:
  --url URL       Override the model endpoint discovered from config.
  --token TOKEN   Override the bearer token discovered from config.
  --output FILE   Write to FILE instead of ~/.codex/<PROFILE>.models.json.
  -h, --help      Show this help.
EOF
}

PROFILE=""
URL=""
TOKEN=""
OUTPUT=""

while [[ $# -gt 0 ]]
do
  if [[ "$1" == "-h" || "$1" == "--help" ]]
  then
    usage
    exit 0
  elif [[ "$1" == "--url" ]]
  then
    if [[ $# -lt 2 ]]
    then
      usage >&2
      exit 2
    fi
    URL="$2"
    shift 2
  elif [[ "$1" == "--token" ]]
  then
    if [[ $# -lt 2 ]]
    then
      usage >&2
      exit 2
    fi
    TOKEN="$2"
    shift 2
  elif [[ "$1" == "--output" ]]
  then
    if [[ $# -lt 2 ]]
    then
      usage >&2
      exit 2
    fi
    OUTPUT="$2"
    shift 2
  elif [[ "$1" == --* ]]
  then
    echo "Unknown option: $1" >&2
    usage >&2
    exit 2
  else
    if [[ -n "$PROFILE" ]]
    then
      echo "Only one PROFILE is allowed" >&2
      exit 2
    fi
    PROFILE="$1"
    shift
  fi
done

if [[ -z "$PROFILE" ]]
then
  usage >&2
  exit 2
fi

if [[ ! "$PROFILE" =~ ^[A-Za-z0-9._-]+$ ]]
then
  echo "PROFILE must contain only letters, numbers, dots, underscores, or hyphens" >&2
  exit 2
fi

CODEX_HOME="${CODEX_HOME:-$HOME/.codex}"
PROFILE_CONFIG="$CODEX_HOME/$PROFILE.config.toml"
GLOBAL_CONFIG="$CODEX_HOME/config.toml"

if [[ ! -f "$PROFILE_CONFIG" ]]
then
  echo "Profile config not found: $PROFILE_CONFIG" >&2
  exit 1
fi

for tool in curl jq python3
do
  if ! command -v "$tool" >/dev/null 2>&1
  then
    echo "$tool is required" >&2
    exit 1
  fi
done

tmpdir=$(mktemp -d)
trap 'rm -rf "$tmpdir"' EXIT
config_values="$tmpdir/config-values"
raw_models="$tmpdir/models.json"
catalog="$tmpdir/catalog.json"

python3 - "$PROFILE_CONFIG" "$GLOBAL_CONFIG" > "$config_values" <<'PY'
import os
import sys
import tomllib

profile_path, global_path = sys.argv[1], sys.argv[2]

with open(profile_path, "rb") as handle:
    profile = tomllib.load(handle)

global_config = {}
if os.path.exists(global_path):
    with open(global_path, "rb") as handle:
        global_config = tomllib.load(handle)

provider_name = profile.get("model_provider") or global_config.get("model_provider") or ""
providers = {}
providers.update(global_config.get("model_providers", {}))
providers.update(profile.get("model_providers", {}))
provider = providers.get(provider_name, {})

values = [
    provider_name,
    provider.get("base_url", ""),
    provider.get("env_key", ""),
    provider.get("model_catalog_url", ""),
]
print("\t".join(values))
PY

IFS=$'\t' read -r PROVIDER BASE_URL ENV_KEY MODEL_CATALOG_URL < "$config_values"

if [[ -n "$URL" ]]
then
  MODEL_ENDPOINT="$URL"
elif [[ -n "$MODEL_CATALOG_URL" ]]
then
  MODEL_ENDPOINT="$MODEL_CATALOG_URL"
elif [[ -n "$BASE_URL" ]]
then
  MODEL_ENDPOINT="${BASE_URL%/}/models"
else
  echo "No model endpoint found for provider: ${PROVIDER:-unknown}" >&2
  exit 1
fi

if [[ -n "$TOKEN" ]]
then
  AUTH_TOKEN="$TOKEN"
elif [[ -n "$ENV_KEY" && -n "${!ENV_KEY:-}" ]]
then
  AUTH_TOKEN="${!ENV_KEY}"
else
  echo "No bearer token found for provider: ${PROVIDER:-unknown}" >&2
  exit 1
fi

curl --fail --silent --show-error --max-time 20 \
  "$MODEL_ENDPOINT" \
  -H "Authorization: Bearer ${AUTH_TOKEN}" \
  -o "$raw_models"

if jq -e 'has("models")' "$raw_models" >/dev/null
then
  cp "$raw_models" "$catalog"
elif jq -e 'has("data")' "$raw_models" >/dev/null
then
  jq '
    .data
    | sort_by(.id)
    | unique_by(.id)
    | map(
        {
          slug: .id,
          display_name: .id,
          description: ("Provider model " + .id),
          default_reasoning_level: "high",
          supported_reasoning_levels: [
            {effort: "low", description: "Light reasoning"},
            {effort: "high", description: "Balanced reasoning"},
            {effort: "max", description: "Maximum reasoning"}
          ],
          shell_type: "shell_command",
          visibility: "list",
          supported_in_api: true,
          priority: 0,
          base_instructions: "",
          supports_reasoning_summaries: true,
          default_reasoning_summary: "none",
          support_verbosity: false,
          apply_patch_tool_type: null,
          truncation_policy: {mode: "bytes", limit: 10000},
          context_window: 1048576,
          max_context_window: 1048576,
          effective_context_window_percent: 95,
          supports_parallel_tool_calls: true,
          experimental_supported_tools: [],
          input_modalities: ["text"]
        }
      )
    | {models: .}
  ' "$raw_models" > "$catalog"
else
  echo "Unsupported model response from: $MODEL_ENDPOINT" >&2
  exit 1
fi

jq -e '
  .models
  | map(.slug | length > 0)
  | all
' "$catalog" >/dev/null

OUTPUT="${OUTPUT:-$CODEX_HOME/$PROFILE.models.json}"
mkdir -p "$(dirname "$OUTPUT")"
mv "$catalog" "$OUTPUT"

echo "Refreshed $(jq '.models | length' "$OUTPUT") models in $OUTPUT"
