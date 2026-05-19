# Bordereaux Validation Tool

An Excel-based validation tool for insurance bordereaux processing.

## Overview

This project provides:

- An **Excel task pane add-in** (`frontend/`) using Office.js
- A **Python API backend** (`backend/`) using FastAPI
- A **PostgreSQL database** for subscription management and rate limiting
- Cell-level validation with:
  - multiple tests per column
  - multiple test packs executed in one run
  - color severity from green → red by failure count
  - comments describing failed tests

## Quick Start (Docker)

The easiest way to run the full stack is with Docker:

```zsh
# 1. Copy environment file and configure
cp .env.example .env

# 2. Ensure SSL certificates exist (required for Excel add-in)
npx office-addin-dev-certs install

# 3. Start all services
./scripts/start-all.sh
```

This starts:
- **Frontend**: https://localhost:443
- **Backend API**: https://localhost:443/api/
- **PostgreSQL**: localhost:5432

### Docker Commands

```zsh
# Start all services
./scripts/start-all.sh

# Start only backend + database
./scripts/start-backend.sh

# Start only frontend
./scripts/start-frontend.sh

# Stop all services
./scripts/stop-all.sh

# View logs
docker compose logs -f

# Remove all data (including database)
docker compose down -v
```

## Development Mode (Without Docker)

For faster iteration during development:

```zsh
./scripts/start-dev.sh
```

This runs services directly without Docker containers.

## Architecture

- The add-in reads the currently selected range (`values` + per-cell addresses).
- It posts data to `POST /validate-range` on the Python backend.
- The backend runs configured validation rules and returns per-cell results.
- The backend can also return a coverage report per test pack/test.
- The add-in applies returned color and comment output back into Excel.

## Validation Rules (Column Rules)

Rules are provided by zero-based column index as strings in JSON, for example:

```json
{
  "0": [{ "name": "required" }, { "name": "type", "expected": "text" }],
  "1": [
    { "name": "required" },
    { "name": "type", "expected": "number" },
    { "name": "min", "value": 0 },
    { "name": "max", "value": 100 }
  ]
}
```

Supported test types:

- `required`
- `type` (`text`, `number`, `date`)
- `min`
- `max`
- `regex`
- `allowed_values`

## Test Packs

Test packs are backend Python classes with `@register_test` methods. You can run multiple packs in one request.

Current included pack:

- `bordereaux` - Placeholder pack for bordereaux validation rules

### Range shape for packs

When running packs, the selected range must include a **header row** with exact field names.

## Coverage Report

`POST /validate-range` now accepts `includeCoverage` (default `true`).

When enabled, the response includes:

- `coverage.summary`: total data rows/cells, failed cells, passed cells
- `coverage.packs.<pack>.tests.<test>`: `evaluatedRows`, `failedRows`, `passedRows`, target column, description
- `coverage.packs.<pack>.totals`: aggregate rows across tests and number of tests run

This helps distinguish between:

- tests that **passed**
- tests that **failed**
- tests that had **zero applicable rows** (`evaluatedRows = 0`)

### Task pane pack config

In the add-in task pane:

- Set `Test Packs` to comma-separated pack names, e.g. `bordereaux`.
- Set `Pack Configs` JSON, for example:

```json
{
  "bordereaux": {
    "RefColumn": "policy_reference"
  }
}
```

## Backend Setup (Manual)

```zsh
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Backend runs at `http://127.0.0.1:8000`.

## Frontend (Excel Add-in) Setup (Manual)

```zsh
cd frontend
npm install
npm run start:web
```

This serves add-in files at `http://localhost:3000`.

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DB_PASSWORD` | PostgreSQL password | `postgres` |
| `DATABASE_URL` | Full database URL | Auto-generated |
| `DEFAULT_SUBSCRIPTION_TIER` | Default tier for new users | `trial` |
| `DEV_API_KEY` | Development API key | Random UUID |

## Subscription Tiers

| Tier | Rate Limit | Max Cells |
|------|------------|-----------|
| TRIAL | 5 requests/day | 1,000 cells |
| BORDEREAUX | 500 requests/day | 10,000 cells |

## Sideload Manifest in Excel (Mac)

1. Open Excel.
2. Go to **Insert → Add-ins → My Add-ins → Manage My Add-ins**.
3. Upload `frontend/manifest.xml` as a custom add-in manifest.
4. Open the task pane via the ribbon button **Open Validator**.

## Use the Plugin

1. Select a range in the sheet.
2. In task pane, keep backend URL as `http://127.0.0.1:8000`.
3. Adjust column rules JSON if needed.
4. Click **Validate Selected Range**.

Cells are filled from green to red based on failure count, and comments are added with test failure details.

## Quick Backend Tests

```zsh
cd backend
source .venv/bin/activate
pytest -q
```
