# Features

## Core features

- Range validation against one or more configurable test packs.
- Subscription-aware controls: API-key auth, allowed-pack access, rate limiting, and cell-count limits.
- Pack configuration per workbook/sheet, including field mappings and territory-sensitive mandatory fields.
- Validation result persistence with history, statistics, and reusable version snapshots.
- Exception management lifecycle (create, update, delete, list, analytics) with tagged-cell application.
- Rules engine payload support for frontend rule exploration.

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
- Saved report versions persist an individual worksheet as a single-sheet Excel file in AWS S3 (`bordereaux-report`) with validation highlighting/comments preserved, restore the matching saved pack configuration for that sheet, and can be launched directly into a new worksheet tab without re-validation.

### Exceptions
- Exceptions are organisation-scoped records with status and linkage metadata.
- Exception tagging attaches exception IDs to stored cells and supports cleanup when exceptions are removed.
- The exception management modal includes a "New Exception" action that exits edit mode and resets the form back to create mode.

### Database administration
- Shell scripts in `scripts/db-admin/` provide CRUD operations for users and organisations.
- Organisation management: list, get, create, update, and delete organisations.
- User management: list, get, create, update, delete, activate, deactivate, and regenerate API keys.
- See `scripts/db-admin/README.md` for detailed usage examples.

## Testing and coverage policy

- Unit tests are required for core business logic, service orchestration, utility helpers, and critical API/frontend flows.
- Coverage is enforced in CI for both backend and frontend test suites.
- Combined coverage across frontend + backend must remain at or above **75%**.
- Pull requests receive an automated coverage summary comment, including delta vs the target branch.
