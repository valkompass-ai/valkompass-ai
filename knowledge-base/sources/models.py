from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl, field_validator, model_validator

DiscoveryMode = Literal["manual", "sitemap", "site_map_page", "links", "pdf_links"]
SourceType = Literal[
    "party_program",
    "election_manifesto",
    "website_policy_index",
    "website_policy_page",
    "press_material",
    "official_data",
    "other",
]
Priority = Literal["core", "supporting", "experimental"]


class RateLimitConfig(BaseModel):
    requests_per_second: float = Field(gt=0)
    max_concurrency_per_host: int = Field(ge=1)


class SourceDefinition(BaseModel):
    source_id: str
    source_type: SourceType
    base_url: HttpUrl
    seed_urls: list[HttpUrl]
    discovery: list[DiscoveryMode]
    allow_paths: list[str]
    deny_paths: list[str] = []
    include_media_types: list[str]
    election_year: int
    priority: Priority
    max_pages: int = Field(default=100, ge=1)
    max_link_depth: int = Field(default=1, ge=0)

    @field_validator("source_id")
    @classmethod
    def source_id_is_slug(cls, value: str) -> str:
        if not value or not all(c.isalnum() or c in "-_" for c in value):
            raise ValueError("source_id must be a stable slug")
        return value

    @field_validator("allow_paths", "deny_paths")
    @classmethod
    def paths_start_with_slash(cls, value: list[str]) -> list[str]:
        for path in value:
            if not path.startswith("/"):
                raise ValueError(f"path must start with '/': {path}")
        return value

    @model_validator(mode="after")
    def validate_seed_hosts(self) -> SourceDefinition:
        base_host = self.base_url.host
        for seed_url in self.seed_urls:
            if seed_url.host != base_host:
                raise ValueError(
                    f"seed URL host {seed_url.host} must match base host {base_host}"
                )
        if "links" in self.discovery and not self.allow_paths:
            raise ValueError("link discovery requires allow_paths")
        return self


class PartySourceConfig(BaseModel):
    party_id: str
    name: str
    document_folder: str
    enabled: bool = True
    sources: list[SourceDefinition]


class SourceRegistry(BaseModel):
    schema_version: int
    default_user_agent: str
    default_rate_limit: RateLimitConfig
    parties: list[PartySourceConfig]

    @model_validator(mode="after")
    def validate_unique_sources(self) -> SourceRegistry:
        source_ids: set[str] = set()
        party_ids: set[str] = set()
        for party in self.parties:
            if party.party_id in party_ids:
                raise ValueError(f"duplicate party_id: {party.party_id}")
            party_ids.add(party.party_id)
            for source in party.sources:
                if source.source_id in source_ids:
                    raise ValueError(f"duplicate source_id: {source.source_id}")
                source_ids.add(source.source_id)
        return self


class SnapshotRecord(BaseModel):
    snapshot_id: str
    source_id: str
    party_id: str
    requested_url: str
    final_url: str
    canonical_url: str
    retrieved_at: str
    http_status: int
    content_type: str
    etag: str | None = None
    last_modified: str | None = None
    raw_path: str
    raw_sha256: str
    raw_bytes: int
    fetcher_version: str
    registry_sha256: str


class CrawlFailure(BaseModel):
    source_id: str
    party_id: str
    url: str
    error: str


class ExtractedItem(BaseModel):
    item_id: str
    url: str
    title: str | None
    content: str
    content_sha256: str
    snapshot_id: str
    raw_sha256: str


class CrawlReport(BaseModel):
    run_id: str
    generated_at: str = Field(
        default_factory=lambda: datetime.now(UTC).replace(microsecond=0).isoformat()
    )
    registry_sha256: str
    parties: list[str]
    sources: list[str]
    fetched: int = 0
    unchanged: int = 0
    extracted_documents: int = 0
    extracted_items: int = 0
    skipped: list[str] = []
    failures: list[CrawlFailure] = []
