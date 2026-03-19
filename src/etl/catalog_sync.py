"""Sync World Bank catalogue data (sources, countries, indicators) into the DB.

Designed to run once at startup if tables are empty, or on-demand via the UI.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import WBCountry, WBIndicator, WBSource
from src.etl.wb_client import wb_client

logger = logging.getLogger(__name__)


async def sync_sources(session: AsyncSession) -> int:
    """Fetch all WB sources and upsert into wb_sources. Returns count."""
    sources = await wb_client.get_sources()
    now = datetime.now(timezone.utc)

    for src in sources:
        stmt = pg_insert(WBSource).values(
            id=src.id,
            name=src.name,
            description=src.description,
            url=src.url,
            last_synced_at=now,
        ).on_conflict_do_update(
            index_elements=["id"],
            set_={
                "name": src.name,
                "description": src.description,
                "url": src.url,
                "last_synced_at": now,
            },
        )
        await session.execute(stmt)

    await session.commit()
    logger.info("Synced %d sources", len(sources))
    return len(sources)


async def sync_countries(session: AsyncSession) -> int:
    """Fetch all WB countries and upsert into wb_countries. Returns count."""
    countries = await wb_client.get_countries()
    now = datetime.now(timezone.utc)

    for c in countries:
        stmt = pg_insert(WBCountry).values(
            iso3_code=c.iso3_code,
            iso2_code=c.iso2_code,
            name=c.name,
            region=c.region,
            income_level=c.income_level,
            last_synced_at=now,
        ).on_conflict_do_update(
            index_elements=["iso3_code"],
            set_={
                "iso2_code": c.iso2_code,
                "name": c.name,
                "region": c.region,
                "income_level": c.income_level,
                "last_synced_at": now,
            },
        )
        await session.execute(stmt)

    await session.commit()
    logger.info("Synced %d countries", len(countries))
    return len(countries)


async def sync_indicators_for_source(session: AsyncSession, source_id: int) -> int:
    """Fetch all indicators for a given WB source and upsert. Returns count."""
    indicators = await wb_client.get_all_indicators_for_source(source_id)
    now = datetime.now(timezone.utc)

    for ind in indicators:
        stmt = pg_insert(WBIndicator).values(
            code=ind.code,
            name=ind.name,
            source_id=ind.source_id,
            source_note=ind.source_note,
            topic=ind.topic,
            last_synced_at=now,
        ).on_conflict_do_update(
            index_elements=["code"],
            set_={
                "name": ind.name,
                "source_id": ind.source_id,
                "source_note": ind.source_note,
                "topic": ind.topic,
                "last_synced_at": now,
            },
        )
        await session.execute(stmt)

    await session.commit()
    logger.info("Synced %d indicators for source %d", len(indicators), source_id)
    return len(indicators)


async def is_catalog_empty(session: AsyncSession) -> bool:
    """Return True if the sources table has zero rows."""
    result = await session.execute(select(func.count()).select_from(WBSource))
    return result.scalar_one() == 0


async def full_catalog_sync(session: AsyncSession) -> dict[str, int]:
    """Run a full sync: sources → countries → indicators for each source."""
    logger.info("Starting full catalogue sync …")
    counts: dict[str, int] = {}

    counts["sources"] = await sync_sources(session)
    counts["countries"] = await sync_countries(session)

    # Fetch indicators for each source (be polite — one at a time)
    result = await session.execute(select(WBSource.id))
    source_ids = [row[0] for row in result.all()]

    total_indicators = 0
    for sid in source_ids:
        try:
            n = await sync_indicators_for_source(session, sid)
            total_indicators += n
        except Exception:
            logger.exception("Failed to sync indicators for source %d", sid)

    counts["indicators"] = total_indicators
    logger.info("Full catalogue sync complete: %s", counts)
    return counts
