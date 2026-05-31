# 02. Source Ingestion

## Problem

Valkompass.ai needs a transparent, reproducible, and auditable source-ingestion system for Swedish party material ahead of the 2026 election. The current repository has useful raw documents and website policy JSON, but collection is manual and not fully traceable from a generated answer back to the exact fetched bytes, extraction run, segment, and graph import.

The next system must treat source ingestion as a data supply chain:

```text
source registry -> polite fetch -> committed snapshots -> extracted documents -> segments -> embeddings -> Neo4j index -> cited answer
```

Every committed data artifact should answer:

- Which party and source definition produced this?
- What URL was requested and what final URL was fetched?
- When was it fetched?
- What HTTP metadata was observed?
- What raw bytes were committed?
- What canonical text was indexed?
- Which parser/version produced the derived text?
- Which segment hash was embedded and stored in Neo4j?

## Current State

- Current party documents are mostly 2022 election material.
- Website policy JSON exists for several parties, but there is no source registry or crawler in the repo.
- Kristdemokraterna is missing from `knowledge-base/documents/`.
- The parser supports PDFs and legacy website JSON only.
- `knowledge-base/main.py` assigns document IDs from parse order, so IDs are not stable when the file set changes.
- `Document` currently stores `id`, `path`, `raw_content`, and `segments`, but no first-class source/provenance fields.
- `DocumentSegment` stores text offsets, page, type, `public_url`, and optional metadata, but no segment hash or source snapshot ID.
- Neo4j stores `Document`, `DocumentSegment`, `Topic`, and `Party`; source provenance is mostly implicit in paths and metadata.
- Party linking in Neo4j is folder-name based.
- Bun/TypeScript scripts under `commands/` collect Riksdag voting data, but party document parsing and graph import are Python.
- Existing voting data has partial provenance fields such as `source` and `extractedAt`, but not raw response hashes or request-level manifests.

## Research Findings

### Standards and Practices

- Do not use `robots.txt` as a blocking gate for this project. The crawler should instead be constrained by the reviewed source registry, explicit host/path allowlists, conservative rate limits, and transparent run reports.
- Use conditional HTTP requests where supported. `ETag`, `Last-Modified`, `If-None-Match`, and `If-Modified-Since` let us re-check sources without redownloading unchanged material.
- Use SHA-256 for committed artifact hashes. Python `hashlib` provides SHA-256 directly and is appropriate for content identity and change detection.
- Model provenance using a W3C PROV-inspired structure even if we do not store RDF. The useful concepts are `Entity` (source definition, fetched snapshot, extracted document, segment), `Activity` (fetch, extract, parse, embed, graph import), and `Agent` (script/version/config that performed the activity).
- Use a dataset-package mindset. A root manifest that lists resources, paths, media types, byte sizes, hashes, and generation time makes the committed knowledge base inspectable and reproducible.

### Official Source Surface, Checked 2026-05-31

The first registry should cover the eight current major Riksdag parties and constrain discovery to central/national party material. Local district sites, candidate pages, campaign microsites, and social media should be excluded unless explicitly added later.

| Party | Home | Useful Crawl Surfaces Observed |
| --- | --- | --- |
| S | `https://www.socialdemokraterna.se/` | `/webbkarta`, `/var-politik`, `/var-politik/a-till-o`, `/vart-parti` |
| M | `https://moderaterna.se/` | `/sitemap_index.xml`, `/var-politik/` |
| SD | `https://www.sd.se/` | `/sitemap_index.xml` |
| MP | `https://www.mp.se/` | `/sitemap.xml`, `/politik/` |
| C | `https://www.centerpartiet.se/` | `/sitemap.xml`, `/centerpartiets-politik`, `/centerpartiets-politik/centerpartiets-politik-a-o`, `/om-centerpartiet` |
| L | `https://www.liberalerna.se/` | `/sitemap_index.xml`, `/politik-a-o`, `/vart-parti` |
| KD | `https://kristdemokraterna.se/` | `/ovrigt/webbkarta`, `/var-politik`, `/var-politik/politik-a-till-o`, `/vart-parti` |
| V | `https://www.vansterpartiet.se/` | `/sitemap.xml`, `/var-politik/`, `/var-politik/politik-a-o/`, `/resursbank/partiprogram/` |

