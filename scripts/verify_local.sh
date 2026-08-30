#!/usr/bin/env bash
# E2E verification against the FULLY LOCAL stack (docker compose): Firestore and
# Pub/Sub emulators, a filesystem stand-in for Cloud Storage, and FAKE_LLM
# canned extraction. Nothing here touches GCP or costs money.
#
# What this proves: the pipeline, the push wiring, idempotency, the guardrail,
# the conflict rule, the impact flip, and the UI's API surface.
# What this does NOT prove: extraction accuracy, embedding quality, judge
# behaviour, IAM, or real Vertex output. Those need scripts/verify_e2e.sh
# against the deployed stack.
set -uo pipefail

API="${API:-http://localhost:8080}"
EU_PDF="${EU_PDF:-data/regulations/excerpts/EU-annex-II-14.1.4-flavoured-drinks-excerpt.pdf}"

say() { printf '\n=== %s\n' "$1"; }
fail() { echo "FAIL: $1"; exit 1; }

say "stack up"
docker compose up -d firestore pubsub api worker >/dev/null 2>&1 || fail "compose up"
for _ in $(seq 1 60); do
  curl -sf -m 3 "$API/health" >/dev/null && break
  sleep 2
done
curl -sf "$API/health" | head -c 200; echo || fail "health"
curl -sf "http://localhost:8081/health" | head -c 120; echo || fail "worker health"

say "topics + push subscriptions"
docker compose up pubsub-init 2>&1 | grep -E "subscription" | sed 's/^/  /'

say "markets seed"
curl -s -X POST "$API/markets/seed" >/dev/null || fail "markets seed"
echo "  seeded"

say "seed job (baseline: BPOM ingested, Indonesia compliant)"
docker compose run --rm api python -m app.job 2>&1 | tail -1
PRODUCT=$(curl -sf "$API/products" | python3 -c "import sys,json; ps=json.load(sys.stdin)['products']; print(next(p['id'] for p in ps if p['name']=='Herbal Drink Powder'))")
echo "product: $PRODUCT"

say "baseline compliance"
curl -sf "$API/products/$PRODUCT/compliance" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print('statuses:', d['statuses'])
print('issues:', d['issue_counts'])
assert d['statuses'].get('market_id') == 'compliant', 'Indonesia must read compliant'
assert d['statuses'].get('market_de') == 'unknown', 'Germany must read unknown'
print('UC baseline OK')" || fail "baseline"

say "upload EU PDF (filesystem storage, real multipart path)"
DOC=$(curl -s -X POST "$API/documents" \
  -F source_type=official_regulation \
  -F source_name="Commission Regulation (EU) No 1129/2011" \
  -F jurisdiction=EU \
  -F "file=@$EU_PDF;type=application/pdf")
DOC_ID=$(echo "$DOC" | python3 -c "import sys,json; print(json.load(sys.stdin)['document']['id'])") || fail "upload"
echo "document: $DOC_ID"

say "poll document until extracted"
STATUS=""
for _ in $(seq 1 40); do
  STATUS=$(curl -sf "$API/documents/$DOC_ID" | python3 -c "import sys,json; print(json.load(sys.stdin)['document']['status'])")
  echo "  $STATUS"
  [ "$STATUS" = "extracted" ] && break
  [ "$STATUS" = "failed" ] && fail "document failed"
  sleep 3
done
[ "$STATUS" = "extracted" ] || fail "extraction did not finish"

say "cross-jurisdiction conflict"
for _ in $(seq 1 20); do
  N=$(curl -sf "$API/conflicts" | python3 -c "import sys,json; print(len(json.load(sys.stdin)['conflicts']))")
  [ "$N" -ge 1 ] && break
  sleep 3
done
echo "  $N open conflict(s)"
[ "${N:-0}" -ge 1 ] || fail "expected a cross-jurisdiction conflict"

say "the flip: Germany non_compliant with no user action"
for _ in $(seq 1 20); do
  DE=$(curl -sf "$API/products/$PRODUCT/compliance" | python3 -c "import sys,json; print(json.load(sys.stdin)['statuses'].get('market_de'))")
  echo "  market_de=$DE"
  [ "$DE" = "non_compliant" ] && break
  sleep 3
done
[ "$DE" = "non_compliant" ] || fail "Germany did not flip"

say "alerts"
curl -sf "$API/alerts" | python3 -c "
import sys, json
a = json.load(sys.stdin)['alerts']
assert len(a) >= 1, 'no alert'
print(f'{len(a)} alert(s); newest:', a[0].get('after'))" || fail "alerts"

