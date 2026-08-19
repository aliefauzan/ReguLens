"""Every config value comes from the environment. Nothing here is hardcoded at a
call site, and nothing secret lives in this file — secrets arrive as mounted
Secret Manager values and are read as ordinary env vars."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Identity
    project_id: str = "regulens-506014"
    region: str = "asia-southeast1"
    service_name: str = "regulens-api"
    version: str = "dev"

    # Vertex. asia-southeast1 only carries gemini-2.5-flash, which fails the
    # hackathon's 3.5+ requirement, so generation runs against the global
    # endpoint while embeddings stay in-region.
    gemini_model: str = "gemini-3.5-flash"
    gemini_location: str = "global"
    embed_model: str = "text-multilingual-embedding-002"
    embed_location: str = "asia-southeast1"

    # Storage
    uploads_bucket: str = "regulens-506014-uploads"
    firestore_database: str = "(default)"

    # Pub/Sub
    topic_document_uploaded: str = "document.uploaded"
    topic_clause_extracted: str = "clause.extracted"
    topic_graph_changed: str = "graph.changed"

    # Behaviour switches
    fake_llm: bool = False
    cors_origins: str = "http://localhost:3000"
    log_level: str = "INFO"

    # Emulators — set only in docker compose, never in production.
    firestore_emulator_host: str | None = None
    pubsub_emulator_host: str | None = None

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
