"""System-design diagram for ReguLens. Writes docs/architecture.svg and .png.

Renders the deployed Google Cloud topology — the one `scripts/setup.sh`
provisions and `cloudbuild.yaml` deploys.

    pip install -r docs/requirements.txt   # for the bundled GCP icon set
    brew install librsvg                   # for rsvg-convert
    python docs/architecture.py            # writes both files

**Why this emits SVG by hand instead of calling `mingrammer/diagrams`.** It used
to call it. The committed PNG, however, was not what that produced: somebody had
taken the graphviz output into draw.io, laid it out properly, added a legend and
exported by hand — leaving `docs/architecture.xml` as a third artefact and the
README claiming a generator that had not drawn the picture in the README for
some time. Two sources and one of them stale is how a diagram starts lying about
the system. Graphviz also re-ranks the entire graph when an edge is added, so
one new flow reshuffled boxes that had nothing to do with it.

Positions here are therefore explicit. Adding a node moves nothing else, and the
file that describes the picture is the file that draws it. Icons are the ones
`diagrams` ships, embedded as data URIs so the SVG stands alone.

Nothing here talks to GCP; it only draws.
"""

from __future__ import annotations

import base64
import shutil
import subprocess
import sys
from pathlib import Path
from xml.sax.saxutils import escape

HERE = Path(__file__).parent
SVG_OUT = HERE / "architecture.svg"
PNG_OUT = HERE / "architecture.png"

ICONS = Path(sys.prefix) / "lib" / f"python3.{sys.version_info.minor}" / "site-packages" / "resources"

W, H = 2180, 900

INK = "#2d3436"
MUTED = "#6b7280"
CARD = "#ffffff"
CARD_EDGE = "#d7dce2"
CLUSTER = "#eef4fb"
CLUSTER_EDGE = "#cfe0f2"
BANNER = "#4a90d9"

# One colour per kind of connection, and the legend spells each one out. The
# rule the picture has to carry is that the async backbone and the model calls
# are different things, and that discovery is a third thing that ends by joining
# the first.
SYNC = "#2f6fb5"
EVENT = "#1f8a4c"
MODEL = "#7c4dbe"
AGENT = "#e08a1e"
DISCOVER = "#b5379a"
DLQ = "#d64545"
PLUMBING = "#8a929c"


def icon(rel: str) -> str:
    raw = (ICONS / rel).read_bytes()
    return "data:image/png;base64," + base64.b64encode(raw).decode()


def cluster(x, y, w, h, label):
    return (
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" fill="{CLUSTER}" '
        f'stroke="{CLUSTER_EDGE}"/>'
        f'<text x="{x + 14}" y="{y + 22}" font-size="14" fill="{MUTED}" '
        f'font-family="Helvetica, Arial, sans-serif">{escape(label)}</text>'
    )


def card(x, y, w, h, img, title, *lines, accent=None):
    out = [
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" fill="{CARD}" '
        f'stroke="{accent or CARD_EDGE}" stroke-width="{2 if accent else 1}"/>'
    ]
    if img:
        out.append(f'<image href="{icon(img)}" x="{x + 12}" y="{y + (h - 34) / 2}" width="34" height="34"/>')
    tx = x + (58 if img else 14)
    ty = y + 26 if lines else y + h / 2 + 5
    out.append(
        f'<text x="{tx}" y="{ty}" font-size="15" font-weight="600" fill="{INK}" '
        f'font-family="Helvetica, Arial, sans-serif">{escape(title)}</text>'
    )
    for i, line in enumerate(lines):
        out.append(
            f'<text x="{tx}" y="{ty + 18 + i * 15}" font-size="12.5" fill="{MUTED}" '
            f'font-family="Helvetica, Arial, sans-serif">{escape(line)}</text>'
        )
    return "".join(out)


def edge(pts, colour, label=None, dashed=False, label_at=0.5, label_dy=-6, label_dx=0):
    d = f"M {pts[0][0]} {pts[0][1]} " + " ".join(f"L {x} {y}" for x, y in pts[1:])
    dash = ' stroke-dasharray="7,5"' if dashed else ""
    out = [
        f'<path d="{d}" fill="none" stroke="{colour}" stroke-width="2"{dash} '
        f'marker-end="url(#arrow-{colour.lstrip("#")})"/>'
    ]
    if label:
        i = max(0, int(len(pts) * label_at) - 1)
        ax, ay = pts[i]
        bx, by = pts[min(i + 1, len(pts) - 1)]
        mx, my = (ax + bx) / 2 + label_dx, (ay + by) / 2 + label_dy
        for n, line in enumerate(label.split("\n")):
            out.append(
                f'<text x="{mx}" y="{my + n * 14}" font-size="12" fill="{colour}" '
                f'text-anchor="middle" font-family="Helvetica, Arial, sans-serif" '
                f'paint-order="stroke" stroke="#ffffff" stroke-width="4">{escape(line)}</text>'
            )
    return "".join(out)