These observations should seed the first configuration file, not become hard-coded crawler logic.

### Initial Registry Coverage

The first `source-registry.json` should start conservative. Each party gets one core policy index source, plus explicit party-program/manifesto PDF sources when those URLs are known and confirmed. The crawler can discover child pages and linked PDFs from these seeds, but only within the configured path allowlist.

| Party | First Core Source IDs | Seed URLs |
| --- | --- | --- |
| S | `s-politik-a-till-o`, `s-vart-parti` | `https://www.socialdemokraterna.se/var-politik/a-till-o`, `https://www.socialdemokraterna.se/vart-parti` |
| M | `m-var-politik` | `https://moderaterna.se/var-politik/` |
| SD | `sd-sitemap-policy-discovery` | `https://www.sd.se/sitemap_index.xml` |
| MP | `mp-politik` | `https://www.mp.se/politik/` |
| C | `c-politik-a-o`, `c-vart-parti` | `https://www.centerpartiet.se/centerpartiets-politik/centerpartiets-politik-a-o`, `https://www.centerpartiet.se/om-centerpartiet` |
| L | `l-politik-a-o`, `l-vart-parti` | `https://www.liberalerna.se/politik-a-o`, `https://www.liberalerna.se/vart-parti` |
| KD | `kd-politik-a-o`, `kd-vart-parti` | `https://kristdemokraterna.se/var-politik/politik-a-till-o`, `https://kristdemokraterna.se/vart-parti` |
| V | `v-politik-a-o`, `v-partiprogram` | `https://www.vansterpartiet.se/var-politik/politik-a-o/`, `https://www.vansterpartiet.se/resursbank/partiprogram/` |

## Product Requirements

1. All source material used by the app must be committed in the repo or generated from committed raw data.
2. Every source must be declared in a reviewed JSON registry before it can be crawled.
3. Every fetch run must produce a committed manifest and report.
4. Every raw fetched artifact must have a SHA-256 hash, byte size, media type, request URL, final URL, party, source definition ID, and fetch timestamp.
5. Every extracted document must link to exactly one source snapshot and include a canonical text hash.
6. Every segment must include a stable segment ID and segment text hash.
7. Neo4j must index enough source metadata for answers, citations, audits, and debugging.
8. The crawler must use a descriptive Valkompass user agent, rate-limit by host, and only follow configured allowed hosts/path prefixes.
9. The crawler must be deterministic enough that repeated runs produce stable IDs and predictable diffs when source content is unchanged.
10. The ingestion workflow must produce coverage reports showing which parties and configured sources are current, missing, failed, changed, or excluded.

## Proposed Architecture

### Source Registry

Add a reviewed registry at:

```text
knowledge-base/source-registry.json
```

Initial shape:

```json
{
  "schema_version": 1,
  "default_user_agent": "valkompass-ai-sourcebot/0.1 (+https://valkompass.ai)",
  "default_rate_limit": {
    "requests_per_second": 0.5,
    "max_concurrency_per_host": 1
  },
  "parties": [
    {
      "party_id": "S",
      "name": "Socialdemokraterna",
      "document_folder": "socialdemokraterna",
      "enabled": true,
      "sources": [
        {
          "source_id": "s-politik-a-till-o",
          "source_type": "website_policy_index",
          "base_url": "https://www.socialdemokraterna.se/",
          "seed_urls": [
            "https://www.socialdemokraterna.se/var-politik/a-till-o"
          ],
          "discovery": ["links"],
          "allow_paths": ["/var-politik/"],
          "deny_paths": ["/press/", "/nyheter/", "/kalender/"],
          "include_media_types": ["text/html", "application/pdf"],
          "election_year": 2026,
          "priority": "core"
        }
      ]
    }
  ]
}
```

