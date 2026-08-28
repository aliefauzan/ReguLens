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
    api >> Edge(label="grounded query", style="dashed") >> vertex

    # event pipeline — extract, reconcile, impact: all land on the worker
    topics >> Edge(label="push /internal/*") >> worker
    worker >> Edge(label="publish next stage", style="dashed", constraint="false") >> topics
    worker >> Edge(label="extract x2 · judge", style="dashed") >> vertex
    worker >> Edge(label="verdict + audit event") >> fs
    topics >> Edge(color="firebrick", style="dotted", label="max retries") >> dlq
    dlq >> Edge(color="firebrick", label="/internal/dead-letter") >> worker

    # plumbing
    job >> Edge(label="seed baseline") >> fs
    secret >> Edge(style="dashed", label="mounted env") >> api
    secret >> Edge(style="dashed") >> worker
    registry >> Edge(color="darkgreen", label="deploy :SHA") >> api
    api >> Edge(style="dashed", color="gray") >> logs
    worker >> Edge(style="dashed", color="gray") >> logs
