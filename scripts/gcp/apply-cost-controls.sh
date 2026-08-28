#!/usr/bin/env bash
# Applies the storage and registry retention rules that keep the project inside
# the Always Free tier. Everything here needs billing linked to the project —
# the APIs refuse with BILLING_DISABLED otherwise. Safe to re-run.
set -euo pipefail

PROJECT="${PROJECT:-regulens-506014}"
REGION="${REGION:-asia-southeast1}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Project: ${PROJECT}"

# Uploaded documents are demo input. Nothing reads them after extraction, and
# 5 GB is the whole free allowance.
gcloud storage buckets update "gs://${PROJECT}-uploads" \
  --lifecycle-file="${HERE}/uploads-lifecycle.json" \
  --project="${PROJECT}"

# Cloud Build keeps a tarball of the source for every single build.
gcloud storage buckets update "gs://${PROJECT}_cloudbuild" \
  --lifecycle-file="${HERE}/cloudbuild-lifecycle.json" \
  --project="${PROJECT}"

# Artifact Registry gives 0.5 GB free. One API image is a large fraction of
# that, and every build pushes another SHA tag.
gcloud artifacts repositories set-cleanup-policies regulens \
  --location="${REGION}" \
  --policy="${HERE}/artifact-cleanup-policy.json" \
  --project="${PROJECT}"

echo "Done. Verify with:"
echo "  gcloud storage buckets describe gs://${PROJECT}-uploads --format='value(lifecycle)'"
echo "  gcloud artifacts repositories describe regulens --location=${REGION}"
