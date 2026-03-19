# wb-web-app

ETL pipeline that fetches data from the [World Bank API](https://datahelpdesk.worldbank.org/knowledgebase/articles/889392-about-the-indicators-api-documentation) and stores it in a local PostgreSQL database.

## Project Structure

```
wb-web-app/
├── src/
│   ├── etl/           # ETL pipelines (extract, transform, load)
│   ├── api/           # Web API layer
│   ├── db/
│   │   ├── migrations/  # Alembic or similar migrations
│   │   ├── models/      # Database models / schemas
│   │   └── seeds/       # Seed data
│   ├── config/        # App configuration
│   └── utils/         # Shared helpers
├── frontend/          # Web frontend (TBD)
├── tests/
│   ├── unit/
│   ├── integration/
│   └── fixtures/
├── docker/            # Dockerfile & docker-compose
├── .github/workflows/ # CI/CD
├── docs/              # Documentation
└── scripts/           # Utility scripts
```

## Getting Started

```bash
# 1. Copy env file
cp .env.example .env

# 2. Start services
cd docker && docker compose up -d

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run tests
pytest tests/ -v
```

## License

TBD