def build() -> str:
    colours = [SYNC, EVENT, MODEL, AGENT, DISCOVER, DLQ, PLUMBING]
    markers = "".join(
        f'<marker id="arrow-{c.lstrip("#")}" viewBox="0 0 10 10" refX="9" refY="5" '
        f'markerWidth="6" markerHeight="6" orient="auto-start-reverse">'
        f'<path d="M 0 0 L 10 5 L 0 10 z" fill="{c}"/></marker>'
        for c in colours
    )

    p = [
        f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'width="{W}" height="{H}" viewBox="0 0 {W} {H}">',
        f'<defs>{markers}</defs>',
        f'<rect width="{W}" height="{H}" fill="#ffffff"/>',
        f'<rect x="0" y="0" width="{W}" height="46" fill="{BANNER}"/>',
        '<text x="20" y="30" font-size="18" font-weight="600" fill="#ffffff" '
        'font-family="Helvetica, Arial, sans-serif">Architecture: ReguLens</text>',
        '<text x="250" y="30" font-size="13" fill="#e8f1fb" '
        'font-family="Helvetica, Arial, sans-serif">'
        'three ways in — an upload, the nightly sweep, and a country nobody seeded'
        '</text>',
    ]

    # ---- left column: the open web ---------------------------------------
    p.append(cluster(30, 76, 400, 318, "Watched sources  (the open web)"))
    p.append(card(48, 104, 364, 62, "gcp/devtools/scheduler.png", "Cloud Scheduler",
                  "regulens-source-check · 06:00 Asia/Jakarta"))
    p.append(card(48, 180, 364, 74, "onprem/client/client.png", "Four watched addresses",
                  "EU catalogue · SPARQL — CELLAR act — EC feed",
                  "BPOM JDIH index"))
    p.append(card(48, 268, 364, 78, "onprem/client/client.png", "A country nobody seeded",
                  "its regulator's own site: root page,",
                  "then the regulations index on it", accent=DISCOVER))

    p.append(card(48, 424, 240, 62, "onprem/client/users.png", "Exporter", "(browser)"))

    p.append(cluster(30, 520, 400, 300, "Pub/Sub  · push · OIDC · dead-lettered"))
    p.append(card(48, 548, 364, 76, "gcp/analytics/pubsub.png", "Pipeline topics",
                  "document.uploaded · document.chunk",
                  "clause.extracted · graph.changed"))
    p.append(card(48, 638, 364, 52, "gcp/analytics/pubsub.png", "country.requested",
                  accent=DISCOVER))
    p.append(card(48, 736, 364, 52, "gcp/analytics/pubsub.png", "dead-letter topic"))

    # ---- middle: Cloud Run -------------------------------------------------
    p.append(cluster(560, 76, 420, 400, "Cloud Run · asia-southeast1 — one container image"))
    p.append(card(578, 108, 384, 62, "gcp/compute/run.png", "regulens-web", "Next.js · public"))
    p.append(card(578, 182, 384, 62, "gcp/compute/run.png", "regulens-api", "FastAPI · public"))
    p.append(card(578, 256, 384, 62, "gcp/compute/run.png", "regulens-worker", "private · OIDC"))
    p.append(card(578, 330, 384, 62, "gcp/compute/run.png", "regulens-job", "demo seed"))

    p.append(cluster(560, 520, 420, 230, "Managed data"))
    p.append(card(578, 548, 384, 78, "gcp/database/firestore.png", "Firestore",
                  "products · clauses · conflicts · markets",
                  "watched_sources · discovery_jobs · graph_events"))
    p.append(card(578, 640, 384, 62, "gcp/storage/storage.png", "Cloud Storage",
                  "uploaded PDFs"))

    # ---- right: agents, AI, CI/CD -----------------------------------------
    p.append(cluster(1040, 76, 420, 250, "Google ADK agents  (in-process)"))
    p.append(card(1058, 106, 384, 56, "programming/language/python.png", "Extraction agent",
                  "per document part × 2"))
    p.append(card(1058, 174, 384, 56, "programming/language/python.png", "Reconciliation agent",
                  "ambiguous pairs only"))
    p.append(card(1058, 242, 384, 56, "programming/language/python.png", "Query agent",
                  "tool selection"))

    p.append(cluster(1040, 360, 420, 240, "AI"))
    p.append(card(1058, 390, 384, 74, "gcp/ml/vertex-ai.png", "Vertex AI  /  Gemini Developer API",
                  "gemini-3.5-flash + embeddings",
                  "everything except discovery"))
    p.append(card(1058, 480, 384, 100, "gcp/ml/ai-platform.png", "Gemma 4 · Developer API only",
                  "gemma-4-31b-it · free of charge",
                  "names the regulator, then picks an index",
                  "from links we fetched — never writes a URL",
                  accent=DISCOVER))

    p.append(cluster(1040, 634, 420, 186, "CI/CD  (Cloud Build)"))
    p.append(card(1058, 664, 384, 56, "gcp/devtools/build.png", "Cloud Build",
                  "lint · test · build one image"))
    p.append(card(1058, 736, 384, 56, "gcp/devtools/container-registry.png", "Artifact Registry"))

    p.append(card(1520, 106, 340, 76, "gcp/security/key-management-service.png", "Secret Manager",
                  "gemini-api-key", "gemini-discovery-key"))
    p.append(card(1520, 204, 340, 62, "gcp/operations/logging.png", "Cloud Logging",
                  "structured · trace_id"))

    # ---- edges -------------------------------------------------------------
    # Seven vertical lanes in the gutter between the open web and Cloud Run, so
    # no two flows share a line. Adding one is adding a lane, not re-ranking the
    # graph — which is the whole reason this file places things by hand.
    L1, L2, L3, L4, L5, L6, L7 = 442, 458, 474, 490, 506, 522, 538
    e = []

    # a person, and the page they load
    e.append(edge([(288, 455), (L7, 455), (L7, 139), (578, 139)], SYNC, "HTTPS",
                  label_at=0.34, label_dx=-116, label_dy=-10))
    e.append(edge([(770, 170), (770, 182)], SYNC, "fetch", label_dx=32))

    # the API writes, and publishes
    e.append(edge([(770, 244), (770, 548)], EVENT, "read / write", label_dx=52, label_at=0.9))
    e.append(edge([(962, 213), (1002, 213), (1002, 671), (962, 671)], EVENT, "put PDF",
                  label_at=0.6, label_dx=42, label_dy=-8))
    e.append(edge([(578, 213), (L4, 213), (L4, 586), (412, 586)], EVENT,
                  "publish document.uploaded", label_at=0.66, label_dx=-118, label_dy=-8))

    # the nightly sweep
    e.append(edge([(412, 135), (L1, 135), (L1, 275), (578, 275)], SYNC,
                  "POST /internal/check-sources · OIDC", label_at=0.66, label_dx=104, label_dy=-8))
    e.append(edge([(578, 289), (L2, 289), (L2, 217), (412, 217)], SYNC, "conditional GET",
                  label_at=0.66, label_dx=-64, label_dy=-8))

    # the async backbone
    e.append(edge([(412, 600), (L5, 600), (L5, 296), (578, 296)], EVENT, "push /internal/*",
                  label_at=0.66, label_dx=76, label_dy=126))
    e.append(edge([(412, 612), (426, 612), (426, 750), (412, 750)], DLQ, "max retries",
                  label_at=0.5, label_dx=-60, label_dy=4))
    e.append(edge([(412, 774), (L6, 774), (L6, 310), (578, 310)], DLQ, "/internal/dead-letter",
                  label_at=0.34, label_dx=98, label_dy=-8))

    # agents, and the one model arrow they share
    e.append(edge([(962, 271), (1010, 271), (1010, 134), (1058, 134)], AGENT, "runs",
                  label_at=0.66, label_dy=-8))
    e.append(edge([(962, 283), (1022, 283), (1022, 202), (1058, 202)], AGENT, "runs",
                  label_at=0.66, label_dy=12))
    e.append(edge([(962, 206), (1034, 206), (1034, 270), (1058, 270)], AGENT, "POST /query",
                  label_at=0.34, label_dy=-8))
    e.append(edge([(1250, 298), (1250, 390)], MODEL, "extract · embed · judge · answer",
                  label_dx=-4, label_dy=18))

    # impact is the one stage with no model call, and says so
    e.append(edge([(578, 300), (566, 300), (566, 540), (578, 540), (578, 560)], EVENT,
                  "impact: no model call", label_at=0.5, label_dx=-8, label_dy=76))

    # country discovery
    e.append(edge([(578, 227), (L3, 227), (L3, 664), (412, 664)], DISCOVER,
                  "POST /countries/discover", label_at=0.34, label_dx=-46, label_dy=-10))
    e.append(edge([(412, 652), (434, 652), (434, 324), (578, 324)], DISCOVER,
                  "push /internal/country-requested", label_at=0.9, label_dx=140, label_dy=-8))
    e.append(edge([(962, 296), (996, 296), (996, 530), (1058, 530)], DISCOVER,
                  "regulator + root,\nthen pick an index", label_at=0.66, label_dx=-86,
                  label_dy=-58))
    e.append(edge([(578, 262), (452, 262), (452, 300), (412, 300)], DISCOVER,
                  "GET root → index", label_at=0.9, label_dy=-8))
    e.append(edge([(830, 318), (830, 536), (818, 536), (818, 548)], DISCOVER,
                  "watched source + market\nverified, or refused with a reason",
                  label_at=0.34, label_dx=150, label_dy=88))

    # plumbing
    e.append(edge([(1520, 144), (1490, 144), (1490, 60), (770, 60), (770, 108)], PLUMBING,
                  "mounted env", dashed=True, label_at=0.8, label_dx=-56, label_dy=-8))
    e.append(edge([(1520, 235), (1490, 235), (1490, 336), (1006, 336), (1006, 420), (962, 420)], PLUMBING,
                  "logs", dashed=True, label_at=0.6, label_dx=-160, label_dy=-8))
    e.append(edge([(1058, 764), (1012, 764), (1012, 361), (962, 361)], EVENT, "deploy :SHA",
                  label_at=0.66, label_dx=-48, label_dy=-8))
    e.append(edge([(1250, 720), (1250, 736)], PLUMBING, "push :SHA", label_dx=46))
    e.append(edge([(578, 376), (540, 376), (540, 572), (578, 572)], PLUMBING, "seed baseline",
                  label_at=0.66, label_dx=-50, label_dy=-46))

    p.extend(e)

    # ---- legend ------------------------------------------------------------
    lx, ly = 1520, 320
    p.append(f'<rect x="{lx}" y="{ly}" width="620" height="264" rx="10" fill="#ffffff" '
             f'stroke="{CARD_EDGE}"/>')
    p.append(f'<text x="{lx + 18}" y="{ly + 28}" font-size="14" font-weight="600" fill="{INK}" '
             f'font-family="Helvetica, Arial, sans-serif">'
             f'Connection legend (dashed = supporting / sidecar path)</text>')
    rows = [
        (SYNC, "Synchronous HTTP request / response", False),
        (EVENT, "Pub/Sub event — the async pipeline backbone", False),
        (DISCOVER, "Country discovery — ends as an ordinary watched source", False),
        (MODEL, "Model / embedding call", False),
        (AGENT, "In-process ADK agent call", False),
        (DLQ, "Dead-letter — delivery failed after max retries", False),
        (PLUMBING, "Datastore · Logging · Secret Manager · CI/CD", True),
    ]
    for i, (colour, text, dashed) in enumerate(rows):
        y = ly + 58 + i * 28
        dash = ' stroke-dasharray="7,5"' if dashed else ""
        p.append(f'<path d="M {lx + 20} {y} L {lx + 74} {y}" stroke="{colour}" stroke-width="2"'
                 f'{dash} marker-end="url(#arrow-{colour.lstrip("#")})"/>')
        p.append(f'<text x="{lx + 88}" y="{y + 5}" font-size="13" fill="{INK}" '
                 f'font-family="Helvetica, Arial, sans-serif">{escape(text)}</text>')

    # The one claim the picture must not overstate.
    note = [
        "Discovery proposes and selects; it never authors a URL. The link pattern is",
        "derived from paths we fetched, in typed code, and a candidate that cannot be",
        "read is refused with the reason a user sees.",
    ]
    for i, line in enumerate(note):
        p.append(f'<text x="{lx}" y="{ly + 296 + i * 18}" font-size="12.5" fill="{MUTED}" '
                 f'font-family="Helvetica, Arial, sans-serif">{escape(line)}</text>')

    p.append("</svg>")
    return "".join(p)


def main() -> int:
    SVG_OUT.write_text(build(), encoding="utf-8")
    print(f"wrote {SVG_OUT.relative_to(HERE.parent)}")
    rsvg = shutil.which("rsvg-convert")
    if not rsvg:
        print("rsvg-convert not on PATH — install librsvg to also write the PNG")
        return 0
    subprocess.run(
        [rsvg, "-w", str(W * 2), "-o", str(PNG_OUT), str(SVG_OUT)], check=True
    )
    print(f"wrote {PNG_OUT.relative_to(HERE.parent)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
