# 02. Source Ingestion

## Research

- Current party documents are mostly 2022 election material.
- Website policy JSON exists for several parties, but there is no source registry or crawler in the repo.
- Kristdemokraterna is missing from `knowledge-base/documents/`.
- The parser currently supports PDFs and website JSON.
- The 2026 Swedish general election is on 2026-09-13.

References:

- Valmyndigheten election dates: https://www.val.se/servicelankar/servicelankar/pressrum/nyheter--pressmeddelanden/pressmeddelande-nya/2026-03-13-viktiga-datum-for-valen-2026
- Valmyndigheten 2026 raw data: https://www.val.se/valresultat-och-statistik/statistik-och-data/radata-val-2026

## Plan

1. Add a source registry for all major Swedish parties.
2. Build a crawler for official party websites and linked documents.
3. Support HTML policy pages, PDFs, manifestos, party programs, and election platforms.
4. Store source metadata such as party, URL, title, source type, capture date, and election year.
5. Produce a crawl report showing covered parties, collected sources, failed URLs, and changed content.
6. Feed the scraped material into the existing parse, embed, topic, and graph pipeline.
