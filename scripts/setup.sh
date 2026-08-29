#!/usr/bin/env bash
# ReguLens — GCP provisioning. Re-runnable: every step is idempotent, so running
# this twice is a no-op, not an error. This is the IaC substitute for the
# hackathon and it is what the README points at.
set -euo pipefail

# Read regulens.env when it exists so a clone configures one file, not five.
CONFIG="${CONFIG:-$(dirname "$0")/../regulens.env}"
if [[ -f "$CONFIG" ]]; then
  while IFS= read -r line; do
    [[ "$line" =~ ^[[:space:]]*# ]] && continue
    [[ "$line" != *=* ]] && continue
    key="$(printf %s "${line%%=*}" | tr -d '[:space:]')"
    [[ "$key" =~ ^[A-Z_][A-Z0-9_]*$ ]] || continue
    [[ -n "${!key:-}" ]] && continue     # a real env var still wins
    printf -v "$key" %s "${line#*=}"
    export "${key?}"
  done < "$CONFIG"
fi

PROJECT_ID="${PROJECT_ID:?set PROJECT_ID, or put it in regulens.env}"
REGION="${REGION:-asia-southeast1}"
BUCKET="${BUCKET:-${PROJECT_ID}-uploads}"
REPO="${REPO:-regulens}"

# Vertex: asia-southeast1 only carries gemini-2.5-flash, which fails the
# hackathon's 3.5+ requirement, so generation runs against the global endpoint
# while embeddings stay in-region.
GEMINI_LOCATION="${GEMINI_LOCATION:-global}"
GEMINI_MODEL="${GEMINI_MODEL:-gemini-3.5-flash}"
EMBED_LOCATION="${EMBED_LOCATION:-asia-southeast1}"
EMBED_MODEL="${EMBED_MODEL:-text-multilingual-embedding-002}"

TOPICS=(document.uploaded clause.extracted graph.changed)
DLQ_TOPIC="regulens.deadletter"

SA_API="regulens-api"
SA_WORKER="regulens-worker"
SA_INVOKER="regulens-pubsub-invoker"

g() { gcloud "$@" --project "$PROJECT_ID"; }
say() { printf '\n=== %s\n' "$1"; }

say "APIs"
g services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  firestore.googleapis.com \
  storage.googleapis.com \
  pubsub.googleapis.com \
  aiplatform.googleapis.com \
  secretmanager.googleapis.com \
  monitoring.googleapis.com \
  logging.googleapis.com \
  cloudtrace.googleapis.com \
  cloudscheduler.googleapis.com \
  clouderrorreporting.googleapis.com \
  billingbudgets.googleapis.com

say "Artifact Registry"
g artifacts repositories describe "$REPO" --location "$REGION" >/dev/null 2>&1 || \
  g artifacts repositories create "$REPO" --repository-format=docker --location "$REGION" \
    --description="ReguLens container images"

say "Firestore (Native mode)"
g firestore databases describe --database="(default)" >/dev/null 2>&1 || \
  g firestore databases create --location="$REGION" --type=firestore-native

say "Firestore composite indexes"
# Single-field filters are served by Firestore's automatic indexes, which is why
# there are only three of these: the API deliberately filters on one field and
# refines in process. Creating an index that already exists returns an error
# rather than a no-op, so the failure is tolerated instead of aborting the run.
INDEX_FILE="$(dirname "$0")/../firestore.indexes.json"
if [[ -f "$INDEX_FILE" ]]; then
  g firestore indexes create --file="$INDEX_FILE" >/dev/null 2>&1 \
    && echo "indexes submitted (they build in the background)" \
    || echo "indexes already present, or already building"
else
  echo "no firestore.indexes.json — skipping"
fi

say "GCS bucket"
gcloud storage buckets describe "gs://$BUCKET" --project "$PROJECT_ID" >/dev/null 2>&1 || \
  gcloud storage buckets create "gs://$BUCKET" --project "$PROJECT_ID" \
    --location="$REGION" --uniform-bucket-level-access --public-access-prevention

say "Pub/Sub topics"
for t in "${TOPICS[@]}" "$DLQ_TOPIC"; do
  g pubsub topics describe "$t" >/dev/null 2>&1 || g pubsub topics create "$t"
done

say "Service accounts"
for sa in "$SA_API" "$SA_WORKER" "$SA_INVOKER"; do
  g iam service-accounts describe "${sa}@${PROJECT_ID}.iam.gserviceaccount.com" >/dev/null 2>&1 || \
    g iam service-accounts create "$sa" --display-name "ReguLens ${sa}"
done

api="serviceAccount:${SA_API}@${PROJECT_ID}.iam.gserviceaccount.com"
worker="serviceAccount:${SA_WORKER}@${PROJECT_ID}.iam.gserviceaccount.com"
invoker="serviceAccount:${SA_INVOKER}@${PROJECT_ID}.iam.gserviceaccount.com"

say "IAM — narrow roles, never the default compute SA"
# Project-level roles that have no per-resource equivalent worth the complexity.
for role in roles/datastore.user roles/aiplatform.user roles/pubsub.publisher \
            roles/logging.logWriter roles/cloudtrace.agent roles/errorreporting.writer; do
  g projects add-iam-policy-binding "$PROJECT_ID" --member "$api" --role "$role" --condition=None >/dev/null
  g projects add-iam-policy-binding "$PROJECT_ID" --member "$worker" --role "$role" --condition=None >/dev/null
done

# Bucket-scoped, not project-wide.
gcloud storage buckets add-iam-policy-binding "gs://$BUCKET" --project "$PROJECT_ID" \
  --member "$api" --role roles/storage.objectAdmin >/dev/null
gcloud storage buckets add-iam-policy-binding "gs://$BUCKET" --project "$PROJECT_ID" \
  --member "$worker" --role roles/storage.objectViewer >/dev/null

# Pub/Sub needs to mint OIDC tokens as the invoker SA when pushing.
PROJECT_NUMBER="$(g projects describe "$PROJECT_ID" --format='value(projectNumber)')"
g projects add-iam-policy-binding "$PROJECT_ID" \
  --member "serviceAccount:service-${PROJECT_NUMBER}@gcp-sa-pubsub.iam.gserviceaccount.com" \
  --role roles/iam.serviceAccountTokenCreator --condition=None >/dev/null

say "Push subscriptions"
# The worker must exist before its push endpoint does. Re-run this script after
# the first deploy, with WORKER_URL set, to create them.
WORKER_URL="${WORKER_URL:-$(g run services describe regulens-worker --region "$REGION" \
  --format='value(status.url)' 2>/dev/null || true)}"
if [[ -z "$WORKER_URL" ]]; then
  echo "worker service not deployed yet — skipping subscriptions. Re-run after deploy."
else
  g run services add-iam-policy-binding regulens-worker --region "$REGION" \
    --member "$invoker" --role roles/run.invoker >/dev/null
  for t in "${TOPICS[@]}" "$DLQ_TOPIC"; do
    sub="${t}.worker"
    path="/internal/$(echo "$t" | tr '.' '-')"
    # The dead-letter route has no dots to translate; keep the mapping explicit.
    if [[ "$t" == "$DLQ_TOPIC" ]]; then path="/internal/dead-letter"; fi
    args=(--push-endpoint="${WORKER_URL}${path}"
          --push-auth-service-account="${SA_INVOKER}@${PROJECT_ID}.iam.gserviceaccount.com"
          --ack-deadline=600)
    if [[ "$t" != "$DLQ_TOPIC" ]]; then
      args+=(--dead-letter-topic="$DLQ_TOPIC" --max-delivery-attempts=5)
    fi
    if g pubsub subscriptions describe "$sub" >/dev/null 2>&1; then
      g pubsub subscriptions update "$sub" "${args[@]}"
    else
      g pubsub subscriptions create "$sub" --topic "$t" "${args[@]}"
    fi
  done
  g pubsub subscriptions describe "${DLQ_TOPIC}.pull" >/dev/null 2>&1 || \
    g pubsub subscriptions create "${DLQ_TOPIC}.pull" --topic "$DLQ_TOPIC"
fi

say "Cloud Scheduler — the nightly source check"
# What makes the product a monitor rather than a checker: once a day the worker
# re-reads every watched regulator address. A check that finds nothing costs a
# conditional GET and a hash comparison, so the daily run is close to free; the
# model only runs when a regulation actually changed.
#
# 06:00 Asia/Jakarta, so a change that landed overnight in Brussels is already
# in the graph before anyone in the target market opens the app.
if [[ -z "${WORKER_URL:-}" ]]; then
  echo "worker service not deployed yet — skipping the scheduler job. Re-run after deploy."
else
  # Cloud Scheduler mints the OIDC token as the invoker SA, which already holds
  # run.invoker on the worker. It needs permission to act as that SA, and the
  # binding is not always created for you.
  g iam service-accounts add-iam-policy-binding \
    "${SA_INVOKER}@${PROJECT_ID}.iam.gserviceaccount.com" \
    --member "serviceAccount:service-${PROJECT_NUMBER}@gcp-sa-cloudscheduler.iam.gserviceaccount.com" \
    --role roles/iam.serviceAccountTokenCreator >/dev/null 2>&1 || true

  JOB="regulens-source-check"
  # The audience must be the service's root URL, not the path being called.
  # Cloud Run validates it against its own hostname and rejects a token whose
  # audience carries the path — a 401 that reads exactly like a missing role.
  sched_args=(--schedule="0 6 * * *"
              --time-zone="Asia/Jakarta"
              --uri="${WORKER_URL}/internal/check-sources"
              --http-method=POST
              --headers="Content-Type=application/json"
              --message-body='{"force":false}'
              --oidc-service-account-email="${SA_INVOKER}@${PROJECT_ID}.iam.gserviceaccount.com"
              --oidc-token-audience="${WORKER_URL}"
              --attempt-deadline=1800s
              --location="$REGION")
  if g scheduler jobs describe "$JOB" --location "$REGION" >/dev/null 2>&1; then
    g scheduler jobs update http "$JOB" "${sched_args[@]}"
  else
    g scheduler jobs create http "$JOB" "${sched_args[@]}"
  fi
  echo "scheduler job $JOB -> ${WORKER_URL}/internal/check-sources (daily 06:00 Asia/Jakarta)"
fi

say "Done"
cat <<EOF
project        $PROJECT_ID
region         $REGION
bucket         gs://$BUCKET
gemini         $GEMINI_MODEL @ $GEMINI_LOCATION
embeddings     $EMBED_MODEL @ $EMBED_LOCATION
topics         ${TOPICS[*]} (dlq: $DLQ_TOPIC)
source check   daily 06:00 Asia/Jakarta (Cloud Scheduler -> worker /internal/check-sources)
EOF
