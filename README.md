# World Bank Data Browser

A web application for browsing, downloading, and querying data from the [World Bank Indicators API](https://datahelpdesk.worldbank.org/knowledgebase/articles/889392-about-the-indicators-api-documentation). It syncs the World Bank catalogue into a local PostgreSQL database and serves a dashboard UI for exploring sources, indicators, countries, and time-series data.

## Tech Stack

- **Backend:** Python 3.12, FastAPI, SQLAlchemy (async), Alembic
- **Database:** PostgreSQL 16 (with `pg_trgm` for fuzzy search)
- **ETL:** httpx + tenacity for resilient World Bank API fetching
- **Frontend:** Server-side Jinja2 templates with dark mode support
- **Infrastructure:** Docker Compose, GitHub Actions CI

## Prerequisites

- Python 3.12+
- PostgreSQL 16+ (or Docker)
- Git

## Getting Started

### 1. Clone the repo

```bash
git clone https://github.com/carlosyv/wb_data_app.git
cd wb_data_app
```

### 2. Set up environment variables

```bash
cp .env.example .env
# Edit .env with your database credentials
```

### 3. Start the database

**Option A — Docker (recommended):**

```bash
cd docker && docker compose up db -d
```

This starts a PostgreSQL 16 container with the `pg_trgm` extension pre-configured.

**Option B — Local PostgreSQL:**

Make sure you have a running PostgreSQL instance and create the database:

```sql
CREATE DATABASE wb_web_app;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
```

### 4. Install Python dependencies

```bash
python -m venv .venv
source .venv/bin/activate   # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 5. Run database migrations

```bash
alembic upgrade head
```

### 6. Start the app

```bash
uvicorn src.main:app --reload
```

The app will be available at [http://localhost:8000](http://localhost:8000). On first startup, it automatically syncs the World Bank catalogue if the database is empty.

### Full-stack with Docker

To run both the database and the app in Docker:

```bash
cd docker && docker compose up -d
```

The entrypoint script waits for PostgreSQL to be ready, runs migrations, and starts the server.

## Project Structure

```
wb_data_app/
├── src/
│   ├── main.py            # FastAPI app entry point & lifespan
│   ├── api/               # Route handlers (pages, sources, indicators, etc.)
│   ├── config/            # Pydantic settings loaded from .env
│   ├── db/
│   │   ├── engine.py      # Async SQLAlchemy engine & session factory
│   │   ├── models.py      # ORM models (sources, countries, indicators, data points)
│   │   └── migrations/    # Alembic migration scripts
│   ├── etl/               # World Bank API client, catalogue sync, download manager
│   └── utils/             # Shared helpers (data_reader)
├── templates/             # Jinja2 HTML templates (dashboard, browse, download, etc.)
├── static/                # Client-side JavaScript
├── tests/                 # Test suite
├── docker/                # Dockerfile, docker-compose.yml, entrypoint, init SQL
├── .github/workflows/     # CI pipeline (lint + test)
├── .env.example           # Template for environment variables
├── alembic.ini            # Alembic configuration
├── requirements.txt       # Production dependencies
└── requirements-dev.txt   # Dev/test dependencies (pytest, ruff, mypy)
```

## Development

### Install dev dependencies

```bash
pip install -r requirements-dev.txt
```

### Run tests

```bash
pytest tests/ -v
```

### Lint

```bash
ruff check .
```

### Type checking

```bash
mypy src/
```

## Environment Variables

| Variable | Description | Default |
|---|---|---|
| `DB_HOST` | PostgreSQL host | `localhost` |
| `DB_PORT` | PostgreSQL port | `5432` |
| `DB_NAME` | Database name | `wb_web_app` |
| `DB_USER` | Database user | `user` |
| `DB_PASSWORD` | Database password | `changeme` |
| `WB_API_BASE_URL` | World Bank API base URL | `https://api.worldbank.org/v2` |
| `APP_ENV` | Environment (development/production) | `development` |
| `APP_PORT` | Application port | `8000` |
| `APP_DEBUG` | Enable debug mode | `true` |

## License

TBD
