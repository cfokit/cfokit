#!/usr/bin/env bash
# Where OpenTofu's state lives, made before `tofu init` can be: a versioned bucket, and a KMS key
# its state is encrypted with (ADR-0060 § 6). Safe to run again.
# shellcheck source=env.sh
. "$(dirname "$0")/env.sh"

bucket="gs://${CFOKIT_PROJECT}-tofu-state"

step "State bucket $bucket"
if ! gcloud storage buckets describe "$bucket" >/dev/null 2>&1; then
  gcloud storage buckets create "$bucket" --location "$CFOKIT_REGION" \
    --uniform-bucket-level-access --public-access-prevention --quiet
fi
gcloud storage buckets update "$bucket" --versioning --quiet >/dev/null
done_ "versioned"

step "State encryption key"
if ! gcloud kms keyrings describe tofu --location "$CFOKIT_REGION" >/dev/null 2>&1; then
  gcloud kms keyrings create tofu --location "$CFOKIT_REGION"
fi
if ! gcloud kms keys describe state --keyring tofu --location "$CFOKIT_REGION" >/dev/null 2>&1; then
  gcloud kms keys create state --keyring tofu --location "$CFOKIT_REGION" --purpose encryption
fi
# Rotated every 90 days; older versions stay to decrypt what they encrypted (SOC2-14).
next=$(python3 -c 'import datetime as d; print((d.datetime.now(d.timezone.utc) + d.timedelta(days=90)).strftime("%Y-%m-%dT%H:%M:%SZ"))')
gcloud kms keys update state --keyring tofu --location "$CFOKIT_REGION" \
  --rotation-period 90d --next-rotation-time "$next" --quiet >/dev/null
# Owner does not include encrypting and decrypting with a key.
gcloud kms keys add-iam-policy-binding state --keyring tofu --location "$CFOKIT_REGION" \
  --member "user:$(gcloud config get account)" \
  --role roles/cloudkms.cryptoKeyEncrypterDecrypter --quiet >/dev/null
done_ "tofu/state, usable by $(gcloud config get account)"

step "tofu init"
tf init -input=false -reconfigure >/dev/null
done_ "initialized"
