#!/usr/bin/env bash
# ReguLens — clone to running stack, one command.
#
#   cp regulens.env.example regulens.env   # set PROJECT_ID
#   bash scripts/quickstart.sh
#
# Provisions the infrastructure, stores your key, deploys api + worker + job +
# web, wires the Pub/Sub push subscriptions, seeds the demo baseline, and prints
# the URL to open. Every step is idempotent: run it again after a code change
# and it redeploys without touching anything that already exists.
set -euo pipefail

cd "$(dirname "$0")/.."
CONFIG="${CONFIG:-regulens.env}"

if [[ ! -f "$CONFIG" ]]; then
  cat >&2 <<EOF
No $CONFIG found. Start from the example — it is the only file you edit:

    cp regulens.env.example $CONFIG
    \$EDITOR $CONFIG        # set PROJECT_ID
    bash scripts/quickstart.sh
EOF
  exit 1
fi

# Read the config without executing it: a config file is data, and `source` on
# data turns a stray backtick into a shell command.
while IFS= read -r line; do
  [[ "$line" =~ ^[[:space:]]*# ]] && continue
  [[ "$line" =~ ^[[:space:]]*$ ]] && continue
  [[ "$line" != *=* ]] && continue
  key="${line%%=*}"; value="${line#*=}"
  key="$(printf %s "$key" | tr -d '[:space:]')"
  [[ "$key" =~ ^[A-Z_][A-Z0-9_]*$ ]] || continue
  printf -v "$key" %s "$value"
  export "${key?}"
done < "$CONFIG"

PROJECT_ID="${PROJECT_ID:-}"
REGION="${REGION:-asia-southeast1}"
GEMINI_API_KEY="${GEMINI_API_KEY:-}"

say() { printf '\n\033[1m=== %s\033[0m\n' "$1"; }
die() { printf '\n%s\n' "$1" >&2; exit 1; }

[[ -n "$PROJECT_ID" && "$PROJECT_ID" != "your-project-id" ]] \
  || die "Set PROJECT_ID in $CONFIG to your own GCP project."
command -v gcloud >/dev/null || die "gcloud is not installed: https://cloud.google.com/sdk/docs/install"
gcloud auth print-access-token >/dev/null 2>&1 \
  || die "Not signed in. Run: gcloud auth login && gcloud auth application-default login"

say "project"
gcloud projects describe "$PROJECT_ID" --format='value(projectId,name)' \
  || die "Cannot read project $PROJECT_ID. Check the id and your permissions."
PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"

# Cloud Run publishes every service at https://SERVICE-PROJECTNUMBER.REGION.run.app.
# That is knowable before the first deploy, which is what lets this be one build
# instead of deploy-look-rebuild. The older project-hash hostname is added below
# once the services exist, because a browser sends whichever the user typed.
API_URL="https://regulens-api-${PROJECT_NUMBER}.${REGION}.run.app"
WEB_URL="https://regulens-web-${PROJECT_NUMBER}.${REGION}.run.app"
ORIGINS="http://localhost:3000,http://localhost:3111,${WEB_URL}"

say "infrastructure"
PROJECT_ID="$PROJECT_ID" REGION="$REGION" bash scripts/setup.sh

say "gemini key"
if [[ -n "$GEMINI_API_KEY" ]]; then
  if gcloud secrets describe gemini-api-key --project "$PROJECT_ID" >/dev/null 2>&1; then
    printf %s "$GEMINI_API_KEY" | gcloud secrets versions add gemini-api-key \
      --project "$PROJECT_ID" --data-file=- >/dev/null
    echo "  updated gemini-api-key"
  else
    printf %s "$GEMINI_API_KEY" | gcloud secrets create gemini-api-key \
      --project "$PROJECT_ID" --data-file=- >/dev/null
    echo "  created gemini-api-key"
  fi
else
  # cloudbuild.yaml mounts the secret unconditionally, so it has to exist. An
  # empty value is read as "no key" and the stack falls back to Vertex AI, which
  # works identically and bills per token.
  gcloud secrets describe gemini-api-key --project "$PROJECT_ID" >/dev/null 2>&1 || \
    printf %s "" | gcloud secrets create gemini-api-key --project "$PROJECT_ID" --data-file=- >/dev/null
  echo "  no key set — model calls will go to Vertex AI"
fi
for sa in regulens-api regulens-worker; do
  gcloud secrets add-iam-policy-binding gemini-api-key --project "$PROJECT_ID" \
    --member "serviceAccount:${sa}@${PROJECT_ID}.iam.gserviceaccount.com" \
    --role roles/secretmanager.secretAccessor >/dev/null
done

say "deploy"
# A unique tag per deploy: Cloud Run skips creating a revision when the image
# tag has not changed, so a plain git short-SHA silently redeploys nothing.
TAG="$(git rev-parse --short HEAD 2>/dev/null || echo manual)-$(date +%H%M%S)"
# ^@^ picks a different separator for the substitution list, because the list of
# allowed origins is itself comma-separated and the default parser splits it.
gcloud builds submit --project "$PROJECT_ID" --config cloudbuild.yaml \
  --substitutions="^@^SHORT_SHA=${TAG}@_REGION=${REGION}@_API_URL=${API_URL}@_WEB_ORIGINS=${ORIGINS}"

say "push subscriptions"
# The worker had no URL before it was deployed, so this is the second pass that
# setup.sh's own message asks for.
PROJECT_ID="$PROJECT_ID" REGION="$REGION" bash scripts/setup.sh

say "origins"
# Whatever hostnames Cloud Run actually handed out, allowed for real.
REAL_WEB="$(gcloud run services describe regulens-web --project "$PROJECT_ID" \
  --region "$REGION" --format='value(status.url)' 2>/dev/null || true)"
REAL_API="$(gcloud run services describe regulens-api --project "$PROJECT_ID" \
  --region "$REGION" --format='value(status.url)' 2>/dev/null || true)"
if [[ -n "$REAL_WEB" && "$REAL_WEB" != "$WEB_URL" ]]; then
  ORIGINS="${ORIGINS},${REAL_WEB}"
  gcloud run services update regulens-api --project "$PROJECT_ID" --region "$REGION" \
    --update-env-vars "^@^CORS_ORIGINS=${ORIGINS}" >/dev/null
  echo "  added $REAL_WEB"
fi

say "seed"
gcloud run jobs execute regulens-job --project "$PROJECT_ID" --region "$REGION" --wait >/dev/null
curl -sf -X POST "${REAL_API:-$API_URL}/markets/seed" >/dev/null || true
echo "  demo product and markets in place"

say "ready"
cat <<EOF
web   ${REAL_WEB:-$WEB_URL}
api   ${REAL_API:-$API_URL}

Open the web URL. The workspace starts with one product and the Indonesian
rule; add the EU rule from the built-in rulebook and watch Germany flip.

Verify the whole pipeline against what you just deployed:
  API=${REAL_API:-$API_URL} bash scripts/verify_e2e.sh
EOF
