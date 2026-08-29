#!/usr/bin/env bash
# E2E verification against the deployed stack. Not a test suite — a live check
# of the plan's exit criteria, one curl at a time.
set -uo pipefail

# `pipefail` alone was not enough: every check below is a pipeline ending in a
# python assertion, and nothing read the pipeline's status, so a check that
# crashed printed its traceback and the run still reported ALL CHECKS PASSED.
# That happened, on a query that came back empty. Every check now ends in
# `|| fail "<name>"`, and the query calls carry a timeout so a hung request
# fails loudly instead of piping nothing into a JSON parser.

# Read regulens.env so this needs no arguments after a quickstart run.
CONFIG="${CONFIG:-$(dirname "$0")/../regulens.env}"
if [[ -f "$CONFIG" ]]; then
  while IFS= read -r line; do
    [[ "$line" =~ ^[[:space:]]*# ]] && continue
    [[ "$line" != *=* ]] && continue
    key="$(printf %s "${line%%=*}" | tr -d '[:space:]')"
    [[ "$key" =~ ^[A-Z_][A-Z0-9_]*$ ]] || continue
    [[ -n "${!key:-}" ]] && continue
    printf -v "$key" %s "${line#*=}"; export "${key?}"
  done < "$CONFIG"
fi
PROJECT_ID="${PROJECT_ID:?set PROJECT_ID, or put it in regulens.env}"
REGION="${REGION:-asia-southeast1}"
# Cloud Run's project-number hostname, which is knowable without a lookup.
PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"
API="${API:-https://regulens-api-${PROJECT_NUMBER}.${REGION}.run.app}"
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
gcloud run jobs execute regulens-job --region "$REGION" --project "$PROJECT_ID" --wait 2>&1 | tail -3
PRODUCT=$(curl -sf "$API/products" | python3 -c "import sys,json; ps=json.load(sys.stdin)['products']; print(next(p['id'] for p in ps if p['name']=='Herbal Drink Powder'))")
echo "product: $PRODUCT"

say "baseline compliance"
# The whole drill rests on Germany starting from `unknown`: the headline is that
# it flips without anyone asking. That is only true on a workspace with no EU
# rules in it, and this script uploads one — so it removes it again at the end.
# Before that cleanup existed the assertion could only hold on the first run
# ever, and because no check read its exit status it failed in silence while the
# script still printed ALL CHECKS PASSED.
curl -sf "$API/products/$PRODUCT/compliance" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print('statuses:', d['statuses'])
print('issues:', d['issue_counts'])
assert d['statuses'].get('market_id') == 'compliant', 'Indonesia must read compliant'
if d['statuses'].get('market_de') != 'unknown':
    raise SystemExit(
        'PRECONDITION NOT MET: Germany reads ' + str(d['statuses'].get('market_de'))
        + ', not unknown, so the unprompted flip cannot be observed here — it has '
        'already happened. This workspace holds EU rules, most likely the bundled '
        'rulebook. Either run scripts/verify_local.sh, which starts from a wiped '
        'stack, or remove the EU documents first (DELETE /documents/{id}).'
    )
print('UC baseline OK')" || fail "baseline compliance"

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
print('UC-C OK: cross-jurisdiction conflict open')" || fail "cross-jurisdiction conflict"

say "the flip: Germany non_compliant with no user action"
sleep 30
curl -sf "$API/products/$PRODUCT/compliance" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print('statuses:', d['statuses'])
assert d['statuses'].get('market_de') == 'non_compliant', 'Germany must flip to non_compliant'
print('UC-B OK: unprompted flip')" || fail "unprompted flip"

say "alerts"
curl -sf "$API/alerts" | python3 -c "
import sys, json
a = json.load(sys.stdin)['alerts']
assert len(a) >= 1, 'no alert'
print(f'{len(a)} alert(s); newest:', a[0].get('after'))
print('alert OK')" || fail "alert"

say "query: why is my product at risk"
curl -s --max-time 120 -X POST "$API/query" -H 'Content-Type: application/json' \
  -d "{\"question\": \"Why is my product at risk?\", \"product_id\": \"$PRODUCT\"}" | python3 -c "
import sys, json
r = json.load(sys.stdin)
print('intent:', r['intent'], '| refusal:', r['refusal'])
print('answer:', r['answer'][:220])
assert r['cited_clauses'], 'must cite stored clauses'
print('grounding OK,', len(r['cited_clauses']), 'citation(s)')" || fail "grounded query"

say "query refusal: no data for Japan"
curl -s --max-time 120 -X POST "$API/query" -H 'Content-Type: application/json' \
  -d '{"question": "What are the Japan requirements for sodium benzoate?"}' | python3 -c "
import sys, json
r = json.load(sys.stdin)
print('refusal:', r['refusal'], '| answer:', r['answer'][:140])
assert r['refusal'], 'must refuse when no data ingested'
print('refusal OK')" || fail "query refusal"

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
print('cached:', d['cached'], '-> same doc id', d['document']['id'])" || fail "upload cache"

say "redelivery produces no duplicate clauses"
COUNT_BEFORE=$(curl -sf "$API/documents/$DOC_ID" | python3 -c "import sys,json; print(len(json.load(sys.stdin)['clauses']))")
gcloud pubsub topics publish document.uploaded --project "$PROJECT_ID" \
  --message="{\"document_id\":\"$DOC_ID\",\"workspace_id\":\"ws_demo\"}" >/dev/null
sleep 25
COUNT_AFTER=$(curl -sf "$API/documents/$DOC_ID" | python3 -c "import sys,json; print(len(json.load(sys.stdin)['clauses']))")
echo "clauses before=$COUNT_BEFORE after=$COUNT_AFTER"
[ "$COUNT_BEFORE" = "$COUNT_AFTER" ] && echo "redelivery OK" || fail "duplicate clauses after redelivery"

say "cleanup: put the workspace back where the drill found it"
# Without this the run is not repeatable: the EU document it uploads is exactly
# what makes Germany non_compliant, so the next run's baseline assertion cannot
# hold. Leaving it behind is also how six copies of one regulation accumulated in
# the demo workspace. Pass KEEP=1 to inspect the document after a run.
if [ -n "${KEEP:-}" ]; then
  echo "kept $DOC_ID (KEEP is set); the next run's baseline check will fail"
else
  curl -s -X DELETE "$API/documents/$DOC_ID" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print('removed', d['deleted'] + ':', d['clauses'], 'clauses,', d['derived'],
      'derived records,', d['products_reevaluated'], 'product(s) re-evaluated')" \
    || fail "cleanup"
  # Reported, not asserted. Germany returns to `unknown` only if nothing else in
  # the graph carries an EU limit, and a workspace that has loaded the bundled
  # rulebook has plenty — that is the rulebook working, not a dirty workspace.
  curl -sf "$API/products/$PRODUCT/compliance" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print('statuses after cleanup:', d['statuses'])
if d['statuses'].get('market_de') != 'unknown':
    print('note: Germany still reads', d['statuses'].get('market_de'), '— other EU rules')
    print('      remain in the graph, most likely the bundled rulebook. Re-running')
    print('      the unprompted-flip drill needs a workspace without EU rules;')
    print('      scripts/verify_local.sh gets one from a wiped stack every time.')" \
    || fail "cleanup status read"
fi

say "ALL CHECKS PASSED"
