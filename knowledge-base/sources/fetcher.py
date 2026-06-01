from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .extractors import sha256_bytes
from .models import SnapshotRecord
from .url_tools import canonicalize_url, extension_for_content_type

FETCHER_VERSION = "source-crawler@0.1.0"


@dataclass
class FetchResult:
    record: SnapshotRecord
    body: bytes


class SourceFetcher:
    def __init__(
        self,
        *,
        output_dir: Path,
        user_agent: str,
        requests_per_second: float,
        registry_sha256: str,
    ):
        self.output_dir = output_dir
        self.user_agent = user_agent
        self.delay_seconds = 1 / requests_per_second
        self.registry_sha256 = registry_sha256
        self._last_fetch_at = 0.0

    def fetch(
        self,
        *,
        url: str,
        source_id: str,
        party_id: str,
        party_folder: str,
    ) -> FetchResult:
        elapsed = time.monotonic() - self._last_fetch_at
        if elapsed < self.delay_seconds:
            time.sleep(self.delay_seconds - elapsed)

        requested_url = canonicalize_url(url)
        req = Request(requested_url, headers={"User-Agent": self.user_agent})
        try:
            with urlopen(req, timeout=30) as response:
                body = response.read()
                final_url = canonicalize_url(response.geturl())
                status = response.status
                headers = response.headers
        except HTTPError as exc:
            raise RuntimeError(f"HTTP {exc.code}") from exc
        except URLError as exc:
            raise RuntimeError(str(exc.reason)) from exc
        finally:
            self._last_fetch_at = time.monotonic()

        raw_sha256 = sha256_bytes(body)
        content_type = headers.get("content-type", "application/octet-stream").split(
            ";", 1
        )[0]
        extension = extension_for_content_type(content_type, final_url)
        raw_rel_path = (
            Path("knowledge-base/source-snapshots/raw")
            / party_folder
            / source_id
            / f"sha256-{raw_sha256}.{extension}"
        )
        raw_abs_path = (
            self.output_dir
            / "raw"
            / party_folder
            / source_id
            / f"sha256-{raw_sha256}.{extension}"
        )
        raw_abs_path.parent.mkdir(parents=True, exist_ok=True)
        if not raw_abs_path.exists():
            raw_abs_path.write_bytes(body)

        snapshot_id = f"snap_sha256_{raw_sha256[:24]}"
        record = SnapshotRecord(
            snapshot_id=snapshot_id,
            source_id=source_id,
            party_id=party_id,
            requested_url=requested_url,
            final_url=final_url,
            canonical_url=final_url,
            retrieved_at=datetime.now(UTC).replace(microsecond=0).isoformat(),
            http_status=status,
            content_type=content_type,
            etag=headers.get("etag"),
            last_modified=headers.get("last-modified"),
            raw_path=str(raw_rel_path),
            raw_sha256=raw_sha256,
            raw_bytes=len(body),
            fetcher_version=FETCHER_VERSION,
            registry_sha256=self.registry_sha256,
        )
        return FetchResult(record=record, body=body)
