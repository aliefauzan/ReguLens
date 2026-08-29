#!/usr/bin/env python3
"""Measure the upload-to-flip latency the README quotes, stage by stage.

The 183s figure recorded on 23 August came from a hand-timed drill. A number
that goes in a README should be reproducible by whoever reads it, so this is
the drill written down: one document in, a stopwatch on each stage, one line of
output per stage.

    python3 scripts/measure_latency.py                      # short pasted rule
    python3 scripts/measure_latency.py <path-to.pdf>        # a real document
    API=http://localhost:8080 python3 scripts/measure_latency.py

Give it the 4-page EU excerpt the other drills use to compare against the
183s figure recorded on 23 August:

    python3 scripts/measure_latency.py \\
      data/regulations/excerpts/EU-annex-II-14.1.4-flavoured-drinks-excerpt.pdf

Stages, all measured from the moment the upload request returns:

    upload -> extracted        text out of the document, clauses persisted
    extracted -> reconciled    every clause of this document out of
                               pending_reconciliation
    reconciled -> evaluated    the product's requirements name a clause from
                               this document, i.e. impact has landed

The document is pasted text with a run marker appended, because identical bytes
hit the upload cache by design and a cached upload measures nothing.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid

def _default_api() -> str:
    """Where to measure when `API` is not set.

    `regulens.env` is the one file a clone edits, so the project id lives there.
    Cloud Run publishes a service at https://SERVICE-PROJECTNUMBER.REGION.run.app,
    which is derivable from the project — no hostname belonging to any one
    deployment is written down here.
    """
    config = pathlib.Path(__file__).resolve().parent.parent / "regulens.env"
    values: dict[str, str] = {}
    if config.exists():
        for line in config.read_text().splitlines():
            if line.strip().startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip()
    project = os.environ.get("PROJECT_ID") or values.get("PROJECT_ID", "")
    region = os.environ.get("REGION") or values.get("REGION") or "asia-southeast1"
    if not project or project == "your-project-id":
        raise SystemExit(
            "Set API, or PROJECT_ID in regulens.env, so this knows what to measure."
        )
    number = subprocess.run(
        ["gcloud", "projects", "describe", project, "--format=value(projectNumber)"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    return f"https://regulens-api-{number}.{region}.run.app"


API = (os.environ.get("API") or _default_api()).rstrip("/")
TIMEOUT = float(os.environ.get("TIMEOUT", "600"))

# A verbatim row from EU 1129/2011 Annex II, food category 14.1.4 — the same
# clause every other drill turns on. The marker line is outside the quoted text
# and carries no number, so it cannot become a clause.
EU_TEXT = """Commission Regulation (EU) No 1129/2011
Official Journal of the European Union

Food category 14.1.4: Flavoured drinks

| E number | Additive | Maximum level (mg/l or mg/kg as appropriate) |
| E 210-213 | Benzoic acid - benzoates | 150 |

