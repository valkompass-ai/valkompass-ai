# 04. Optional Sources

## Research

- Riksdagen voting data already exists under `knowledge-base/documents/voting/`, but it is excluded from the document parsing pipeline.
- Valmyndigheten publishes official election metadata and 2026 raw data.
- SCB publishes official statistics such as Partisympatiundersökningen.

References:

- Riksdagen voting dataset: https://data.riksdagen.se/dataset/katalog/dataset-votering.html
- Valmyndigheten 2026 raw data: https://www.val.se/valresultat-och-statistik/statistik-och-data/radata-val-2026
- SCB Partisympatiundersökningen: https://www.scb.se/hitta-statistik/statistik-efter-amne/demokrati/partisympatier/partisympatiundersokningen-psu/

## Plan

1. Add source-family metadata for party sources, Riksdagen, Valmyndigheten, SCB, and other official sources.
2. Add retrieval filters for optional source families.
3. Add API support for choosing optional source families.
4. Add frontend controls for enabling optional sources.
5. Keep party sources as the default.