Registry rules:

- `party_id` must match `knowledge-base/documents/voting/parties.json` for Riksdag parties.
- `source_id` is stable and never reused for unrelated content.
- `base_url` and every seed URL must be HTTPS unless an official source only supports HTTP.
- `allow_paths` and `deny_paths` are required for link discovery.
- `discovery` may include `manual`, `sitemap`, `site_map_page`, `links`, and `pdf_links`.
- `source_type` should be one of `party_program`, `election_manifesto`, `website_policy_index`, `website_policy_page`, `press_material`, `official_data`, or `other`.
- `priority` should be `core`, `supporting`, or `experimental`. Only `core` and `supporting` sources enter production indexing by default.

### Snapshot Store

Add committed raw snapshots under:

```text
knowledge-base/source-snapshots/
  manifest.json
  runs/
    2026-05-31T160000Z.json
  raw/
    socialdemokraterna/
      s-politik-a-till-o/
        sha256-<hash>.html
    kristdemokraterna/
      kd-principprogram/
        sha256-<hash>.pdf
```

Snapshot records should include:

```json
{
  "snapshot_id": "snap_01H...",
  "source_id": "s-politik-a-till-o",
  "party_id": "S",
  "requested_url": "https://www.socialdemokraterna.se/var-politik/a-till-o",
  "final_url": "https://www.socialdemokraterna.se/var-politik/a-till-o",
  "canonical_url": "https://www.socialdemokraterna.se/var-politik/a-till-o",
  "retrieved_at": "2026-05-31T16:00:00Z",
  "http_status": 200,
  "content_type": "text/html",
  "etag": "\"example\"",
  "last_modified": "Tue, 26 May 2026 12:00:00 GMT",
  "raw_path": "knowledge-base/source-snapshots/raw/socialdemokraterna/s-politik-a-till-o/sha256-abc.html",
  "raw_sha256": "abc...",
  "raw_bytes": 12345,
  "fetcher_version": "source-crawler@0.1.0",
  "registry_sha256": "def..."
}
```

### Derived Document Store

Keep the existing pipeline-compatible committed files under `knowledge-base/documents/`, but make generated website JSON richer and source-linked:

```text
knowledge-base/documents/{party}/web/{source_id}.json
knowledge-base/documents/{party}/pdf/{source_slug}.pdf
```

Website JSON should move from the legacy `{url, content}` list to a versioned envelope:

```json
{
  "schema_version": 2,
  "document_id": "doc_sha256_<canonical_text_hash>",
  "party_id": "S",
  "source_id": "s-politik-a-till-o",
  "source_type": "website_policy_index",
  "election_year": 2026,
  "title": "Politik A till Ö",
  "public_url": "https://www.socialdemokraterna.se/var-politik/a-till-o",
  "snapshot_id": "snap_01H...",
  "raw_sha256": "abc...",
  "canonical_text_sha256": "xyz...",
  "captured_at": "2026-05-31T16:00:00Z",
  "items": [
    {
      "item_id": "url_sha256_<hash>",
      "url": "https://www.socialdemokraterna.se/var-politik/a-till-o/sjukvard-halsa-och-omvard",
      "title": "Sjukvård, hälsa och omvårdnad",
      "content": "Canonical extracted text...",
      "content_sha256": "..."
    }
  ]
}
```

The parser should support both legacy list JSON and schema-versioned JSON during migration.

### Indexing and Graph Model

Extend Pydantic models:

- `Document.source_id`
- `Document.party_id`
- `Document.source_type`
- `Document.election_year`
- `Document.public_url`
- `Document.snapshot_id`
- `Document.raw_sha256`
- `Document.canonical_text_sha256`
- `Document.captured_at`
- `Document.parser_version`
- `DocumentSegment.segment_sha256`
- `DocumentSegment.source_id`
- `DocumentSegment.snapshot_id`
- `DocumentSegment.title`