The maximum level applies to the product as consumed.
"""


def get(path: str) -> dict:
    with urllib.request.urlopen(f"{API}{path}", timeout=30) as response:
        return json.load(response)


def post_document(text: str, pdf: bytes | None = None) -> dict:
    """Multipart is what the browser sends; text_inline is the same endpoint
    without a file, and it keeps this script dependency-free."""
    boundary = uuid.uuid4().hex
    fields = {
        "source_type": "official_regulation",
        "source_name": "Commission Regulation (EU) No 1129/2011",
        "jurisdiction": "EU",
    }
    if pdf is None:
        fields["text"] = text
    body = b""
    for name, value in fields.items():
        body += (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
            f"{value}\r\n"
        ).encode()
    if pdf is not None:
        body += (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="excerpt.pdf"\r\n'
            f"Content-Type: application/pdf\r\n\r\n"
        ).encode()
        body += pdf + b"\r\n"
    body += f"--{boundary}--\r\n".encode()
    request = urllib.request.Request(
        f"{API}/documents",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def wait(label: str, predicate, started: float) -> float:
    """Poll until the predicate holds. Returns seconds since `started`."""
    deadline = time.monotonic() + TIMEOUT
    while time.monotonic() < deadline:
        try:
            if predicate():
                return time.monotonic() - started
        except urllib.error.HTTPError as exc:
            if exc.code >= 500:
                raise
        time.sleep(2)
    raise SystemExit(f"TIMEOUT waiting for: {label}")


def main() -> int:
    marker = uuid.uuid4().hex[:8]
    products = get("/products")["products"]
    if not products:
        raise SystemExit("no product in the workspace — run the seed job first")
    # The seeded demo product is the one every other drill measures, and the one
    # whose markets include the EU. A product with no EU market never grows a
    # requirement from an EU clause, and the last stage would wait forever for
    # something that is correctly not happening.
    product_id = next(
        (p["id"] for p in products if p.get("name") == "Herbal Drink Powder"),
        products[0]["id"],
    )
    print(f"api={API}\nproduct={product_id}\nrun={marker}\n")

    pdf_path = sys.argv[1] if len(sys.argv) > 1 else None
    pdf = None
    if pdf_path:
        with open(pdf_path, "rb") as handle:
            # A comment line after %%EOF is legal PDF and every parser ignores
            # it. It changes the hash, which is the whole point: identical bytes
            # short-circuit by design and a cached upload measures nothing.
            pdf = handle.read() + f"\n%ReguLens measurement run {marker}\n".encode()
        print(f"document source: {pdf_path} ({len(pdf)} bytes)")

    started = time.monotonic()
    result = post_document(f"{EU_TEXT}\nReguLens measurement run {marker}\n", pdf)
    if result.get("cached"):
        raise SystemExit("upload was cached — the marker failed to make it unique")
    document_id = result["document"]["id"]
    print(f"document={document_id}")

    def extracted() -> bool:
        status = get(f"/documents/{document_id}")["document"]["status"]
        if status == "failed":
            raise SystemExit("document failed during extraction")
        return status in ("extracted", "reconciling", "reconciled")

    t_extract = wait("extraction", extracted, started)
    clauses = get(f"/documents/{document_id}")["clauses"]
    print(f"  upload -> extracted        {t_extract:6.1f}s  ({len(clauses)} clauses)")

    def reconciled() -> bool:
        current = get(f"/documents/{document_id}")["clauses"]
        return bool(current) and all(
            c.get("status") != "pending_reconciliation" for c in current
        )

    if clauses:
        t_reconcile = wait("reconciliation", reconciled, started)
        print(f"  extracted -> reconciled    {t_reconcile - t_extract:6.1f}s")
    else:
        t_reconcile = t_extract
        print("  extracted -> reconciled       0.0s  (no clauses to reconcile)")

    clause_ids = {c["id"] for c in get(f"/documents/{document_id}")["clauses"]}

    def evaluated() -> bool:
        compliance = get(f"/products/{product_id}/compliance")
        for requirement in compliance.get("requirements", []):
            if requirement.get("clause_id") in clause_ids:
                return True
        return False

    if clause_ids:
        t_impact = wait("impact", evaluated, started)
        print(f"  reconciled -> evaluated    {t_impact - t_reconcile:6.1f}s")
    else:
        t_impact = t_reconcile

    statuses = get(f"/products/{product_id}/compliance")["statuses"]
    print(f"\n  TOTAL upload -> evaluated  {t_impact:6.1f}s")
    print(f"  statuses: {statuses}")

    # Measuring must not leave a mess behind. Six runs of this script against the
    # deployed stack left six near-identical copies of the same EU regulation in
    # the demo workspace, and the next verification run counted them as findings.
    # Pass KEEP=1 to inspect the document afterwards.
    if os.environ.get("KEEP"):
        print(f"\n  kept {document_id} (KEEP is set)")
    else:
        request = urllib.request.Request(f"{API}/documents/{document_id}", method="DELETE")
        with urllib.request.urlopen(request, timeout=120) as response:
            removed = json.load(response)
        print(
            f"\n  cleaned up {document_id}: {removed.get('clauses')} clauses, "
            f"{removed.get('derived')} derived records, "
            f"{removed.get('products_reevaluated')} product(s) re-evaluated"
        )
        after = get(f"/products/{product_id}/compliance")["statuses"]
        print(f"  statuses after cleanup: {after}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
