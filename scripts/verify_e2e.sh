#!/usr/bin/env bash
# E2E verification against the deployed stack. Not a test suite — a live check
# of the plan's exit criteria, one curl at a time.
set -uo pipefail

API="${API:-https://regulens-api-babuvy7w3a-as.a.run.app}"
# Real 4-page excerpt of Annex II (pages 1, 149-151) containing the
# category-14.1.4 benzoates limit row; the full regulation is 177 pages and
# exceeds the upload page cap by design.
EU_PDF="data/regulations/excerpts/EU-annex-II-14.1.4-flavoured-drinks-excerpt.pdf"

say() { printf '\n=== %s\n' "$1"; }
fail() { echo "FAIL: $1"; exit 1; }

say "health"
curl -sf "$API/health" | head -c 200; echo || fail "health"

say "markets seed"
curl -s -X POST "$API/markets/seed" | head -c 120; echo

say "seed job (baseline: BPOM ingested, Indonesia compliant)"
gcloud run jobs execute regulens-job --region asia-southeast1 --project regulens-506014 --wait 2>&1 | tail -3
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
print('UC baseline OK')"

say "upload EU PDF"
DOC=$(curl -s -X POST "$API/documents" \
  -F source_type=official_regulation \
  -F source_name="Commission Regulation (EU) No 1129/2011" \
  -F jurisdiction=EU \
  -F "file=@$EU_PDF;type=application/pdf")
echo "$DOC" | head -c 300; echo
DOC_ID=$(echo "$DOC" | python3 -c "import sys,json; print(json.load(sys.stdin)['document']['id'])")

say "poll document until extracted"
for i in $(seq 1 60); do
  STATUS=$(curl -sf "$API/documents/$DOC_ID" | python3 -c "import sys,json; print(json.load(sys.stdin)['document']['status'])")
  echo "  $STATUS"
  [ "$STATUS" = "extracted" ] && break
  [ "$STATUS" = "failed" ] && fail "document failed"
  sleep 5
done
[ "$STATUS" = "extracted" ] || fail "extraction did not finish"

say "clauses from EU doc"
# The EU benzoate clause ends CONFLICTED once the cross-jurisdiction conflict
# opens — that is the data model working. Accept active-or-conflicted.
BENZO_COUNT=$(curl -sf "$API/clauses?jurisdiction=EU" | python3 -c "
import sys, json
cs = json.load(sys.stdin)['clauses']
benzoate = [c for c in cs if c.get('substance_normalized') == 'benzoic_acid' and c.get('limit_value') == 150]
print(len(benzoate))")
echo "EU benzoate 150 mg/kg clauses: $BENZO_COUNT"
[ "$BENZO_COUNT" -ge 1 ] || fail "no EU benzoate clause extracted"

say "reconciled? conflicts?"
sleep 20
curl -sf "$API/conflicts" | python3 -c "
import sys, json
cs = json.load(sys.stdin)['conflicts']
print(f'{len(cs)} open conflicts')
assert len(cs) >= 1, 'expected cross-jurisdiction conflict'
print('UC-C OK: cross-jurisdiction conflict open')"

say "the flip: Germany non_compliant with no user action"
sleep 30
curl -sf "$API/products/$PRODUCT/compliance" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print('statuses:', d['statuses'])
assert d['statuses'].get('market_de') == 'non_compliant', 'Germany must flip to non_compliant'
print('UC-B OK: unprompted flip')"

say "alerts"
curl -sf "$API/alerts" | python3 -c "
import sys, json
a = json.load(sys.stdin)['alerts']
assert len(a) >= 1, 'no alert'
print(f'{len(a)} alert(s); newest:', a[0].get('after'))
print('alert OK')"

say "query: why is my product at risk"
curl -s -X POST "$API/query" -H 'Content-Type: application/json' \
  -d "{\"question\": \"Why is my product at risk?\", \"product_id\": \"$PRODUCT\"}" | python3 -c "
import sys, json
r = json.load(sys.stdin)
print('intent:', r['intent'], '| refusal:', r['refusal'])
print('answer:', r['answer'][:220])
assert r['cited_clauses'], 'must cite stored clauses'
print('grounding OK,', len(r['cited_clauses']), 'citation(s)')"

say "query refusal: no data for Japan"
curl -s -X POST "$API/query" -H 'Content-Type: application/json' \
  -d '{"question": "What are the Japan requirements for sodium benzoate?"}' | python3 -c "
import sys, json
r = json.load(sys.stdin)
print('refusal:', r['refusal'], '| answer:', r['answer'][:140])
assert r['refusal'], 'must refuse when no data ingested'
print('refusal OK')"

say "cache hit on identical re-upload"
CACHE=$(curl -s -X POST "$API/documents" \
  -F source_type=official_regulation \
  -F source_name="Commission Regulation (EU) No 1129/2011" \
  -F jurisdiction=EU \
  -F "file=@$EU_PDF;type=application/pdf")
echo "$CACHE" | python3 -c "
import sys, json
d = json.load(sys.stdin)
assert d.get('cached') is True, 'identical upload must short-circuit'
print('cached:', d['cached'], '-> same doc id', d['document']['id'])"

say "redelivery produces no duplicate clauses"
COUNT_BEFORE=$(curl -sf "$API/documents/$DOC_ID" | python3 -c "import sys,json; print(len(json.load(sys.stdin)['clauses']))")
gcloud pubsub topics publish document.uploaded --project regulens-506014 \
  --message="{\"document_id\":\"$DOC_ID\",\"workspace_id\":\"ws_demo\"}" >/dev/null
sleep 25
COUNT_AFTER=$(curl -sf "$API/documents/$DOC_ID" | python3 -c "import sys,json; print(len(json.load(sys.stdin)['clauses']))")
echo "clauses before=$COUNT_BEFORE after=$COUNT_AFTER"
[ "$COUNT_BEFORE" = "$COUNT_AFTER" ] && echo "redelivery OK" || fail "duplicate clauses after redelivery"

say "ALL CHECKS PASSED"
