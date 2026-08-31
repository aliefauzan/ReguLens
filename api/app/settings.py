"""Every config value comes from the environment. Nothing here is hardcoded at a
call site, and nothing secret lives in this file — secrets arrive as mounted
Secret Manager values and are read as ordinary env vars."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Identity. The default is deliberately not a real project: a clone that
    # forgets to set PROJECT_ID must fail against a name that does not exist,
    # not quietly read and write somebody else's Firestore.
    project_id: str = "regulens-unset-project"
    region: str = "asia-southeast1"
    service_name: str = "regulens-api"
    version: str = "dev"

    # Two ways to reach Gemini, and the hackathon accepts either. Setting
    # GEMINI_API_KEY switches every call to the Gemini Developer API, whose
    # free tier covers gemini-3.5-flash and the embedding models outright.
    # Leaving it unset keeps the Vertex path, which bills per token.
    #
    # The key must come from a project with no billing account linked —
    # linking billing promotes the key to the paid tier and the free
    # allowance disappears.
    gemini_api_key: str | None = None

    # Vertex. asia-southeast1 only carries gemini-2.5-flash, which fails the
    # hackathon's 3.5+ requirement, so generation runs against the global
    # endpoint while embeddings stay in-region.
    gemini_model: str = "gemini-3.5-flash"
    gemini_location: str = "global"
    embed_model: str = "text-multilingual-embedding-002"
    embed_location: str = "asia-southeast1"

    # Gemini Developer API embedding. Defaults to 3072 dimensions; 768 keeps
    # Firestore documents small and is one of the sizes Google recommends.
    # Vectors from this model are NOT comparable with Vertex vectors, so
    # switching means re-embedding every stored clause.
    gemini_embed_model: str = "gemini-embedding-001"
    embed_dimensions: int = 768

    # Storage. Bucket names are globally unique, so the project id is the only
    # thing that reliably makes one unique — derived rather than configured, and
    # `scripts/setup.sh` creates exactly this name.
    uploads_bucket: str = ""
    firestore_database: str = "(default)"

    # Pub/Sub
    topic_document_uploaded: str = "document.uploaded"
    topic_clause_extracted: str = "clause.extracted"
    topic_graph_changed: str = "graph.changed"
    # One message per piece of a long document. It exists because the worker's
    # request budget is 300 seconds: a 300-page annex cannot be read inside one
    # request no matter how the work is arranged, and raising the size refusal
    # without this would turn a named refusal into an unexplained timeout.
    topic_document_chunk: str = "document.chunk"

    # Behaviour switches
    fake_llm: bool = False
    debug_view: bool = False  # /debug/* endpoints; enable in dev, keep off in prod by default
    max_document_pages: int = 100
    # Pages read when working out what a document is. The masthead and the
    # entry-into-force clause live at the front; reading further costs time
    # on every upload and buys nothing.
    detect_pages: int = 3
    max_document_mb: int = 20
    cors_origins: str = "http://localhost:3000"
    log_level: str = "INFO"

    # Watched sources — re-reading a regulator's own page on a schedule.
    fetch_timeout_seconds: float = 30.0
    # Where a worsening verdict is sent, so a person learns about it without
    # opening the app. Empty means alerts stay in-app — the default, because a
    # URL is a credential and nothing should be posted anywhere by accident.
    # Any endpoint accepting a JSON POST works; a Slack incoming webhook is one.
    alert_webhook_url: str = ""
    alert_webhook_timeout_seconds: float = 10.0
    # A cap per pipeline run. A first ingestion can move dozens of verdicts at
    # once, and delivering all of them is how a useful channel becomes one
    # people mute.
    alert_webhook_max_per_run: int = 5
    # At or above this many characters a document is read piece by piece, each
    # piece its own Pub/Sub message with its own request budget. Read from the
    # `char_count` stored at upload, so an ordinary document never pays for the
    # check. Roughly five chunks at the current chunk size.
    extraction_fanout_min_chars: int = 60_000
    # The ceiling on pieces. Refuse, do not truncate — and refuse here rather
    # than let a thousand-chunk document spend an hour of model calls before
    # anyone notices.
    extraction_max_chunks: int = 60
    max_fetch_mb: int = 20
    # Refuse, do not truncate. A silently half-read regulation produces a
    # confident answer from the half we happened to read, which is worse than
    # saying the document is too big to read in one piece.
    # Raised from 200,000 when chunk fan-out landed: a document this long is now
    # read in pieces rather than refused. It is still a refusal and not a
    # truncation — above it, nothing is read at all.
    max_fetch_chars: int = 400_000
    # Below this, whatever came back is not a regulation — a login wall, an
    # error page, or a PDF with no text layer.
    min_fetch_chars: int = 200
    source_check_interval_hours: int = 24
    # How far back a catalogue query looks. Deliberately a fixed window rather
    # than "since the last check": a missed run, a clock skew or a restored
    # backup would otherwise open a gap nobody notices. Re-asking for the same
    # window is free — everything already seen is already remembered.
    source_sparql_lookback_days: int = 120
    # A feed that publishes ten things overnight must not become ten extraction
    # runs before anyone is awake to see the bill.
    source_max_new_per_check: int = 3
    # How many entry ids a feed remembers. Enough that a slow-moving feed never
    # re-ingests, small enough that the record stays well inside Firestore's
    # per-document limit.
    source_seen_entry_cap: int = 500
    # A lock older than this is assumed to belong to a crashed check.
    source_check_lock_seconds: int = 900
    source_user_agent: str = (
        "ReguLens/1.0 (regulatory change monitor; +https://github.com/aliefauzan/ReguLens)"
    )

    # Emulators — set only in docker compose, never in production.
    firestore_emulator_host: str | None = None
    pubsub_emulator_host: str | None = None
    # Filesystem stand-in for Cloud Storage. Set only in docker compose; when
    # unset every object goes to the real uploads bucket.
    local_storage_dir: str | None = None

    @property
    def use_gemini_api(self) -> bool:
        """True when calls go to the Gemini Developer API instead of Vertex.

        A key that is obviously a placeholder counts as no key at all. This is
        not tidiness: an unset secret left at `YOUR_KEY_HERE` routes every call
        to an endpoint that answers "API key not valid", and the failure is
        quiet in the worst place — embeddings fail one clause at a time, the
        similarity search degrades to nothing, and the app answers questions
        with "no regulation covers this" while holding the regulation. Falling
        back to Vertex keeps the stack working and makes the misconfiguration a
        cost line rather than a silent wrong answer.
        """
        key = (self.gemini_api_key or "").strip()
        if len(key) < 20:
            return False
        return not key.lower().startswith(("your", "todo", "changeme", "placeholder", "xxx"))

    @property
    def uploads_bucket_name(self) -> str:
        """`UPLOADS_BUCKET` when set, otherwise `<project-id>-uploads`."""
        return self.uploads_bucket or f"{self.project_id}-uploads"

    @property
    def cors_origin_list(self) -> list[str]:
        """Allowed origins, stripped of anything a shell pipeline left behind.

        A browser sends `Origin: https://host` exactly. An entry carrying a
        stray quote — `https://host'` — matches nothing and the site is simply
        dead for whoever opened that hostname, with the only symptom a CORS
        error in a console the operator is not looking at. That shipped once,
        out of a deploy step that read the current value back through gcloud and
        got a Python-style list. Cheap to defend against here, so it is.
        """
        cleaned = []
        for origin in self.cors_origins.split(","):
            origin = origin.strip().strip("\"'[]").strip()
            if origin:
                cleaned.append(origin)
        return cleaned


@lru_cache
def get_settings() -> Settings:
    return Settings()
