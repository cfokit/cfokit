#!/usr/bin/env bash
# Record what this deployment is called, so every later step reads the same values.
#
#   configure.sh PROJECT_ID DOMAIN [REGION] [OWNER/REPOSITORY]
#
# Names only; no secret is written here or anywhere else by these scripts.
set -euo pipefail

if [ $# -lt 2 ]; then
  echo "usage: $0 PROJECT_ID DOMAIN [REGION] [OWNER/REPOSITORY]" >&2
  exit 2
fi

file="${CFOKIT_ENV_FILE:-$HOME/.config/cfokit/deploy.env}"
mkdir -p "$(dirname "$file")"
cat >"$file" <<EOF
CFOKIT_PROJECT=$1
CFOKIT_DOMAIN=$2
CFOKIT_REGION=${3:-us-central1}
CFOKIT_REPOSITORY=${4:-cfokit/cfokit}
EOF

# shellcheck source=env.sh
. "$(dirname "$0")/env.sh"
echo "Recorded in $file:"
echo "  project     $CFOKIT_PROJECT"
echo "  region      $CFOKIT_REGION (database in $CFOKIT_ZONE)"
echo "  hostnames   app.$CFOKIT_DOMAIN  mcp.$CFOKIT_DOMAIN  auth.$CFOKIT_DOMAIN"
echo "  deploys     from github.com/$CFOKIT_REPOSITORY, branch main"
