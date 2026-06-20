# Bordereaux Validation

Bordereaux Validation is an Excel-oriented validation platform that checks bordereaux data against configurable test packs, stores validation outcomes, and supports exception-aware review workflows.

## Key capabilities

- Validate worksheet ranges against one or more test packs.
- Configure pack behavior by workbook/sheet scope.
- Generate template headers and estimate field mappings for pack requirements.
- Persist validation history, KPIs, and versioned result snapshots.
- Manage exception records and apply exception tags to result cells.
- Enforce API-key authentication, subscription-based access, and rate limits.

## High-level architecture

- Frontend: Office add-in UI and workflows in [frontend](frontend).
- Backend: FastAPI APIs, orchestration services, and validation logic in [backend/app](backend/app).
- Data store: PostgreSQL for subscriptions, configs, runs, exceptions, and result versions.

## Installation and setup

1. Prerequisites: Python 3.12+, Node.js 20+, npm, and (optionally) Docker + Docker Compose.
2. Backend dependencies: install from [backend/requirements.txt](backend/requirements.txt).
3. Frontend dependencies: run `npm install` in [frontend](frontend).
4. Start locally (HTTPS dev): run `scripts/start-all.sh`.
5. Or start with containers: run `scripts/start-all.sh --docker`.

## Running tests and checks

Run full repository checks with:

- `scripts/ci.sh`

This runs backend lint + tests and frontend lint + tests.

## Further documentation

- [Documentation index](docs)
- [Architecture](docs/architecture.md)
- [Features](docs/features.md)
- [Contributing guide](CONTRIBUTING.md)