Extend Neo4j:

- Add `Source` nodes keyed by `source_id`.
- Add `SourceSnapshot` nodes keyed by `snapshot_id`.
- Keep `Party`, `Document`, `DocumentSegment`, and `Topic`.
- Add indexes on `Source.source_id`, `SourceSnapshot.raw_sha256`, `Document.canonical_text_sha256`, `Document.party_id`, `Document.source_type`, `Document.election_year`, and `DocumentSegment.segment_sha256`.
- Add relationships:
  - `(Party)-[:PUBLISHES]->(Source)`
  - `(Source)-[:HAS_SNAPSHOT]->(SourceSnapshot)`
  - `(SourceSnapshot)-[:EXTRACTED_TO]->(Document)`
  - `(Document)-[:CONTAINS]->(DocumentSegment)`
  - `(DocumentSegment)-[:MENTIONS]->(Topic)`

Runtime retrieval should return the current citation fields plus source/provenance fields so debugging can trace an answer to source hash and capture date.

## Crawler Design

Implement the party source crawler in Python under `knowledge-base/`, because the parser, embedding, topic modeling, and graph import are already Python.

Proposed modules:

```text
knowledge-base/sources/
  __init__.py
  models.py          # Pydantic models for registry, snapshots, reports
  registry.py        # load and validate source-registry.json
  fetcher.py         # HTTP client, conditional GET, retries, hashes
  discovery.py       # sitemap, webbkarta/site-map, link extraction, PDF discovery
  extractors.py      # HTML/PDF metadata and canonical text extraction
  manifest.py        # manifest read/write, stable sorted output
  report.py          # markdown/json coverage and diff reports
  cli.py             # uv run python -m sources.cli ...
```

Recommended CLI:

```bash
cd knowledge-base
uv run python -m sources.cli validate-registry
uv run python -m sources.cli crawl --party S --dry-run
uv run python -m sources.cli crawl --all --since-last
uv run python -m sources.cli extract --all
uv run python -m sources.cli report --all
```

Crawler requirements:

- Load only enabled registry entries by default.
- Fail registry validation for duplicate `source_id`, unknown party IDs, non-HTTPS URLs, missing allow/deny paths for link discovery, or seed URLs outside allowed hosts.
- Send a descriptive user agent.
- Enforce host allowlist and path allow/deny filters before fetch.
- Canonicalize URLs by normalizing scheme/host case, removing fragments, sorting query parameters where safe, and resolving redirects.
- Persist ETag and Last-Modified values in the manifest and use them on later crawls.
- Treat HTTP 304 as unchanged and do not rewrite raw artifacts.
- Hash every fetched body with SHA-256 before writing.
- Deduplicate identical raw content by hash while preserving multiple source records if two URLs resolve to the same content.
- Store failed fetches in the run report with URL, status/error, source ID, retry count, and whether indexing was skipped.
- Never fetch unbounded site areas such as news archives, events, membership flows, donation pages, search pages, or local district subdomains unless explicitly configured.
- Sort output deterministically to keep git diffs reviewable.

## Reports

Every crawl should write:

```text
knowledge-base/source-snapshots/runs/{timestamp}.json
knowledge-base/source-snapshots/reports/{timestamp}.md
knowledge-base/source-snapshots/latest-report.md
```

Report sections:

- Run metadata: timestamp, registry hash, git commit, user agent, command, dry-run flag.
- Party coverage: configured sources, fetched sources, unchanged sources, failed sources, excluded URLs.
- Source changes: new, changed, unchanged, removed from registry.
- Hash inventory: raw hash, canonical text hash, structured document path.
- Index readiness: parse status, segment count, embedding status, graph import status.
- Warnings: unsupported media type, missing title, duplicate canonical URL, suspiciously short content.

