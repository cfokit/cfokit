#!/usr/bin/env bash
# Build both images for one commit and push them, tagged with the commit and as `latest`.
#
# The services are created from `latest` (run.tf), so this runs before the first apply; after
# that, deploy.sh runs it and moves each service to the commit's tag. Cloud Run runs
# linux/amd64 whatever builds it.
#
#   images.sh [COMMIT]     default: the checkout's HEAD
# shellcheck source=env.sh
. "$(dirname "$0")/env.sh"

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
  gcloud artifacts docker tags add "$image" "${repository}/${name}:latest" --quiet >/dev/null 2>&1
done
