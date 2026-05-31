import json

from neo4j import GraphDatabase

from model import Document, Party, Topic

# 1) Define your schema in Python
SCHEMA = {
    "constraints": [
        # unique IDs on each label
        {
            "name": "topic_id_unique",
            "cypher": "CONSTRAINT IF NOT EXISTS FOR (n:Topic) REQUIRE n.id IS UNIQUE",
        },
        {
            "name": "document_id_unique",
            "cypher": "CONSTRAINT IF NOT EXISTS FOR (n:Document) REQUIRE n.id IS UNIQUE",
        },
        {
            "name": "segment_id_unique",
            "cypher": "CONSTRAINT IF NOT EXISTS FOR (n:DocumentSegment) REQUIRE n.id IS UNIQUE",
        },
        {
            "name": "party_abbreviation_unique",
            "cypher": "CONSTRAINT IF NOT EXISTS FOR (n:Party) REQUIRE n.abbreviation IS UNIQUE",
        },
        {
            "name": "source_id_unique",
            "cypher": "CONSTRAINT IF NOT EXISTS FOR (n:Source) REQUIRE n.source_id IS UNIQUE",
        },
        {
            "name": "source_snapshot_id_unique",
            "cypher": "CONSTRAINT IF NOT EXISTS FOR (n:SourceSnapshot) REQUIRE n.snapshot_id IS UNIQUE",
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

    def clear_database(self) -> None:
        """Remove all data, indexes, and constraints from the database."""
        with self.driver.session() as session:
            # Drop all constraints
            for ct in SCHEMA["constraints"]:
                stmt = f"DROP CONSTRAINT {ct['name']} IF EXISTS"
                try:
                    session.run(stmt)
                except Exception as e:
                    # It's okay if a constraint doesn't exist when we try to drop it
                    print(f"Error dropping constraint {ct['name']}: {e}")

            # Drop all indexes
            for idx in SCHEMA["indexes"]:
                index_name = idx["name"]
                stmt = f"DROP INDEX {index_name} IF EXISTS"
                try:
                    session.run(stmt)
                except Exception as e:
                    # It's okay if an index doesn't exist when we try to drop it
                    print(f"Error dropping index {index_name}: {e}")

            # Delete all nodes and relationships
            session.run("MATCH (n) DETACH DELETE n")
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
                    d.raw_content = $raw_content,
                    d.source_id = $source_id,
                    d.party_id = $party_id,
                    d.source_type = $source_type,
                    d.election_year = $election_year,
                    d.public_url = $public_url,
                    d.snapshot_id = $snapshot_id,
                    d.raw_sha256 = $raw_sha256,
                    d.canonical_text_sha256 = $canonical_text_sha256,
                    d.captured_at = $captured_at,
                    d.parser_version = $parser_version
                """,
                id=doc.id,
                path=doc.path,
                raw_content=doc.raw_content,
                source_id=doc.source_id,
                party_id=doc.party_id,
                source_type=doc.source_type,
                election_year=doc.election_year,
                public_url=doc.public_url,
                snapshot_id=doc.snapshot_id,
                raw_sha256=doc.raw_sha256,
                canonical_text_sha256=doc.canonical_text_sha256,
                captured_at=doc.captured_at,
                parser_version=doc.parser_version,
            )

            if doc.source_id:
                session.run(
                    """
                    MERGE (src:Source {source_id:$source_id})
                    SET src.source_type = $source_type,
                        src.election_year = $election_year,
                        src.public_url = $public_url
                    WITH src
                    OPTIONAL MATCH (p:Party {abbreviation:$party_id})
                    FOREACH (_ IN CASE WHEN p IS NULL THEN [] ELSE [1] END |
                        MERGE (p)-[:PUBLISHES]->(src)
                    )
                    """,
                    source_id=doc.source_id,
                    source_type=doc.source_type,
                    election_year=doc.election_year,
                    public_url=doc.public_url,
                    party_id=doc.party_id,
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
                        s.title = seg_data.title
                    WITH s, seg_data
                    MATCH (d:Document {id:seg_data.doc_id})
                    MERGE (d)-[:CONTAINS]->(s)
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
