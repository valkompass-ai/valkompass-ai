import json
from pathlib import Path

from neo4j import GraphDatabase

from model import Document, Party, Topic

# 1) Define your schema in Python
SCHEMA = {
    "constraints": [
        # unique IDs on each label
        {
            "name": "topic_id_unique",
            "cypher": "CONSTRAINT topic_id_unique IF NOT EXISTS FOR (n:Topic) REQUIRE n.id IS UNIQUE",
        },
        {
            "name": "document_id_unique",
            "cypher": "CONSTRAINT document_id_unique IF NOT EXISTS FOR (n:Document) REQUIRE n.id IS UNIQUE",
        },
        {
            "name": "segment_id_unique",
            "cypher": "CONSTRAINT segment_id_unique IF NOT EXISTS FOR (n:DocumentSegment) REQUIRE n.id IS UNIQUE",
        },
        {
            "name": "party_abbreviation_unique",
            "cypher": "CONSTRAINT party_abbreviation_unique IF NOT EXISTS FOR (n:Party) REQUIRE n.abbreviation IS UNIQUE",
        },
        {
            "name": "source_id_unique",
            "cypher": "CONSTRAINT source_id_unique IF NOT EXISTS FOR (n:Source) REQUIRE n.source_id IS UNIQUE",
        },
        {
            "name": "source_snapshot_id_unique",
            "cypher": "CONSTRAINT source_snapshot_id_unique IF NOT EXISTS FOR (n:SourceSnapshot) REQUIRE n.snapshot_id IS UNIQUE",
        },
        {
            "name": "source_document_path_unique",
            "cypher": "CONSTRAINT source_document_path_unique IF NOT EXISTS FOR (n:SourceDocument) REQUIRE n.path IS UNIQUE",
        },
        {
            "name": "raw_snapshot_package_sha_unique",
            "cypher": "CONSTRAINT raw_snapshot_package_sha_unique IF NOT EXISTS FOR (n:RawSnapshotPackage) REQUIRE n.archive_sha256 IS UNIQUE",
        },
    ],
    "indexes": [
        # basic look-ups
        {
            "name": "topic_name_idx",
            "cypher": "INDEX topic_name_idx IF NOT EXISTS FOR (n:Topic) ON (n.name)",
        },
        {
            "name": "doc_path_idx",
            "cypher": "INDEX doc_path_idx IF NOT EXISTS FOR (n:Document) ON (n.path)",
        },
        {
            "name": "party_full_name_idx",
            "cypher": "INDEX party_full_name_idx IF NOT EXISTS FOR (n:Party) ON (n.full_name)",
        },
        {
            "name": "doc_source_id_idx",
            "cypher": "INDEX doc_source_id_idx IF NOT EXISTS FOR (n:Document) ON (n.source_id)",
        },
        {
            "name": "doc_party_id_idx",
            "cypher": "INDEX doc_party_id_idx IF NOT EXISTS FOR (n:Document) ON (n.party_id)",
        },
        {
            "name": "doc_canonical_text_sha256_idx",
            "cypher": "INDEX doc_canonical_text_sha256_idx IF NOT EXISTS FOR (n:Document) ON (n.canonical_text_sha256)",
        },
        {
            "name": "segment_sha256_idx",
            "cypher": "INDEX segment_sha256_idx IF NOT EXISTS FOR (n:DocumentSegment) ON (n.segment_sha256)",
        },
        {
            "name": "source_snapshot_raw_sha256_idx",
            "cypher": "INDEX source_snapshot_raw_sha256_idx IF NOT EXISTS FOR (n:SourceSnapshot) ON (n.raw_sha256)",
        },
        {
            "name": "source_document_sha256_idx",
            "cypher": "INDEX source_document_sha256_idx IF NOT EXISTS FOR (n:SourceDocument) ON (n.sha256)",
        },
        # vector indexes for fast embedding search (requires Neo4j vector plugin)
        {
            "name": "topic_embedding_idx",
            "cypher": "VECTOR INDEX topic_embedding_idx IF NOT EXISTS FOR (n:Topic) ON (n.embedding) OPTIONS { indexConfig: { `vector.dimensions`: 1536, `vector.similarity_function`: 'cosine'} }",
        },
        {
            "name": "segment_embedding_idx",
            "cypher": "VECTOR INDEX segment_embedding_idx IF NOT EXISTS FOR (n:DocumentSegment) ON (n.embedding) OPTIONS { indexConfig: { `vector.dimensions`: 1536, `vector.similarity_function`: 'cosine'} }",
        },
    ],
}


