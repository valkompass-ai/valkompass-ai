from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .models import PartySourceConfig, SourceDefinition, SourceRegistry


def stable_json_hash(data: object) -> str:
    payload = json.dumps(
        data, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def load_registry(path: Path) -> tuple[SourceRegistry, str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    registry = SourceRegistry(**data)
    return registry, stable_json_hash(data)


def iter_enabled_sources(
    registry: SourceRegistry, party_id: str | None = None, source_id: str | None = None
) -> list[tuple[PartySourceConfig, SourceDefinition]]:
    selected: list[tuple[PartySourceConfig, SourceDefinition]] = []
    for party in registry.parties:
        if not party.enabled:
            continue
        if party_id and party.party_id != party_id:
            continue
        for source in party.sources:
            if source_id and source.source_id != source_id:
                continue
            selected.append((party, source))
    return selected
