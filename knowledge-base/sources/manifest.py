from __future__ import annotations

import json
from pathlib import Path

from .models import CrawlReport, SnapshotRecord


def load_manifest(path: Path) -> dict:
    if not path.exists():
        return {"schema_version": 1, "snapshots": []}
    return json.loads(path.read_text(encoding="utf-8"))


def write_manifest(path: Path, manifest: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    manifest["snapshots"] = sorted(
        manifest.get("snapshots", []),
        key=lambda item: (item["source_id"], item["canonical_url"], item["raw_sha256"]),
    )
    path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def upsert_snapshot(manifest: dict, record: SnapshotRecord) -> bool:
    snapshots = manifest.setdefault("snapshots", [])
    for index, existing in enumerate(snapshots):
        if (
            existing["source_id"] == record.source_id
            and existing["canonical_url"] == record.canonical_url
        ):
            if existing["raw_sha256"] == record.raw_sha256:
                return False
            snapshots[index] = record.model_dump()
            return True
    snapshots.append(record.model_dump())
    return True


def write_report(report: CrawlReport, output_dir: Path) -> None:
    runs_dir = output_dir / "runs"
    reports_dir = output_dir / "reports"
    runs_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    json_path = runs_dir / f"{report.run_id}.json"
    json_path.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")

    failures = "\n".join(
        f"- `{failure.party_id}` `{failure.source_id}` {failure.url}: {failure.error}"
        for failure in report.failures
    )
    skipped = "\n".join(f"- {item}" for item in report.skipped)
    markdown = f"""# Source Crawl Report {report.run_id}

- Generated at: `{report.generated_at}`
- Registry SHA-256: `{report.registry_sha256}`
- Parties: `{", ".join(report.parties)}`
- Sources: `{", ".join(report.sources)}`
- Fetched snapshots: `{report.fetched}`
- Unchanged snapshots: `{report.unchanged}`
- Extracted documents: `{report.extracted_documents}`
- Extracted items: `{report.extracted_items}`

## Skipped

{skipped or "- None"}

## Failures

{failures or "- None"}
"""
    md_path = reports_dir / f"{report.run_id}.md"
    md_path.write_text(markdown, encoding="utf-8")
    (output_dir / "latest-report.md").write_text(markdown, encoding="utf-8")