class SchemaManager:
    def __init__(self, uri: str, user: str, password: str):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self):
        self.driver.close()

    def apply_schema(self) -> None:
        """Create constraints & indexes if they don't already exist."""
        with self.driver.session() as session:
            for ct in SCHEMA["constraints"]:
                stmt = f"CREATE {ct['cypher']}"
                session.run(stmt)
            for idx in SCHEMA["indexes"]:
                stmt = f"CREATE {idx['cypher']}"
                session.run(stmt)

    @staticmethod
    def _quote_schema_name(name: str) -> str:
        return f"`{name.replace('`', '``')}`"

    def clear_database(self) -> None:
        """Remove all data, indexes, and constraints from the database."""
        with self.driver.session() as session:
            # Delete all nodes and relationships
            session.run("MATCH (n) DETACH DELETE n")

            # Drop live constraints by actual database name. Older imports created
            # auto-named constraints, so relying only on SCHEMA names leaves schema
            # residue behind.
            constraints = list(session.run("SHOW CONSTRAINTS YIELD name RETURN name"))
            for record in constraints:
                constraint_name = record["name"]
                session.run(
                    f"DROP CONSTRAINT {self._quote_schema_name(constraint_name)} IF EXISTS"
                )

            # Drop live non-lookup indexes by actual database name. Constraint-backed
            # indexes are removed with their constraints above.
            indexes = list(
                session.run(
                    "SHOW INDEXES YIELD name, type "
                    "WHERE type <> 'LOOKUP' "
                    "RETURN name"
                )
            )
            for record in indexes:
                index_name = record["name"]
                session.run(f"DROP INDEX {self._quote_schema_name(index_name)} IF EXISTS")

            print("Database nuked: all data, indexes, and constraints removed.")

    def upsert_topic(self, topic: Topic) -> None:
        with self.driver.session() as session:
            session.run(
                """
                MERGE (t:Topic {id:$id})
                SET t.name       = $name,
                    t.description= $description,
                    t.embedding  = $embedding
                """,
                id=topic.id,
                name=topic.name,
                description=topic.description,
                embedding=topic.embedding.tolist()
                if topic.embedding is not None
                else None,
            )

    def upsert_document(self, doc: Document) -> None:
        with self.driver.session() as session:
            # upsert Document node
            session.run(
                """
                MERGE (d:Document {id:$id})
                SET d.path        = $path,
                    d.title       = $title,
                    d.raw_content = $raw_content,
                    d.source_id = $source_id,
                    d.party_id = $party_id,
                    d.source_type = $source_type,
                    d.document_type = $document_type,
                    d.election_year = $election_year,
                    d.public_url = $public_url,
                    d.snapshot_id = $snapshot_id,
                    d.raw_sha256 = $raw_sha256,
                    d.canonical_text_sha256 = $canonical_text_sha256,
                    d.captured_at = $captured_at,
                    d.parser_version = $parser_version,
                    d.source_page_url = $source_page_url,
                    d.download_url = $download_url,
                    d.final_url = $final_url,
                    d.content_type = $content_type,
                    d.byte_size = $byte_size
                """,
                id=doc.id,
                path=doc.path,
                title=doc.title,
                raw_content=doc.raw_content,
                source_id=doc.source_id,
                party_id=doc.party_id,
                source_type=doc.source_type,
                document_type=doc.document_type,
                election_year=doc.election_year,
                public_url=doc.public_url,
                snapshot_id=doc.snapshot_id,
                raw_sha256=doc.raw_sha256,
                canonical_text_sha256=doc.canonical_text_sha256,
                captured_at=doc.captured_at,
                parser_version=doc.parser_version,
                source_page_url=doc.source_page_url,
                download_url=doc.download_url,
                final_url=doc.final_url,
                content_type=doc.content_type,
                byte_size=doc.byte_size,
            )

            if doc.source_id:
                session.run(
                    """
                    MERGE (src:Source {source_id:$source_id})
                    SET src.source_type = $source_type,
                        src.party_id = $party_id,
                        src.election_year = $election_year,
                        src.public_url = $public_url
                    WITH src
                    MATCH (d:Document {id:$doc_id})
                    MERGE (src)-[:PRODUCED_DOCUMENT]->(d)
                    WITH src
                    OPTIONAL MATCH (p:Party {abbreviation:$party_id})
                    FOREACH (_ IN CASE WHEN p IS NULL THEN [] ELSE [1] END |
                        MERGE (p)-[:PUBLISHES]->(src)
                    )
                    """,
                    source_id=doc.source_id,
                    source_type=doc.source_type,
                    party_id=doc.party_id,
                    election_year=doc.election_year,
                    public_url=doc.public_url,
                    doc_id=doc.id,
                )

            if doc.snapshot_id:
                session.run(
                    """
                    MERGE (snap:SourceSnapshot {snapshot_id:$snapshot_id})
                    SET snap.raw_sha256 = $raw_sha256,
                        snap.captured_at = $captured_at,
                        snap.public_url = $public_url
                    WITH snap
                    MATCH (d:Document {id:$doc_id})
                    MERGE (snap)-[:EXTRACTED_TO]->(d)
                    WITH snap
                    OPTIONAL MATCH (src:Source {source_id:$source_id})
                    FOREACH (_ IN CASE WHEN src IS NULL THEN [] ELSE [1] END |
                        MERGE (src)-[:HAS_SNAPSHOT]->(snap)
                    )
                    """,
                    snapshot_id=doc.snapshot_id,
                    raw_sha256=doc.raw_sha256,
                    captured_at=doc.captured_at,
                    public_url=doc.public_url,
                    doc_id=doc.id,
                    source_id=doc.source_id,
                )

            if doc.raw_sha256:
                session.run(
                    """
                    OPTIONAL MATCH (source_doc:SourceDocument {sha256:$raw_sha256})
                    MATCH (d:Document {id:$doc_id})
                    FOREACH (_ IN CASE WHEN source_doc IS NULL THEN [] ELSE [1] END |
                        MERGE (source_doc)-[:PARSED_TO]->(d)
                    )
                    """,
                    raw_sha256=doc.raw_sha256,
                    doc_id=doc.id,
                )

            # Prepare segment data for bulk upsert
            segments_data = []
            for seg in doc.segments:
                segments_data.append(
                    {
                        "seg_id": seg.id,
                        "text": seg.text,
                        "start_index": seg.start_index,
                        "end_index": seg.end_index,
                        "page": seg.page,
                        "metadata": json.dumps(seg.metadata)
                        if seg.metadata is not None
                        else None,
                        "embedding": seg.embedding.tolist()
                        if seg.embedding is not None
                        else None,
                        "public_url": seg.public_url,
                        "doc_id": doc.id,
                        "type": seg.type,
                        "segment_sha256": seg.segment_sha256,
                        "source_id": seg.source_id,
                        "snapshot_id": seg.snapshot_id,
                        "title": seg.title,
                        "topic_id": seg.topic_id,
                    }
                )

            # Bulk upsert segments and link them to the document
            if segments_data:
                session.run(
                    """
                    UNWIND $segments_data AS seg_data
                    MERGE (s:DocumentSegment {id:seg_data.seg_id})
                    SET s.text        = seg_data.text,
                        s.start_index = seg_data.start_index,
                        s.end_index   = seg_data.end_index,
                        s.page        = seg_data.page,
                        s.metadata    = seg_data.metadata,
                        s.embedding   = seg_data.embedding,
                        s.public_url  = seg_data.public_url,
                        s.type        = seg_data.type,
                        s.segment_sha256 = seg_data.segment_sha256,
                        s.source_id = seg_data.source_id,
                        s.snapshot_id = seg_data.snapshot_id,
                        s.title = seg_data.title,
                        s.topic_id = seg_data.topic_id
                    WITH s, seg_data
                    MATCH (d:Document {id:seg_data.doc_id})
                    MERGE (d)-[:CONTAINS]->(s)
                    WITH s, seg_data
                    OPTIONAL MATCH (snap:SourceSnapshot {snapshot_id:seg_data.snapshot_id})
                    FOREACH (_ IN CASE WHEN snap IS NULL THEN [] ELSE [1] END |
                        MERGE (snap)-[:EXTRACTED_SEGMENT]->(s)
                    )
                    """,
                    segments_data=segments_data,
                )

            # Prepare topic mentions for bulk upsert
            topic_mentions_data = []
            for seg in doc.segments:
                if seg.topic_id is not None:
                    topic_mentions_data.append(
                        {
                            "seg_id": seg.id,
                            "topic_id": seg.topic_id,
                        }
                    )

            # Bulk link segments to topics if they mention them
            if topic_mentions_data:
                session.run(
                    """
                    UNWIND $topic_mentions_data AS mention_data
                    MATCH (s:DocumentSegment {id:mention_data.seg_id})
                    MATCH (t:Topic {id:mention_data.topic_id})
                    MERGE (s)-[:MENTIONS]->(t)
                    """,
                    topic_mentions_data=topic_mentions_data,
                )

    def upsert_party(self, party: Party) -> None:
        """Insert or update a party node"""
        with self.driver.session() as session:
            session.run(
                """
                MERGE (p:Party {abbreviation: $abbreviation})
                SET p.full_name = $full_name
                """,
                abbreviation=party.abbreviation,
                full_name=party.full_name,
            )

    def upsert_parties(self, parties: list[Party]) -> None:
        """Bulk insert or update party nodes"""
        parties_data = [
            {"abbreviation": p.abbreviation, "full_name": p.full_name} for p in parties
        ]
        with self.driver.session() as session:
            session.run(
                """
                UNWIND $parties AS party
                MERGE (p:Party {abbreviation: party.abbreviation})
                SET p.full_name = party.full_name
                """,
                parties=parties_data,
            )

    def link_sources_to_parties(self) -> None:
        """Link Source nodes with party_id metadata to Party nodes."""
        with self.driver.session() as session:
            session.run(
                """
                MATCH (src:Source)
                WHERE src.party_id IS NOT NULL
                MATCH (p:Party {abbreviation: src.party_id})
                MERGE (p)-[:PUBLISHES]->(src)
                """
            )

    def upsert_source_registry(self, registry_path: Path) -> None:
        """Store configured source registry entries as Source nodes."""
        if not registry_path.exists():
            return

        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        sources_data = []
        for party in registry.get("parties", []):
            party_id = party.get("party_id")
            for source in party.get("sources", []):
                sources_data.append(
                    {
                        "source_id": source.get("source_id"),
                        "party_id": party_id,
                        "party_name": party.get("name"),
                        "document_folder": party.get("document_folder"),
                        "source_type": source.get("source_type"),
                        "base_url": source.get("base_url"),
                        "seed_urls": source.get("seed_urls", []),
                        "discovery": source.get("discovery", []),
                        "allow_paths": source.get("allow_paths", []),
                        "deny_paths": source.get("deny_paths", []),
                        "include_media_types": source.get("include_media_types", []),
                        "election_year": source.get("election_year"),
                        "priority": source.get("priority"),
                        "max_pages": source.get("max_pages"),
                        "max_link_depth": source.get("max_link_depth"),
                    }
                )

        if not sources_data:
            return

        with self.driver.session() as session:
            session.run(
                """
                UNWIND $sources AS source
                MERGE (src:Source {source_id: source.source_id})
                SET src.party_id = source.party_id,
                    src.party_name = source.party_name,
                    src.document_folder = source.document_folder,
                    src.source_type = source.source_type,
                    src.base_url = source.base_url,
                    src.seed_urls = source.seed_urls,
                    src.discovery = source.discovery,
                    src.allow_paths = source.allow_paths,
                    src.deny_paths = source.deny_paths,
                    src.include_media_types = source.include_media_types,
                    src.election_year = source.election_year,
                    src.priority = source.priority,
                    src.max_pages = source.max_pages,
                    src.max_link_depth = source.max_link_depth
                """,
                sources=sources_data,
            )

    def upsert_source_snapshots(self, manifest_path: Path) -> None:
        """Store raw crawl snapshot records as SourceSnapshot nodes."""
        if not manifest_path.exists():
            return

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        snapshots = manifest.get("snapshots", [])
        if not snapshots:
            return

        with self.driver.session() as session:
            session.run(
                """
                UNWIND $snapshots AS snapshot
                MERGE (snap:SourceSnapshot {snapshot_id: snapshot.snapshot_id})
                SET snap.source_id = snapshot.source_id,
                    snap.party_id = snapshot.party_id,
                    snap.requested_url = snapshot.requested_url,
                    snap.final_url = snapshot.final_url,
                    snap.canonical_url = snapshot.canonical_url,
                    snap.retrieved_at = snapshot.retrieved_at,
                    snap.http_status = snapshot.http_status,
                    snap.content_type = snapshot.content_type,
                    snap.etag = snapshot.etag,
                    snap.last_modified = snapshot.last_modified,
                    snap.raw_path = snapshot.raw_path,
                    snap.raw_sha256 = snapshot.raw_sha256,
                    snap.raw_bytes = snapshot.raw_bytes,
                    snap.fetcher_version = snapshot.fetcher_version,
                    snap.registry_sha256 = snapshot.registry_sha256
                WITH snap, snapshot
                OPTIONAL MATCH (src:Source {source_id: snapshot.source_id})
                FOREACH (_ IN CASE WHEN src IS NULL THEN [] ELSE [1] END |
                    MERGE (src)-[:HAS_SNAPSHOT]->(snap)
                )
                """,
                snapshots=snapshots,
            )

    def upsert_raw_snapshot_package(self, package_manifest_path: Path) -> None:
        """Store the LFS raw snapshot archive manifest."""
        if not package_manifest_path.exists():
            return

        package = json.loads(package_manifest_path.read_text(encoding="utf-8"))
        with self.driver.session() as session:
            session.run(
                """
                MERGE (pkg:RawSnapshotPackage {archive_sha256:$archive_sha256})
                SET pkg.archive_path = $archive_path,
                    pkg.archive_bytes = $archive_bytes,
                    pkg.source_manifest_path = $source_manifest_path,
                    pkg.source_manifest_sha256 = $source_manifest_sha256,
                    pkg.raw_file_count = $raw_file_count,
                    pkg.raw_total_bytes = $raw_total_bytes,
                    pkg.snapshot_count = $snapshot_count,
                    pkg.generated_at = $generated_at
                """,
                archive_sha256=package.get("archive_sha256"),
                archive_path=package.get("archive_path"),
                archive_bytes=package.get("archive_bytes"),
                source_manifest_path=package.get("source_manifest_path"),
                source_manifest_sha256=package.get("source_manifest_sha256"),
                raw_file_count=package.get("raw_file_count"),
                raw_total_bytes=package.get("raw_total_bytes"),
                snapshot_count=package.get("snapshot_count"),
                generated_at=package.get("generated_at"),
            )

            files = package.get("files", [])
            if files:
                session.run(
                    """
                    UNWIND $files AS file
                    MATCH (pkg:RawSnapshotPackage {archive_sha256:$archive_sha256})
                    MATCH (snap:SourceSnapshot {snapshot_id:file.snapshot_id})
                    MERGE (pkg)-[:CONTAINS_RAW_SNAPSHOT]->(snap)
                    """,
                    archive_sha256=package.get("archive_sha256"),
                    files=files,
                )

    def upsert_pdf_source_documents(self, manifest_path: Path) -> None:
        """Store official PDF source-document manifest records."""
        if not manifest_path.exists():
            return

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        documents = manifest.get("documents", [])
        if not documents:
            return

        records = []
        for record in documents:
            source_id = Path(record["path"]).stem
            records.append({**record, "source_id": source_id})

        with self.driver.session() as session:
            session.run(
                """
                UNWIND $records AS record
                MERGE (src:Source {source_id:record.source_id})
                SET src.party_id = record.party_id,
                    src.party_name = record.party,
                    src.source_type = record.document_type,
                    src.election_year = record.year,
                    src.public_url = record.public_path,
                    src.download_url = record.download_url,
                    src.source_page_url = record.source_page_url
                MERGE (source_doc:SourceDocument {path:record.path})
                SET source_doc.source_id = record.source_id,
                    source_doc.party_id = record.party_id,
                    source_doc.party = record.party,
                    source_doc.document_type = record.document_type,
                    source_doc.year = record.year,
                    source_doc.title = record.title,
                    source_doc.public_path = record.public_path,
                    source_doc.source_page_url = record.source_page_url,
                    source_doc.download_url = record.download_url,
                    source_doc.final_url = record.final_url,
                    source_doc.retrieved_at = record.retrieved_at,
                    source_doc.content_type = record.content_type,
                    source_doc.bytes = record.bytes,
                    source_doc.sha256 = record.sha256
                MERGE (src)-[:HAS_SOURCE_DOCUMENT]->(source_doc)
                """,
                records=records,
            )

    def link_documents_to_parties(self) -> None:
        """
        Create AUTHORED relationships based on file paths.
        Documents are organized as: knowledge-base/documents/{party_name}/

        This method uses a mapping approach since folder names don't always match party names exactly.
        """
        # Direct folder-to-party mapping
        folder_to_party_mapping = {
            "centerpartiet": "C",
            "liberalerna": "L",
            "miljopartiet": "MP",
            "moderaterna": "M",
            "socialdemokraterna": "S",
            "sverigedemokraterna": "SD",
            "vansterpartiet": "V",
            "kristdemokraterna": "KD",
        }

        with self.driver.session() as session:
            for folder_name, party_abbr in folder_to_party_mapping.items():
                print(
                    f"Linking documents to party {party_abbr} from folder {folder_name}"
                )
                session.run(
                    """
                    MATCH (d:Document)
                    WHERE d.path CONTAINS $folder_pattern
                    MATCH (p:Party {abbreviation: $party_abbr})
                    MERGE (p)-[:AUTHORED]->(d)
                    """,
                    folder_pattern=f"/documents/{folder_name}/",
                    party_abbr=party_abbr,
                )


if __name__ == "__main__":
    # adjust URI/credentials as needed
    mgr = SchemaManager("bolt://localhost:7687", "neo4j", "password")
    try:
        # Example usage:
        # To apply schema:
        # mgr.apply_schema()
        # print("Schema applied successfully.")

        # To nuke the database (use with caution!):
        # print("Attempting to nuke the database...")
        # mgr.nuke_database()
        # print("Database nuke attempt finished.")

        # For regular schema application:
        mgr.apply_schema()
        print("Schema applied successfully.")
    finally:
        mgr.close()
