#!/usr/bin/env bash
# Build both images for one commit and push them, tagged with the commit.
#
#   images.sh [--latest] [COMMIT]     default: the checkout's HEAD
#
# --latest also tags them `latest`, which the services and jobs are created from (run.tf), so the
# tutorial passes it before the first apply. A deploy does not: it moves each service to the
# commit's own tag, and `latest` matters to nothing that already exists. Cloud Run runs
# linux/amd64 whatever builds it.
# shellcheck source=env.sh
. "$(dirname "$0")/env.sh"

latest=false
if [ "${1:-}" = "--latest" ]; then
  latest=true
  shift
fi
sha="${1:-$(git -C "$CFOKIT_ROOT" rev-parse HEAD)}"
registry="${CFOKIT_REGION}-docker.pkg.dev"
repository="${registry}/${CFOKIT_PROJECT}/cfokit"

step "Images for ${sha:0:12}"
gcloud auth configure-docker "$registry" --quiet >/dev/null 2>&1
for name in app issuer; do
  target=$([ "$name" = app ] && echo runtime || echo issuer)
  image="${repository}/${name}:${sha}"
  if gcloud artifacts docker images describe "$image" >/dev/null 2>&1; then
    done_ "$image exists"
  else
    # The empty CA file satisfies the Dockerfile's optional build secret.
    ca=$(mktemp)
    docker buildx build --platform linux/amd64 --target "$target" \
      --secret "id=build_ca,src=$ca" --tag "$image" --push "$CFOKIT_ROOT"
    rm -f "$ca"
    done_ "$image pushed"
  fi
  if $latest; then
    gcloud artifacts docker tags add "$image" "${repository}/${name}:latest" --quiet
  fi
done
