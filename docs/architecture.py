"""System-design diagram for ReguLens, drawn with `mingrammer/diagrams`.

Renders the deployed Google Cloud topology — the one `scripts/setup.sh`
provisions and `cloudbuild.yaml` deploys. Source of `docs/architecture.png`,
which the README embeds.

Regenerate after any infrastructure change:

    brew install graphviz                   # or apt-get install graphviz
    pip install -r docs/requirements.txt
    python docs/architecture.py             # writes docs/architecture.png

Nothing here talks to GCP; it only draws.
"""

from diagrams import Cluster, Diagram, Edge
from diagrams.gcp.analytics import PubSub
from diagrams.gcp.compute import Run
from diagrams.gcp.database import Firestore
from diagrams.gcp.devtools import Build, ContainerRegistry
from diagrams.gcp.ml import VertexAI
from diagrams.gcp.operations import Logging
from diagrams.gcp.security import SecretManager
from diagrams.gcp.storage import GCS
from diagrams.onprem.client import Users
from diagrams.programming.language import Python

GRAPH_ATTR = {
    "fontsize": "24",
    "labelloc": "t",
    "pad": "0.75",
    "nodesep": "0.7",
    "ranksep": "1.6",
    "splines": "spline",
}
NODE_ATTR = {"fontsize": "13"}
EDGE_ATTR = {"fontsize": "12"}

with Diagram(
    "ReguLens — Google Cloud architecture",
    filename="docs/architecture",
    outformat="png",
    show=False,
    direction="TB",
    graph_attr=GRAPH_ATTR,
    node_attr=NODE_ATTR,
    edge_attr=EDGE_ATTR,
):
    user = Users("Exporter\n(browser)")

    with Cluster("CI/CD  (Cloud Build)"):
        build = Build("lint · test\nbuild one image")
        registry = ContainerRegistry("Artifact\nRegistry")
        build >> Edge(label="push :SHA") >> registry

    with Cluster("Cloud Run · asia-southeast1 — one container image"):
        web = Run("regulens-web\nNext.js · public")
        api = Run("regulens-api\nFastAPI · public")
        worker = Run("regulens-worker\nprivate · OIDC")
        job = Run("regulens-job\ndemo seed")

    with Cluster("Pub/Sub · push · OIDC · dead-lettered"):
        topics = PubSub("document.uploaded\nclause.extracted\ngraph.changed")
        dlq = PubSub("dead-letter")

    with Cluster("Managed data"):
        fs = Firestore("Firestore\nproducts · clauses\nconflicts · graph_events")
        gcs = GCS("Cloud Storage\nuploaded PDFs")

    # The agents live inside the two runtimes above — they are libraries, not
    # services — but leaving them off the picture made the interesting half of
    # the system invisible, so they are drawn where they actually run.
    with Cluster("Google ADK agents  (in-process)"):
        extraction_agent = Python("Extraction\nper document part x2")
        reconciliation_agent = Python("Reconciliation\nambiguous pairs only")
        query_agent = Python("Query\ntool selection")

    with Cluster("AI"):
        vertex = VertexAI("Vertex AI  —  or\nGemini Developer API\ngemini-3.5-flash + embeddings")

    secret = SecretManager("Secret Manager\ngemini-api-key")
    logs = Logging("Cloud Logging\nstructured · trace_id")

    # request path
    user >> Edge(label="HTTPS") >> web >> Edge(label="fetch") >> api

    # the API is the only writer
    api >> Edge(label="read / write") >> fs
    api >> Edge(label="put PDF") >> gcs
    api >> Edge(label="publish  document.uploaded") >> topics

    # event pipeline — extract, reconcile, impact: all land on the worker
    topics >> Edge(label="push /internal/*") >> worker
    worker >> Edge(label="publish next stage", style="dashed", constraint="false") >> topics
    worker >> Edge(label="verdict + audit event") >> fs

    # Who runs which agent, and what the agents call. `constraint=false`
    # throughout: these edges describe what calls what, and letting them pull on
    # the ranking dragged regulens-api out of its own Cloud Run box.
    api >> Edge(color="darkorange", label="POST /query", constraint="false") >> query_agent
    worker >> Edge(color="darkorange", label="runs", constraint="false") >> extraction_agent
    worker >> Edge(color="darkorange", label="runs", constraint="false") >> reconciliation_agent
    for agent in (extraction_agent, reconciliation_agent, query_agent):
        agent >> Edge(style="dashed", constraint="false") >> vertex
    query_agent >> Edge(style="dashed", label="its own retrieval", constraint="false") >> fs
    # Impact has no agent and no model call at all: requirements, evaluation and
    # the status rollup are plain typed code. Said out loud because every other
    # stage has an arrow into the model and this one deliberately does not.
    worker >> Edge(color="darkgreen", label="impact: no model call") >> fs
    topics >> Edge(color="firebrick", style="dotted", label="max retries") >> dlq
    dlq >> Edge(color="firebrick", label="/internal/dead-letter") >> worker

    # plumbing
    job >> Edge(label="seed baseline") >> fs
    secret >> Edge(style="dashed", label="mounted env") >> api
    secret >> Edge(style="dashed") >> worker
    registry >> Edge(color="darkgreen", label="deploy :SHA") >> api
    api >> Edge(style="dashed", color="gray") >> logs
    worker >> Edge(style="dashed", color="gray") >> logs