say "a rule that has not entered into force yet"
# Indonesia passes today at 400 mg/kg. This document tightens it to 50 and says
# it applies in 2027. Today's verdict must not move; the deadline must appear.
FUTURE_DOC=$(curl -sf -X POST "$API/documents" \
  -F source_type=official_regulation \
  -F source_name="BPOM Perka 3/2027 (draft, adopted)" \
  -F jurisdiction=ID_BPOM \
  -F "text=Peraturan Badan POM Nomor 3 Tahun 2027 tentang Bahan Tambahan Pangan.

Pengawet — natrium benzoat, INS: 211.

14.1.4 Minuman berbasis air berperisa 50

Peraturan ini shall apply from 2027-01-12." \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['document']['id'])") || fail "future upload"
echo "document: $FUTURE_DOC"

for _ in $(seq 1 20); do
  STATE=$(curl -sf "$API/documents/$FUTURE_DOC" | python3 -c "import sys,json; print(json.load(sys.stdin)['document']['status'])")
  echo "  $STATE"
  case "$STATE" in extracted|reconciled) break ;; failed) fail "future document failed to extract" ;; esac
  sleep 3
done
case "$STATE" in extracted|reconciled) ;; *) fail "future document never finished extracting" ;; esac

for _ in $(seq 1 20); do
  OK=$(curl -sf "$API/products/$PRODUCT/compliance" | python3 -c "
import sys, json
d = json.load(sys.stdin)
up = (d.get('upcoming') or {}).get('market_id') or {}
print('yes' if up.get('effective_date') == '2027-01-12' else 'no')")
  [ "$OK" = "yes" ] && break
  sleep 3
done
curl -sf "$API/products/$PRODUCT/compliance" | python3 -c "
import sys, json
d = json.load(sys.stdin)
today = d['statuses'].get('market_id')
up = (d.get('upcoming') or {}).get('market_id') or {}
assert today != 'non_compliant', f'a 2027 rule must not fail the product today (got {today})'
assert up.get('effective_date') == '2027-01-12', f'no deadline reported: {up}'
assert up.get('status') == 'non_compliant', f'the deadline must carry its verdict: {up}'
assert up.get('clause_id') and up.get('document_id'), f'the deadline must name the rule that sets it: {up}'
print('today:', today, '-> ', up['status'], 'from', up['effective_date'], 'because of', up['clause_id'])" || fail "time-aware verdict"

curl -sf "$API/alerts" | python3 -c "
import sys, json
a = json.load(sys.stdin)['alerts']
scheduled = [x for x in a if (x.get('context') or {}).get('scheduled')]
assert scheduled, 'a deadline nobody is told about is not a warning'
ctx = scheduled[0]['context']
assert ctx.get('cause_available'), 'a scheduled alert that cannot name its rule reads as if the rule was deleted'
assert ctx.get('effective_date') == '2027-01-12', f'the alert must carry the date: {ctx}'
print(len(scheduled), 'scheduled alert(s); first:', scheduled[0]['after'], '| source:', ctx.get('source_name'))" || fail "scheduled alert"

say "cache hit on identical re-upload"
curl -s -X POST "$API/documents" \
  -F source_type=official_regulation \
  -F source_name="Commission Regulation (EU) No 1129/2011" \
  -F jurisdiction=EU \
  -F "file=@$EU_PDF;type=application/pdf" | python3 -c "
import sys, json
d = json.load(sys.stdin)
assert d.get('cached') is True, 'identical upload must short-circuit'
print('cached:', d['cached'], '-> same doc id', d['document']['id'])" || fail "cache"

say "redelivery produces no duplicate clauses"
BEFORE=$(curl -sf "$API/documents/$DOC_ID" | python3 -c "import sys,json; print(len(json.load(sys.stdin)['clauses']))")
docker compose exec -T -e PUBSUB_EMULATOR_HOST=pubsub:8085 api python -c "
from google.cloud import pubsub_v1
import json, os
p = pubsub_v1.PublisherClient()
p.publish(p.topic_path('regulens-local','document.uploaded'),
          json.dumps({'document_id': '$DOC_ID', 'workspace_id': 'ws_demo'}).encode()).result()
print('republished')" || fail "republish"
sleep 12
AFTER=$(curl -sf "$API/documents/$DOC_ID" | python3 -c "import sys,json; print(len(json.load(sys.stdin)['clauses']))")
echo "clauses before=$BEFORE after=$AFTER"
[ "$BEFORE" = "$AFTER" ] || fail "duplicate clauses after redelivery"

say "ALL LOCAL CHECKS PASSED"