## Test Strategy

Add focused Python tests:

- Registry validation accepts the initial registry and rejects unsafe config.
- URL canonicalization is stable.
- Conditional GET sends ETag/Last-Modified validators from the previous manifest.
- Raw body hash and canonical text hash are stable.
- Legacy website JSON still parses.
- Schema-versioned website JSON parses into `Document` and `DocumentSegment` with source metadata.
- Segment IDs remain stable when unrelated files are added.
- Graph upsert stores source fields and creates source/snapshot relationships.

Use mocked HTTP responses for crawler tests. Do not require live party websites in CI.

## Implementation Plan

### Phase 1: Provenance Schema and Registry

1. Add `knowledge-base/source-registry.json` with the eight major party home URLs and initial core source definitions.
2. Add Pydantic registry models and validation tests.
3. Add source/provenance fields to `Document` and `DocumentSegment` while preserving backward compatibility.
4. Change document and segment ID generation from parse-order IDs to stable IDs derived from source metadata and hashes.

### Phase 2: Snapshot Fetcher

1. Add fetcher with user agent, rate limits, redirects, retries, conditional GET, and SHA-256 hashing.
2. Add manifest and run report writers.
3. Implement dry-run mode that discovers candidate URLs without writing raw snapshots.
4. Commit the first dry-run report for review before committing large source snapshots.

### Phase 3: HTML/PDF Extraction

1. Add HTML canonical text extraction for central party policy pages.
2. Preserve raw HTML snapshots and generated schema-versioned website JSON.
3. Preserve downloaded PDFs as raw committed artifacts with snapshot metadata.
4. Update `json_website_parser.py` to parse both legacy and schema-versioned JSON.
5. Add tests for representative party HTML and PDF metadata.

### Phase 4: Graph and Runtime Provenance

1. Extend Neo4j schema with `Source` and `SourceSnapshot` nodes, indexes, and relationships.
2. Store source fields on `Document` and `DocumentSegment`.
3. Update retrieval queries to return source ID, snapshot ID, capture date, and hashes for debugging.
4. Keep user-facing citations clean, but make provenance visible in logs/debug tools.

### Phase 5: First 2026 Data Refresh

1. Run crawler for each party in dry-run mode and review exclusions.
2. Run crawler for core sources and commit raw snapshots, manifests, extracted JSON/PDF files, and reports.
3. Run parse, embed, topic modeling, and graph import.
4. Commit structured knowledge-base updates.
5. Update the roadmap item status and README/agent docs if commands or data layout changed.

## Acceptance Criteria

- A reviewer can open `source-registry.json` and see every configured party source that is allowed into the knowledge base.
- A reviewer can inspect a crawl report and understand coverage, failures, exclusions, and changed content.
- A committed structured document can be traced to a snapshot manifest entry by `snapshot_id`.
- A snapshot manifest entry can be traced to raw committed bytes by path and SHA-256.
- A Neo4j segment used in retrieval contains enough metadata to trace it back to source URL, snapshot ID, source hash, parser version, and capture date.
- Re-running the crawler with unchanged source content produces no noisy rewrites.
- CI covers registry validation, parsers, hashing, stable IDs, and graph source metadata.

## References

- Valmyndigheten election dates: https://www.val.se/servicelankar/servicelankar/pressrum/nyheter--pressmeddelanden/pressmeddelande-nya/2026-03-13-viktiga-datum-for-valen-2026
- Valmyndigheten 2026 raw data: https://www.val.se/valresultat-och-statistik/statistik-och-data/radata-val-2026
- HTTP conditional requests: https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Conditional_requests
- HTTP 304 Not Modified: https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Status/304
- Python `hashlib`: https://docs.python.org/3/library/hashlib.html
- W3C PROV-DM: https://www.w3.org/TR/prov-dm/
- Frictionless Data Package guide: https://specs.frictionlessdata.io/guides/data-package/
