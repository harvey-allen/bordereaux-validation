# Features

## Core features

- Range validation against one or more configurable test packs.
- Subscription-aware controls: API-key auth, allowed-pack access, rate limiting, and cell-count limits.
- Pack configuration per workbook/sheet, including field mappings and territory-sensitive mandatory fields.
- Validation result persistence with history, statistics, and reusable version snapshots.
- Exception management lifecycle (create, update, delete, list, analytics) with tagged-cell application.
- Rules engine payload support for frontend rule exploration.

## User workflows

```mermaid
flowchart TD
    Start[Open workbook] --> Auth[Authenticate with API key]
    Auth --> SelectPack[Select test pack(s)]
    SelectPack --> Configure[Load or edit pack config]
    Configure --> Validate[Run range validation]
    Validate --> Review[Review failures/coverage]
    Review --> Tag[Apply exception tags if needed]
    Tag --> Save[Save result version]
    Save --> Compare[Compare against prior versions]
```

## Feature descriptions

### Validation execution
- Entry point validates matrix structure, applies subscription checks, and runs pack rules.
- Returns row/cell outcomes, optional coverage summaries, and usage statistics.

### Configuration and templates
- Territory lookup and template generation expose pack-specific required headers.
- Field mapping estimation supports fuzzy matching from uploaded headers to expected fields.

### Results and analytics
- History endpoints expose prior validation runs and detailed run payloads.
- Version endpoints support create/read/update/delete, latest retrieval, and comparison views.
- Statistics endpoint provides aggregated pass/fail trends by period and optional pack filter.

### Exceptions
- Exceptions are organisation-scoped records with status and linkage metadata.
- Exception tagging attaches exception IDs to stored cells and supports cleanup when exceptions are removed.
