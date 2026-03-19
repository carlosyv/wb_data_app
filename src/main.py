"""FastAPI application entry point for the World Bank Data Browser.

Start with:
    cd /Users/carlosyalta/Documentos/claude-workspace/wb_data_app
    uvicorn src.main:app --reload
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from src.api import countries, data, downloads, indicators, pages, sources
from src.db.engine import async_session_factory, engine
from src.etl.catalog_sync import full_catalog_sync, is_catalog_empty
from src.etl.wb_client import wb_client

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent  # wb_data_app/


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle hook."""
    # ── Startup ──────────────────────────────────────────────────────────
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
    )
    logger.info("Starting WB Data Browser …")

    # Open the WB API client
    await wb_client.open()

    # Auto-sync catalogue if the DB is empty
    async with async_session_factory() as session:
        if await is_catalog_empty(session):
            logger.info("Catalogue tables are empty — triggering initial sync …")
            try:
                await full_catalog_sync(session)
            except Exception:
                logger.exception("Initial catalogue sync failed (will retry on next request)")

    yield

    # ── Shutdown ─────────────────────────────────────────────────────────
    await wb_client.close()
    await engine.dispose()
    logger.info("WB Data Browser shut down.")


# ── Create the FastAPI app ───────────────────────────────────────────────

app = FastAPI(
    title="World Bank Data Browser",
    description="Browse, download, and query World Bank data from a local PostgreSQL database.",
    version="0.1.0",
    lifespan=lifespan,
)

# Mount static files
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

# Jinja2 templates
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.state.templates = templates

# ── Register routers ────────────────────────────────────────────────────

app.include_router(sources.router)
app.include_router(indicators.router)
app.include_router(countries.router)
app.include_router(downloads.router)
app.include_router(data.router)
app.include_router(pages.router)
