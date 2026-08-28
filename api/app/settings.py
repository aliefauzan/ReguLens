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
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
