#!/usr/bin/env bash
# Refuse to ship an image with a critical vulnerability that has a fix.
#
#   vulnerabilities.sh IMAGE...
#
# Artifact Analysis scans every image when it is pushed (infra/gcp/main.tf). This waits for each
# image's scan to finish, lists its critical and high findings, and fails if any critical one has
# a fixed version available: that is a dependency to upgrade before the image runs. A critical
# finding with no fix yet, and every high one, is listed and does not fail, because nothing can be
# done about it but wait. A finding is acted on here, at the deploy, because nobody reads the
# registry's findings otherwise.
#
# A person deploying by hand can accept named findings for one run, which is logged:
#   CFOKIT_ACCEPT_VULNERABILITIES=CVE-2026-1234,CVE-2026-5678 deploy.sh COMMIT
# shellcheck source=env.sh
. "$(dirname "$0")/env.sh"

accepted=",${CFOKIT_ACCEPT_VULNERABILITIES:-},"
failed=0

for image in "$@"; do
  step "Vulnerabilities: ${image##*/}"

  # The scan starts on push and usually finishes in a minute or two.
  report=
  for _ in $(seq 60); do
    report=$(gcloud artifacts docker images describe "$image" \
      --show-package-vulnerability --show-all-metadata --format=json)
    status=$(python3 -c '
import json, sys
d = json.load(sys.stdin)
found = (d.get("discovery_summary") or {}).get("discovery") or [{}]
print((found[0].get("discovery") or {}).get("analysisStatus", "PENDING"))' <<<"$report")
    case "$status" in
      FINISHED_SUCCESS) break ;;
      FINISHED_FAILED | FINISHED_UNSUPPORTED)
        need "The scan of ${image##*/} ended $status: nothing is known about its vulnerabilities."
        exit 1
        ;;
    esac
    sleep 10
  done
  if [ "$status" != FINISHED_SUCCESS ]; then
    need "The scan of ${image##*/} did not finish in ten minutes (last status: $status)."
    exit 1
  fi

  ACCEPTED="$accepted" python3 -c '
import json, os, sys
d = json.load(sys.stdin)
accepted = os.environ["ACCEPTED"]
found = (d.get("package_vulnerability_summary") or {}).get("vulnerabilities") or {}
rows, blocking = [], 0
for severity in ("CRITICAL", "HIGH"):
    for occurrence in found.get(severity, []):
        cve = occurrence.get("noteName", "").rsplit("/", 1)[-1]
        v = occurrence.get("vulnerability", {})
        fix = bool(v.get("fixAvailable"))
        for issue in v.get("packageIssue", []) or [{}]:
            package = issue.get("affectedPackage", "?")
            have = issue.get("affectedVersion", {}).get("fullName", "?")
            want = issue.get("fixedVersion", {}).get("fullName", "") or "no fix yet"
            verdict = "-"
            if severity == "CRITICAL" and fix:
                if f",{cve}," in accepted:
                    verdict = "accepted for this deploy"
                else:
                    verdict = "BLOCKS THE DEPLOY"
                    blocking += 1
            rows.append(f"  {severity:<8} {cve:<18} {package:<34} {have} -> {want}  {verdict}")
print("\n".join(sorted(set(rows))) or "  no critical or high findings")
sys.exit(1 if blocking else 0)' <<<"$report" || failed=1
done

if [ "$failed" != 0 ]; then
  need "A critical vulnerability with a fix is in an image above. Upgrade the package it names, or its base image, and deploy again."
  exit 1
fi
if [ "$accepted" = ",," ]; then
  done_ "no critical vulnerability with a fix"
else
  done_ "no critical vulnerability with a fix, beyond those accepted above"
fi
