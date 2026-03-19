"""API routes for World Bank countries."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.engine import get_session
from src.db.models import WBCountry
from src.etl.catalog_sync import sync_countries

router = APIRouter(prefix="/api/countries", tags=["countries"])


@router.get("")
async def list_countries(
    q: str | None = Query(None, description="Search country names"),
    region: str | None = Query(None),
    income_level: str | None = Query(None),
    session: AsyncSession = Depends(get_session),
):
    """List countries from local DB with optional filters."""
    stmt = select(WBCountry)

    if q:
        stmt = stmt.where(WBCountry.name.ilike(f"%{q}%"))
    if region:
        stmt = stmt.where(WBCountry.region.ilike(f"%{region}%"))
    if income_level:
        stmt = stmt.where(WBCountry.income_level.ilike(f"%{income_level}%"))

    stmt = stmt.order_by(WBCountry.name)
    result = await session.execute(stmt)
    countries = result.scalars().all()

    return [
        {
            "iso3_code": c.iso3_code,
            "iso2_code": c.iso2_code,
            "name": c.name,
            "region": c.region,
            "income_level": c.income_level,
        }
        for c in countries
    ]


@router.post("/sync")
async def trigger_sync(session: AsyncSession = Depends(get_session)):
    """Re-sync countries from the World Bank API."""
    count = await sync_countries(session)
    return {"synced": count}
