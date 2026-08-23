"""Create local topics and push subscriptions against the Pub/Sub emulator.

Idempotent: re-running leaves the same topics and subscriptions. The emulator
does not enforce OIDC, which is exactly why the phase-0 round-trip is also
proven against real Cloud Run — local "working" is not evidence.
"""

import os

from google.api_core import exceptions
from google.cloud import pubsub_v1

PROJECT = os.environ.get("PROJECT_ID", "regulens-local")
WORKER = os.environ.get("WORKER_URL", "http://worker:8080")

ROUTES = {
    "document.uploaded": "/internal/document-uploaded",
    "clause.extracted": "/internal/clause-extracted",
    "graph.changed": "/internal/graph-changed",
}
DLQ = "regulens.deadletter"

DLQ_PUSH_SUB = "regulens.deadletter.worker"


def main() -> None:
    publisher = pubsub_v1.PublisherClient()
    subscriber = pubsub_v1.SubscriberClient()

    for topic in [*ROUTES, DLQ]:
        try:
            publisher.create_topic(name=publisher.topic_path(PROJECT, topic))
        except exceptions.AlreadyExists:
            print(f"topic {topic} already exists")

    dlq_name = subscriber.subscription_path(PROJECT, DLQ_PUSH_SUB)
    try:
        subscriber.create_subscription(
            name=dlq_name,
            topic=publisher.topic_path(PROJECT, DLQ),
            push_config=pubsub_v1.types.PushConfig(
                push_endpoint=f"{WORKER}/internal/dead-letter"
            ),
            ack_deadline_seconds=600,
        )
        print(f"created subscription {DLQ_PUSH_SUB} -> /internal/dead-letter")
    except exceptions.AlreadyExists:
        print(f"subscription {DLQ_PUSH_SUB} already exists")

    for topic, path in ROUTES.items():
        name = subscriber.subscription_path(PROJECT, f"{topic}.worker")
        try:
            subscriber.create_subscription(
                name=name,
                topic=publisher.topic_path(PROJECT, topic),
                push_config=pubsub_v1.types.PushConfig(push_endpoint=f"{WORKER}{path}"),
                ack_deadline_seconds=600,
            )
            print(f"created subscription {topic}.worker -> {path}")
        except exceptions.AlreadyExists:
            print(f"subscription {topic}.worker already exists")


if __name__ == "__main__":
    main()
