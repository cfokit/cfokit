#!/usr/bin/env bash
# Ship one commit: build, migrate, publish the web build, roll out, check (ADR-0060 § 5).
#
# The same script runs from Cloud Shell for the first deploy and from GitHub Actions on every
# merge to main, so the two cannot drift. It reads no OpenTofu state, which the deploy identity
# cannot read: every name it needs is derived from the project and region by the convention
# infra/gcp/ declares them under.
#
#   deploy.sh [COMMIT]     default: the checkout's HEAD
# shellcheck source=env.sh
. "$(dirname "$0")/env.sh"

sha="${1:-$(git -C "$CFOKIT_ROOT" rev-parse HEAD)}"
registry="${CFOKIT_REGION}-docker.pkg.dev"
repository="${registry}/${CFOKIT_PROJECT}/cfokit"
bucket="gs://${CFOKIT_PROJECT}-web"
app="${repository}/app:${sha}"
issuer="${repository}/issuer:${sha}"

step "Images for ${sha:0:12}"
gcloud auth configure-docker "$registry" --quiet >/dev/null 2>&1
for target in runtime issuer; do
  image=$([ "$target" = runtime ] && echo "$app" || echo "$issuer")
  if gcloud artifacts docker images describe "$image" >/dev/null 2>&1; then
    done_ "$image exists"
    continue
  fi
  # Cloud Run runs linux/amd64 whatever builds it. The empty CA file satisfies the Dockerfile's
  # optional build secret.
  ca=$(mktemp)
  docker buildx build --platform linux/amd64 --target "$target" \
    --secret "id=build_ca,src=$ca" --tag "$image" --push "$CFOKIT_ROOT"
  rm -f "$ca"
  done_ "$image pushed"
done

# Before any revision that needs it serves traffic, never by a service at startup (ADR-0004).
step "Migrate"
gcloud run jobs update cfokit-migrate --region "$CFOKIT_REGION" --image "$app" --quiet >/dev/null
gcloud run jobs execute cfokit-migrate --region "$CFOKIT_REGION" --wait --quiet
done_ "migrations current"

# ADR-0055 § 3: the files built into this image, new files first and index.html last; the
# previous build's files stay, so an open tab can still load its chunks.
step "Web build"
work=$(mktemp -d)
container=$(docker create --platform linux/amd64 "$app")
docker cp "${container}:/app/web" "$work/build" >/dev/null
docker rm "$container" >/dev/null
(
  cd "$work/build"
  gcloud storage cp --recursive --quiet \
    --cache-control="public, max-age=31536000, immutable" assets "${bucket}/app/"
  find . -type f ! -path './assets/*' ! -name index.html | sed 's|^\./||' | while read -r f; do
    gcloud storage cp --quiet --cache-control="no-cache" "$f" "${bucket}/app/${f}"
  done
  gcloud storage cp --quiet --cache-control="no-cache" index.html "${bucket}/app/index.html"

  find . -type f | sed 's|^\./|app/|' | sort >"$work/current.txt"
  gcloud storage cp "${bucket}/builds/current.txt" "$work/previous.txt" --quiet 2>/dev/null \
    || : >"$work/previous.txt"
  gcloud storage cp "$work/current.txt" "${bucket}/builds/current.txt" --quiet
  gcloud storage cp "$work/previous.txt" "${bucket}/builds/previous.txt" --quiet
  sort -u "$work/current.txt" "$work/previous.txt" >"$work/keep.txt"
  gcloud storage ls --recursive "${bucket}/app/**" | sed "s|^${bucket}/||" | sort >"$work/present.txt"
  comm -23 "$work/present.txt" "$work/keep.txt" | sed "s|^|${bucket}/|" \
    | xargs -r gcloud storage rm --quiet
)
done_ "published"

step "Roll out"
for service in cfokit-rest cfokit-mcp; do
  gcloud run services update "$service" --region "$CFOKIT_REGION" --image "$app" --quiet >/dev/null
  done_ "$service"
done
gcloud run services update cfokit-issuer --region "$CFOKIT_REGION" --image "$issuer" --quiet >/dev/null
done_ "cfokit-issuer"

CFOKIT_ASSET="$(cd "$work/build" && find assets -name '*.js' | head -1)" \
  "$(dirname "$0")/check.sh"
rm -rf "$work"
